"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: shot_generator_models.py
@Description: 模型
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/18 14:26
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from penshot.neopen.agent.script_parser.script_parser_models import EmotionType


class ShotType(str, Enum):
    """MVP镜头类型（简化）"""
    """
        人物对话时的表情变化
        重要道具展示
        情感表达（喜悦、悲伤、愤怒）
        角色反应镜头
    """
    CLOSE_UP = "close_up"    # 特写
    """
        眼睛特写（表现恐惧、震惊）
        扣动扳机的手指
        时钟指针跳动
        瞳孔放大/缩小
        泪水滑落瞬间
    """
    EXTREME_CLOSE_UP = "extreme_close_up" # 极特写

    WIDE_SHOT = "wide_shot"  # 远景/广角
    LONG_SHOT = "long_shot"  # 全景/远景
    MEDIUM_SHOT = "medium_shot"  # 中景

    # 特殊镜头类型
    OVER_SHOULDER = "over_shoulder"  # 过肩镜头
    POV = "pov"  # 主观视角
    TWO_SHOT = "two_shot"  # 双人镜头

    # 动态镜头类型
    FOLLOWING_SHOT = "following_shot"  # 跟拍镜头
    PANORAMA = "panorama"  # 摇摄/全景移动
    ZOOM = "zoom"  # 推拉镜头

    # 动作相关
    ACTION = "action"  # 动作镜头
    MOVING = "moving"  # 移动镜头

    @classmethod
    def get_type_mapping(cls) -> Dict['ShotType', str]:
        """获取镜头类型描述映射"""
        return {
            cls.WIDE_SHOT: "远景镜头，展现场景全貌",
            cls.LONG_SHOT: "全景镜头，展示人物全身",
            cls.MEDIUM_SHOT: "中景镜头，展现人物上半身",
            cls.CLOSE_UP: "特写镜头，聚焦面部表情",
            cls.EXTREME_CLOSE_UP: "极特写镜头，强调细节",
            cls.OVER_SHOULDER: "过肩镜头，对话视角",
            cls.POV: "主观视角，第一人称",
            cls.TWO_SHOT: "双人镜头，两人同框",
            cls.FOLLOWING_SHOT: "跟拍镜头，跟随运动",
            cls.PANORAMA: "摇摄镜头，水平移动",
            cls.ZOOM: "推拉镜头，焦距变化",
            cls.ACTION: "动作镜头，捕捉动作",
            cls.MOVING: "移动镜头，动态视角",
        }


class ShotInfo(BaseModel):
    """MVP镜头信息模型"""
    id: str = Field(..., description="镜头唯一ID，格式：shot_001")

    # 基础关联信息
    scene_id: str = Field(..., description="所属场景ID")

    # 情绪信息（简化）
    emotion: str = Field(
        default=EmotionType.NEUTRAL.value,
        description="伴随情绪：neutral/happy/angry/sad/fear"
    )

    # 内容描述
    description: str = Field(..., description="镜头内容简洁描述")

    # 时间信息
    start_time: float = Field(default=0.0, description="全局开始时间（秒）")
    duration: float = Field(
        default=3.0,
        ge=0.5,
        description="镜头时长（秒）"
    )

    # 视觉类型（简化）
    shot_type: ShotType = Field(
        default=ShotType.MEDIUM_SHOT,
        description="镜头类型"
    )

    # 核心内容关联
    main_character: Optional[str] = Field(
        default=None,
        description="主要角色（如有）"
    )

    # 简化的元素引用
    element_ids: List[str] = Field(
        default_factory=list,
        description="引用的剧本元素ID列表"
    )

    # 简化的元数据
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="分镜决策置信度"
    )


class ShotSequence(BaseModel):
    """MVP镜头序列输出"""

    # 简化的元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "generated_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "parser_type": "shot_splitter_v1"
        }
    )

    # 源剧本引用
    script_reference: Dict[str, Any] = Field(
        default_factory=lambda: {
            "title": "",
            "total_elements": 0,
            "original_duration": 0.0
        }
    )

    # 核心镜头列表
    shots: List[ShotInfo] = Field(
        default_factory=list,
        description="按时间顺序排列的镜头列表"
    )

    # 简化的统计数据
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "shot_count": 0,
            "total_duration": 0.0,
            "avg_shot_duration": 0.0,
            "close_up_count": 0,
            "wide_shot_count": 0
        }
    )
