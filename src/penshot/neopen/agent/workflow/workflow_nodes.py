"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: workflow_nodes.py
@Description: LangGraph工作流节点实现，包含所有工作流执行功能
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10 - 2025/11
"""

import time
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional

from penshot.config.config import settings
from penshot.logger import error, debug, info, warning
from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import ContinuityGuardianChecker
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import ContinuityCheckResult, ContinuityIssueType, ContinuityIssue
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import ContinuityRepairGenerator
from penshot.neopen.agent.human_decision.human_decision_intervention import HumanIntervention
from penshot.neopen.agent.quality_auditor.quality_auditor_models import AuditStatus, QualityAuditReport, SeverityLevel, QualityRepairParams
from penshot.neopen.agent.workflow.workflow_error_handler import WorkflowErrorHandler, ErrorHandlerMiddleware
from penshot.neopen.agent.workflow.workflow_memory import WorkflowMemory
from penshot.neopen.agent.workflow.workflow_models import AgentStage, PipelineNode
from penshot.neopen.agent.workflow.workflow_output import WorkflowOutputWriter
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig, MemoryLevel
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager
from penshot.neopen.task.task_models import TaskStage, TaskStatus
from penshot.neopen.tools.result_storage_tool import create_result_storage
from penshot.utils.log_utils import print_log_exception


class WorkflowNodes:
    """
    工作流节点集合，封装所有工作流执行功能

    职责：
    - 剧本解析节点：将原始剧本解析为结构化元素序列
    - 镜头拆分节点：将结构化剧本拆分为视觉镜头
    - 视频分割节点：将镜头按限制切分为AI可处理的片段
    - 提示词转换节点：为每个片段生成AI视频生成提示词
    - 质量审查节点：合并基本规则审查和LLM深度审查
    - 连续性检查节点：检查所有阶段的连续性
    - 错误处理节点：处理工作流中的错误和异常
    - 结果生成节点：组装最终输出结果
    - 人工干预节点：暂停流程等待人工输入
    - 循环检查节点：检查节点循环次数并记录状态
    """

    def __init__(self, script_id, script_parser, shot_segmenter, video_splitter,
                 prompt_converter, quality_auditor,
                 llm, embeddings, task_manager):
        """
        初始化工作流节点集合

        Args:
            script_id: 脚本ID
            script_parser: 剧本解析器实例
            shot_segmenter: 分镜生成器实例
            video_splitter: 视频分割器实例
            prompt_converter: 提示词转换器实例
            quality_auditor: 质量审查实例
            llm: 语言模型实例
            embeddings: 嵌入模型实例
            task_manager: 任务管理器实例
        """
        self.script_id = script_id
        self.llm = llm
        self.embeddings = embeddings
        self.task_manager = task_manager

        # 初始化底层记忆管理器（仅供 WorkflowMemory 内部使用）
        self._memory = MemoryManager(
            llm=self.llm,
            script_id=self.script_id,
            config=MemoryConfig(
                embeddings=self.embeddings,
                short_term_size=20,
                short_term_ttl=3600,
                medium_term_max_tokens=500,
                long_term_enabled=True,
                long_term_k=3,
            )
        )

        # 初始化提示词模板管理器
        self.knowledge_manager = PromptTemplateManager(
            embedding_model=self.embeddings,
            script_id=self.script_id,
            storage_dir=settings.get_data_paths().get('data_embedding'),
            memory_manager=self._memory,
            min_similarity_score=0.7,
            top_k=3
        )

        # 初始化工作流记忆管理器（统一记忆访问入口）：内部封装了三层记忆存储（短期、中期、长期）
        self.workflow_memory = WorkflowMemory(script_id, self._memory, self.knowledge_manager)

        # 初始化各智能体
        self.script_parser = script_parser
        self.shot_segmenter = shot_segmenter
        self.video_splitter = video_splitter
        self.prompt_converter = prompt_converter
        self.quality_auditor = quality_auditor

        # 初始化人工干预节点
        self.human_intervention = HumanIntervention(timeout_seconds=180)
        self.storage = create_result_storage()

        # 初始化连续性守护组件
        self.generator = ContinuityRepairGenerator()
        self.checker = ContinuityGuardianChecker()

        # 初始化输出写入器
        self.output_writer = WorkflowOutputWriter(self.storage, self._memory)

        # 初始化统一错误处理器
        self.error_handler = WorkflowErrorHandler()
        self.error_middleware = ErrorHandlerMiddleware(self.error_handler)

        # 警告标记
        self._enhanced_warning_issued = False
        self._quality_warning_issued = False

    # ======================== 剧本解析节点 ========================

    def parse_script_node(self, state: WorkflowState) -> WorkflowState:
        """
        剧本解析节点（增强版）

        功能：将原始剧本解析为结构化元素序列，支持修复参数

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        try:
            # 更新状态：开始解析
            self._update_task_status(state.input.task_id, TaskStatus.PROCESSING)
            self._update_task_progress(state.input.task_id, TaskStage.PARSING_START, 0)

            # 1. 加载历史上下文（使用 workflow_memory）
            recent_strategy = self.workflow_memory.get_memory_dict(
                "parsing_strategy_recent", level=MemoryLevel.SHORT_TERM
            )
            historical_stats = self.workflow_memory.get_memory_dict(
                "stats_parse_script", level=MemoryLevel.MEDIUM_TERM
            )
            common_issues = self.workflow_memory.get_memory_list(
                "common_parse_issues", level=MemoryLevel.LONG_TERM, default=[]
            )

            historical_context = {
                "recent_strategy": recent_strategy,
                "historical_stats": historical_stats,
                "common_issues": common_issues
            }

            # 只有存在有效内容时才应用历史上下文
            if historical_context and any(v is not None for v in historical_context.values()):
                self.script_parser.apply_historical_context(historical_context)

            # 2. 加载修复参数
            repair_params = state.domain.repair_params.get(PipelineNode.PARSE_SCRIPT, None)
            if repair_params:
                self.script_parser.apply_repair_params(PipelineNode.PARSE_SCRIPT, repair_params)

                info(f"剧本解析节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")
            else:
                debug("剧本解析节点执行（无修复参数）")

            # 更新状态：解析中
            self._update_task_progress(state.input.task_id, TaskStage.PARSING_SCRIPT, 30)

            # 3. 执行解析
            parsed_script = self.script_parser.process(
                state.input.raw_script,
                knowledge_manager=self.knowledge_manager,
                script_id=state.input.script_id
            )

            debug(f"剧本解析完成，场景数: {len(parsed_script.scenes)}，角色数: {len(parsed_script.characters)}")
            debug(f"完整性评分: {parsed_script.stats.get('completeness_score', 0)}")

            # 更新状态：解析完成
            self._update_task_progress(state.input.task_id, TaskStage.PARSING_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.PARSING_COMPLETE, {
                "scene_count": len(parsed_script.scenes),
                "character_count": len(parsed_script.characters),
                "completeness_score": parsed_script.stats.get("completeness_score", 0)
            })

            # 4. 保存结果
            self.storage.save_obj_result(
                state.input.script_id, state.input.task_id,
                parsed_script, "script_parser_result.json"
            )

            # 5. 问题检测（使用 workflow_memory 存储问题列表）
            parse_issues = self.script_parser.detect_issues(parsed_script, state.input.raw_script)
            if parse_issues:
                self.workflow_memory.store_short_term_memory(
                    stage_key="parse_script_issues",
                    result=[issue.dict() for issue in parse_issues],
                    stats={"issue_count": len(parse_issues)},
                    timestamp=datetime.now().isoformat()
                )

            # 6. 保存阶段记忆（统一入口）
            self.workflow_memory.after_stage_completion(
                stage="parse_script",
                result=parsed_script,
                metadata={
                    "repair_applied": repair_params is not None,
                    "issue_count": len(parse_issues) if parse_issues else 0,
                    "repair_params": repair_params.model_dump() if repair_params else None
                }
            )

            # 7. 更新状态
            state.domain.parsed_script = parsed_script
            state.execution.current_stage = AgentStage.PARSER
            state.execution.current_node = PipelineNode.PARSE_SCRIPT

            # 8. 清理临时状态
            self.script_parser.clear_repair_params()
            self.script_parser.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"剧本解析失败: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)
            debug(f"解析异常堆栈: {traceback.format_exc()}")

            state.execution.current_node = PipelineNode.PARSE_SCRIPT
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.PARSE_SCRIPT

        return state

    # ======================== 镜头拆分节点 ========================

    def split_shots_node(self, state: WorkflowState) -> WorkflowState:
        """
        镜头拆分节点（增强版）

        功能：将结构化剧本拆分为视觉镜头，支持修复参数

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        try:
            # 更新状态：开始拆分
            self._update_task_progress(state.input.task_id, TaskStage.SEGMENT_START, 0)

            # 1. 加载历史上下文（使用 workflow_memory）
            historical_shot_stats = self.workflow_memory.get_memory_dict(
                f"stats_segment_shot", level=MemoryLevel.MEDIUM_TERM
            )
            historical_shot_issues = self.workflow_memory.get_memory_list(
                f"issues_segment_shot", level=MemoryLevel.SHORT_TERM, default=[]
            )
            common_shot_patterns = self.workflow_memory.get_memory_list(
                "common_shot_patterns", level=MemoryLevel.LONG_TERM, default=[]
            )

            historical_context = {
                "historical_stats": historical_shot_stats,
                "historical_issues": historical_shot_issues,
                "common_patterns": common_shot_patterns
            }

            if historical_context and any(v is not None for v in historical_context.values()):
                self.shot_segmenter.apply_historical_context(historical_context)

            # 2. 加载修复参数
            repair_params = state.domain.repair_params.get(PipelineNode.SEGMENT_SHOT, None)

            if repair_params:
                self.shot_segmenter.apply_repair_params(PipelineNode.SEGMENT_SHOT, repair_params)

                info(f"分镜生成节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")

                # 修复历史由 workflow_memory.after_stage_completion 统一处理
            else:
                debug("分镜生成节点执行（无修复参数）")

            # 更新状态：拆分中
            self._update_task_progress(state.input.task_id, TaskStage.SEGMENTING, 50)

            # 3. 执行分镜生成
            shot_sequence = self.shot_segmenter.process(state.domain.parsed_script)

            # 更新状态：拆分完成
            self._update_task_progress(state.input.task_id, TaskStage.SEGMENT_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.SEGMENT_COMPLETE, {
                "shot_count": len(shot_sequence.shots),
                "total_duration": sum(s.duration for s in shot_sequence.shots)
            })

            if not shot_sequence:
                raise Exception("分镜生成返回空结果")

            debug(f"分镜解析完成，镜头数: {len(shot_sequence.shots)}")
            debug(f"总时长: {sum(s.duration for s in shot_sequence.shots):.1f}秒")

            # 统计镜头类型分布
            shot_types = {}
            for shot in shot_sequence.shots:
                shot_types[shot.shot_type.value] = shot_types.get(shot.shot_type.value, 0) + 1
            debug(f"镜头类型分布: {shot_types}")

            # 4. 保存结果
            self.storage.save_obj_result(
                state.input.script_id, state.input.task_id,
                shot_sequence, "shot_segmenter_result.json"
            )

            # 5. 问题检测
            segment_issues = self.shot_segmenter.detect_issues(shot_sequence, state.domain.parsed_script)
            if segment_issues:
                debug(f"分镜过程发现问题: {len(segment_issues)}个")

            # 6. 保存阶段记忆（统一入口）
            self.workflow_memory.after_stage_completion(
                stage="segment_shot",
                result=shot_sequence,
                metadata={
                    "repair_applied": repair_params is not None,
                    "shot_count": len(shot_sequence.shots),
                    "shot_types": shot_types,
                    "issue_count": len(segment_issues) if segment_issues else 0
                }
            )

            # 7. 更新状态
            state.domain.shot_sequence = shot_sequence
            state.execution.current_stage = AgentStage.SEGMENTER
            state.execution.current_node = PipelineNode.SEGMENT_SHOT

            # 8. 清理临时状态
            self.shot_segmenter.clear_repair_params()
            self.shot_segmenter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"分镜解析节点异常: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)

            state.execution.current_node = PipelineNode.SEGMENT_SHOT
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.SEGMENT_SHOT

        return state

    # ======================== 视频分割节点 ========================

    def fragment_for_ai_node(self, state: WorkflowState) -> WorkflowState:
        """
        AI分段节点（增强版）

        功能：将镜头按限制切分为AI可处理的片段，支持修复参数

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        try:
            # 更新状态：开始分段
            self._update_task_progress(state.input.task_id, TaskStage.SPLIT_START, 0)

            # 1. 加载历史上下文（使用 workflow_memory）
            historical_split_stats = self.workflow_memory.get_memory_dict(
                f"stats_split_video", level=MemoryLevel.MEDIUM_TERM
            )
            historical_split_issues = self.workflow_memory.get_memory_list(
                f"issues_split_video", level=MemoryLevel.SHORT_TERM, default=[]
            )
            common_split_patterns = self.workflow_memory.get_memory_list(
                "common_split_patterns", level=MemoryLevel.LONG_TERM, default=[]
            )

            historical_context = {
                "historical_stats": historical_split_stats,
                "historical_issues": historical_split_issues,
                "common_patterns": common_split_patterns
            }

            if historical_context and any(v is not None for v in historical_context.values()):
                self.video_splitter.apply_historical_context(historical_context)

            # 2. 加载修复参数
            repair_params = state.domain.repair_params.get(PipelineNode.SPLIT_VIDEO, None)

            if repair_params:
                self.video_splitter.apply_repair_params(PipelineNode.SPLIT_VIDEO, repair_params)

                info(f"视频分割节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")
            else:
                debug("视频分割节点执行（无修复参数）")

            # 更新状态：分段中
            self._update_task_progress(state.input.task_id, TaskStage.SPLITTING, 50)

            # 3. 执行视频分割
            fragment_sequence = self.video_splitter.process(
                state.domain.shot_sequence,
                parsed_script=state.domain.parsed_script,
            )

            # 自动调整超长片段（软限制）
            max_duration = state.config.max_fragment_duration
            for fragment in fragment_sequence.fragments:
                if fragment.duration > max_duration:
                    fragment.duration = max_duration
                    info("已自动调整超长片段时长")

            # 更新状态：分段完成
            self._update_task_progress(state.input.task_id, TaskStage.SPLIT_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.SPLIT_COMPLETE, {
                "fragment_count": len(fragment_sequence.fragments),
                "total_duration": sum(f.duration for f in fragment_sequence.fragments)
            })

            if not fragment_sequence:
                raise Exception("视频分割返回空结果")

            debug(f"视频分段完成，视频片段数: {len(fragment_sequence.fragments)}")
            total_duration = sum(f.duration for f in fragment_sequence.fragments)
            debug(f"总时长: {total_duration:.1f}秒")

            # 统计片段时长分布
            durations = [f.duration for f in fragment_sequence.fragments]
            debug(f"时长分布: 最小={min(durations):.1f}s, 最大={max(durations):.1f}s, 平均={sum(durations) / len(durations):.1f}s")

            # 4. 保存结果
            self.storage.save_obj_result(
                state.input.script_id, state.input.task_id,
                fragment_sequence, "video_splitter_result.json"
            )

            # 5. 问题检测
            split_issues = self.video_splitter.detect_issues(fragment_sequence, state.domain.shot_sequence)
            if split_issues:
                debug(f"分割过程发现问题: {len(split_issues)}个")

            # 6. 保存阶段记忆（统一入口）
            self.workflow_memory.after_stage_completion(
                stage="split_video",
                result=fragment_sequence,
                metadata={
                    "repair_applied": repair_params is not None,
                    "fragment_count": len(fragment_sequence.fragments),
                    "issue_count": len(split_issues) if split_issues else 0
                }
            )

            # 7. 更新状态
            state.domain.fragment_sequence = fragment_sequence
            state.execution.current_stage = AgentStage.SPLITTER
            state.execution.current_node = PipelineNode.SPLIT_VIDEO

            # 8. 清理临时状态
            self.video_splitter.clear_repair_params()
            self.video_splitter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"视频分段异常: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)

            state.execution.current_node = PipelineNode.SPLIT_VIDEO
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.SPLIT_VIDEO

        return state

    # ======================== 提示词转换节点 ========================

    def generate_prompts_node(self, state: WorkflowState) -> WorkflowState:
        """
        Prompt生成节点（增强版）

        功能：为每个片段生成AI视频生成提示词，支持修复参数

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        try:
            # 更新状态：开始转换
            self._update_task_progress(state.input.task_id, TaskStage.CONVERT_START, 0)

            # 1. 加载历史上下文（使用 workflow_memory）
            historical_convert_stats = self.workflow_memory.get_memory_dict(
                f"stats_convert_prompt", level=MemoryLevel.MEDIUM_TERM
            )
            historical_convert_issues = self.workflow_memory.get_memory_list(
                f"issues_convert_prompt", level=MemoryLevel.SHORT_TERM, default=[]
            )
            successful_prompts = self.workflow_memory.get_memory_list(
                "successful_prompt_patterns", level=MemoryLevel.LONG_TERM, default=[]
            )

            historical_context = {
                "historical_stats": historical_convert_stats,
                "historical_issues": historical_convert_issues,
                "successful_patterns": successful_prompts
            }

            if historical_context and any(v is not None for v in historical_context.values()):
                self.prompt_converter.apply_historical_context(historical_context)

            # 2. 加载修复参数
            repair_params = state.domain.repair_params.get(PipelineNode.CONVERT_PROMPT, None)

            if repair_params:
                self.prompt_converter.apply_repair_params(PipelineNode.CONVERT_PROMPT, repair_params)

                info(f"提示词转换节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")
            else:
                debug("提示词转换节点执行（无修复参数）")

            # 更新状态：转换中
            self._update_task_progress(state.input.task_id, TaskStage.CONVERTING, 50)

            # 3. 执行提示词转换
            instructions = self.prompt_converter.process(
                state.domain.fragment_sequence,
                parsed_script=state.domain.parsed_script,
            )

            # 更新状态：转换完成
            self._update_task_progress(state.input.task_id, TaskStage.CONVERT_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.CONVERT_COMPLETE, {
                "prompt_count": len(instructions.fragments),
                "audio_prompt_count": sum(1 for f in instructions.fragments if f.audio)
            })

            if not instructions:
                raise Exception("提示词转换返回空结果")

            debug(f"片段指令转换完成，指令片段数: {len(instructions.fragments)}")

            # 4. 使用知识库增强提示词
            if self.knowledge_manager and self.knowledge_manager.is_available():
                for fragment in instructions.fragments:
                    enhanced_prompt = self.knowledge_manager.enhance_prompt(
                        fragment.prompt,
                        enhancement_mode="append"
                    )
                    if enhanced_prompt != fragment.prompt:
                        fragment.prompt = enhanced_prompt
                        debug(f"已使用知识库增强提示词: {fragment.fragment_id}")

            # 统计提示词信息
            prompt_lengths = [len(f.prompt) for f in instructions.fragments]
            debug(f"提示词长度统计: 平均={sum(prompt_lengths) / len(prompt_lengths):.0f}, "
                  f"最小={min(prompt_lengths)}, 最大={max(prompt_lengths)}")

            # 统计音频提示词
            audio_count = sum(1 for f in instructions.fragments if f.audio)
            debug(f"音频提示词: {audio_count}/{len(instructions.fragments)}个片段")

            # 统计风格分布
            styles = {}
            for f in instructions.fragments:
                if f.style:
                    styles[f.style] = styles.get(f.style, 0) + 1
            if styles:
                debug(f"风格分布: {styles}")

            # 5. 保存结果
            self.storage.save_obj_result(
                state.input.script_id, state.input.task_id,
                instructions, "prompt_converter_result.json"
            )

            # 6. 问题检测
            convert_issues = self.prompt_converter.detect_issues(instructions, state.domain.fragment_sequence)
            if convert_issues:
                debug(f"转换过程发现问题: {len(convert_issues)}个")

            # 7. 保存阶段记忆（统一入口）
            self.workflow_memory.after_stage_completion(
                stage="convert_prompt",
                result=instructions,
                metadata={
                    "repair_applied": repair_params is not None,
                    "prompt_count": len(instructions.fragments),
                    "audio_prompt_count": audio_count,
                    "issue_count": len(convert_issues) if convert_issues else 0
                }
            )

            # 8. 更新状态
            state.domain.instructions = instructions
            state.execution.current_stage = AgentStage.CONVERTER
            state.execution.current_node = PipelineNode.CONVERT_PROMPT

            # 9. 清理临时状态
            self.prompt_converter.clear_repair_params()
            self.prompt_converter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"片段指令转换异常: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)

            state.execution.current_node = PipelineNode.CONVERT_PROMPT
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.CONVERT_PROMPT

        return state

    # ======================== 质量审查节点 ========================

    def quality_audit_node(self, state: WorkflowState) -> WorkflowState:
        """
        质量审查节点（增强版）

        功能：合并基本规则审查和LLM深度审查，输出详细的审查报告

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        # 检查是否短时间内重复执行（使用 workflow_memory 获取历史）
        if state.domain.audit_executed and state.domain.audit_timestamp:
            last_time = datetime.fromisoformat(state.domain.audit_timestamp)
            current_time = datetime.now()
            time_diff = (current_time - last_time).total_seconds()

            # 只有在真正重复时才跳过（检查是否有新的修复参数需要应用）
            has_new_repair = state.domain.repair_params and any(
                p.fix_needed for p in state.domain.repair_params.values()
            ) if state.domain.repair_params else False

            if time_diff < 10 and not has_new_repair:
                info(f"质量审查在 {time_diff:.1f} 秒内重复调用，"
                     f"使用上次结果 (修复参数: {has_new_repair})")
                return state
            elif time_diff < 10:
                info(f"质量审查重新执行 (有新的修复参数: {list(state.domain.repair_params.keys())})")
                last_result = self.workflow_memory.get_memory_dict(
                    "latest_audit_result", level=MemoryLevel.SHORT_TERM
                )
                if last_result:
                    report_data = last_result.get("report")
                    if report_data:
                        state.domain.audit_report = QualityAuditReport(**report_data)
                        return state

        info(f"进入质量审查节点（增强版），当前阶段={state.execution.current_stage.value}")
        info(f"审查前状态: 片段数={len(state.domain.fragment_sequence.fragments) if state.domain.fragment_sequence else 0}")

        # 更新状态：开始审查
        self._update_task_progress(state.input.task_id, TaskStage.AUDIT_START, 0)

        # 从记忆模块获取各阶段问题（使用 workflow_memory）
        all_stage_issues = {
            PipelineNode.PARSE_SCRIPT: self.workflow_memory.get_memory_list(
                f"issues_parse_script", level=MemoryLevel.SHORT_TERM, default=[]
            ),
            PipelineNode.SEGMENT_SHOT: self.workflow_memory.get_memory_list(
                f"issues_segment_shot", level=MemoryLevel.SHORT_TERM, default=[]
            ),
            PipelineNode.SPLIT_VIDEO: self.workflow_memory.get_memory_list(
                f"issues_split_video", level=MemoryLevel.SHORT_TERM, default=[]
            ),
            PipelineNode.CONVERT_PROMPT: self.workflow_memory.get_memory_list(
                f"issues_convert_prompt", level=MemoryLevel.SHORT_TERM, default=[]
            ),
        }

        # 回忆历史审查经验（使用 workflow_memory）
        historical_audit_results = self.workflow_memory.get_memory_list(
            "audit_results_history", level=MemoryLevel.MEDIUM_TERM, default=[]
        )
        successful_repair_patterns = self.workflow_memory.get_memory_list(
            "repair_success_patterns", level=MemoryLevel.LONG_TERM, default=[]
        )

        # 构建历史上下文
        historical_context = {
            "historical_audit_results": historical_audit_results,
            "successful_repair_patterns": successful_repair_patterns
        }

        # 更新状态：审查中
        self._update_task_progress(state.input.task_id, TaskStage.AUDITING, 20)

        try:
            # 执行质量审查
            result = self.quality_auditor.qa_process(
                state.domain.instructions,
                all_stage_issues,
                historical_context
            )

            debug(f"质量审查完成:")
            debug(f"  - 审查状态: {result.status.value}")
            debug(f"  - 质量分数: {result.score}%")
            debug(f"  - 总问题数: {len(result.violations)}")
            debug(f"  - 检查项数: {len(result.checks)}")

            # 更新状态：审查完成
            self._update_task_progress(state.input.task_id, TaskStage.AUDIT_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.AUDIT_COMPLETE, {
                "status": result.status.value,
                "score": result.score,
                "violations_count": len(result.violations)
            })

            # 更新执行标志
            state.domain.audit_executed = True
            state.domain.repair_params = result.repair_params
            state.domain.audit_timestamp = datetime.now().isoformat()

            # 存储最新审查结果（使用 workflow_memory）
            self.workflow_memory.store_short_term_memory(
                stage_key="latest_audit_result",
                result={
                    "timestamp": datetime.now().isoformat(),
                    "status": result.status.value,
                    "score": result.score,
                    "violations": [v.dict() for v in result.violations],
                    "repair_params": {k: v.model_dump() for k, v in result.repair_params.items()} if result.repair_params else None,
                    "report": result.model_dump()
                },
                stats={"score": result.score, "status": result.status.value},
                timestamp=datetime.now().isoformat()
            )

            info(f"审计结果汇总: 状态={result.status.value}, 分数={result.score}%, 问题统计={result.stats}")

            # 审查通过后，保存成功的提示词
            if result.status == AuditStatus.PASSED and state.domain.instructions:
                for fragment in state.domain.instructions.fragments:
                    self.knowledge_manager.save_successful_prompt(
                        fragment_id=fragment.fragment_id,
                        prompt_text=fragment.prompt,
                        quality_score=result.score,
                        script_id=state.input.script_id,
                        additional_metadata={
                            "scene": getattr(fragment, 'scene', ''),
                            "style": getattr(fragment, 'style', ''),
                            "duration": getattr(fragment, 'duration', 0),
                            "task_id": state.input.task_id,
                            "script_id": state.input.script_id
                        }
                    )
                info(f"质量审查通过，已保存 {len(state.domain.instructions.fragments)} 个成功提示词")

            # 记录错误来源
            if result.status in [AuditStatus.FAILED, AuditStatus.CRITICAL_ISSUES]:
                state.errors.error_source = PipelineNode.AUDIT_QUALITY
                critical_issues = [
                    v for v in result.violations
                    if v.severity in [SeverityLevel.CRITICAL, SeverityLevel.ERROR]
                ]
                if critical_issues:
                    state.errors.error = f"质量审查发现严重问题: {len(critical_issues)}个"
                    state.errors.error_messages.extend([
                        f"[{v.severity.value}] {v.description}"
                        for v in critical_issues[:3]
                    ])

            # 调用各阶段修复器
            if result.repair_params:
                for node, params in result.repair_params.items():
                    if not params.fix_needed:
                        continue

                    debug(f"开始修复阶段 {node.value}，问题类型: {params.issue_types}")

                    try:
                        if node == PipelineNode.PARSE_SCRIPT:
                            state.domain.parsed_script = self.script_parser.repair_result(
                                state.domain.parsed_script,
                                params.issues if hasattr(params, 'issues') else [],
                                state.input.raw_script
                            )
                            info(f"剧本解析修复完成")

                        elif node == PipelineNode.SEGMENT_SHOT:
                            state.domain.shot_sequence = self.shot_segmenter.repair_result(
                                state.domain.shot_sequence,
                                params.issues if hasattr(params, 'issues') else [],
                                state.domain.parsed_script
                            )
                            info(f"分镜生成修复完成")

                        elif node == PipelineNode.SPLIT_VIDEO:
                            state.domain.fragment_sequence = self.video_splitter.repair_result(
                                state.domain.fragment_sequence,
                                params.issues if hasattr(params, 'issues') else [],
                                state.domain.shot_sequence
                            )
                            info(f"视频分割修复完成")

                        elif node == PipelineNode.CONVERT_PROMPT:
                            state.domain.instructions = self.prompt_converter.repair_result(
                                state.domain.instructions,
                                params.issues if hasattr(params, 'issues') else [],
                                state.domain.fragment_sequence
                            )
                            debug(f"提示词转换修复完成")

                    except Exception as e:
                        error(f"修复阶段 {node.value} 时出错: {str(e)}")
                        print_log_exception()
                        state.errors.error_messages.append(f"修复{node.value}失败: {str(e)}")

            # 保存审查结果
            self.storage.save_obj_result(
                state.input.script_id, state.input.task_id,
                result, "quality_auditor_result.json"
            )

            if hasattr(result, 'detailed_analysis'):
                self.storage.save_obj_result(
                    state.input.script_id, state.input.task_id,
                    result.detailed_analysis, "quality_auditor_detailed_analysis.json"
                )

            state.domain.audit_report = result
            state.execution.current_stage = AgentStage.AUDITOR
            state.execution.current_node = PipelineNode.AUDIT_QUALITY

            # 根据审查状态决定后续流程
            if result.status == AuditStatus.PASSED:
                info("质量审查通过，继续执行后续流程")
            elif result.status == AuditStatus.MINOR_ISSUES:
                info("质量审查发现轻微问题，可以继续但建议关注")
            elif result.status in [AuditStatus.MODERATE_ISSUES, AuditStatus.MAJOR_ISSUES]:
                warning("质量审查发现中等问题，需要修复")
            elif result.status in [AuditStatus.CRITICAL_ISSUES, AuditStatus.FAILED]:
                error("质量审查发现严重问题，需要人工干预")
                state.execution.needs_human_review = True
                state.errors.error_source = PipelineNode.AUDIT_QUALITY

        except Exception as e:
            print_log_exception()
            error_msg = f"质量审查异常: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)

            state.execution.current_node = PipelineNode.AUDIT_QUALITY
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.AUDIT_QUALITY

            state.domain.audit_report = self._create_fallback_audit_report(state)

        return state

    # ======================== 连续性检查节点 ========================

    def continuity_check_node(self, state: WorkflowState) -> WorkflowState:
        """
        连续性守护节点

        职责：
        1. 检查所有阶段的连续性（视觉、角色、场景、动作）
        2. 识别连续性问题的来源阶段
        3. 生成修复方案并触发重试

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        # 更新状态：开始检查
        self._update_task_progress(state.input.task_id, TaskStage.CONTINUITY_START, 0)

        try:
            # 初始化或获取重试计数
            if not hasattr(state.domain, 'continuity_retry_count'):
                state.domain.continuity_retry_count = 0
            if not hasattr(state.domain, 'max_continuity_retries'):
                state.domain.max_continuity_retries = 3

            # 回忆历史连续性问题（使用 workflow_memory）
            historical_continuity_issues = self.workflow_memory.get_memory_list(
                "continuity_issues_history", level=MemoryLevel.MEDIUM_TERM, default=[]
            )
            successful_continuity_fixes = self.workflow_memory.get_memory_list(
                "successful_continuity_fixes", level=MemoryLevel.LONG_TERM, default=[]
            )

            # 构建历史上下文
            historical_context = {
                "historical_issues": historical_continuity_issues,
                "successful_fixes": successful_continuity_fixes
            }

            # 1. 收集所有阶段的输出
            continuity_context = {
                "parsed_script": state.domain.parsed_script,
                "shot_sequence": state.domain.shot_sequence,
                "fragment_sequence": state.domain.fragment_sequence,
                "instructions": state.domain.instructions,
                "historical_context": historical_context
            }

            # 更新状态：检查中
            self._update_task_progress(state.input.task_id, TaskStage.CONTINUITY_CHECKING, 50)

            # 2. 执行连续性检查
            check_result = self._check_continuity(continuity_context)

            # 更新状态：检查完成
            self._update_task_progress(state.input.task_id, TaskStage.CONTINUITY_COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.CONTINUITY_COMPLETE, {
                "passed": check_result.passed,
                "total_issues": check_result.total_issues,
                "retry_count": state.domain.continuity_retry_count
            })

            # 3. 如果没有问题，通过检查
            if check_result.passed and check_result.total_issues == 0:
                debug("连续性检查通过")
                state.domain.continuity_passed = True
                state.execution.current_stage = AgentStage.CONTINUITY
                state.domain.continuity_retry_count = 0
                return state

            # 4. 获取问题列表
            continuity_issues = check_result.issues
            state.domain.continuity_issues = continuity_issues

            # 使用知识库检索历史解决方案
            if self.knowledge_manager and self.knowledge_manager.is_script_kb_available():
                enhanced_issues = []
                for issue in continuity_issues:
                    issue_desc = getattr(issue, 'description', str(issue))
                    similar_scenes = self.knowledge_manager.search_similar_scene(issue_desc,script_id=state.input.script_id, top_k=2)
                    if similar_scenes:
                        if hasattr(issue, 'historical_solutions'):
                            issue.historical_solutions = similar_scenes
                    enhanced_issues.append(issue)
                state.domain.continuity_issues = enhanced_issues
                info("已使用知识库检索历史连续性解决方案")

            # 5. 分析问题来源
            issues_by_stage = self._analyze_continuity_issues(continuity_issues, continuity_context)

            warning(f"发现 {len(continuity_issues)} 个连续性问题，分布在: {[s.name for s in issues_by_stage.keys()]}, "
                    f"重试次数: {state.domain.continuity_retry_count}/{state.domain.max_continuity_retries}")

            # 6. 检查重试限制
            if state.domain.continuity_retry_count < state.domain.max_continuity_retries:
                # 7. 生成修复参数并触发重试
                for stage, issues in issues_by_stage.items():
                    repair_params = self._create_continuity_repair_params(issues, stage)
                    state.domain.repair_params[stage] = repair_params
                    info(f"为阶段 {stage.value} 生成连续性修复参数，共{len(issues)}个问题")

                # 标记需要重试
                state.domain.continuity_retry_count += 1
                state.domain.needs_continuity_repair = True
                state.errors.error_source = PipelineNode.CONTINUITY_CHECK

                info(f"连续性修复重试 ({state.domain.continuity_retry_count}/{state.domain.max_continuity_retries})")

                return self._route_to_fix_stage(state, issues_by_stage)
            else:
                error(f"连续性修复重试次数超限: {state.domain.continuity_retry_count}/{state.domain.max_continuity_retries}")
                state.execution.needs_human_review = True
                state.errors.error_source = PipelineNode.CONTINUITY_GUARDIAN
                state.execution.current_stage = AgentStage.CONTINUITY

        except Exception as e:
            error(f"连续性守护节点异常: {e}")
            print_log_exception()
            error_msg = f"连续性检查失败: {str(e)}"
            error(error_msg)
            state.errors.error = error_msg
            state.errors.error_messages.append(error_msg)

            state.execution.current_node = PipelineNode.CONTINUITY_CHECK
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.errors.error_source = PipelineNode.CONTINUITY_CHECK

            state.domain.audit_report = self._create_fallback_audit_report(state)

        return state

    # ======================== 错误处理节点 ========================

    def error_handler_node(self, graph_state: WorkflowState) -> WorkflowState:
        """
        错误处理节点 - 处理工作流中的错误和异常

        Args:
            graph_state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        error_time = time.time()

        if not graph_state.errors.error_messages:
            graph_state.errors.error_messages = ["未知错误：进入错误处理节点但没有错误信息"]
            warning("错误处理节点没有接收到错误信息")

        recent_errors = graph_state.errors.error_messages[-5:] if len(graph_state.errors.error_messages) > 5 else graph_state.errors.error_messages
        error_analysis = self._analyze_errors(recent_errors)

        info(f"进入错误处理节点，错误分析: {error_analysis}")

        recovery_action = self._determine_recovery_action(error_analysis, graph_state)

        error_details = {
            "timestamp": error_time,
            "recent_errors": recent_errors,
            "error_analysis": error_analysis,
            "recovery_action": recovery_action,
            "current_node": graph_state.execution.current_node,
            "global_loops": graph_state.execution.global_current_loops,
            "retry_count": getattr(graph_state, 'total_retries', 0),
        }

        graph_state.errors.error_handling_history.append(error_details)

        if len(graph_state.errors.error_handling_history) > 10:
            graph_state.errors.error_handling_history = graph_state.errors.error_handling_history[-10:]

        self._execute_recovery_action(recovery_action, graph_state, error_analysis)

        graph_state.execution.current_node = PipelineNode.ERROR_HANDLER
        graph_state.execution.current_stage = AgentStage.ERROR_HANDLER

        processing_time = time.time() - error_time
        info(f"错误处理完成，采取行动: {recovery_action}，耗时: {processing_time:.2f}秒")

        return graph_state

    # ======================== 结果生成节点 ========================

    def generate_output_node(self, state: WorkflowState) -> WorkflowState:
        """
        结果生成节点

        功能：组装最终输出结果

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        debug("进入生成输出节点")
        self._update_task_progress(state.input.task_id, TaskStage.OUTPUT_START, 0)

        try:
            output_data = {
                "task_id": state.input.task_id,
                "script_analysis": state.domain.parsed_script.model_dump() if state.domain.parsed_script else None,
                "shot_sequence": state.domain.shot_sequence.model_dump() if state.domain.shot_sequence else None,
                "fragment_sequence": state.domain.fragment_sequence.model_dump() if state.domain.fragment_sequence else None,
                "instructions": state.domain.instructions.model_dump() if state.domain.instructions else None,
                "audit_report": state.domain.audit_report.model_dump() if state.domain.audit_report else None,
                "continuity_issues": state.domain.continuity_issues,
                "created_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "status": "completed"
            }

            state.output.final_output = output_data
            state.execution.current_stage = AgentStage.END
            state.execution.current_node = PipelineNode.GENERATE_OUTPUT

            self._update_task_progress(state.input.task_id, TaskStage.OUTPUT_GENERATING, 50)

            self.output_writer.save_all_reports(state)

            self._update_task_progress(state.input.task_id, TaskStage.COMPLETE, 100)
            self._complete_stage(state.input.task_id, TaskStage.COMPLETE, {"status": "completed"})

            # 任务完成，清理该任务的记忆
            self._memory.clear_script(state.input.script_id)

            # 清理所有智能体状态
            self.script_parser.clear_all_state()
            self.shot_segmenter.clear_all_state()
            self.video_splitter.clear_all_state()
            self.prompt_converter.clear_all_state()

            state.domain.continuity_issues = []

            info(f"生成输出完成，数据大小: {len(str(output_data))} 字符，阶段更新为 END")

        except Exception as e:
            error(f"生成输出时出错: {str(e)}")
            print_log_exception()
            state.errors.error_messages.append(f"生成输出失败: {str(e)}")
            state.execution.current_stage = AgentStage.ERROR_HANDLER
            state.execution.current_node = PipelineNode.GENERATE_OUTPUT
            state.errors.error_source = PipelineNode.GENERATE_OUTPUT

        return state

    # ======================== 人工干预节点 ========================

    def human_intervention_node(self, state: WorkflowState) -> WorkflowState:
        """
        人工干预节点

        功能：暂停流程等待人工输入

        Args:
            state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        state.execution.current_stage = AgentStage.HUMAN_INTERVENTION
        state.execution.current_node = PipelineNode.HUMAN_INTERVENTION

        if state.execution.needs_human_review:
            info(f"进入人工干预节点，任务ID: {state.input.task_id}")

            # 检查是否设置了自动继续标志（用于自动化测试）
            auto_continue = getattr(state.config, 'auto_continue_on_human_intervention', False)

            if auto_continue:
                # 自动继续模式
                warning("人工干预自动继续模式已启用，跳过等待")
                state.execution.human_feedback = {
                    "decision": "CONTINUE",
                    "timeout": False,
                    "auto_decision": True,
                    "reason": "auto_continue_enabled",
                    "timestamp": time.time(),
                    "raw_input": "AUTO_CONTINUE",
                }
            else:
                # 执行人工干预，使用已有的 HumanIntervention 类
                try:
                    # 调用 HumanIntervention 实例，它会显示控制台提示并等待输入
                    state = self.human_intervention(state)
                except Exception as e:
                    error(f"人工干预执行失败: {e}")
                    # 发生异常时使用默认继续
                    state.execution.human_feedback = {
                        "decision": "CONTINUE",
                        "timeout": True,
                        "auto_decision": True,
                        "reason": f"error: {str(e)}",
                        "timestamp": time.time(),
                        "raw_input": "AUTO_CONTINUE",
                    }

            state.execution.needs_human_review = False
            decision = state.execution.human_feedback.get("decision", "CONTINUE")
            info(f"人工干预完成，决策: {decision}")
        else:
            warning("进入人工干预节点但不需要人工审查，使用默认继续")
            state.execution.human_feedback = {
                "decision": "CONTINUE",
                "timeout": False,
                "auto_decision": True,
                "timestamp": time.time(),
                "raw_input": "AUTO_CONTINUE",
            }

        return state

    # ======================== 循环检查节点 ========================

    def loop_check_node(self, graph_state: WorkflowState) -> WorkflowState:
        """
        循环检查节点 - 检查节点循环次数并记录状态

        Args:
            graph_state: 工作流状态

        Returns:
            更新后的工作流状态
        """
        graph_state.execution.global_current_loops += 1

        current_node = graph_state.execution.current_node or None

        current_node_loops = graph_state.execution.node_current_loops.get(current_node, 0) + 1
        graph_state.execution.node_current_loops[current_node] = current_node_loops

        node_max_loops = graph_state.execution.node_max_loops.get(current_node, 3)

        info(f"节点循环检查: 节点={current_node}, "
             f"节点循环={current_node_loops}/{node_max_loops}, "
             f"全局循环={graph_state.execution.global_current_loops}/{graph_state.execution.global_max_loops}")

        if current_node_loops > node_max_loops:
            graph_state.execution.node_loop_exceeded[current_node] = True
            error(f"节点 '{current_node}' 循环次数超过限制: {current_node_loops}/{node_max_loops}")

            graph_state.errors.error_messages.append(
                f"节点 '{current_node}' 循环次数超过限制 ({current_node_loops}/{node_max_loops})"
            )

        if graph_state.execution.global_current_loops > graph_state.execution.global_max_loops:
            graph_state.execution.global_loop_exceeded = True
            error(f"全局循环次数超过限制: {graph_state.execution.global_current_loops}/{graph_state.execution.global_max_loops}")

            graph_state.errors.error_messages.append(
                f"全局循环次数超过限制 ({graph_state.execution.global_current_loops}/{graph_state.execution.global_max_loops})"
            )

        elif current_node_loops >= node_max_loops * 0.8:
            if not graph_state.execution.loop_warning_issued:
                graph_state.execution.loop_warning_issued = True
                warning(f"节点 '{current_node}' 循环次数接近限制: {current_node_loops}/{node_max_loops}")

        graph_state.execution.node_loop_details.append({
            "node": current_node,
            "node_loop": current_node_loops,
            "global_loop": graph_state.execution.global_current_loops,
            "timestamp": time.time()
        })

        graph_state.execution.last_node = current_node

        return graph_state

    # =============================================== 私有方法 ===============================================

    async def _wait_for_human_with_timeout(self, timeout: int) -> Optional[Dict]:
        """
        等待人工输入（带超时）- 保留作为备用接口

        注意：当前版本中，人工干预通过 HumanIntervention 类的同步方法实现，
        此方法保留仅用于可能的未来扩展。

        Args:
            timeout: 超时时间（秒）

        Returns:
            人工输入结果，超时返回 None
        """
        # 此方法已废弃，实际人工干预由 human_intervention_node 中的
        # self.human_intervention(state) 处理
        debug(f"_wait_for_human_with_timeout 被调用但未实现，timeout={timeout}")
        return None

    def _create_fallback_audit_report(self, state: WorkflowState) -> QualityAuditReport:
        """
        创建回退报告（当审查异常时）

        Args:
            state: 工作流状态

        Returns:
            质量审查报告
        """
        return QualityAuditReport(
            project_info={
                "title": getattr(state.domain.instructions, 'project_info', {}).get("title", "未知项目"),
                "fragment_count": len(state.domain.instructions.fragments) if state.domain.instructions else 0,
                "total_duration": getattr(state.domain.instructions, 'project_info', {}).get("total_duration", 0.0)
            },
            status=AuditStatus.FAILED,
            checks=[],
            violations=[],
            stats={"error": "audit_exception", "message": state.errors.error},
            score=0.0
        )

    def _analyze_errors(self, error_list: List[str]) -> Dict[str, Any]:
        """
        分析错误列表，分类错误类型

        Args:
            error_list: 错误信息列表

        Returns:
            错误分析结果字典
        """
        analysis = {
            "total_errors": len(error_list),
            "error_types": {},
            "most_common_error": "",
            "suggested_action": "unknown",
            "can_recover": True,
        }

        if not error_list:
            return analysis

        error_categories = {
            "network": ["network", "timeout", "connection", "socket", "http", "request"],
            "validation": ["validation", "invalid", "format", "type", "value"],
            "resource": ["memory", "disk", "cpu", "resource", "out of"],
            "configuration": ["configuration", "config", "parameter", "setting"],
            "business": ["业务", "逻辑", "规则", "requirement", "business"],
            "external": ["api", "external", "third", "service", "dependency"],
            "system": ["system", "os", "kernel", "fatal", "critical", "segmentation"],
            "data": ["data", "corrupt", "missing", "empty", "null"],
            "loop": ["循环", "loop", "exceeded", "超过限制"],
            "auth": ["401", "unauthorized", "authentication", "api-key", "apikey", "invalid api"],
            "unknown": ["unknown", "未定义", "不明"],
        }

        type_counts = {category: 0 for category in error_categories.keys()}

        for error_msg in error_list:
            error_msg_lower = error_msg.lower()
            matched = False

            for category, keywords in error_categories.items():
                for keyword in keywords:
                    if keyword in error_msg_lower:
                        type_counts[category] += 1
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                type_counts["unknown"] += 1

        if type_counts:
            most_common = max(type_counts.items(), key=lambda x: x[1])
            analysis["most_common_error"] = most_common[0]
            analysis["error_types"] = {k: v for k, v in type_counts.items() if v > 0}

        if type_counts.get("system", 0) > 0 or type_counts.get("fatal", 0) > 0:
            analysis["suggested_action"] = "abort"
            analysis["can_recover"] = False
        elif type_counts.get("auth", 0) > 0:
            analysis["suggested_action"] = "human_intervention"
            analysis["can_recover"] = False
        elif type_counts.get("loop", 0) > 0:
            analysis["suggested_action"] = "human_intervention"
            analysis["can_recover"] = False
        elif type_counts.get("resource", 0) > 0:
            analysis["suggested_action"] = "retry_with_delay"
        elif type_counts.get("network", 0) > 0:
            analysis["suggested_action"] = "retry"
        elif type_counts.get("validation", 0) > 0 or type_counts.get("data", 0) > 0:
            analysis["suggested_action"] = "repair"
        else:
            analysis["suggested_action"] = "retry"

        return analysis

    def _determine_recovery_action(self, error_analysis: Dict[str, Any],
                                   state: WorkflowState) -> str:
        """
        根据错误分析和当前状态确定恢复行动

        Args:
            error_analysis: 错误分析结果
            state: 当前工作流状态

        Returns:
            恢复行动类型
        """
        if state.execution.workflow_start_time:
            elapsed_time = time.time() - state.execution.workflow_start_time
            if elapsed_time > 1800:
                warning(f"工作流执行超时: {elapsed_time:.1f}秒，超过30分钟限制")
                return "abort"

        if state.execution.global_loop_exceeded:
            return "abort"

        current_node = state.execution.current_node
        if current_node and state.execution.node_loop_exceeded.get(current_node, False):
            return "human_intervention"

        total_retries = len(state.errors.error_handling_history)
        max_allowed_retries = 3

        if total_retries >= max_allowed_retries:
            return "human_intervention"

        suggested_action = error_analysis.get("suggested_action", "retry")

        if suggested_action == "retry":
            recent_retries = sum(1 for h in state.errors.error_handling_history[-3:]
                                 if h.get("recovery_action") == "retry")
            if recent_retries >= 2:
                return "retry_with_delay"
            return "retry"

        elif suggested_action == "repair":
            return "repair_with_adjustment"

        elif suggested_action == "abort":
            return "abort"

        elif suggested_action == "human_intervention":
            return "human_intervention"

        else:
            return "retry_with_delay"

    def _execute_recovery_action(self, action: str, state: WorkflowState,
                                 error_analysis: Dict[str, Any]) -> None:
        """
        执行具体的恢复行动

        Args:
            action: 恢复行动类型
            state: 工作流状态（会被修改）
            error_analysis: 错误分析结果
        """
        info(f"执行恢复行动: {action}")

        if action == "retry":
            state.errors.error_messages = state.errors.error_messages[-3:]
            info("准备重试：清理错误信息，保持原状态")

        elif action == "retry_with_delay":
            state.errors.error_messages = state.errors.error_messages[-3:]

            if not hasattr(state.execution, 'recovery_flags'):
                state.execution.recovery_flags = {}
            state.execution.recovery_flags['need_delay'] = True
            state.execution.recovery_flags['delay_seconds'] = 5

            warning("检测到连续错误，将在重试前延迟5秒")

        elif action == "repair":
            state.errors.error_messages = state.errors.error_messages[-3:]

            if not hasattr(state.execution, 'recovery_flags'):
                state.execution.recovery_flags = {}

            state.execution.recovery_flags['need_repair'] = True
            state.execution.recovery_flags['repair_type'] = error_analysis.get("most_common_error", "general")

            if error_analysis.get("most_common_error") == "validation":
                state.execution.recovery_flags['adjust_validation'] = True
            elif error_analysis.get("most_common_error") == "configuration":
                state.execution.recovery_flags['adjust_config'] = True

            info(f"准备修复：错误类型={error_analysis.get('most_common_error')}")

        elif action == "repair_with_adjustment":
            state.errors.error_messages = state.errors.error_messages[-3:]

            if not hasattr(state.execution, 'recovery_flags'):
                state.execution.recovery_flags = {}

            state.execution.recovery_flags['need_repair'] = True
            state.execution.recovery_flags['need_adjustment'] = True

            common_error = error_analysis.get("most_common_error", "")
            if common_error == "network":
                state.execution.recovery_flags['adjust_timeout'] = True
                state.execution.recovery_flags['timeout_multiplier'] = 1.5
            elif common_error == "resource":
                state.execution.recovery_flags['reduce_load'] = True
                state.execution.recovery_flags['batch_size'] = 0.5

            warning(f"准备修复并调整参数：{common_error}")

        elif action == "human_intervention":
            state.execution.needs_human_review = True

            if not hasattr(state.execution, 'human_intervention_info'):
                state.execution.human_intervention_info = {}

            state.execution.human_intervention_info['reason'] = "自动恢复失败，需要人工决策"
            state.execution.human_intervention_info['error_summary'] = error_analysis
            state.execution.human_intervention_info['suggested_actions'] = [
                "retry_with_adjusted_params",
                "skip_current_stage",
                "abort_process"
            ]

            warning("错误需要人工干预：自动恢复失败")

        elif action == "abort":
            state.errors.error_messages.append("流程被中止：无法恢复的错误")

            if not hasattr(state.execution, 'recovery_flags'):
                state.execution.recovery_flags = {}
            state.execution.recovery_flags['should_abort'] = True

            error("流程中止：无法恢复的错误")

        else:
            warning(f"未知恢复行动: {action}，使用默认重试")
            state.errors.error_messages = state.errors.error_messages[-3:]

    # ======================== 连续性节点私有方法 ========================

    def _check_continuity(self, context: Dict[str, Any]) -> ContinuityCheckResult:
        """
        执行连续性检查

        Args:
            context: 包含各阶段输出的上下文

        Returns:
            ContinuityCheckResult: 连续性检查结果对象
        """
        info("开始执行连续性检查...")

        result = self.checker.check_all_continuity(context)

        summary = result.get_summary()
        info(f"连续性检查完成: 通过={summary['passed']}, "
             f"问题总数={summary['total_issues']}, "
             f"严重={summary['critical']}, "
             f"主要={summary['major']}, "
             f"中度={summary['moderate']}, "
             f"轻微={summary['minor']}")

        for issue in result.issues:
            warning(f"连续性问题 [{issue.severity.value}]: {issue.type.value} - {issue.description}")
            if issue.suggestion:
                debug(f"  修复建议: {issue.suggestion}")

        return result

    def _analyze_continuity_issues(self, issues: List[ContinuityIssue],
                                   context: Dict) -> Dict[PipelineNode, List[ContinuityIssue]]:
        """
        分析连续性问题的来源阶段

        Args:
            issues: ContinuityIssue 列表
            context: 上下文信息

        Returns:
            按阶段分组的问题字典
        """
        issues_by_stage = {
            PipelineNode.PARSE_SCRIPT: [],
            PipelineNode.SEGMENT_SHOT: [],
            PipelineNode.SPLIT_VIDEO: [],
            PipelineNode.CONVERT_PROMPT: [],
        }

        for issue in issues:
            if issue.source_stage:
                try:
                    stage = PipelineNode(issue.source_stage)
                    if stage in issues_by_stage:
                        issues_by_stage[stage].append(issue)
                        continue
                except ValueError:
                    pass

            source = self._infer_issue_source(issue.type)
            issues_by_stage[source].append(issue)

        return {k: v for k, v in issues_by_stage.items() if v}

    def _infer_issue_source(self, issue_type: ContinuityIssueType) -> PipelineNode:
        """
        根据问题类型推断来源阶段

        Args:
            issue_type: 问题类型

        Returns:
            来源阶段
        """
        source_mapping = {
            ContinuityIssueType.CHARACTER_MISSING: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.SCENE_JUMP: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.SCENE_TOO_FREQUENT: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.ACTION_BREAK: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.STYLE_INCONSISTENT: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.STYLE_SUDDEN_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.TIME_GAP: PipelineNode.SPLIT_VIDEO,
            ContinuityIssueType.TIME_OVERLAP: PipelineNode.SPLIT_VIDEO,
            ContinuityIssueType.PROP_CHANGE: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.PROP_DISAPPEAR: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.PROP_APPEAR: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.LIGHTING_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.COLOR_INCONSISTENT: PipelineNode.CONVERT_PROMPT,
        }
        return source_mapping.get(issue_type, PipelineNode.CONVERT_PROMPT)

    def _create_continuity_repair_params(self, issues: List[ContinuityIssue],
                                         stage: PipelineNode) -> QualityRepairParams:
        """
        创建连续性修复参数

        Args:
            issues: 连续性问题列表
            stage: 目标阶段

        Returns:
            修复参数
        """
        return self.generator.generate_repair_params(issues, stage)

    def _route_to_fix_stage(self, state: WorkflowState,
                            issues_by_stage: Dict[PipelineNode, List[ContinuityIssue]]) -> WorkflowState:
        """
        路由到需要修复的阶段

        Args:
            state: 工作流状态
            issues_by_stage: 按阶段分组的问题

        Returns:
            更新后的工作流状态
        """
        stage_priority = [
            PipelineNode.PARSE_SCRIPT,
            PipelineNode.SEGMENT_SHOT,
            PipelineNode.SPLIT_VIDEO,
            PipelineNode.CONVERT_PROMPT,
        ]

        for stage in stage_priority:
            if stage in issues_by_stage:
                info(f"路由到阶段 {stage.value} 进行连续性修复")
                state.execution.current_node = stage

                stage_mapping = {
                    PipelineNode.PARSE_SCRIPT: AgentStage.PARSER,
                    PipelineNode.SEGMENT_SHOT: AgentStage.SEGMENTER,
                    PipelineNode.SPLIT_VIDEO: AgentStage.SPLITTER,
                    PipelineNode.CONVERT_PROMPT: AgentStage.CONVERTER,
                }
                state.execution.current_stage = stage_mapping.get(stage, AgentStage.CONVERTER)
                return state

        state.execution.current_node = PipelineNode.CONVERT_PROMPT
        state.execution.current_stage = AgentStage.CONVERTER
        return state

    # ============================= 节点任务状态管理 =============================

    def _update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 任务状态
        """
        try:
            if self.task_manager:
                self.task_manager.update_task_status(task_id, status)
        except Exception as e:
            warning(f"更新任务状态失败: {e}")

    def _update_task_progress(self, task_id: str, stage: TaskStage,
                              progress: float = None, details: Dict = None) -> None:
        """
        更新任务进度

        Args:
            task_id: 任务ID
            stage: 任务阶段
            progress: 进度百分比
            details: 详细信息
        """
        try:
            if self.task_manager:
                self.task_manager.update_progress(task_id, stage, progress, details)
        except Exception as e:
            warning(f"更新任务进度失败: {e}")
            print_log_exception()

    def _complete_stage(self, task_id: str, stage: TaskStage, result: Dict = None) -> None:
        """
        完成阶段

        Args:
            task_id: 任务ID
            stage: 任务阶段
            result: 阶段结果
        """
        try:
            if self.task_manager:
                self.task_manager.complete_stage(task_id, stage, result)
        except Exception as e:
            warning(f"完成阶段失败: {e}")
            print_log_exception()
