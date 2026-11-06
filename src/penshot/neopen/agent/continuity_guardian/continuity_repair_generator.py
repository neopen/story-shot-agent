"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: continuity_repair_generator.py
@Description: 连续性修复参数生成器
@Author: NeoPen
@Time: 2026/3/28 21:03
"""

from typing import Any, Dict, List, Optional

from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    SeverityLevel,
    QualityRepairParams,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from .continuity_guardian_models import ContinuityIssue
from .contract_repair import (
    describe_character_anchors,
    describe_prop_anchors,
    describe_scene_anchors,
    describe_style_anchors,
)

# 需要角色契约锚点驱动的连续性问题类型
_CHARACTER_ISSUE_TYPES = {
    "character_missing",
    "character_disappear",
    "appearance_change",
}
# 需要风格契约锚点驱动的连续性问题类型
_STYLE_ISSUE_TYPES = {
    "style_inconsistent",
    "style_sudden_change",
    "color_inconsistent",
    "lighting_change",
}
# 需要场景契约锚点驱动的连续性问题类型
_SCENE_ISSUE_TYPES = {"scene_jump", "scene_inconsistent", "scene_too_frequent"}
# 需要道具资产锚点驱动的连续性问题类型
_PROP_ISSUE_TYPES = {"prop_change", "prop_disappear", "prop_appear"}


class ContinuityRepairGenerator:
    """连续性修复参数生成器"""

    def __init__(self):
        self.repair_strategies = {
            "character_missing": self._repair_character_missing,
            "character_disappear": self._repair_character_disappear,
            "appearance_change": self._repair_character_appearance_change,
            "scene_jump": self._repair_scene_jump,
            "scene_inconsistent": self._repair_scene_inconsistent,
            "action_break": self._repair_action_break,
            "style_inconsistent": self._repair_style_inconsistent,
            "style_sudden_change": self._repair_style_sudden_change,
            "lighting_change": self._repair_style_inconsistent,
            "color_inconsistent": self._repair_style_inconsistent,
            "time_gap": self._repair_time_gap,
            "time_overlap": self._repair_time_overlap,
            "prop_change": self._repair_prop_change,
            "prop_disappear": self._repair_prop_change,
            "prop_appear": self._repair_prop_change,
        }

    def generate_repair_params(
        self,
        issues: List[ContinuityIssue],
        stage: PipelineNode,
        contract: Optional[Any] = None,
    ) -> QualityRepairParams:
        """为特定阶段生成修复参数

        Args:
            issues: 连续性问题列表
            stage: 目标修复阶段
            contract: 全局一致性契约；传入后会把角色/场景/风格/道具锚点
                拼接进修复建议，使修复由契约驱动而非泛化文案

        Returns:
            可直接交给各阶段 Agent 消费的修复参数
        """
        issue_types = list(set([i.type for i in issues]))
        suggestions = {}

        for issue in issues:
            strategy = self.repair_strategies.get(issue.type)
            if strategy is not None:
                suggestion = strategy(issue)
            else:
                suggestion = "按一致性契约修复该问题"
                description = (issue.description or "").strip()
                if description:
                    suggestion = f"{suggestion}：{description[:80]}"

            # 补充契约锚点约束（角色外观/场景/风格/道具）
            anchor_hint = self._contract_anchor_hint(issue, contract)
            if anchor_hint:
                suggestion = f"{suggestion}；{anchor_hint}"

            key = issue.fragment_id or "global"
            suggestions[key] = suggestions.get(key, []) + [suggestion]

        return QualityRepairParams(
            fix_needed=True,
            issue_count=len(issues),
            issue_types=issue_types,
            fragments=list(set([i.fragment_id for i in issues if i.fragment_id])),
            suggestions=suggestions,
            severity_summary=self._get_severity_summary(issues),
        )

    def _contract_anchor_hint(
        self, issue: ContinuityIssue, contract: Optional[Any]
    ) -> str:
        """按问题类型补充契约锚点约束"""
        if contract is None:
            return ""

        issue_type = getattr(issue.type, "value", issue.type)
        issue_type = str(issue_type)

        if issue_type in _CHARACTER_ISSUE_TYPES:
            return describe_character_anchors(
                contract, self._issue_character(issue, contract)
            )
        if issue_type in _STYLE_ISSUE_TYPES:
            return describe_style_anchors(contract)
        if issue_type in _SCENE_ISSUE_TYPES:
            return describe_scene_anchors(contract, getattr(issue, "scene_id", None))
        if issue_type in _PROP_ISSUE_TYPES:
            return describe_prop_anchors(contract, issue.description)
        return ""

    def _issue_character(self, issue: ContinuityIssue, contract: Any) -> str:
        """从问题元数据或描述中解析关联角色名"""
        metadata = getattr(issue, "metadata", None) or {}
        if isinstance(metadata, dict):
            for key in ("character", "character_name", "main_character"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        description = getattr(issue, "description", "") or ""
        for name in getattr(contract, "characters", {}) or {}:
            if name and name in description:
                return name
        return ""

    def _repair_character_missing(self, issue: ContinuityIssue) -> str:
        return "为角色添加镜头，确保出现在相应场景中"

    def _repair_character_disappear(self, issue: ContinuityIssue) -> str:
        return "补充角色离开画面的合理动作（转身/出画），避免角色突然消失"

    def _repair_character_appearance_change(self, issue: ContinuityIssue) -> str:
        return "统一角色外观描述，按契约外观锚点重新生成该片段"

    def _repair_scene_jump(self, issue: ContinuityIssue) -> str:
        metadata = getattr(issue, "metadata", None) or {}
        prev_scene = metadata.get("prev_scene") if isinstance(metadata, dict) else None
        next_scene = metadata.get("next_scene") if isinstance(metadata, dict) else None
        if prev_scene and next_scene:
            return (
                f"在场景 {prev_scene} 与 {next_scene} 的切换处插入1个过渡镜头"
                "（空镜或角色反应镜头），并使用与相邻镜头不同的景别"
            )
        return "在场景切换处插入过渡镜头（如空镜、角色反应镜头），并使用与相邻镜头不同的景别"


    def _repair_scene_inconsistent(self, issue: ContinuityIssue) -> str:
        return "统一场景地点与时间描述，按契约场景锚点修正该片段"

    def _repair_action_break(self, issue: ContinuityIssue) -> str:
        return "补充分解动作镜头，确保动作连贯"

    def _repair_style_inconsistent(self, issue: ContinuityIssue) -> str:
        return f"统一视觉风格，建议使用 {issue.suggestion or 'cinematic'} 风格"

    def _repair_style_sudden_change(self, issue: ContinuityIssue) -> str:
        return "在风格变化处添加过渡描述，使风格变化更平滑"

    def _repair_time_gap(self, issue: ContinuityIssue) -> str:
        return "调整片段时间，消除时间间隙"

    def _repair_time_overlap(self, issue: ContinuityIssue) -> str:
        return "调整片段时间，消除重叠"

    def _repair_prop_change(self, issue: ContinuityIssue) -> str:
        return "检查道具连续性，确保角色手持道具前后一致"

    def _get_severity_summary(self, issues: List[ContinuityIssue]) -> Dict[str, int]:
        summary = {severity.value: 0 for severity in SeverityLevel}
        for issue in issues:
            summary[issue.severity.value] = summary.get(issue.severity.value, 0) + 1
        return summary
