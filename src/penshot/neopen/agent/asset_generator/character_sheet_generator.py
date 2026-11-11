"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character_sheet_generator.py
@Description: 角色三视图资产提示词生成（正/侧/背）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, List, Sequence

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetConsistency,
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    APPEARANCE_FIELDS,
    extract_appearance_anchors,
    truncate_at_clause_boundary,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)

# 角色三视图统一视角：正/侧/背
CHARACTER_SHEET_VIEWS: List[str] = ["front", "side", "back"]

# 三视图只做身份参考：中性棚拍光与中性背景，禁止拼接剧情氛围打光（FR-053）
CHARACTER_SHEET_BASE_PARTS: Sequence[str] = (
    "front view, side view and back view",
    "full body",
    "neutral grey background",
    "soft even studio lighting",
    "consistent facial identity and outfit",
)

CHARACTER_SHEET_TAIL = "highly detailed character design"

CHARACTER_SHEET_MAX_PROMPT_LENGTH = 400

CHARACTER_NEGATIVE_PROMPT = (
    "multiple characters, duplicate faces, extra limbs, deformed hands, "
    "inconsistent outfit, different identity, text, watermark, low quality"
)


def _joined_length(parts: Sequence[str]) -> int:
    """计算以 ", " 拼接后的长度"""
    return len(", ".join(parts))


def _outfit_record(parsed_script: Any, character_name: str) -> Dict[str, str]:
    """提取某个角色的结构化服装记录（供契约缺失时兜底）"""
    metadata = getattr(parsed_script, "global_metadata", None)
    for outfit in getattr(metadata, "character_outfits", None) or []:
        if getattr(outfit, "character", "") != character_name:
            continue
        return {
            field_name: value
            for field_name in ("description", "color", "style", "material")
            if (value := str(getattr(outfit, field_name, "") or "").strip())
        }
    return {}


def _appearance_values(parsed_script: Any, contract: Any, name: str) -> List[str]:
    """按白名单固定顺序输出外观值；契约为空时用同一规则从解析结果兜底"""
    anchors: Dict[str, Any] = {}
    char_contract = (
        getattr(contract, "characters", {}).get(name) if contract is not None else None
    )
    if char_contract is not None:
        anchors = getattr(char_contract, "appearance_anchors", {}) or {}

    if not any(
        str(anchors.get(field_name) or "").strip() for field_name in APPEARANCE_FIELDS
    ):
        description = ""
        for char in getattr(parsed_script, "characters", None) or []:
            if getattr(char, "name", "") == name:
                description = str(getattr(char, "description", None) or "")
                break
        anchors = extract_appearance_anchors(
            description, _outfit_record(parsed_script, name)
        )

    return [
        value
        for field_name in APPEARANCE_FIELDS
        if (value := str(anchors.get(field_name) or "").strip())
    ]


def _dedupe_values(values: Sequence[str]) -> List[str]:
    """按出现顺序去重，包含关系视为同一段描述（避免服装被重复拼接）"""
    result: List[str] = []
    for value in values:
        folded = value.strip()
        if not folded:
            continue
        if any(folded in existing or existing in folded for existing in result):
            continue
        result.append(folded)
    return result


def _compose_prompt(name: str, appearance_values: Sequence[str]) -> str:
    """按固定顺序拼装提示词；超限时只在子句/字段边界裁剪，不切半截词"""
    parts: List[str] = [
        f"character reference sheet of {name}",
        *CHARACTER_SHEET_BASE_PARTS,
    ]

    for value in appearance_values:
        if (
            _joined_length(parts + [value, CHARACTER_SHEET_TAIL])
            <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
        ):
            parts.append(value)
            continue

        room = (
            CHARACTER_SHEET_MAX_PROMPT_LENGTH
            - _joined_length(parts)
            - len(", ")
            - len(", ")
            - len(CHARACTER_SHEET_TAIL)
        )
        truncated = truncate_at_clause_boundary(value, room) if room > 0 else ""
        if (
            truncated
            and len(truncated) < len(value)
            and _joined_length(parts + [truncated, CHARACTER_SHEET_TAIL])
            <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
        ):
            parts.append(truncated)
        break

    if (
        _joined_length(parts + [CHARACTER_SHEET_TAIL])
        <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
    ):
        parts.append(CHARACTER_SHEET_TAIL)
    return ", ".join(parts)


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

    specs: List[AssetSpec] = []
    for index, name in enumerate(names, start=1):
        appearance = _dedupe_values(_appearance_values(parsed_script, contract, name))
        specs.append(
            AssetSpec(
                asset_id=f"char_{index:03d}",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name=name,
                image_prompt=_compose_prompt(name, appearance),
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
