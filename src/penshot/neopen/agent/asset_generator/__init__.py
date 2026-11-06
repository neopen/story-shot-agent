"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: __init__.py
@Description: 资产锚点生成层公共 API（M0.4.2）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from penshot.neopen.agent.asset_generator.asset_generator_agent import (
    AssetGeneratorAgent,
)
from penshot.neopen.agent.asset_generator.asset_models import (
    ASSET_SCHEMA_VERSION,
    AssetBinding,
    AssetConsistency,
    AssetGenerationReport,
    AssetManifest,
    AssetPlanDocument,
    AssetPromptEdit,
    AssetSpec,
    AssetStatus,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.asset_generator.character_sheet_generator import (
    build_character_sheet_specs,
)
from penshot.neopen.agent.asset_generator.execution_adapter import (
    AssetExecutionAdapter,
    ImageClientExecutionAdapter,
)
from penshot.neopen.agent.asset_generator.prop_scene_asset_generator import (
    build_prop_specs,
    build_scene_specs,
)

__all__ = [
    "ASSET_SCHEMA_VERSION",
    "AssetBinding",
    "AssetConsistency",
    "AssetExecutionAdapter",
    "AssetGeneratorAgent",
    "AssetGenerationReport",
    "AssetManifest",
    "AssetPlanDocument",
    "AssetPromptEdit",
    "AssetSpec",
    "AssetStatus",
    "AssetType",
    "AssetUsage",
    "ImageClientExecutionAdapter",
    "build_character_sheet_specs",
    "build_prop_specs",
    "build_scene_specs",
]
