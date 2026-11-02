"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: __init__.py
@Description: 目标模型适配层（M0.4.0）公共 API
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

from penshot.neopen.agent.model_adapter.capability_registry import (
    all_capabilities,
    get_capability,
    list_model_names,
    register_model,
)
from penshot.neopen.agent.model_adapter.model_adapter_factory import (
    adapt_instructions,
    get_adapter,
    resolve_model_name,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    AestheticBias,
    ModelCapability,
    RouteDecision,
    RoutePlan,
)

__all__ = [
    "ModelCapability",
    "AdaptedPromptPackage",
    "RouteDecision",
    "RoutePlan",
    "AestheticBias",
    "register_model",
    "get_capability",
    "list_model_names",
    "all_capabilities",
    "get_adapter",
    "resolve_model_name",
    "adapt_instructions",
]
