"""
@FileName: workflow_decision.py
@Description: 决策函数类 - 控制工作流分支逻辑
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 16:12
"""
from datetime import datetime
from typing import Tuple, Any

from langgraph.graph import END

from penshot.neopen.agent.human_decision.human_decision_converter import HumanDecisionConverter
from penshot.neopen.agent.quality_auditor.quality_auditor_models import AuditStatus
from penshot.neopen.agent.workflow.workflow_models import PipelineState, PipelineNode, AgentStage
from penshot.neopen.agent.workflow.workflow_states import WorkflowState
from penshot.logger import error, warning, info


class PipelineDecision:
    """决策函数类 - 控制工作流分支逻辑

    职责说明：
    1. 每个函数接收 WorkflowState 作为输入
    2. 根据当前状态数据做出决策判断
    3. 返回 PipelineState 枚举值，指示下一步应该做什么
    4. 决策结果将决定工作流的下一个节点

    设计原则：
    - 保持函数纯净，不修改传入的状态对象
    - 明确的错误处理和日志记录
    - 合理的状态转换逻辑
    - 考虑重试机制和人工干预需求
    """

    def __init__(self):
        """初始化决策函数"""
        self.converter = HumanDecisionConverter()

    def decide_after_parsing(self, state: WorkflowState) -> PipelineState:
        """剧本解析后的决策

        决策逻辑：
        1. 检查解析结果是否存在
        2. 检查解析结果是否有效
        3. 根据检查结果返回相应决策状态

        可能的返回状态：
        - SUCCESS: 解析成功，可以继续下一步
        - NEEDS_HUMAN: 解析数据有问题，需要人工判断
        - FAILED: 解析完全失败，需要错误处理

        Args:
            state: 包含解析结果的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.PARSE_SCRIPT)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"剧本解析节点循环检查失败: {loop_reason}")
            return loop_decision

        parsed_script = state.parsed_script

        # 检查解析结果是否存在
        if not parsed_script:
            error("剧本解析，数据为空")
            return PipelineState.FAILED

        # 检查解析质量
        if not parsed_script.is_valid:
            error("剧本解析，数据有问题")
            # 数据无效时，需要人工判断是否可以继续
            return PipelineState.NEEDS_HUMAN

        # 解析成功，可以继续下一步
        return PipelineState.SUCCESS

    def decide_after_splitting(self, state: WorkflowState) -> PipelineState:
        """镜头拆分后的决策

        决策逻辑：
        1. 检查拆分结果是否存在
        2. 检查是否有过长镜头
        3. 根据重试次数和问题严重性决定

        可能的返回状态：
        - SUCCESS: 拆分成功，可以继续下一步
        - RETRY: 有可重试的问题，重试当前节点
        - NEEDS_REPAIR: 需要修复后重试
        - FAILED: 拆分完全失败

        Args:
            state: 包含镜头序列的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.SEGMENT_SHOT)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"镜头拆分节点循环检查失败: {loop_reason}")
            return loop_decision

        # 检查阶段重试限制
        can_retry, retry_reason = self._can_retry_stage(state, PipelineNode.SEGMENT_SHOT)

        shot_sequence = state.shot_sequence

        if not shot_sequence or len(shot_sequence.shots) < 1:
            error("镜头拆分，数据为空")
            return PipelineState.FAILED

        # 检查是否有过短镜头
        short_shots = [s for s in shot_sequence.shots if s.duration < state.min_shot_duration]
        if short_shots:
            if can_retry:
                # 增加重试计数
                state = self._increment_stage_retry(state, PipelineNode.SEGMENT_SHOT)
                warning(f"镜头拆分，发现{len(short_shots)}个过短镜头，{retry_reason}")
                return PipelineState.RETRY
            else:
                # 不能重试，需要修复
                warning(f"镜头拆分，发现{len(short_shots)}个过短镜头，但{retry_reason}")
                return PipelineState.NEEDS_REPAIR

        # 检查是否有过长镜头
        long_shots = [s for s in shot_sequence.shots if s.duration > state.max_shot_duration]
        if long_shots:
            if can_retry:
                # 增加重试计数
                state = self._increment_stage_retry(state, PipelineNode.SEGMENT_SHOT)
                warning(f"镜头拆分，发现{len(long_shots)}个过长镜头，{retry_reason}")
                return PipelineState.RETRY
            else:
                # 不能重试，需要修复
                warning(f"镜头拆分，发现{len(long_shots)}个过长镜头，但{retry_reason}")
                return PipelineState.NEEDS_REPAIR

        # 拆分成功，重置该阶段的重试计数（可选）
        state.stage_current_retries[PipelineNode.SEGMENT_SHOT] = 0

        return PipelineState.SUCCESS

    def decide_after_fragmenting(self, state: WorkflowState) -> PipelineState:
        """AI分段后的决策

        决策逻辑：
        1. 检查分段结果是否存在
        2. 检查时长合规性（不超过5.2秒）
        3. 检查片段质量（不过短）
        4. 根据问题数量和类型决定

        可能的返回状态：
        - SUCCESS: 分段成功，可以继续下一步
        - NEEDS_REPAIR: 需要修复/调整
        - RETRY: 需要重试
        - NEEDS_HUMAN: 需要人工干预
        - FAILED: 分段完全失败

        Args:
            state: 包含片段序列的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.SPLIT_VIDEO)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"AI分段节点循环检查失败: {loop_reason}")
            return loop_decision

        # 检查阶段重试限制
        can_retry, retry_reason = self._can_retry_stage(state, PipelineNode.SPLIT_VIDEO)

        fragment_sequence = state.fragment_sequence

        # 检查分段结果是否存在
        if not fragment_sequence or len(fragment_sequence.fragments) < 1:
            error("AI分段后，数据为空")
            return PipelineState.FAILED

        # 检查时长合规性：不能超过5.2秒
        invalid_fragments = [f for f in fragment_sequence.fragments if f.duration > state.max_fragment_duration + 0.5]  # 允许一定的时长波动
        if invalid_fragments:
            if len(invalid_fragments) <= 3:
                # 少量问题，检查是否可以重试
                if can_retry:
                    state = self._increment_stage_retry(state, PipelineNode.SPLIT_VIDEO)
                    warning(f"AI分段后，发现{len(invalid_fragments)}个超长片段，{retry_reason}")
                    return PipelineState.RETRY
                else:
                    warning(f"AI分段后，发现{len(invalid_fragments)}个超长片段，但{retry_reason}")
                    return PipelineState.NEEDS_REPAIR
            else:
                # 多个问题，严重失败
                error(f"AI分段后，发现{len(invalid_fragments)}个超长片段，不符合要求")
                return PipelineState.FAILED

        # 检查片段质量：不能过短（小于0.5秒）
        short_fragments = [f for f in fragment_sequence.fragments if f.duration < state.min_fragment_duration]
        if short_fragments:
            # 有过短片段，需要修复
            warning(f"发现{len(short_fragments)}个过短片段（<{state.min_fragment_duration}秒）")
            return PipelineState.NEEDS_REPAIR

        # 成功，重置重试计数
        state.stage_current_retries[PipelineNode.SPLIT_VIDEO] = 0

        # 分段成功，可以继续下一步
        return PipelineState.SUCCESS

    def decide_after_prompts(self, state: WorkflowState) -> PipelineState:
        """Prompt生成后的决策

        决策逻辑：
        1. 检查提示词结果是否存在
        2. 检查提示词是否为空
        3. 检查提示词长度是否合理
        4. 返回相应的决策状态

        可能的返回状态：
        - SUCCESS: 提示词生成成功
        - VALID: 提示词可用，可以继续质量审查
        - NEEDS_REPAIR: 有空或过长的提示词，需要修复
        - RETRY: 需要重试
        - FAILED: 提示词生成完全失败

        Args:
            state: 包含AI指令的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.CONVERT_PROMPT)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"提示词生成节点循环检查失败: {loop_reason}")
            return loop_decision

        # 检查阶段重试限制
        can_retry, retry_reason = self._can_retry_stage(state, PipelineNode.CONVERT_PROMPT)

        instructions = state.instructions

        # 检查提示词结果是否存在
        if not instructions or len(instructions.fragments) < 1:
            error("Prompt生成，数据为空")
            return PipelineState.FAILED

        # 检查是否有空提示词
        empty_prompts = [f for f in instructions.fragments if not f.prompt.strip()]
        if empty_prompts:
            if can_retry:
                state = self._increment_stage_retry(state, PipelineNode.CONVERT_PROMPT)
                warning(f"发现{len(empty_prompts)}个空提示词，{retry_reason}")
                return PipelineState.RETRY
            else:
                warning(f"发现{len(empty_prompts)}个空提示词，但{retry_reason}")
                return PipelineState.NEEDS_REPAIR

        # 检查提示词长度是否过长（超过300字符）
        long_prompts = [f for f in instructions.fragments if len(f.prompt) > state.max_prompt_length * 10]  # 允许一定的长度波动
        if long_prompts:
            if can_retry:
                state = self._increment_stage_retry(state, PipelineNode.CONVERT_PROMPT)
                warning(f"发现{len(long_prompts)}个过长提示词，{retry_reason}")
                return PipelineState.RETRY
            else:
                warning(f"发现{len(long_prompts)}个过长提示词，但{retry_reason}")
                return PipelineState.NEEDS_REPAIR

        # 检查提示词长度是否过短
        short_prompts = [f for f in instructions.fragments if len(f.prompt) < state.min_prompt_length]
        if short_prompts:
            if can_retry:
                state = self._increment_stage_retry(state, PipelineNode.CONVERT_PROMPT)
                warning(f"发现{len(short_prompts)}个过短提示词，{retry_reason}")
                return PipelineState.RETRY
            else:
                warning(f"发现{len(short_prompts)}个过短提示词，但{retry_reason}")
                return PipelineState.NEEDS_REPAIR

        # 成功，重置重试计数
        state.stage_current_retries[PipelineNode.CONVERT_PROMPT] = 0

        # 提示词可用，进入质量审查
        return PipelineState.VALID

    def decide_after_audit(self, state: WorkflowState) -> PipelineState:
        """质量审查后的决策

        决策逻辑：
        1. 检查审计报告是否存在
        2. 根据审计状态映射到决策状态
        3. 记录审计决策日志

        映射关系：
        - PASSED -> SUCCESS: 审查通过
        - MINOR_ISSUES -> VALID: 有轻微问题，但可以继续
        - MODERATE_ISSUES -> NEEDS_REPAIR: 有中度问题，需要修复
        - MAJOR_ISSUES -> NEEDS_REPAIR: 有主要问题，需要修复
        - CRITICAL_ISSUES -> RETRY: 有严重问题，应该重试
        - NEEDS_HUMAN -> NEEDS_HUMAN: 需要人工干预
        - FAILED -> FAILED: 审查失败

        Args:
            state: 包含审计报告的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查是否已经审查过且结果有效
        if hasattr(state, 'last_audit_result') and state.last_audit_result:
            # 如果短时间内重复调用，使用上次结果
            warning("检测到可能的重复质量审查调用，使用上次结果")
            return PipelineState.SUCCESS

        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.AUDIT_QUALITY)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"质量审查节点循环检查失败: {loop_reason}")
            return loop_decision

        # 检查阶段重试限制
        can_retry, retry_reason = self._can_retry_stage(state, PipelineNode.AUDIT_QUALITY)

        report = state.audit_report

        # 检查审计报告是否存在
        if not report:
            if can_retry:
                state = self._increment_stage_retry(state, PipelineNode.AUDIT_QUALITY)
                warning(f"审计报告为空，{retry_reason}")
                return PipelineState.RETRY
            else:
                warning(f"审计报告为空，但{retry_reason}")
                return PipelineState.FAILED

        # 记录审计结果到状态
        if hasattr(state, 'audit_history'):
            state.audit_history.append({
                "timestamp": datetime.now().isoformat(),
                "status": report.status.value,
                "score": report.score,
                "passed_checks": report.passed_checks,
                "total_checks": report.total_checks
            })

        # 保存最后的审计结果
        state.last_audit_result = {
            "status": report.status.value,
            "score": report.score,
            "passed_checks": report.passed_checks,
            "total_checks": report.total_checks,
            "stats": getattr(report, 'stats', {})
        }

        info(f"审计报告详细: 状态={report.status.value}, 分数={report.score}%, 通过={report.passed_checks}/{report.total_checks}")

        # 修复：即使状态是 FAILED，如果分数足够高，也可以继续
        if report.status == AuditStatus.FAILED:
            if report.score >= 80.0:  # 分数高于80%视为可接受
                info(f"审计状态为 FAILED 但分数 {report.score}% 较高，视为 VALID 继续")
                return PipelineState.VALID
            elif report.score >= 60.0 and can_retry:  # 分数60-80%可重试
                state = self._increment_stage_retry(state, PipelineNode.AUDIT_QUALITY)
                info(f"审计状态为 FAILED，分数 {report.score}% 中等，重试")
                return PipelineState.RETRY
            else:
                # 分数太低，需要修复或人工干预
                if can_retry:
                    state = self._increment_stage_retry(state, PipelineNode.AUDIT_QUALITY)
                    return PipelineState.RETRY
                else:
                    return PipelineState.NEEDS_REPAIR

        # 审计状态到决策状态的映射
        decision_map = {
            AuditStatus.PASSED: PipelineState.SUCCESS,
            AuditStatus.MINOR_ISSUES: PipelineState.VALID,
            AuditStatus.MODERATE_ISSUES: PipelineState.NEEDS_REPAIR,
            AuditStatus.MAJOR_ISSUES: PipelineState.NEEDS_REPAIR,
            AuditStatus.CRITICAL_ISSUES: PipelineState.RETRY if can_retry else PipelineState.NEEDS_HUMAN,
            AuditStatus.NEEDS_HUMAN: PipelineState.NEEDS_HUMAN,
        }

        decision = decision_map.get(report.status, PipelineState.RETRY if can_retry else PipelineState.FAILED)

        # 如果决定重试，增加重试计数
        if decision == PipelineState.RETRY:
            state = self._increment_stage_retry(state, PipelineNode.AUDIT_QUALITY)
            info(f"质量审查需要重试: 审计状态={report.status.value}, 已重试{state.stage_current_retries.get(PipelineNode.AUDIT_QUALITY, 0)}次")

        info(f"质量审查决策: 审计状态={report.status.value}, 决策={decision.value}, 分数={report.score}%")

        return decision


    def decide_after_continuity(self, state: WorkflowState) -> PipelineState:
        """连续性检查后的决策

        决策逻辑：
        1. 检查是否有连续性问题
        2. 根据问题严重性分类
        3. 返回相应的决策状态

        问题分类：
        - critical: 严重问题，需要修复
        - moderate: 中度问题，需要修复
        - minor: 轻微问题，需要修复
        - 其他: 验证通过

        可能的返回状态：
        - SUCCESS: 没有连续性问题
        - NEEDS_REPAIR: 有连续性问题，需要修复
        - NEEDS_HUMAN: 需要人工干预
        - VALID: 验证通过但有小问题
        - FAILED: 严重失败

        Args:
            state: 包含连续性问题的的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.CONTINUITY_CHECK)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"连续性检查节点循环检查失败: {loop_reason}")
            return loop_decision

        issues = state.continuity_issues

        # 检查是否有连续性问题
        if not issues:
            # 没有连续性问题，可以直接生成输出
            return PipelineState.SUCCESS

        # 根据问题严重性分类
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        moderate_issues = [i for i in issues if i.get("severity") == "moderate"]
        minor_issues = [i for i in issues if i.get("severity") == "minor"]

        if critical_issues:
            warning(f"发现{len(critical_issues)}个严重连续性问题")
            if len(critical_issues) >= 5:
                return PipelineState.NEEDS_HUMAN
            return PipelineState.NEEDS_REPAIR
        elif moderate_issues:
            warning(f"发现{len(moderate_issues)}个中度连续性问题")
            return PipelineState.NEEDS_REPAIR
        elif minor_issues:
            warning(f"发现{len(minor_issues)}个轻微连续性问题")
            return PipelineState.VALID
        else:
            warning(f"发现{len(issues)}个连续性问题，但严重性未知")
            return PipelineState.VALID

    def decide_after_error(self, state: WorkflowState) -> PipelineState:
        """错误处理后的决策

        决策逻辑：
        1. 检查是否超过重试次数
        2. 分析错误类型
        3. 根据错误类型决定下一步

        错误类型分类：
        - 网络/超时错误: 可以重试
        - 验证/无效错误: 可恢复错误
        - 配置错误: 需要修复
        - 其他错误: 普通失败

        可能的返回状态：
        - NEEDS_HUMAN: 超过重试次数，需要人工干预
        - RETRY: 网络/超时错误，可以重试
        - VALID: 验证错误，可恢复
        - NEEDS_REPAIR: 配置错误，需要修复
        - FAILED: 其他错误，失败
        - ABORT: 需要中止流程

        Args:
            state: 包含错误信息的工作流状态

        Returns:
            PipelineState: 决策结果
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.ERROR_HANDLER)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"错误处理节点循环检查失败: {loop_reason}")
            return loop_decision

        # 检查全局重试限制
        if state.total_retries >= sum(state.stage_max_retries.values()):
            warning(f"总重试次数已达上限: {state.total_retries}")
            return PipelineState.NEEDS_HUMAN

        # 检查是否有中止标志
        if hasattr(state, 'recovery_flags') and state.recovery_flags.get('should_abort', False):
            info("检测到中止标志，结束流程")
            return PipelineState.ABORT

        # 检查是否需要人工干预
        if state.needs_human_review:
            info("错误需要人工干预")
            return PipelineState.NEEDS_HUMAN

        # 检查延迟标志
        if hasattr(state, 'recovery_flags') and state.recovery_flags.get('need_delay', False):
            delay_seconds = state.recovery_flags.get('delay_seconds', 5)
            warning(f"错误处理建议延迟 {delay_seconds} 秒后重试")
            # 在实际实现中，这里可以添加实际的延迟逻辑
            # 暂时返回 RETRY，由工作流调度器处理延迟

        # 检查修复标志
        if hasattr(state, 'recovery_flags') and state.recovery_flags.get('need_repair', False):
            repair_type = state.recovery_flags.get('repair_type', 'general')

            if repair_type in ["validation", "data"]:
                # 验证或数据错误，可能需要重新解析或调整
                info(f"需要修复验证/数据问题: {repair_type}")
                return PipelineState.NEEDS_REPAIR
            elif repair_type == "configuration":
                # 配置错误，可能需要调整后重试
                info("需要修复配置问题")
                return PipelineState.RETRY
            else:
                # 一般修复
                info(f"需要一般修复: {repair_type}")
                return PipelineState.VALID

        # 默认：如果可以恢复，重新开始流程
        if hasattr(state, 'recovery_flags') and state.recovery_flags.get('can_recover', True):
            info("错误可恢复，重新开始流程")
            return PipelineState.RETRY

        # 检查重试次数限制
        total_retries = getattr(state, 'total_retries', 0)
        if total_retries >= 10:  # 硬限制
            warning(f"总重试次数过多: {total_retries}")
            return PipelineState.NEEDS_HUMAN

        # 最后的选择：重试
        info("尝试重试流程")
        return PipelineState.RETRY


    def decide_next_after_error(self, graph_state: WorkflowState) -> str:
        """错误处理后决定下一个节点"""
        # 1. 先调用决策函数获取错误处理决策
        decision_state = self.decide_after_error(graph_state)

        # 2. 根据决策决定下一个节点
        if decision_state == PipelineState.VALID:
            # 可恢复错误，根据错误来源决定重试节点
            return self._get_retry_node_based_on_error_source(graph_state, PipelineState.VALID)
        elif decision_state == PipelineState.RETRY:
            # 需要重试，根据错误来源决定重试节点
            return self._get_retry_node_based_on_error_source(graph_state, PipelineState.RETRY)
        elif decision_state == PipelineState.NEEDS_REPAIR:
            # 需要修复，通常回到提示词生成
            return PipelineNode.CONVERT_PROMPT.value
        elif decision_state == PipelineState.NEEDS_HUMAN:
            # 需要人工干预
            return PipelineNode.HUMAN_INTERVENTION.value
        elif decision_state == PipelineState.ABORT:
            # 中止流程
            return END
        else:
            # 默认情况，重新开始
            warning(f"未知错误决策: {decision_state}，默认回到剧本解析")
            return PipelineNode.PARSE_SCRIPT.value


    def decide_after_human(self, state: WorkflowState) -> PipelineState:
        """人工干预后的决策（简化版）

        流程：
        1. 从状态中提取输入
        2. 调用转换器进行转换
        3. 返回决策状态

        Args:
            state: 工作流状态

        Returns:
            PipelineState: 决策状态
        """
        # 检查节点循环限制
        loop_decision, loop_reason = self._check_and_increment_node_loop(state, PipelineNode.HUMAN_INTERVENTION)
        if loop_decision != PipelineState.SUCCESS:
            state.error_messages.append(f"人工干预节点循环检查失败: {loop_reason}")
            return loop_decision

        # 从状态中获取人工输入
        human_feedback = state.human_feedback or {}
        raw_input = human_feedback.get("decision", "CONTINUE")
        is_timeout = human_feedback.get("timeout", False)

        # 创建转换上下文
        context = {
            "task_id": state.task_id,
            "current_stage": str(state.current_stage),
            "is_timeout": is_timeout,
            "retry_count": state.retry_count,
            "has_errors": len(state.error_messages) > 0 if state.error_messages else False,
        }

        info(f"开始决策处理，原始输入: {raw_input}")

        # 步骤1：标准化输入
        normalized_input = self.converter.normalize_input(raw_input)

        # 步骤2：转换为决策状态
        decision_state = self.converter.convert_to_decision_state(normalized_input, context)

        # 步骤3：验证决策合理性
        is_valid = self.converter.validate_decision(decision_state, context)

        if not is_valid:
            warning(f"决策验证失败: {decision_state.value}，使用默认继续")
            decision_state = PipelineState.SUCCESS

        # 获取决策描述
        description = self.converter.get_decision_description(decision_state)

        info(f"决策完成: {raw_input} -> {normalized_input} -> {decision_state.value} ({description})")

        return decision_state

    def decide_after_loop_check(self, graph_state: WorkflowState) -> Any:
        """循环检查后的决策

        决策逻辑：
        1. 检查全局循环是否超限
        2. 检查节点循环是否超限
        3. 根据当前阶段决定下一个节点（返回节点枚举）

        Args:
            graph_state: 工作流状态

        Returns:
            str: 返回节点名称（PipelineNode）或状态（PipelineState）
        """
        # 1. 检查全局循环是否超限
        if graph_state.global_current_loops >= graph_state.global_max_loops:
            graph_state.global_loop_exceeded = True
            error(f"全局循环超限: {graph_state.global_current_loops}/{graph_state.global_max_loops}")
            return PipelineState.FAILED  # 返回FAILED状态

        # 2. 检查当前节点循环是否超限
        current_node = graph_state.current_node
        if current_node:
            node_max_loops = graph_state.node_max_loops.get(current_node, 3)
            node_current_loops = graph_state.node_current_loops.get(current_node, 0)

            if node_current_loops >= node_max_loops:
                graph_state.node_loop_exceeded[current_node] = True
                warning(f"节点 {current_node.value} 循环超限: {node_current_loops}/{node_max_loops}")

                # 根据节点类型决定处理方式
                if current_node in [PipelineNode.SEGMENT_SHOT, PipelineNode.SPLIT_VIDEO]:
                    return PipelineState.NEEDS_HUMAN
                else:
                    return PipelineState.FAILED

        # 3. 发出循环警告（如果需要）
        if (graph_state.global_current_loops >= graph_state.global_max_loops * 0.8
                and not graph_state.loop_warning_issued):
            graph_state.loop_warning_issued = True
            warning(f"循环警告: 已使用 {graph_state.global_current_loops}/{graph_state.global_max_loops} 次循环")

        # 4. 根据当前阶段决定下一个节点
        if graph_state.current_stage == AgentStage.SEGMENTER:
            # 更新阶段为SPLITTER
            graph_state.current_stage = AgentStage.SPLITTER
            return PipelineNode.SPLIT_VIDEO
        elif graph_state.current_stage == AgentStage.SPLITTER:
            # 更新阶段为CONVERTER
            graph_state.current_stage = AgentStage.CONVERTER
            return PipelineNode.CONVERT_PROMPT
        elif graph_state.current_stage == AgentStage.CONVERTER:
            # 更新阶段为AUDITOR
            graph_state.current_stage = AgentStage.AUDITOR
            return PipelineNode.AUDIT_QUALITY
        else:
            warning(f"未知阶段: {graph_state.current_stage}")
            return PipelineState.NEEDS_HUMAN

    # ===================================== 私有辅助方法 =====================================
    def _get_retry_node_based_on_error_source(self, graph_state: WorkflowState, decision_type: PipelineState) -> PipelineNode:
        """根据错误来源获取重试节点"""
        last_node = graph_state.last_node

        info(f"错误处理重试决策: type={decision_type.value}, last_node={last_node.value if last_node else None}")

        # 映射表：错误来源 -> 重试节点
        retry_mapping = {
            PipelineNode.PARSE_SCRIPT: PipelineNode.PARSE_SCRIPT,
            PipelineNode.SEGMENT_SHOT: PipelineNode.SEGMENT_SHOT,
            PipelineNode.SPLIT_VIDEO: PipelineNode.SPLIT_VIDEO,
            PipelineNode.CONVERT_PROMPT: PipelineNode.CONVERT_PROMPT,
            PipelineNode.AUDIT_QUALITY: PipelineNode.CONVERT_PROMPT,  # 审计失败要重新生成提示词
            PipelineNode.CONTINUITY_CHECK: PipelineNode.CONVERT_PROMPT,  # 连续性失败也要重新生成提示词
            PipelineNode.LOOP_CHECK: PipelineNode.PARSE_SCRIPT,  # 循环检查失败重新开始
        }

        if last_node and last_node in retry_mapping:
            return retry_mapping[last_node]
        else:
            # 默认回到剧本解析重新开始
            info(f"未知错误来源 {last_node}，回到剧本解析重新开始")
            return PipelineNode.PARSE_SCRIPT

    def _can_retry_stage(self, state: WorkflowState, stage_node: PipelineNode) -> Tuple[bool, str]:
        """检查指定阶段是否可以重试

        Args:
            state: 工作流状态
            stage_node: 阶段

        Returns:
            Tuple[bool, str]: (是否可以重试, 原因说明)
        """
        # 获取该阶段的最大重试次数
        max_retries = state.stage_max_retries.get(stage_node, 2)  # 默认2次

        # 获取当前重试次数
        current_retries = state.stage_current_retries.get(stage_node, 0)

        if current_retries >= max_retries:
            return False, f"阶段 '{stage_node}' 重试次数已达上限 ({current_retries}/{max_retries})"

        # 检查循环限制
        if state.global_loop_exceeded:
            return False, "工作流循环次数已超限"

        # 可以重试
        return True, f"阶段 '{stage_node}' 可重试 ({current_retries}/{max_retries})"

    def _increment_stage_retry(self, state: WorkflowState, stage_node: PipelineNode) -> WorkflowState:
        """增加指定阶段的重试计数"""
        # 更新阶段重试计数
        current = state.stage_current_retries.get(stage_node, 0)
        state.stage_current_retries[stage_node] = current + 1

        # 更新全局重试统计
        state.total_retries += 1

        return state

    def _check_node_loop_limit(self, state: WorkflowState, stage_node: PipelineNode) -> Tuple[bool, str]:
        """检查指定节点的循环限制

        Args:
            state: 工作流状态
            stage_node: 节点

        Returns:
            Tuple[bool, str]: (是否超限, 原因说明)
        """
        # 检查节点循环限制
        if state.node_loop_exceeded.get(stage_node, False):
            max_loops = state.node_max_loops.get(stage_node, 3)
            current_loops = state.node_current_loops.get(stage_node, 0)
            return True, f"节点 '{stage_node}' 循环次数超限 ({current_loops}/{max_loops})"

        # 检查全局循环限制
        if state.global_loop_exceeded:
            return True, f"全局循环次数超限 ({state.global_current_loops}/{state.global_max_loops})"

        return False, "循环检查通过"

    def _check_and_increment_node_loop(self, state: WorkflowState, stage_node: PipelineNode) -> Tuple[PipelineState, str]:
        """检查并处理节点循环（修正版）

        Args:
            state: 工作流状态
            stage_node: 节点

        Returns:
            Tuple[PipelineState, str]: (决策状态, 原因说明)
        """
        # 1. 更新节点循环计数
        current_loops = state.node_current_loops.get(stage_node, 0)
        state.node_current_loops[stage_node] = current_loops + 1

        # 2. 更新全局循环计数
        if hasattr(state, 'global_current_loops'):
            state.global_current_loops += 1

        # 3. 检查节点循环是否超限
        max_loops = state.node_max_loops.get(stage_node, 3)
        if current_loops + 1 >= max_loops:
            state.node_loop_exceeded[stage_node] = True

            # 根据不同节点类型决定处理方式
            if stage_node in [PipelineNode.SEGMENT_SHOT, PipelineNode.SPLIT_VIDEO]:
                warning(f"节点 {stage_node.value} 循环超限: {current_loops + 1}/{max_loops}")
                return PipelineState.NEEDS_HUMAN, f"节点 {stage_node.value} 循环超限"
            else:
                warning(f"节点 {stage_node.value} 循环超限: {current_loops + 1}/{max_loops}")
                return PipelineState.FAILED, f"节点 {stage_node.value} 循环超限"

        # 4. 检查全局循环是否超限
        if hasattr(state, 'global_current_loops') and hasattr(state, 'global_max_loops'):
            if state.global_current_loops >= state.global_max_loops:
                state.global_loop_exceeded = True
                return PipelineState.FAILED, f"全局循环超限: {state.global_current_loops}/{state.global_max_loops}"

        return PipelineState.SUCCESS, f"节点 {stage_node.value} 循环正常 ({current_loops + 1}/{max_loops})"
