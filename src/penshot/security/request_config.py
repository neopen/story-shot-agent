"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: request_config.py
@Description: 请求侧配置安全处理 - 阻止外部请求覆盖服务端基础设施配置，
并统一校验批量请求中的模型提供商子项（覆盖平铺与 default/fallback 嵌套结构）。
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/17
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel

from penshot.config.config import settings
from penshot.config.config_models import (
    EmbeddingBaseConfig,
    EmbeddingConfig,
    ImageBaseConfig,
    ImageConfig,
    LLMBaseConfig,
    LLMConfig,
)
from penshot.neopen.shot_config import ShotConfig


def sanitize_shot_config(cfg: Optional[ShotConfig]) -> Optional[ShotConfig]:
    """重置请求传入的宿主机路径与数据库连接配置，防止外部请求覆盖服务端基础设施路径。"""
    if cfg is not None:
        cfg.checkpoint_dir = settings.get_data_paths().get("data_checkpoint")
        cfg.postgres_uri = None
    return cfg


def validate_provider_section(
    section: Any,
    base_cls: type[BaseModel],
    group_cls: type[BaseModel],
) -> None:
    """校验模型提供商子项（同时覆盖平铺配置与 default/fallback 嵌套结构）。"""
    if section is None:
        return
    if isinstance(section, BaseModel):
        section = section.model_dump()
    if not isinstance(section, dict):
        raise ValueError(
            f"Provider configuration must be a mapping, got {type(section).__name__}"
        )
    if "default" in section or "fallback" in section:
        nested = {k: section[k] for k in ("default", "fallback") if k in section}
        group_cls(**nested)
        if "api_key" in section:
            base_cls(api_key=section["api_key"])
        return
    base_cls(**section)


def sanitize_batch_config(
    cfg: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """剔除批量请求中可覆盖宿主机的基础设施字段，并校验 llm/embed/image 提供商子项。"""
    if isinstance(cfg, dict):
        cleaned = dict(cfg)
        cleaned.pop("checkpoint_dir", None)
        cleaned.pop("postgres_uri", None)
        validate_provider_section(cleaned.get("llm"), LLMBaseConfig, LLMConfig)
        validate_provider_section(
            cleaned.get("embed"), EmbeddingBaseConfig, EmbeddingConfig
        )
        validate_provider_section(cleaned.get("image"), ImageBaseConfig, ImageConfig)
        return cleaned
    return cfg
