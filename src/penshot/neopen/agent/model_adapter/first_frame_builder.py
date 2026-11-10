"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: first_frame_builder.py
@Description: 片段专属首帧提示词与资产引用语义（M3：T-301/T-302）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

import re
from typing import Any, Dict, List, Optional

from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    APPEARANCE_FIELDS,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import build_style_text
from penshot.neopen.agent.model_adapter.model_models import PromptReference
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
)

# 景别短语：键与 CameraControl.shot_type / ShotType.value 归一值一致
SHOT_PHRASES: Dict[str, str] = {
    "close_up": "close-up shot",
    "extreme_close_up": "extreme close-up shot",
    "wide_shot": "wide shot",
    "long_shot": "long shot",
    "medium_shot": "medium shot",
    "over_shoulder": "over-the-shoulder shot",
    "pov": "POV shot",
    "two_shot": "two-shot",
}

_STYLE_PREFIX_PATTERN = re.compile(r"^\[Style:[^\]]*\]\s*")

# 天气为晴时不再重复声明，避免首帧提示词堆叠无信息短语
_NEUTRAL_WEATHER = ("", "clear", "clear weather", "sunny")

CHARACTER_SHEET_TYPE = "character_sheet"
SCENE_ASSET_TYPE = "scene"
PROP_ASSET_TYPE = "prop"


def _attr(source: Any, name: str, default: str = "") -> str:
    """读取 dataclass / 字典字段并归一为字符串"""
    if source is None:
        return default
    value = getattr(source, name, None)
    if value is None and isinstance(source, dict):
        value = source.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _contract_assets(contract: Any, asset_type: str) -> List[Any]:
    """按类型筛选契约中的资产锚点"""
    assets = getattr(contract, "assets", None) or {}
    values = assets.values() if isinstance(assets, dict) else assets
    return [
        asset
        for asset in values
        if _attr(asset, "asset_type") == asset_type and _attr(asset, "asset_id")
    ]


def _contract_scenes(contract: Any) -> List[Any]:
    """读取契约中的场景（按场景号排序，保证结果稳定）"""
    scenes = getattr(contract, "scenes", None) or {}
    if isinstance(scenes, dict):
        return [scenes[key] for key in sorted(scenes, key=str)]
    return list(scenes)


