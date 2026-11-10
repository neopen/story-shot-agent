"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: prop_scene_asset_generator.py
@Description: 关键道具与场景锚点静帧提示词生成
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, List, Sequence

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    truncate_at_clause_boundary,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import (
    GENRE_DIMENSIONS,
    build_style_text,
)

PROP_NEGATIVE_PROMPT = "duplicate object, distorted shape, text, watermark, low quality"
SCENE_NEGATIVE_PROMPT = "people, characters, text, watermark, low quality, distorted"

PROP_MAX_PROMPT_LENGTH = 320
SCENE_MAX_PROMPT_LENGTH = 400


def _joined_length(parts: Sequence[str]) -> int:
    """计算以 ", " 拼接后的长度"""
    return len(", ".join(parts))


def _style_parts(contract: Any) -> List[str]:
    """资产风格取六维渲染结果，剔除裸题材标签（FR-054、AC-053）

    道具/场景提示词不得把 ``romance`` 这类题材键直接当画面风格；其余
    维度（打光/色板/氛围/构图/调色）与片段风格同源。
    """
    if contract is None:
        return []
    anchor = getattr(contract, "style_anchor", None) or {}
    raw_genre = str(anchor.get("genre") or "").strip().lower()
    parts: List[str] = []
    for part in build_style_text(anchor).split(","):
        value = part.strip()
        if not value:
            continue
        if value.lower() in GENRE_DIMENSIONS or value.lower() == raw_genre:
            continue
        parts.append(value)
    return parts


def _dedupe_values(values: Sequence[str]) -> List[str]:
    """按出现顺序去重，包含关系视为同一段描述（FR-052）"""
    result: List[str] = []
    for value in values:
        folded = str(value or "").strip()
        if not folded:
            continue
        lowered = folded.lower()
        if any(
            lowered in existing.lower() or existing.lower() in lowered
            for existing in result
        ):
            continue
        result.append(folded)
    return result


def _compose_prompt(
    head: str,
    values: Sequence[str],
    tail: Sequence[str],
    style: Sequence[str],
    max_length: int,
) -> str:
    """按序拼装；超限时在子句边界裁剪，不切半截词（FR-052/FR-055）"""
    parts: List[str] = [head]
    for value in _dedupe_values(values):
        if _joined_length(parts + [value, *tail]) <= max_length:
            parts.append(value)
            continue
        room = (
            max_length
            - _joined_length(parts)
            - len(", ")
            - _joined_length(tail)
            - len(", ")
        )
        truncated = truncate_at_clause_boundary(value, room) if room > 0 else ""
        if (
            truncated
            and len(truncated) < len(value)
            and _joined_length(parts + [truncated, *tail]) <= max_length
        ):
            parts.append(truncated)
        break

    parts = _dedupe_values(parts + list(tail))
    for part in _dedupe_values(style):
        if any(
            part.lower() in existing.lower() or existing.lower() in part.lower()
            for existing in parts
        ):
            continue
        if _joined_length(parts + [part]) <= max_length:
            parts.append(part)
    return ", ".join(parts)


def build_prop_specs(
    parsed_script: Any, contract: GlobalConsistencyContract
) -> List[AssetSpec]:
    """为全局关键道具构建静帧资产规格"""
    metadata = getattr(parsed_script, "global_metadata", None)
    props = getattr(metadata, "key_props", None) or []
    style = _style_parts(contract)

    specs: List[AssetSpec] = []
    for index, prop in enumerate(props, start=1):
        name = str(getattr(prop, "name", "") or "").strip()
        if not name:
            continue
        description = str(getattr(prop, "description", "") or "").strip()
        color = str(getattr(prop, "color", "") or "").strip()
        # 颜色已写在描述里时不再重复拼接（FR-052）
        values = [description]
        if color and color.lower() not in description.lower():
            values.append(f"color: {color}")
        specs.append(
            AssetSpec(
                asset_id=f"prop_{index:03d}",
                asset_type=AssetType.PROP,
                owner_name=name,
                image_prompt=_compose_prompt(
                    f"product still of {name}",
                    values,
                    ["isolated on a neutral background, sharp focus, high detail"],
                    style,
                    PROP_MAX_PROMPT_LENGTH,
                ),
                negative_prompt=PROP_NEGATIVE_PROMPT,
                usage=AssetUsage(),
                metadata={"importance": getattr(prop, "importance", "high")},
            )
        )
    return specs


def build_scene_specs(
    parsed_script: Any, contract: GlobalConsistencyContract
) -> List[AssetSpec]:
    """为每个唯一场景地点构建场景锚点静帧规格"""
    locations: List[Dict[str, Any]] = []

    for scene in getattr(parsed_script, "scenes", None) or []:
        location = str(getattr(scene, "location", "") or "").strip()
        if not location:
            continue
        # 同一地点只生成一个锚点，保留首次出现的时间/天气/描述
        if any(item["location"] == location for item in locations):
            continue
        locations.append(
            {
                "location": location,
                "time_of_day": getattr(scene, "time_of_day", None),
                "weather": getattr(scene, "weather", None),
                "description": getattr(scene, "description", None),
            }
        )

    # 场景由契约补充（解析结果缺失时仍能产出锚点）
    if not locations and contract is not None:
        for scene_contract in getattr(contract, "scenes", {}).values():
            location = str(getattr(scene_contract, "location", "") or "").strip()
            if location and not any(item["location"] == location for item in locations):
                locations.append(
                    {
                        "location": location,
                        "time_of_day": getattr(scene_contract, "time_of_day", None),
                        "weather": getattr(scene_contract, "weather", None),
                        "description": None,
                    }
                )

    visual_cues_map: Dict[str, List[str]] = {}
    metadata = getattr(parsed_script, "global_metadata", None)
    for location_item in getattr(metadata, "key_locations", None) or []:
        name = str(getattr(location_item, "name", "") or "").strip()
        if name:
            visual_cues_map[name] = [
                str(cue).strip()
                for cue in (getattr(location_item, "visual_cues", None) or [])
                if str(cue).strip()
            ]

    style = _style_parts(contract)
    specs: List[AssetSpec] = []
    for index, item in enumerate(locations, start=1):
        values: List[str] = []
        if item.get("time_of_day"):
            values.append(f"{item['time_of_day']} lighting")
        if item.get("weather"):
            values.append(str(item["weather"]))
        if item.get("description"):
            values.append(str(item["description"]))
        values.extend(visual_cues_map.get(item["location"]) or [])
        specs.append(
            AssetSpec(
                asset_id=f"scene_{index:03d}",
                asset_type=AssetType.SCENE,
                owner_name=item["location"],
                image_prompt=_compose_prompt(
                    f"establishing shot still of {item['location']}",
                    values,
                    ["cinematic composition, no people, high detail"],
                    style,
                    SCENE_MAX_PROMPT_LENGTH,
                ),
                negative_prompt=SCENE_NEGATIVE_PROMPT,
                usage=AssetUsage(scenes=[item["location"]]),
                metadata={"role": "environment_anchor"},
            )
        )
    return specs
