"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: rule_quality_auditor.py
@Description: 基于基本规则的审查器
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/27 0:00
"""
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from penshot.logger import info, warning
from penshot.neopen.agent.base_models import parse_model_name
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    EXCLUDE_KEYWORDS,
    classify_anchor_domains,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import (
    LIGHTING_FAMILY_MARKERS,
)
from penshot.neopen.agent.prompt_converter.camera_builder import (
    detect_shot_type_from_text,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.base_quality_auditor import BaseQualityAuditor
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport, RuleType, SeverityLevel
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.str_count_utils import only_count_en

# 半截词尾部标记：子句边界截断不应以这些标记结尾（FR-060）
_DANGLING_TAIL_MARKERS = ("的", "和", "与", "或", "及", "、", "，", ",", "(", "（")


class RuleQualityAuditor(BaseQualityAuditor):
    """基于基本规则的审查器 - MVP版本"""

    def __init__(self, config: Optional[ShotConfig]):
        super().__init__(config)
        self.last_audit_result = None
        self.audit_count = 0

    def audit(self, instructions: AIVideoInstructions,
              historical_context: Optional[Dict[str, Any]] = None,
              contract: Optional[Any] = None) -> QualityAuditReport:
        """执行基本规则审查

        Args:
            instructions: AI 视频指令集
            historical_context: 历史上下文（基本规则审查暂不使用）
            contract: 全局一致性契约；用于外观锚点污染检查（FR-060）
        """
        info(f"开始基本规则审查，片段数: {len(instructions.fragments)}")

        if self._should_use_cached_result():
            warning(f"使用缓存的审查结果，避免重复审查")
            return self.last_audit_result

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
        # G 质量门禁（FR-060..FR-064）
        self._check_appearance_anchor_pollution(contract, report)
        self._check_shot_type_prompt_consistency(instructions, report)
        self._check_style_lighting_conflict(instructions, report)
        self._check_asset_usage(instructions, report)

        self.last_audit_result = report
        self.audit_count += 1

        return self.post_process(report)

    def _should_use_cached_result(self) -> bool:
        return False

    def _check_fragment_duration(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查片段时长"""
        check_name = "片段时长限制检查"
        violations_count = 0

        for fragment in instructions.fragments:
            if fragment.duration > self.config.duration_split_threshold:
                self._add_violation(
                    report=report,
                    rule_type=RuleType.FRAGMENT_DURATION_LIMIT,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    issue_value=fragment.duration,
                    standard_value=self.config.duration_split_threshold,
                    severity=SeverityLevel.ERROR,
                    fragment_id=fragment.fragment_id,
                    suggestion=f"将片段时长调整为 ≤{self.config.duration_split_threshold}秒"
                )
                violations_count += 1

            if fragment.duration < self.config.min_fragment_duration:
                self._add_violation(
                    report=report,
                    rule_type=RuleType.FRAGMENT_DURATION_LIMIT,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    issue_value=fragment.duration,
                    standard_value=self.config.min_fragment_duration,
                    severity=SeverityLevel.WARNING,
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
                    rule_type=RuleType.PROMPT_EMPTY,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    severity=SeverityLevel.ERROR,
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
            prompt_length = only_count_en(fragment.prompt)

            if prompt_length > self.config.prompt_length_max_threshold:
                self._add_violation(
                    report=report,
                    rule_type=RuleType.PROMPT_TOO_LONG,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    issue_value=prompt_length,
                    standard_value=self.config.max_prompt_length,
                    severity=SeverityLevel.WARNING,
                    fragment_id=fragment.fragment_id,
                    suggestion=f"将提示词缩短到{self.config.max_prompt_length} 个单词以内"
                )
                too_long_count += 1

            if prompt_length < self.config.prompt_length_min_threshold:
                self._add_violation(
                    report=report,
                    rule_type=RuleType.PROMPT_TOO_SHORT,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    issue_value=prompt_length,
                    standard_value=self.config.min_prompt_length,
                    severity=SeverityLevel.WARNING,
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
                rule_type=RuleType.FRAGMENT_MISSING,
                source_node=PipelineNode.SEGMENT_SHOT,
                severity=SeverityLevel.ERROR,
            )
            self._add_check(report, check_name, "failed", "没有片段")
        else:
            self._add_check(report, check_name, "passed", f"共{fragment_count}个片段")

    def _check_model_support(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查模型支持"""
        check_name = "模型支持检查"
        unsupported_models = []

        for fragment in instructions.fragments:
            if not parse_model_name(fragment.model):
                unsupported_models.append(fragment.model)

        if unsupported_models:
            unique_models = list(set(unsupported_models))
            self._add_violation(
                report=report,
                rule_type=RuleType.MODEL_UNSUPPORTED,
                source_node=PipelineNode.CONVERT_PROMPT,
                issue_value=f"{', '.join(unique_models)}",
                severity=SeverityLevel.WARNING,
                suggestion="使用支持的模型: runway_gen2, sora, pika"
            )
            self._add_check(report, check_name, "warning", f"发现{len(unique_models)}个不支持的模型")
        else:
            self._add_check(report, check_name, "passed", "所有模型都受支持")

    def _check_appearance_anchor_pollution(self, contract: Optional[Any], report: QualityAuditReport) -> None:
        """检查外观锚点污染（FR-060/FR-064）

        命中任一条件即为污染：``clothing`` 含情绪/动作/表演词、锚点以半截词
        收尾、同一锚点混入多个外观语义域。违规带 ``asset_id`` 便于下游定位角色设定图。
        """
        check_name = "外观锚点污染检查"
        if contract is None:
            self._add_check(report, check_name, "skipped", "缺少一致性契约，跳过锚点污染校验")
            return

        characters = getattr(contract, "characters", None) or {}
        pollution_count = 0
        for name, character in characters.items():
            anchors = getattr(character, "appearance_anchors", None) or {}
            asset_id = self._find_character_asset_id(contract, name)
            for field_name, value in anchors.items():
                text = str(value or "").strip()
                if not text:
                    continue

                reasons: List[str] = []
                if field_name == "clothing" and any(
                    keyword in text for keyword in EXCLUDE_KEYWORDS
                ):
                    reasons.append("含情绪/动作/表演词")
                if text.endswith(_DANGLING_TAIL_MARKERS):
                    reasons.append("含半截词")
                domains = classify_anchor_domains(text)
                if len(domains) >= 2:
                    reasons.append(f"混入多个语义域({'+'.join(domains)})")
                if not reasons:
                    continue

                pollution_count += 1
                self._add_violation(
                    report=report,
                    rule_type=RuleType.APPEARANCE_ANCHOR_POLLUTED,
                    issue_value={"character": name, "field": field_name, "value": text},
                    standard_value="外观锚点仅含单一语义域、完整子句、无表演词",
                    severity=SeverityLevel.MAJOR,
                    asset_id=asset_id,
                    suggestion=f"角色{name}的{field_name}锚点需重新提取：{'；'.join(reasons)}"
                )

        if pollution_count == 0:
            self._add_check(report, check_name, "passed", "所有角色外观锚点字段纯净")
        else:
            self._add_check(report, check_name, "failed", f"发现{pollution_count}个锚点污染问题")

    def _check_shot_type_prompt_consistency(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查 camera.shot_type 与最终提示词景别表述是否一致（FR-061/FR-064）"""
        check_name = "景别与提示词一致性检查"
        mismatch_count = 0

        for fragment in instructions.fragments:
            camera = getattr(fragment, "camera", None)
            if camera is None:
                continue
            expected = str(getattr(camera, "shot_type", "") or "").strip()
            if not expected:
                continue

            detected = detect_shot_type_from_text(fragment.prompt)
            if not detected or detected == expected:
                continue

            mismatch_count += 1
            self._add_violation(
                report=report,
                rule_type=RuleType.SHOT_TYPE_PROMPT_MISMATCH,
                source_node=PipelineNode.CONVERT_PROMPT,
                issue_value={"camera_shot_type": expected, "prompt_shot_type": detected},
                standard_value=expected,
                severity=SeverityLevel.MAJOR,
                fragment_id=fragment.fragment_id,
                suggestion=f"统一景别表述：camera.shot_type={expected}，提示词应使用同一景别"
            )

        if mismatch_count == 0:
            self._add_check(report, check_name, "passed", "景别与提示词表述一致")
        else:
            self._add_check(report, check_name, "failed", f"发现{mismatch_count}个景别不一致片段")

    def _check_style_lighting_conflict(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查风格前缀中的互斥打光并存（FR-062/FR-064）

        同一风格字符串只报一次，并以首个使用该风格的片段作为定位点。
        """
        check_name = "风格打光冲突检查"
        seen_styles = set()
        conflict_count = 0

        for fragment in instructions.fragments:
            style = str(getattr(fragment, "style", "") or "").strip()
            if not style or style in seen_styles:
                continue

            lowered = style.lower()
            markers = [
                marker for marker in LIGHTING_FAMILY_MARKERS if marker in lowered
            ]
            if len(markers) < 2:
                continue

            seen_styles.add(style)
            conflict_count += 1
            self._add_violation(
                report=report,
                rule_type=RuleType.STYLE_LIGHTING_CONFLICT,
                source_node=PipelineNode.CONVERT_PROMPT,
                issue_value={"style": style, "markers": markers},
                standard_value="同一风格前缀只保留一个打光族",
                severity=SeverityLevel.WARNING,
                fragment_id=fragment.fragment_id,
                suggestion=f"合并互斥打光表述：{', '.join(markers)}"
            )

        if conflict_count == 0:
            self._add_check(report, check_name, "passed", "风格前缀打光表述互斥")
        else:
            self._add_check(report, check_name, "failed", f"发现{conflict_count}个互斥打光并存")

    def _check_asset_usage(self, instructions: AIVideoInstructions, report: QualityAuditReport) -> None:
        """检查 route_plan 引用的资产是否在 usage.fragments 中声明（FR-063/FR-064）

        读取 M3 已回填的 ``asset_plan`` / ``route_plan``：路由引用集合必须是
        资产使用范围的子集；违规带 ``fragment_id`` 与 ``asset_id``。
        """
        check_name = "资产使用范围一致性检查"
        route_plan = getattr(instructions, "route_plan", None)
        asset_plan = getattr(instructions, "asset_plan", None)
        if not route_plan or not asset_plan:
            self._add_check(report, check_name, "skipped", "缺少路由计划或资产计划，跳过使用范围校验")
            return

        usage_by_asset: Dict[str, set] = {}
        for spec in self._read_field(asset_plan, "assets", None) or []:
            asset_id = str(self._read_field(spec, "asset_id", "") or "")
            if not asset_id:
                continue
            usage = self._read_field(spec, "usage", None)
            used_fragments = self._read_field(usage, "fragments", None) or []
            usage_by_asset[asset_id] = {str(fragment_id) for fragment_id in used_fragments}

        missing_count = 0
        for package in self._read_field(route_plan, "adapted_packages", None) or []:
            fragment_id = str(self._read_field(package, "fragment_id", "") or "")
            for reference in self._read_field(package, "references", None) or []:
                asset_id = str(self._read_field(reference, "asset_id", "") or "")
                if not asset_id or not fragment_id:
                    continue

                used = usage_by_asset.get(asset_id)
                if used is None:
                    reason = "资产未出现在资产计划中"
                elif fragment_id not in used:
                    reason = "片段未出现在 usage.fragments 中"
                else:
                    continue

                missing_count += 1
                self._add_violation(
                    report=report,
                    rule_type=RuleType.ASSET_USAGE_MISSING,
                    source_node=PipelineNode.ROUTE_MODEL,
                    issue_value={"fragment_id": fragment_id, "asset_id": asset_id, "reason": reason},
                    standard_value="route_plan 引用的资产必须声明该片段的使用范围",
                    severity=SeverityLevel.MAJOR,
                    fragment_id=fragment_id,
                    asset_id=asset_id,
                    suggestion=f"回填资产{asset_id}的 usage.fragments，加入片段{fragment_id}"
                )

        if missing_count == 0:
            self._add_check(report, check_name, "passed", "路由引用资产均已声明使用片段")
        else:
            self._add_check(report, check_name, "failed", f"发现{missing_count}个资产使用范围缺失")

    @staticmethod
    def _find_character_asset_id(contract: Any, name: str) -> Optional[str]:
        """按角色名查找角色设定图资产ID（FR-064 定位用）"""
        assets = getattr(contract, "assets", None) or {}
        for asset in assets.values():
            if (
                getattr(asset, "asset_type", "") == "character_sheet"
                and getattr(asset, "owner_name", "") == name
            ):
                return getattr(asset, "asset_id", None)
        return None

    @staticmethod
    def _read_field(obj: Any, name: str, default: Any = None) -> Any:
        """兼容字典与对象两种形状读取字段（route_plan/asset_plan 可能已序列化）"""
        if obj is None:
            return default
        if isinstance(obj, Mapping):
            return obj.get(name, default)
        return getattr(obj, name, default)
