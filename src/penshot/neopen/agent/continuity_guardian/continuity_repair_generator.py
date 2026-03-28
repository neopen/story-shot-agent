"""
@FileName: continuity_repair_generator.py
@Description: 连续性修复参数生成器
@Author: HiPeng
@Time: 2026/3/28 21:03
"""
from typing import Dict, List

from penshot.neopen.agent.quality_auditor.quality_auditor_models import SeverityLevel, QualityRepairParams
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from .continuity_guardian_models import (
    ContinuityIssue
)


class ContinuityRepairGenerator:
    """连续性修复参数生成器"""

    def __init__(self):
        self.repair_strategies = {
            "character_missing": self._repair_character_missing,
            "scene_jump": self._repair_scene_jump,
            "action_break": self._repair_action_break,
            "style_inconsistent": self._repair_style_inconsistent,
            "style_sudden_change": self._repair_style_sudden_change,
            "time_gap": self._repair_time_gap,
            "time_overlap": self._repair_time_overlap,
            "prop_change": self._repair_prop_change,
        }

    def generate_repair_params(self, issues: List[ContinuityIssue],
                               stage: PipelineNode) -> QualityRepairParams:
        """为特定阶段生成修复参数"""
        issue_types = list(set([i.type for i in issues]))
        suggestions = {}

        for issue in issues:
            if issue.type in self.repair_strategies:
                suggestion = self.repair_strategies[issue.type](issue)
                if issue.fragment_id:
                    suggestions[issue.fragment_id] = suggestions.get(issue.fragment_id, []) + [suggestion]
                else:
                    suggestions["global"] = suggestions.get("global", []) + [suggestion]

        return QualityRepairParams(
            fix_needed=True,
            issue_count=len(issues),
            issue_types=issue_types,
            fragments=list(set([i.fragment_id for i in issues if i.fragment_id])),
            suggestions=suggestions,
            severity_summary=self._get_severity_summary(issues)
        )

    def _repair_character_missing(self, issue: ContinuityIssue) -> str:
        return f"为角色添加镜头，确保出现在相应场景中"

    def _repair_scene_jump(self, issue: ContinuityIssue) -> str:
        return f"添加过渡镜头（如空镜、角色反应镜头）使场景切换更自然"

    def _repair_action_break(self, issue: ContinuityIssue) -> str:
        return f"补充分解动作镜头，确保动作连贯"

    def _repair_style_inconsistent(self, issue: ContinuityIssue) -> str:
        return f"统一视觉风格，建议使用 {issue.suggestion or 'cinematic'} 风格"

    def _repair_style_sudden_change(self, issue: ContinuityIssue) -> str:
        return f"在风格变化处添加过渡描述，使风格变化更平滑"

    def _repair_time_gap(self, issue: ContinuityIssue) -> str:
        return f"调整片段时间，消除时间间隙"

    def _repair_time_overlap(self, issue: ContinuityIssue) -> str:
        return f"调整片段时间，消除重叠"

    def _repair_prop_change(self, issue: ContinuityIssue) -> str:
        return f"检查道具连续性，确保角色手持道具前后一致"

    def _get_severity_summary(self, issues: List[ContinuityIssue]) -> Dict[str, int]:
        summary = {severity.value: 0 for severity in SeverityLevel}
        for issue in issues:
            summary[issue.severity.value] = summary.get(issue.severity.value, 0) + 1
        return summary
