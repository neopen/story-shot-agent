"""
@FileName: continuity_guardian_models.py
@Description: 连续性管理模型
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/18 14:26
"""
from typing import List, Dict, Any

from pydantic import BaseModel, Field


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
            "lighting": "normal"
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
            "activity_level": "low"
        },
        description="背景状态"
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
    scene_state: SceneState = Field(
        default_factory=SceneState,
        description="场景状态"
    )

    # 全局状态
    global_state: Dict[str, Any] = Field(
        default_factory=lambda: {
            "current_scene": "unknown",
            "time_elapsed": 0.0,
            "narrative_phase": "beginning"
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
            "temporal_tolerance": "high"
        },
        description="连续性容差设置"
    )