def _resolve_scene(
    contract: Any,
    prompt: AIVideoPrompt,
    scene: Any = None,
) -> Optional[Any]:
    """解析片段所属场景

    优先使用调用方显式传入的场景（T-303 由镜头 -> 场景映射提供）；缺失时
    回退契约场景：先按地点词命中片段提示词，再按主角色唯一出现的场景判断。
    无法唯一确定时返回 ``None``，不猜测错误场景而污染首帧提示词。
    """
    if scene is not None:
        return scene

    candidates = _contract_scenes(contract)
    if not candidates:
        return None

    prompt_text = _attr(prompt, "prompt")
    matched = [
        item
        for item in candidates
        if _attr(item, "location") and _attr(item, "location") in prompt_text
    ]
    if len(matched) == 1:
        return matched[0]

    main_character = _attr(prompt, "main_character")
    if main_character:
        pool = matched or candidates
        character_scenes = [
            item
            for item in pool
            if main_character in (getattr(item, "characters_in_scene", None) or [])
        ]
        if len(character_scenes) == 1:
            return character_scenes[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _shot_phrase(prompt: AIVideoPrompt, fragment: Any) -> str:
    """景别短语：结构化相机参数 > 来源片段景别 > 中景兜底"""
    camera = getattr(prompt, "camera", None)
    shot_type = _attr(camera, "shot_type") or _attr(fragment, "shot_type")
    return SHOT_PHRASES.get(shot_type.lower(), "medium shot")


def _appearance_text(contract: Any, character_name: str) -> str:
    """角色白名单外观锚点（顺序固定，与三视图同源）"""
    if contract is None or not character_name:
        return ""
    characters = getattr(contract, "characters", None) or {}
    character = characters.get(character_name) if isinstance(characters, dict) else None
    anchors = getattr(character, "appearance_anchors", None) or {}
    parts = [
        f"{field_name}: {anchors[field_name]}"
        for field_name in APPEARANCE_FIELDS
        if anchors.get(field_name)
    ]
    return ", ".join(parts)


def _action_text(prompt: AIVideoPrompt, fragment: Any) -> str:
    """片段动作：优先来源片段描述，回退提示词正文（剥离风格前缀）"""
    description = _attr(fragment, "description")
    if description:
        return description
    return _STYLE_PREFIX_PATTERN.sub("", _attr(prompt, "prompt")).strip()


def build_first_frame_prompt(
    prompt: AIVideoPrompt,
    contract: Any = None,
    scene: Any = None,
    fragment: Any = None,
) -> str:
    """构建片段专属首帧静帧提示词（FR-011、AC-011）

    组成顺序：景别短语 -> 角色（白名单外观） -> 场景地点/时间/天气 ->
    片段动作 -> 风格维度。与角色三视图提示词（固定 turnaround 棚拍表述）
    结构不同，保证 ``image_prompt`` 不会等于三视图提示词。

    Args:
        prompt: 片段提示词；读取 ``main_character`` / ``camera`` / ``prompt``
        contract: 全局一致性契约；提供外观锚点、场景与风格锚点
        scene: 可选已解析场景（具备 location/time_of_day/weather 字段）
        fragment: 可选来源片段；提供 ``description`` 与 ``shot_type``

    Returns:
        英文为主的首帧静帧提示词；无任何上下文时仍包含片段动作
    """
    resolved_scene = _resolve_scene(contract, prompt, scene)
    main_character = _attr(prompt, "main_character")
    location = _attr(resolved_scene, "location")

    subject = main_character
    appearance = _appearance_text(contract, main_character)
    if appearance:
        subject = f"{subject} ({appearance})"
    parts: List[str] = [f"{_shot_phrase(prompt, fragment)} of {subject or 'the scene'}"]

    # 场景地点独立声明：FR-011 要求首帧同时锚定角色与所处环境
    if location:
        parts.append(f"at {location}")

    time_of_day = _attr(resolved_scene, "time_of_day")
    if time_of_day:
        parts.append(f"{time_of_day} lighting")

    weather = _attr(resolved_scene, "weather")
    if weather.lower() not in _NEUTRAL_WEATHER:
        parts.append(weather)

    action = _action_text(prompt, fragment)
    if action:
        parts.append(f"action: {action}")

    if contract is not None:
        style_text = build_style_text(
            getattr(contract, "style_anchor", None),
            getattr(contract, "style_anchor_provenance", None),
        )
        if style_text:
            parts.append(style_text)

    return ", ".join(parts)


def build_package_references(
    prompt: AIVideoPrompt,
    contract: Any = None,
    scene: Any = None,
    fragment: Any = None,
    prop_names: Optional[List[str]] = None,
) -> List[PromptReference]:
    """构建片段的声明式资产引用语义（FR-010/016、AC-010）

    - 角色三视图：``role="identity_reference"``、``as_first_frame=False``；
    - 场景锚点：``role="first_frame"``、``as_first_frame=True``；
    - 道具静帧：``role="prop"``、``as_first_frame=False``。

    仅引用契约中已声明的资产；未声明资产不凭空造 ID。``prop_names`` 传入
    时按场景约束过滤道具（与 ``usage.fragments`` 同一口径，避免引用落在
    使用范围之外）；未传入时按片段文本匹配。

    Args:
        prompt: 片段提示词
        contract: 全局一致性契约
        scene: 可选已解析场景
        fragment: 可选来源片段
        prop_names: 允许引用的道具名集合；``None`` 表示按文本匹配

    Returns:
        声明式资产引用列表
    """
    if contract is None:
        return []

    references: List[PromptReference] = []
    main_character = _attr(prompt, "main_character")

    for asset in _contract_assets(contract, CHARACTER_SHEET_TYPE):
        if main_character and _attr(asset, "owner_name") == main_character:
            references.append(
                PromptReference(
                    asset_id=_attr(asset, "asset_id"),
                    role="identity_reference",
                    view="front",
                    as_first_frame=False,
                    required=True,
                )
            )

    resolved_scene = _resolve_scene(contract, prompt, scene)
    location = _attr(resolved_scene, "location")
    if location:
        for asset in _contract_assets(contract, SCENE_ASSET_TYPE):
            if _attr(asset, "owner_name") == location:
                references.append(
                    PromptReference(
                        asset_id=_attr(asset, "asset_id"),
                        role="first_frame",
                        view="front",
                        as_first_frame=True,
                        required=True,
                    )
                )

    text = f"{_attr(fragment, 'description')} {_attr(prompt, 'prompt')}"
    allowed_props = set(prop_names) if prop_names is not None else None
    for asset in _contract_assets(contract, PROP_ASSET_TYPE):
        owner_name = _attr(asset, "owner_name")
        if not owner_name:
            continue
        if allowed_props is not None:
            matched = owner_name in allowed_props
        else:
            matched = owner_name in text
        if matched:
            references.append(
                PromptReference(
                    asset_id=_attr(asset, "asset_id"),
                    role="prop",
                    view="front",
                    as_first_frame=False,
                    required=False,
                )
            )

    return references
