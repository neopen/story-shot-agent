"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: __init__.py
@Description: 文生图客户端公共 API（M0.4.2）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from penshot.neopen.client.image_generation.base_image_client import (
    BaseImageGenerationClient,
    ImagePayload,
    resolve_asset_dir,
)
from penshot.neopen.client.image_generation.flux_client import FluxImageClient
from penshot.neopen.client.image_generation.image_client_factory import (
    IMAGE_CLIENT_REGISTRY,
    get_default_image_client,
    get_image_client,
    is_image_generation_enabled,
)
from penshot.neopen.client.image_generation.image_models import (
    ImageGenerationRequest,
    ImageGenerationResult,
)

__all__ = [
    "BaseImageGenerationClient",
    "ImagePayload",
    "FluxImageClient",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "IMAGE_CLIENT_REGISTRY",
    "get_image_client",
    "get_default_image_client",
    "is_image_generation_enabled",
    "resolve_asset_dir",
]
