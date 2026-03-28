"""
@FileName: continuity_guardian_models.py
@Description: 连续性管理模型
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/18 14:26
"""
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, field_validator

from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation
from penshot.neopen.agent.workflow.workflow_models import PipelineNode


class ContinuityIssueType(str, Enum):
    """连续性问题类型枚举"""
    # 角色相关
    CHARACTER_MISSING = "character_missing"  # 角色缺失
    CHARACTER_APPEARANCE_CHANGE = "appearance_change"  # 角色外观变化
    CHARACTER_DISAPPEAR = "character_disappear"  # 角色突然消失

    # 场景相关
    SCENE_JUMP = "scene_jump"  # 场景跳跃
    SCENE_TOO_FREQUENT = "scene_too_frequent"  # 场景切换过于频繁
    SCENE_INCONSISTENT = "scene_inconsistent"  # 场景不一致

    # 动作相关
    ACTION_BREAK = "action_break"  # 动作中断
    ACTION_ILLOGICAL = "action_illogical"  # 动作不合逻辑
    ACTION_INCOMPLETE = "action_incomplete"  # 动作不完整

    # 风格相关
    STYLE_INCONSISTENT = "style_inconsistent"  # 风格不一致
    STYLE_SUDDEN_CHANGE = "style_sudden_change"  # 风格突变

    # 时间相关
    TIME_GAP = "time_gap"  # 时间间隙
    TIME_OVERLAP = "time_overlap"  # 时间重叠
    TIME_REVERSE = "time_reverse"  # 时间倒流

    # 道具相关
    PROP_CHANGE = "prop_change"  # 道具变化
    PROP_DISAPPEAR = "prop_disappear"  # 道具消失
    PROP_APPEAR = "prop_appear"  # 道具突然出现

    # 视觉相关
    LIGHTING_CHANGE = "lighting_change"  # 光照变化
    COLOR_INCONSISTENT = "color_inconsistent"  # 色彩不一致
    COMPOSITION_BREAK = "composition_break"  # 构图断裂

    # 其他
    GENERAL = "general"  # 一般连续性问题


class ContinuitySeverity(str, Enum):
    """连续性问题的严重程度"""
    CRITICAL = "critical"  # 严重，必须修复
    MAJOR = "major"  # 主要，建议修复
    MODERATE = "moderate"  # 中度，可考虑修复
    MINOR = "minor"  # 轻微，可忽略
    ERROR = "error"  # 错误
    WARNING = "warning"  # 警告
    INFO = "info"  # 信息，仅记录


class ContinuityIssue(BaseModel):
    """连续性问题标准模型"""

    # 基本信息
    id: str = Field(..., description="问题唯一标识")
    type: ContinuityIssueType = Field(..., description="问题类型")
    description: str = Field(..., description="问题描述", max_length=500)
    severity: ContinuitySeverity = Field(default=ContinuitySeverity.MODERATE, description="严重程度")

    # 位置信息
    fragment_id: Optional[str] = Field(default=None, description="关联的片段ID")
    shot_id: Optional[str] = Field(default=None, description="关联的镜头ID")
    scene_id: Optional[str] = Field(default=None, description="关联的场景ID")
    element_id: Optional[str] = Field(default=None, description="关联的剧本元素ID")
    position: Optional[int] = Field(default=None, description="在序列中的位置索引")

    # 时间信息
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp(), description="检测时间戳")
    start_time: Optional[float] = Field(default=None, description="问题开始时间（秒）")
    end_time: Optional[float] = Field(default=None, description="问题结束时间（秒）")

    # 关联信息
    related_ids: List[str] = Field(default_factory=list, description="关联的其他ID列表")
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文信息")

    # 修复信息
    suggestion: Optional[str] = Field(default=None, description="修复建议", max_length=500)
    auto_fixable: bool = Field(default=True, description="是否可自动修复")
    source_stage: Optional[PipelineNode] = Field(default=None, description="问题来源阶段")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str) -> str:
        """验证描述不为空"""
        if not v or not v.strip():
            raise ValueError("问题描述不能为空")
        return v.strip()

    @field_validator('fragment_id', 'shot_id', 'scene_id', 'element_id', mode='before')
    @classmethod
    def validate_id(cls, v: Optional[str]) -> Optional[str]:
        """验证ID格式"""
        if v is not None and not v.strip():
            return None
        return v

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """序列化时排除空值"""
        kwargs.setdefault('exclude_none', True)
        return super().model_dump(**kwargs)

    def to_basic_violation(self) -> 'BasicViolation':
        """转换为质量审查的 BasicViolation 格式"""
        from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
            BasicViolation, SeverityLevel, IssueType
        )

        # 严重程度映射
        severity_mapping = {
            ContinuitySeverity.CRITICAL: SeverityLevel.CRITICAL,
            ContinuitySeverity.MAJOR: SeverityLevel.MAJOR,
            ContinuitySeverity.MODERATE: SeverityLevel.MODERATE,
            ContinuitySeverity.MINOR: SeverityLevel.WARNING,
            ContinuitySeverity.INFO: SeverityLevel.INFO,
        }

        # 问题类型映射
        issue_type_mapping = {
            ContinuityIssueType.CHARACTER_MISSING: IssueType.CHARACTER,
            ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE: IssueType.CHARACTER,
            ContinuityIssueType.SCENE_JUMP: IssueType.SCENE,
            ContinuityIssueType.ACTION_BREAK: IssueType.ACTION,
            ContinuityIssueType.STYLE_INCONSISTENT: IssueType.STYLE,
            ContinuityIssueType.TIME_GAP: IssueType.CONTINUITY,
            ContinuityIssueType.TIME_OVERLAP: IssueType.CONTINUITY,
            ContinuityIssueType.PROP_CHANGE: IssueType.CONTINUITY,
        }

        return BasicViolation(
            rule_code=f"continuity_{self.type.value}",
            rule_name=f"连续性检查: {self.type.value}",
            issue_type=issue_type_mapping.get(self.type, IssueType.CONTINUITY),
            description=self.description,
            severity=severity_mapping.get(self.severity, SeverityLevel.MODERATE),
            fragment_id=self.fragment_id,
            suggestion=self.suggestion,
            source_node=self.source_stage
        )


