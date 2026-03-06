"""
@FileName: quality_auditor_models.py
@Description: 质量审核模型
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/19 22:58
"""
from datetime import datetime
from enum import Enum, unique
from typing import List, Optional, Any, Dict, Literal

from pydantic import Field, BaseModel


@unique
class SeverityLevel(str, Enum):
    """违规严重程度"""
    INFO = "info"        # 信息级别，不影响执行
    WARNING = "warning"  # 警告级别，建议修复
    MODERATE = "moderate" # 中度问题，需要调整
    MAJOR = "major"      # 主要问题，需要重新处理
    CRITICAL = "critical" # 严重问题，需要人工干预
    ERROR = "error"      # 错误级别，无法继续


@unique
class AuditStatus(str, Enum):
    """质量审查状态枚举"""
    PASSED = "passed"  # 完全通过
    MINOR_ISSUES = "minor_issues"  # 轻微问题（警告级别）
    MODERATE_ISSUES = "moderate_issues"  # 中度问题（需要调整）
    MAJOR_ISSUES = "major_issues"  # 主要问题（需要重新处理）
    CRITICAL_ISSUES = "critical_issues"  # 严重问题（需要人工干预）
    FAILED = "failed"  # 完全失败
    NEEDS_HUMAN = "needs_human"  # 需要人工决策

    NEEDS_REVIEW = "needs_review" # 需要审查
    WARNING = "warning"           # 有警告



class IssueType(str, Enum):
    """问题类型枚举 - 统一规范"""
    TRUNCATION = "截断"          # 提示词截断
    SCENE = "场景"                # 场景引用错误
    WEATHER = "气象"              # 气象矛盾
    CHARACTER = "角色"            # 角色不一致
    ACTION = "动作"               # 动作不连贯
    PROMPT = "提示词"             # 提示词质量问题
    DURATION = "时长"             # 时长不合理
    STYLE = "风格"                # 风格不一致
    OTHER = "其他"                # 其他问题


class BasicViolation(BaseModel):
    """MVP违规记录"""
    rule_id: str = Field(..., description="规则ID")
    rule_name: str = Field(..., description="规则名称")
    description: str = Field(..., description="违规描述")
    severity: Literal[SeverityLevel.INFO, SeverityLevel.WARNING, SeverityLevel.ERROR,
        SeverityLevel.MAJOR, SeverityLevel.MODERATE, SeverityLevel.CRITICAL] = Field(
        default=SeverityLevel.WARNING,
        description="严重程度"
    )
    fragment_id: Optional[str] = Field(
        default=None,
        description="涉及的片段ID"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="改进建议"
    )


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
            "warnings": 0,
            "errors": 0,
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
