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

from typing import Any, Dict, List

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)

PROP_NEGATIVE_PROMPT = "duplicate object, distorted shape, text, watermark, low quality"
SCENE_NEGATIVE_PROMPT = "people, characters, text, watermark, low quality, distorted"


def _style_text(contract: Any) -> str:
    """从契约风格锚点提取英文风格描述"""
    if contract is None:
        return ""
    anchor = getattr(contract, "style_anchor", None) or {}
    genre = str(anchor.get("genre") or "").strip()
    description = str(anchor.get("description") or "").strip()
    return ", ".join(part for part in (genre, description) if part)


def build_prop_specs(
    parsed_script: Any, contract: GlobalConsistencyContract
) -> List[AssetSpec]:
    """为全局关键道具构建静帧资产规格"""
    metadata = getattr(parsed_script, "global_metadata", None)
    props = getattr(metadata, "key_props", None) or []
    style = _style_text(contract)

    specs: List[AssetSpec] = []
    for index, prop in enumerate(props, start=1):
        name = str(getattr(prop, "name", "") or "").strip()
        if not name:
            continue
        description = str(getattr(prop, "description", "") or "").strip()
        color = str(getattr(prop, "color", "") or "").strip()
        prompt_parts = [f"product still of {name}"]
        if description:
            prompt_parts.append(description)
        if color:
            prompt_parts.append(f"color: {color}")
        prompt_parts.append("isolated on a neutral background, sharp focus, high detail")
        if style:
            prompt_parts.append(style)
        specs.append(
            AssetSpec(
                asset_id=f"prop_{index:03d}",
                asset_type=AssetType.PROP,
                owner_name=name,
                image_prompt=", ".join(prompt_parts),
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

    style = _style_text(contract)
    specs: List[AssetSpec] = []
    for index, item in enumerate(locations, start=1):
        prompt_parts = [f"establishing shot still of {item['location']}"]
        if item.get("time_of_day"):
            prompt_parts.append(f"{item['time_of_day']} lighting")
        if item.get("weather"):
            prompt_parts.append(str(item["weather"]))
        if item.get("description"):
            prompt_parts.append(str(item["description"]))
        cues = visual_cues_map.get(item["location"]) or []
        if cues:
            prompt_parts.append(", ".join(cues))
        prompt_parts.append("cinematic composition, no people, high detail")
        if style:
            prompt_parts.append(style)
        specs.append(
            AssetSpec(
                asset_id=f"scene_{index:03d}",
                asset_type=AssetType.SCENE,
                owner_name=item["location"],
                image_prompt=", ".join(prompt_parts),
                negative_prompt=SCENE_NEGATIVE_PROMPT,
                usage=AssetUsage(scenes=[item["location"]]),
                metadata={"role": "environment_anchor"},
            )
        )
    return specs
