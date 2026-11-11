"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: capability_registry.py
@Description: 视频模型能力声明表（静态注册）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

from typing import Dict, List, Optional

from penshot.neopen.agent.model_adapter.model_models import (
    AestheticBias,
    ModelCapability,
)

# ---------------------------------------------------------------------------
# 静态能力声明表：覆盖主流视频模型。
# 字段含义见 ModelCapability；评分（text_rendering_score / character_consistency）
# 为 0~1 的相对主观值，供 M0.4.3 智能路由使用，值可随评测结果调整。
# ---------------------------------------------------------------------------
_MODEL_CAPABILITIES: Dict[str, ModelCapability] = {
    "runway_gen4": ModelCapability(
        model_name="runway_gen4",
        max_duration=10.0,
        supports_image_to_video=True,
        supports_camera_control=True,
        text_rendering_score=0.5,
        character_consistency=0.8,
        aesthetic_bias=AestheticBias.CINEMATIC,
    ),
    "kling_3": ModelCapability(
        model_name="kling_3",
        max_duration=10.0,
        supports_image_to_video=True,
        supports_camera_control=True,
        text_rendering_score=0.7,
        character_consistency=0.9,
        aesthetic_bias=AestheticBias.REALISTIC,
    ),
    "luma_dream": ModelCapability(
        model_name="luma_dream",
        max_duration=5.0,
        supports_image_to_video=True,
        supports_camera_control=True,
        text_rendering_score=0.6,
        character_consistency=0.7,
        aesthetic_bias=AestheticBias.CINEMATIC,
    ),
    "sora_2": ModelCapability(
        model_name="sora_2",
        max_duration=60.0,
        supports_image_to_video=False,
        supports_camera_control=False,
        text_rendering_score=0.95,
        character_consistency=0.85,
        aesthetic_bias=AestheticBias.REALISTIC,
    ),
    "pika_2": ModelCapability(
        model_name="pika_2",
        max_duration=4.0,
        supports_image_to_video=True,
        supports_camera_control=True,
        text_rendering_score=0.4,
        character_consistency=0.6,
        aesthetic_bias=AestheticBias.ANIME,
    ),
}


def register_model(capability: ModelCapability) -> None:
    """注册（或覆盖）一个模型能力声明"""
    _MODEL_CAPABILITIES[capability.model_name] = capability


def get_capability(model_name: str) -> Optional[ModelCapability]:
    """按模型名获取能力声明；未注册时返回 None"""
    return _MODEL_CAPABILITIES.get(model_name)


def list_model_names() -> List[str]:
    """返回已注册模型的名称列表"""
    return list(_MODEL_CAPABILITIES.keys())


def all_capabilities() -> Dict[str, ModelCapability]:
    """返回全部模型能力声明的副本（避免调用方误改内部表）"""
    return dict(_MODEL_CAPABILITIES)