class CharacterState(BaseModel):
    """角色状态快照"""

    character_name: str = Field(..., description="角色名")

    # 外观状态
    appearance: Dict[str, Any] = Field(
        default_factory=dict,
        description="外观状态：服装、发型、妆容等"
    )

    # 位置状态
    position: Dict[str, Any] = Field(
        default_factory=lambda: {
            "location": "unknown",
            "coordinates": None,
            "orientation": "front"
        },
        description="位置和朝向"
    )

    # 道具状态
    props: Dict[str, Any] = Field(
        default_factory=dict,
        description="持有道具状态"
    )

    # 情绪状态
    emotion: Dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "neutral",
            "intensity": 0.5
        },
        description="情绪状态"
    )

    # 动作状态
    action_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="当前动作状态"
    )

    # 视觉状态
    visual_state: Dict[str, Any] = Field(
        default_factory=lambda: {
            "in_frame": True,
            "focus_level": "primary"
        },
        description="视觉状态"
    )


class SceneState(BaseModel):
    """场景状态快照"""

    scene_id: str = Field(..., description="场景ID")

    # 环境状态
    environment: Dict[str, Any] = Field(
        default_factory=lambda: {
            "time_of_day": "day",
            "weather": "clear",
            "lighting": "normal",
            "temperature": "normal"
        },
        description="环境状态"
    )

    # 道具状态
    scene_props: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="场景道具状态"
    )

    # 背景状态
    background: Dict[str, Any] = Field(
        default_factory=lambda: {
            "details": "",
            "activity_level": "low",
            "color_palette": []
        },
        description="背景状态"
    )

    # 音效状态
    audio_state: Dict[str, Any] = Field(
        default_factory=lambda: {
            "ambient_sound": "silence",
            "volume": 0.5
        },
        description="音效状态"
    )


class StateSnapshot(BaseModel):
    """全局状态快照"""

    timestamp: float = Field(..., description="时间戳（秒）")
    snapshot_id: str = Field(..., description="快照ID")

    # 角色状态
    character_states: Dict[str, CharacterState] = Field(
        default_factory=dict,
        description="所有角色状态"
    )

    # 场景状态
    scene_state: Optional[SceneState] = Field(
        default=None,
        description="场景状态"
    )

    # 全局状态
    global_state: Dict[str, Any] = Field(
        default_factory=lambda: {
            "current_scene": "unknown",
            "time_elapsed": 0.0,
            "narrative_phase": "beginning",
            "emotional_tone": "neutral"
        },
        description="全局状态"
    )

    # 引用信息
    references: Dict[str, Any] = Field(
        default_factory=lambda: {
            "fragment_id": None,
            "shot_id": None,
            "element_ids": []
        },
        description="状态来源引用"
    )

    def get_character_state(self, character_name: str) -> Optional[CharacterState]:
        """获取指定角色的状态"""
        return self.character_states.get(character_name)

    def set_character_state(self, character_name: str, state: CharacterState) -> None:
        """设置指定角色的状态"""
        self.character_states[character_name] = state


