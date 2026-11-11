"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: image_client_factory.py
@Description: 文生图客户端工厂（provider 注册表 + default/fallback）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Dict, Optional, Type

from penshot.config.config import settings
from penshot.config.config_models import ImageBaseConfig
from penshot.logger import warning
from penshot.neopen.client.image_generation.base_image_client import (
    BaseImageGenerationClient,
)
from penshot.neopen.client.image_generation.flux_client import FluxImageClient

# 供应商注册表：新增供应商只需实现 BaseImageGenerationClient 并登记
IMAGE_CLIENT_REGISTRY: Dict[str, Type[BaseImageGenerationClient]] = {
    "flux": FluxImageClient,
    "openai": FluxImageClient,
    "ideogram": FluxImageClient,
}


def get_image_client(
    config: Optional[ImageBaseConfig] = None,
) -> BaseImageGenerationClient:
    """按配置构造文生图客户端；未知供应商回退到 Flux"""
    effective = config or settings.get_image_config()
    provider = (effective.provider or "flux").lower()
    client_cls = IMAGE_CLIENT_REGISTRY.get(provider)
    if client_cls is None:
        warning(f"未注册的文生图供应商 '{provider}'，回退到 flux")
        client_cls = FluxImageClient
    return client_cls(effective)


def get_default_image_client() -> Optional[BaseImageGenerationClient]:
    """获取默认可用的文生图客户端；default 不可用时尝试 fallback，均不可用返回 None"""
    for provider in ("default", "fallback"):
        try:
            client = get_image_client(settings.get_image_config(provider))
        except Exception as e:  # 配置异常不应阻断主工作流
            warning(f"文生图客户端初始化失败（{provider}）: {e}")
            continue
        if client.is_configured():
            return client
    return None


def is_image_generation_enabled() -> bool:
    """是否具备真实文生图能力（供工作流快速短路）"""
    return get_default_image_client() is not None
