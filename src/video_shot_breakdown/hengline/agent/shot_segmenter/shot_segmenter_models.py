"""
@FileName: shot_generator_models.py
@Description: 模型
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/18 14:26
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class ShotType(str, Enum):
    """MVP镜头类型（简化）"""
    CLOSE_UP = "close_up"
    MEDIUM_SHOT = "medium_shot"
    WIDE_SHOT = "wide_shot"

    @staticmethod
    def get_type_mapping():
        return {
            ShotType.CLOSE_UP: "特写",
            ShotType.MEDIUM_SHOT: "中景",
            ShotType.WIDE_SHOT: "全景",
        }


class ShotInfo(BaseModel):
    """MVP镜头信息模型"""
    id: str = Field(..., description="镜头唯一ID，格式：shot_001")

    # 基础关联信息
    scene_id: str = Field(..., description="所属场景ID")

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
