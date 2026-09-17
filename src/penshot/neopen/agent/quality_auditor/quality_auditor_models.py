"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: quality_auditor_models.py
@Description: 质量审核模型
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19 22:58
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Any, Dict, Literal

from pydantic import Field, BaseModel

from penshot.neopen.agent.quality_auditor.quality_auditor_enum import RuleType, IssueType, SeverityLevel, AuditStatus
from penshot.neopen.agent.workflow.workflow_models import PipelineNode


class BasicViolation(BaseModel):
    """MVP违规记录"""
    issue_type: IssueType = Field(..., description="问题类型")
    issue_code: Optional[str] = Field(
        default=None,
        description="问题子类型，如 'empty', 'too_long', 'missing_character' 等"
    )
    issue_desc: Optional[str] = Field(
        default=None,
        description="问题描述"
    )
    issue_value: Optional[Any] = Field(
        default=None,
        description="问题值，如 '508' 等"
    )
    standard_value: Optional[Any] = Field(
        default=None,
        description="标准规范值"
    )
    source_node: Optional[PipelineNode] = Field(default=None, description="问题来源阶段")
    severity: Literal[SeverityLevel.INFO, SeverityLevel.WARNING, SeverityLevel.ERROR,
    SeverityLevel.MAJOR, SeverityLevel.MODERATE, SeverityLevel.CRITICAL] = Field(
        default=SeverityLevel.WARNING,
        description="严重程度"
    )
    description: Optional[str] = Field(
        default=None,
        description="详细描述"
    )
    fragment_id: Optional[str] = Field(
        default=None,
        description="涉及的片段ID"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="改进建议"
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BasicViolation':
        """从字典创建实例"""
        return cls(
            issue_code=data.get("issue_code", ""),
            issue_type=IssueType(data.get("issue_type", "other")),
            issue_desc=data.get("issue_desc", ""),
            severity=SeverityLevel(data.get("severity", "warning")),
            fragment_id=data.get("fragment_id"),
            suggestion=data.get("suggestion"),
            source_node=PipelineNode(data.get("source_node")) if data.get("source_node") else None
        )

    @classmethod
    def create(cls, issue_code: str, issue_type: IssueType, issue_desc: str,
               issue_value: Optional[Any] = None, standard_value: Optional[Any] = None,
               severity: SeverityLevel = SeverityLevel.WARNING,
               fragment_id: Optional[str] = None,
               suggestion: Optional[str] = None,
               source_node: PipelineNode = PipelineNode.AUDIT_QUALITY) -> 'BasicViolation':
        """添加违规记录"""
        return BasicViolation(
            issue_type=issue_type,
            issue_code=issue_code,
            issue_desc=issue_desc,
            issue_value=issue_value,
            standard_value=standard_value,
            source_node=source_node,
            severity=severity,
            fragment_id=fragment_id,
            suggestion=suggestion
        )

    @classmethod
    def create_violation(cls, rule_type: RuleType,
                         issue_value: Optional[Any] = None, standard_value: Optional[Any] = None,
                         severity: SeverityLevel = SeverityLevel.WARNING,
                         fragment_id: Optional[str] = None, suggestion: Optional[str] = None,
                         source_node: PipelineNode = PipelineNode.AUDIT_QUALITY) -> 'BasicViolation':
        """添加违规记录"""
        return cls.create(issue_code=rule_type.code, issue_type=rule_type.issue_type, issue_desc=rule_type.description,
                          issue_value=issue_value, standard_value=standard_value,
                          severity=severity, fragment_id=fragment_id, suggestion=suggestion, source_node=source_node)


class QualityRepairParams(BaseModel):
    fix_needed: bool = Field(
        default=False,
        description="是否需要修复"
    )

    issue_count: int = Field(
        default=0,
        description="问题数量"
    )

    issue_types: List[str] = Field(
        default_factory=list,
        description="修复类型"
    )

    issues: List[Any] = Field(
        default_factory=list,
        description="完整问题列表（可以是 BasicViolation 或 ContinuityIssue）"
    )

    fragments: List[str] = Field(
        default_factory=list,
        description="对应的片段ID集合"
    )

    suggestions: Dict[str, List[str]] = Field(
        default=None,
        description="修复建议"
    )

    severity_summary: Dict[str, int] = Field(
        default=None,
        description="严重程度摘要"
    )

    def add_issue_type(self, issue_type: Any) -> None:
        """添加问题类型（自动转换为字符串）"""
        if hasattr(issue_type, 'value'):
            type_str = issue_type.value
        else:
            type_str = str(issue_type)

        if type_str not in self.issue_types:
            self.issue_types.append(type_str)

    def add_suggestion(self, key: str, suggestion: str) -> None:
        """添加修复建议"""
        if key not in self.suggestions:
            self.suggestions[key] = []
        self.suggestions[key].append(suggestion)

    def get_issue_type_objects(self) -> List[Any]:
        """获取原始问题类型对象（需要外部转换）"""
        # 注意：这个方法返回的是字符串，需要外部根据上下文转换
        return self.issue_types


class QualityAuditReport(BaseModel):
    """MVP质量审查报告"""

    # 元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "audited_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "auditor_type": "basic"
        }
    )

    # 项目信息
    project_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "title": "",
            "fragment_count": 0,
            "total_duration": 0.0
        }
    )

    # 审查状态
    status: AuditStatus = Field(
        default=AuditStatus.PASSED,
        description="审查状态：passed=通过, needs_revision=需要调整, failed=失败"
    )

    # 检查明细
    checks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="执行的检查项目"
    )

    # 违规记录
    violations: List[BasicViolation] = Field(
        default_factory=list,
        description="发现的违规问题"
    )

    # 统计数据
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_checks": 0,
            "passed_checks": 0,
            SeverityLevel.WARNING.value: 0,
            SeverityLevel.ERROR.value: 0,
            "fragments_checked": 0
        }
    )

    # 简单建议
    suggestions: List[str] = Field(
        default_factory=lambda: [
            "检查所有片段时长是否≤5秒",
            "确保没有空提示词"
        ]
    )

    # 最终结论
    conclusion: str = Field(
        default="审查通过，可以开始视频生成",
        description="审查结论"
    )

    score: float = Field(
        default=100.0,
        description="质量评分（0-100）"
    )

    detailed_analysis: Dict[str, Any] = Field(
        default=None,
        description="详细分析报告"
    )

    issues_source: Dict[PipelineNode, List[BasicViolation]] = Field(
        default=None,
        description="问题来源"
    )

    repair_params: Dict[PipelineNode, QualityRepairParams] = Field(
        default=None,
        description="修复参数"
    )

    def calculate_weighted_score(self) -> float:
        """统一计算加权分数"""
        if not self.violations:
            return 100.0

        severity_weights = {
            "info": 0,
            "warning": 5,
            "moderate": 10,
            "major": 25,
            "critical": 40,
            "error": 60,
        }

        base_score = 100.0
        for v in self.violations:
            severity = v.severity
            if hasattr(severity, 'value'):
                severity = severity.value
            penalty = severity_weights.get(str(severity).lower(), 5)
            base_score -= penalty

        return max(0.0, min(100.0, base_score))

    def determine_status_from_score(self) -> 'AuditStatus':
        """根据分数确定状态"""
        if self.score >= 90:
            return AuditStatus.PASSED
        elif self.score >= 75:
            return AuditStatus.MINOR_ISSUES
        elif self.score >= 60:
            return AuditStatus.MODERATE_ISSUES
        elif self.score >= 40:
            return AuditStatus.MAJOR_ISSUES
        elif self.score >= 20:
            return AuditStatus.CRITICAL_ISSUES
        else:
            return AuditStatus.FAILED

    def _has_severity(self, severity: SeverityLevel) -> bool:
        """检查是否存在指定严重程度的问题"""
        if not hasattr(self, 'stats'):
            return False
        severity_str = severity.value if hasattr(severity, 'value') else str(severity)
        return self.stats.get(severity_str, 0) > 0


@dataclass
class RepairHistory:
    """修复历史记录"""
    timestamp: float
    stage: str
    issue_count: int
    issues_fixed: List[str]
    success: bool
