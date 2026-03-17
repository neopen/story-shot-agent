"""
@FileName: llm_quality_auditor.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/27 0:00
"""
from typing import Optional

from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.base_quality_auditor import BaseQualityAuditor
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info, warning


class RuleQualityAuditor(BaseQualityAuditor):
    """基于基本规则的审查器 - MVP版本"""

    def __init__(self, config: Optional[ShotConfig]):
        super().__init__(config)
        # 定义基本规则
        self.rules = [
            {"id": "duration_limit", "name": "片段时长限制", "severity": "error"},
            {"id": "prompt_not_empty", "name": "提示词非空", "severity": "error"},
            {"id": "prompt_length", "name": "提示词长度", "severity": "warning"},
            {"id": "fragment_count", "name": "片段数量", "severity": "info"},
            {"id": "model_supported", "name": "模型支持", "severity": "warning"}
        ]
        self.last_audit_result = None
        self.audit_count = 0

    def audit(self, instructions: AIVideoInstructions) -> QualityAuditReport:
        """执行基本规则审查"""
        info(f"开始质量审查，片段数: {len(instructions.fragments)}")

        # 如果短时间内重复调用，返回缓存结果
        if self._should_use_cached_result():
            warning(f"使用缓存的审查结果，避免重复审查")
            return self.last_audit_result

        # 初始化报告
        report = QualityAuditReport(
            project_info={
                "title": instructions.project_info.get("title", "未命名项目"),
                "fragment_count": len(instructions.fragments),
                "total_duration": instructions.project_info.get("total_duration", 0.0)
            }
        )

        # 执行各项检查
        self._check_fragment_duration(instructions, report)
        self._check_prompt_content(instructions, report)
        self._check_prompt_length(instructions, report)
        self._check_fragment_count(instructions, report)
        self._check_model_support(instructions, report)

        # 保存结果
        self.last_audit_result = report
        self.audit_count += 1

        # 后处理
        return self.post_process(report)

    def _should_use_cached_result(self) -> bool:
        """检查是否应该使用缓存结果"""
        # 例如：如果1秒内重复调用，使用缓存
        return False  # 根据实际需求实现

    def _check_fragment_duration(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查片段时长是否超过限制"""
        check_name = "片段时长限制检查"

        violations_count = 0
        for fragment in instructions.fragments:
            # 检查是否超过最大时长
            if fragment.duration > self.config.duration_split_threshold:
                self._add_violation(
                    report=report,
                    rule_id="duration_limit",
                    rule_name="片段时长限制",
                    description=f"片段 {fragment.fragment_id} 时长 {fragment.duration}秒 超过 {self.config.duration_split_threshold}秒 限制",
                    severity="error",
                    fragment_id=fragment.fragment_id,
                    suggestion=f"将片段时长调整为 ≤{self.config.duration_split_threshold}秒"
                )
                violations_count += 1

            # 检查是否低于最小时长
            if fragment.duration < self.config.min_fragment_duration:
                self._add_violation(
                    report=report,
                    rule_id="duration_limit",
                    rule_name="片段时长限制",
                    description=f"片段 {fragment.fragment_id} 时长 {fragment.duration}秒 低于 {self.config.min_fragment_duration}秒 最低要求",
                    severity="warning",
                    fragment_id=fragment.fragment_id,
                    suggestion=f"将片段时长调整为 ≥{self.config.min_fragment_duration}秒"
                )
                violations_count += 1

        if violations_count == 0:
            self._add_check(report, check_name, "passed", "所有片段时长符合要求")
        else:
            self._add_check(report, check_name, "failed", f"发现{violations_count}个时长问题")

    def _check_prompt_content(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查提示词内容"""
        check_name = "提示词内容检查"

        empty_count = 0
        for fragment in instructions.fragments:
            if not fragment.prompt or not fragment.prompt.strip():
                self._add_violation(
                    report=report,
                    rule_id="prompt_not_empty",
                    rule_name="提示词非空",
                    description=f"片段 {fragment.fragment_id} 的提示词为空",
                    severity="error",
                    fragment_id=fragment.fragment_id,
                    suggestion="为片段添加描述性的提示词"
                )
                empty_count += 1

        if empty_count == 0:
            self._add_check(report, check_name, "passed", "所有提示词非空")
        else:
            self._add_check(report, check_name, "failed", f"发现{empty_count}个空提示词")

    def _check_prompt_length(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查提示词长度"""
        check_name = "提示词长度检查"

        too_long_count = 0
        too_short_count = 0

        for fragment in instructions.fragments:
            prompt_length = len(fragment.prompt)

            # 检查是否过长
            max_prompt_length = self.config.max_prompt_length * 10
            if prompt_length > max_prompt_length:
                self._add_violation(
                    report=report,
                    rule_id="prompt_length",
                    rule_name="提示词长度",
                    description=f"片段 {fragment.fragment_id} 提示词过长: {prompt_length}字符 (限制长度: {max_prompt_length})",
                    severity="warning",
                    fragment_id=fragment.fragment_id,
                    suggestion=f"将提示词缩短到{max_prompt_length}字符以内"
                )
                too_long_count += 1

            # 检查是否过短
            if prompt_length < self.config.min_prompt_length:
                self._add_violation(
                    report=report,
                    rule_id="prompt_length",
                    rule_name="提示词长度",
                    description=f"片段 {fragment.fragment_id} 提示词过短: {prompt_length}字符 (建议: ≥{self.config.min_prompt_length})",
                    severity="warning",
                    fragment_id=fragment.fragment_id,
                    suggestion="添加更多描述性内容到提示词"
                )
                too_short_count += 1

        if too_long_count == 0 and too_short_count == 0:
            self._add_check(report, check_name, "passed", "所有提示词长度合适")
        else:
            details = []
            if too_long_count > 0:
                details.append(f"{too_long_count}个过长")
            if too_short_count > 0:
                details.append(f"{too_short_count}个过短")
            self._add_check(report, check_name, "needs_review", ", ".join(details))

    def _check_fragment_count(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查片段数量"""
        check_name = "片段数量检查"
        fragment_count = len(instructions.fragments)

        if fragment_count == 0:
            self._add_violation(
                report=report,
                rule_id="fragment_count",
                rule_name="片段数量",
                description="没有找到任何视频片段",
                severity="error"
            )
            self._add_check(report, check_name, "failed", "没有片段")
        else:
            self._add_check(report, check_name, "passed", f"共{fragment_count}个片段")

    def _check_model_support(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查模型支持"""
        check_name = "模型支持检查"

        unsupported_models = []
        for fragment in instructions.fragments:
            if fragment.model not in ["runway_gen2", "sora", "pika"]:  # MVP支持的基础模型
                unsupported_models.append(fragment.model)

        if unsupported_models:
            unique_models = list(set(unsupported_models))
            self._add_violation(
                report=report,
                rule_id="model_supported",
                rule_name="模型支持",
                description=f"不支持的AI模型: {', '.join(unique_models)}",
                severity="warning",
                suggestion="使用支持的模型: runway_gen2, sora, pika"
            )
            self._add_check(report, check_name, "warning", f"发现{len(unique_models)}个不支持的模型")
        else:
            self._add_check(report, check_name, "passed", "所有模型都受支持")
