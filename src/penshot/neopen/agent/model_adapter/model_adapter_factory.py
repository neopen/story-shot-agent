"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: model_adapter_factory.py
@Description: 模型适配器工厂（按目标模型名选择适配器，默认 + 回退）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

from typing import Dict, List, Optional, Type

from penshot.logger import warning
from penshot.neopen.agent.model_adapter.capability_registry import get_capability
from penshot.neopen.agent.model_adapter.model_adapter import (
    BaseModelAdapter,
    Kling3Adapter,
    LumaDreamAdapter,
    Pika2Adapter,
    RunwayGen4Adapter,
    Sora2Adapter,
)
from penshot.neopen.agent.model_adapter.model_models import AdaptedPromptPackage
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
)

# 默认目标模型：未指定模型名或未注册时的回退项
DEFAULT_MODEL_NAME = "runway_gen4"

# 适配器注册表：模型名 -> 适配器类
ADAPTER_REGISTRY: Dict[str, Type[BaseModelAdapter]] = {
    "runway_gen4": RunwayGen4Adapter,
    "kling_3": Kling3Adapter,
    "luma_dream": LumaDreamAdapter,
    "sora_2": Sora2Adapter,
    "pika_2": Pika2Adapter,
}

# 旧模型名 / 别名 -> 规范模型名（兼容 prompt_converter 产出的 legacy 值）
_MODEL_ALIASES: Dict[str, str] = {
    "runway": "runway_gen4",
    "runway_gen2": "runway_gen4",
    "runway_gen3": "runway_gen4",
    "kling": "kling_3",
    "sora": "sora_2",
    "pika": "pika_2",
    "luma": "luma_dream",
}


def resolve_model_name(model_name: Optional[str]) -> str:
    """将模型名归一化（处理别名/旧名，忽略大小写），未知名原样返回"""
    if not model_name:
        return DEFAULT_MODEL_NAME
    normalized = model_name.strip().lower()
    return _MODEL_ALIASES.get(normalized, normalized)


def get_adapter(model_name: Optional[str] = DEFAULT_MODEL_NAME) -> BaseModelAdapter:
    """按目标模型名获取适配器；未注册时回退到默认适配器"""
    resolved = resolve_model_name(model_name)
    adapter_cls = ADAPTER_REGISTRY.get(resolved)
    if adapter_cls is None:
        warning(f"未注册的模型 '{model_name}'，回退到默认模型 {DEFAULT_MODEL_NAME}")
        resolved = DEFAULT_MODEL_NAME
        adapter_cls = ADAPTER_REGISTRY[DEFAULT_MODEL_NAME]

    capability = get_capability(resolved)
    if capability is None:
        raise ValueError(f"模型 {resolved} 缺少能力声明，无法构造适配器")
    return adapter_cls(capability)


def adapt_instructions(
    instructions: AIVideoInstructions,
    model_name: Optional[str] = None,
) -> List[AdaptedPromptPackage]:
    """把整份通用指令集适配为目标模型专属提示词包列表

    目标模型名优先级：显式入参 > 指令集 metadata 中的 video_model > 默认模型。
    """
    effective_model = (
        model_name or instructions.metadata.get("video_model") or DEFAULT_MODEL_NAME
    )
    adapter = get_adapter(effective_model)
    return [adapter.adapt(fragment) for fragment in instructions.fragments]
