"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: model_models.py
@Description: 目标模型适配层数据模型（M0.4.0）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AestheticBias(str, Enum):
    """模型美学偏好枚举（用于路由与适配时的风格兜底）"""

    CINEMATIC = "cinematic"  # 电影感
    ANIME = "anime"  # 二次元/动画
    REALISTIC = "realistic"  # 写实


class ModelCapability(BaseModel):
    """视频模型能力声明；是路由匹配与提示词适配的共同依据"""

    model_name: str = Field(..., description="模型唯一标识，如 runway_gen4")
    max_duration: float = Field(..., gt=0, description="单次最大时长（秒）")
    supports_image_to_video: bool = Field(default=False, description="是否支持图生视频")
    supports_camera_control: bool = Field(
        default=False, description="是否支持结构化相机参数"
    )
    text_rendering_score: float = Field(
        ..., ge=0.0, le=1.0, description="文字渲染能力 0~1"
    )
    character_consistency: float = Field(
        ..., ge=0.0, le=1.0, description="人物一致性 0~1"
    )
    aesthetic_bias: AestheticBias = Field(
        default=AestheticBias.CINEMATIC, description="美学偏好"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示（便于路由与序列化消费）"""
        return self.model_dump()


class AdaptedPromptPackage(BaseModel):
    """单个片段经模型适配后产出的专属提示词包"""

    fragment_id: str = Field(..., description="片段ID")
    target_model: str = Field(..., description="目标模型名")
    prompt: str = Field(..., description="模型专属正向提示词")
    negative_prompt: str = Field(default="", description="模型专属负向提示词")
    duration: float = Field(..., gt=0, description="适配后的片段时长（秒）")
    style: Optional[str] = Field(
        default=None, description="风格描述（模型美学偏好兜底）"
    )
    camera: Optional[str] = Field(default=None, description="模型专属相机表述")
    model_params: Dict[str, Any] = Field(
        default_factory=dict, description="模型专属生成参数"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class RouteDecision(BaseModel):
    """单个片段的路由决策（片段 -> 目标模型）"""

    fragment_id: str = Field(..., description="片段ID")
    target_model: str = Field(..., description="路由到的目标模型名")
    reason: str = Field(default="", description="路由原因")
    capability: Optional[ModelCapability] = Field(
        default=None, description="目标模型能力声明"
    )


class RoutePlan(BaseModel):
    """可序列化、下游可直接消费的模型路由计划指令包"""

    plan_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="计划唯一标识"
    )
    source_model: str = Field(default="", description="通用 prompt 中声明的原始模型名")
    decisions: List[RouteDecision] = Field(
        default_factory=list, description="路由决策列表"
    )
    adapted_packages: List[AdaptedPromptPackage] = Field(
        default_factory=list, description="适配后的提示词包列表"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示（JSON 可序列化）"""
        return self.model_dump()