class StateTimeline(BaseModel):
    """状态时间线 - 连续性管理核心"""

    # 时间线数据
    snapshots: List[StateSnapshot] = Field(
        default_factory=list,
        description="状态快照列表，按时间顺序排列"
    )

    # 状态演化记录
    state_evolution: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="关键状态的演化历史"
    )

    # 锚点定义
    continuity_anchors: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="连续性锚点定义，用于约束生成"
    )

    # 容差设置
    tolerance_settings: Dict[str, Any] = Field(
        default_factory=lambda: {
            "position_tolerance": "medium",
            "appearance_tolerance": "low",
            "temporal_tolerance": "high",
            "color_tolerance": "medium"
        },
        description="连续性容差设置"
    )

    def add_snapshot(self, snapshot: StateSnapshot) -> None:
        """添加快照"""
        self.snapshots.append(snapshot)
        # 按时间排序
        self.snapshots.sort(key=lambda x: x.timestamp)

    def get_snapshot_at_time(self, timestamp: float) -> Optional[StateSnapshot]:
        """获取指定时间的快照"""
        if not self.snapshots:
            return None

        # 二分查找最接近的快照
        for i, snapshot in enumerate(self.snapshots):
            if snapshot.timestamp >= timestamp:
                return snapshot
        return self.snapshots[-1]

    def get_latest_snapshot(self) -> Optional[StateSnapshot]:
        """获取最新的快照"""
        return self.snapshots[-1] if self.snapshots else None

    def get_character_evolution(self, character_name: str) -> List[Dict[str, Any]]:
        """获取角色的状态演化历史"""
        if character_name not in self.state_evolution:
            return []
        return self.state_evolution[character_name]

    def record_evolution(self, key: str, value: Dict[str, Any]) -> None:
        """记录状态演化"""
        if key not in self.state_evolution:
            self.state_evolution[key] = []
        self.state_evolution[key].append({
            "timestamp": datetime.now().timestamp(),
            **value
        })


class ContinuityCheckResult(BaseModel):
    """连续性检查结果"""

    # 检查状态
    passed: bool = Field(default=True, description="是否通过检查")
    total_issues: int = Field(default=0, description="问题总数")

    # 问题分类
    issues: List[ContinuityIssue] = Field(default_factory=list, description="问题列表")
    issues_by_type: Dict[str, List[ContinuityIssue]] = Field(
        default_factory=dict,
        description="按类型分组的问题"
    )
    issues_by_severity: Dict[str, List[ContinuityIssue]] = Field(
        default_factory=dict,
        description="按严重程度分组的问题"
    )

    # 统计信息
    critical_count: int = Field(default=0, description="严重问题数量")
    major_count: int = Field(default=0, description="主要问题数量")
    moderate_count: int = Field(default=0, description="中度问题数量")
    minor_count: int = Field(default=0, description="轻微问题数量")

    # 时间信息
    check_timestamp: float = Field(default_factory=lambda: datetime.now().timestamp(), description="检查时间")
    check_duration: Optional[float] = Field(default=None, description="检查耗时（秒）")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    def add_issue(self, issue: ContinuityIssue) -> None:
        """添加问题"""
        self.issues.append(issue)
        self.total_issues += 1

        # 更新按类型分组
        issue_type = issue.type.value
        if issue_type not in self.issues_by_type:
            self.issues_by_type[issue_type] = []
        self.issues_by_type[issue_type].append(issue)

        # 更新按严重程度分组
        severity = issue.severity.value
        if severity not in self.issues_by_severity:
            self.issues_by_severity[severity] = []
        self.issues_by_severity[severity].append(issue)

        # 更新计数
        if issue.severity == ContinuitySeverity.CRITICAL:
            self.critical_count += 1
        elif issue.severity == ContinuitySeverity.MAJOR:
            self.major_count += 1
        elif issue.severity == ContinuitySeverity.MODERATE:
            self.moderate_count += 1
        elif issue.severity == ContinuitySeverity.MINOR:
            self.minor_count += 1

        # 更新通过状态
        if self.critical_count > 0 or self.major_count > 3:
            self.passed = False

    def get_summary(self) -> Dict[str, Any]:
        """获取检查摘要"""
        return {
            "passed": self.passed,
            "total_issues": self.total_issues,
            "critical": self.critical_count,
            "major": self.major_count,
            "moderate": self.moderate_count,
            "minor": self.minor_count,
            "issues_by_type": {k: len(v) for k, v in self.issues_by_type.items()},
            "check_timestamp": self.check_timestamp
        }

    def to_report(self) -> Dict[str, Any]:
        """转换为报告格式"""
        return {
            "passed": self.passed,
            "summary": self.get_summary(),
            "issues": [issue.model_dump() for issue in self.issues],
            "metadata": self.metadata
        }


class ContinuityAnchor(BaseModel):
    """连续性锚点 - 用于约束生成"""

    anchor_id: str = Field(..., description="锚点唯一标识")
    anchor_type: str = Field(..., description="锚点类型: character, scene, prop, style")

    # 锚点内容
    name: str = Field(..., description="锚点名称")
    value: Any = Field(..., description="锚点值")

    # 约束范围
    start_time: float = Field(default=0.0, description="生效开始时间")
    end_time: Optional[float] = Field(default=None, description="生效结束时间")
    fragment_range: Optional[List[int]] = Field(default=None, description="生效片段范围")

    # 优先级
    priority: int = Field(default=1, description="优先级（越高越重要）")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    def is_active_at(self, time: float) -> bool:
        """检查锚点是否在指定时间生效"""
        if time < self.start_time:
            return False
        if self.end_time is not None and time > self.end_time:
            return False
        return True
