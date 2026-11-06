"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character_sheet_generator.py
@Description: 角色三视图资产提示词生成（正/侧/背）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, List

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetConsistency,
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)

# 角色三视图统一视角：正/侧/背
CHARACTER_SHEET_VIEWS: List[str] = ["front", "side", "back"]

CHARACTER_NEGATIVE_PROMPT = (
    "multiple characters, duplicate faces, extra limbs, deformed hands, "
    "inconsistent outfit, different identity, text, watermark, low quality"
)


def _style_text(contract: Any) -> str:
    """从契约风格锚点提取英文风格描述（跳过中文）"""
    if contract is None:
        return ""
    anchor = getattr(contract, "style_anchor", None) or {}
    genre = str(anchor.get("genre") or "").strip()
    description = str(anchor.get("description") or "").strip()
    return ", ".join(part for part in (genre, description) if part)


def _outfit_text(parsed_script: Any, character_name: str) -> str:
    """从全局元数据提取角色服装描述"""
    metadata = getattr(parsed_script, "global_metadata", None)
    outfits = getattr(metadata, "character_outfits", None) or []
    for outfit in outfits:
        if getattr(outfit, "character", "") == character_name:
            parts = [
                getattr(outfit, "color", None),
                getattr(outfit, "style", None),
                getattr(outfit, "material", None),
                getattr(outfit, "description", None),
            ]
            return ", ".join(str(p) for p in parts if p)
    return ""


def _appearance_text(parsed_script: Any, contract: Any, name: str) -> str:
    """汇总角色外观锚点：契约锚点优先，其次解析结果描述与关键特征"""
    parts: List[str] = []

    char_contract = None
    if contract is not None:
        char_contract = getattr(contract, "characters", {}).get(name)
    if char_contract is not None:
        anchors: Dict[str, Any] = getattr(char_contract, "appearance_anchors", {}) or {}
        clothing = str(anchors.get("clothing") or "").strip()
        if clothing:
            parts.append(clothing)

    for char in getattr(parsed_script, "characters", None) or []:
        if getattr(char, "name", "") != name:
            continue
        description = str(getattr(char, "description", None) or "").strip()
        if description:
            parts.append(description)
        traits = getattr(char, "key_traits", None) or []
        parts.extend(str(t).strip() for t in traits if str(t).strip())

    outfit = _outfit_text(parsed_script, name)
    if outfit:
        parts.append(f"wearing {outfit}")
    return ", ".join(dict.fromkeys(p for p in parts if p))


def build_character_sheet_specs(
    parsed_script: Any, contract: GlobalConsistencyContract
) -> List[AssetSpec]:
    """为契约中的每个角色构建三视图资产规格"""
    if contract is None:
        return []

    names: List[str] = []
    for char in getattr(parsed_script, "characters", None) or []:
        name = getattr(char, "name", "")
        if name and name not in names:
            names.append(name)
    # 契约里可能有解析结果未列出的角色（来自场景元素）
    for name in getattr(contract, "characters", {}).keys():
        if name not in names:
            names.append(name)

    style = _style_text(contract)
    specs: List[AssetSpec] = []
    for index, name in enumerate(names, start=1):
        appearance = _appearance_text(parsed_script, contract, name)
        prompt_parts = [
            f"character reference sheet of {name}",
            "front view, side view and back view",
            "full body, neutral grey background",
            "consistent facial identity and outfit",
        ]
        if appearance:
            prompt_parts.append(appearance)
        if style:
            prompt_parts.append(style)
        prompt_parts.append("highly detailed character design")
        specs.append(
            AssetSpec(
                asset_id=f"char_{index:03d}",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name=name,
                image_prompt=", ".join(prompt_parts),
                negative_prompt=CHARACTER_NEGATIVE_PROMPT,
                views=list(CHARACTER_SHEET_VIEWS),
                usage=AssetUsage(characters=[name]),
                consistency=AssetConsistency(
                    identity_lock=True,
                    preferred_view=CHARACTER_SHEET_VIEWS[0],
                ),
                metadata={"role": "identity_anchor"},
            )
        )
    return specs
