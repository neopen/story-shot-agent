"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: image_to_video.py
@Description: 图生视频优先路由（M3：首帧语义、引用语义、asset_ref 收紧）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

import re
from typing import Any, Dict, List, Optional

from penshot.logger import info, warning
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    SCENE_ASSET_TYPE,
    build_first_frame_prompt,
    build_motion_prompt,
    build_package_references,
    resolve_scene_anchor,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    RouteMode,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prop_usage import advance_prop_state, mentions_prop

# 可读文字渲染证据：只有明确要求呈现文字内容时才走两段式。
# 场景里的招牌/屏幕/标牌只作氛围时不构成文字渲染需求，旧的宽子串词表会把
# “texture / exit sign / TV screen”误判为 critical_text（0.4.5 稳定版误报修复）。
READABLE_TEXT_MARKERS_ZH = (
    "文字",
    "字迹",
    "地址",
    "手写",
    "字幕",
    "招牌",
    "标牌",
    "海报",
    "书名",
    "报纸",
    "书信",
    "标题",
)

READABLE_TEXT_MARKERS_EN = (
    "text",
    "readable",
    "address",
    "handwriting",
    "subtitle",
    "newspaper",
    "poster",
    "menu",
    "title",
)

# 英文按词边界匹配，避免 texture / context 等词命中 "text"
_READABLE_TEXT_EN_RE = re.compile(
    r"\b(?:" + "|".join(READABLE_TEXT_MARKERS_EN) + r")\b", re.IGNORECASE
)


def contains_readable_text(text: str) -> bool:
    """文本是否明确要求渲染可读文字（路由与 Gate 共用的判定口径）"""
    value = str(text or "")
    if any(marker in value for marker in READABLE_TEXT_MARKERS_ZH):
        return True
    return bool(_READABLE_TEXT_EN_RE.search(value))


def has_critical_text(prompt: str) -> bool:
    """判断片段是否明确要求精确渲染可读文字"""
    return contains_readable_text(prompt)


def _character_has_anchors(prompt: AIVideoPrompt, contract: Any) -> bool:
    """角色是否在契约中登记了外观锚点（需要高强度一致性）"""
    if contract is None or not prompt.main_character:
        return False
    character = getattr(contract, "characters", {}).get(prompt.main_character)
    if character is None:
        return False
    return bool(getattr(character, "appearance_anchors", None))


def _find_character_asset(contract: Any, character_name: str) -> Optional[Any]:
    """在契约资产中查找该角色的三视图；不要求已生成（pending 由下游执行）"""
    if contract is None or not character_name:
        return None
    for asset in getattr(contract, "assets", {}).values():
        if (
            getattr(asset, "asset_type", "") == "character_sheet"
            and getattr(asset, "owner_name", "") == character_name
        ):
            return asset
    return None


def _find_scene_asset(contract: Any, scene: Any) -> Optional[Any]:
    """按场景地点查找契约中的场景资产；不要求已生成（pending 由下游执行）"""
    if contract is None or scene is None:
        return None
    location = str(getattr(scene, "location", "") or "").strip()
    if not location:
        return None
    for asset in getattr(contract, "assets", {}).values():
        if (
            getattr(asset, "asset_type", "") == SCENE_ASSET_TYPE
            and str(getattr(asset, "owner_name", "") or "").strip() == location
        ):
            return asset
    return None


def _manifest_ref(manifest: Any, asset_id: str) -> Optional[str]:
    """从下游回填清单解析资产引用

    返回 ``None`` 表示清单未声明该资产（可回退契约）；返回空字符串表示
    清单已声明但资产未生成，此时不应再使用契约中的旧引用。
    """
    if manifest is None or not asset_id:
        return None

    resolver = getattr(manifest, "get_binding", None)
    if callable(resolver):
        binding = resolver(asset_id)
        return getattr(binding, "asset_ref", "") if binding is not None else None

    if isinstance(manifest, dict):
        bindings = manifest.get("bindings") or []
        id_map = manifest.get("asset_id_map") or {}
        alias = id_map.get(asset_id, asset_id)
        for raw in bindings:
            if isinstance(raw, dict) and raw.get("asset_id") == alias:
                return str(raw.get("asset_ref") or "")
        for raw in bindings:
            if isinstance(raw, dict) and raw.get("asset_id") == asset_id:
                return str(raw.get("asset_ref") or "")
    return None


def _scene_number(scene_id: str) -> Optional[int]:
    """从 ``scene_001`` 形式提取场景序号"""
    if not scene_id:
        return None
    try:
        return int(str(scene_id).split("_")[-1])
    except (ValueError, IndexError):
        return None


def _fragment_scene_id(fragment: Any, shot_index: Dict[str, Any]) -> str:
    """解析片段所属场景ID（片段 -> 镜头 -> scene_id）"""
    if fragment is None:
        return ""
    shot = shot_index.get(str(getattr(fragment, "shot_id", "") or ""))
    if shot is None:
        return ""
    return str(getattr(shot, "scene_id", "") or "")


def _resolve_scene(
    contract: Any,
    fragment: Any,
    shot_index: Dict[str, Any],
) -> Optional[Any]:
    """按「片段 -> 镜头 -> 契约场景」解析片段的场景锚点

    缺失时返回 ``None``，由首帧构建器按提示词/角色再回退，不猜测错误场景。
    """
    scenes = getattr(contract, "scenes", None) or {}
    if not isinstance(scenes, dict):
        return None
    scene_num = _scene_number(_fragment_scene_id(fragment, shot_index))
    if scene_num is None:
        return None
    for key, scene in scenes.items():
        if str(key) == str(scene_num):
            return scene
    return None


def _scene_for_asset(contract: Any, asset_id: str) -> Optional[Any]:
    """按场景资产反查契约场景，供自动替换后重建首帧提示词"""
    assets = getattr(contract, "assets", None) or {}
    asset = assets.get(asset_id) if isinstance(assets, dict) else None
    location = str(getattr(asset, "owner_name", "") or "")
    scenes = getattr(contract, "scenes", None) or {}
    values = scenes.values() if isinstance(scenes, dict) else scenes
    for scene in values:
        if str(getattr(scene, "location", "") or "") == location:
            return scene
    return None


def _props_by_scene(parsed_script: Any) -> Dict[str, set[str]]:
    """道具引用约束：场景ID -> 该场景允许引用的道具名集合

    与 ``usage.fragments`` 使用同一 ``appears_in`` 口径，保证引用集合不会
    落在资产使用范围之外（FR-013）。
    """
    metadata = getattr(parsed_script, "global_metadata", None)
    mapping: Dict[str, set[str]] = {}
    for prop in getattr(metadata, "key_props", None) or []:
        name = str(getattr(prop, "name", "") or "").strip()
        if not name:
            continue
        for scene_id in getattr(prop, "appears_in", None) or []:
            mapping.setdefault(str(scene_id), set()).add(name)
    return mapping


def _prop_names(parsed_script: Any) -> List[str]:
    """从剧本元数据读取全局道具名（保持声明顺序）"""
    metadata = getattr(parsed_script, "global_metadata", None)
    names: List[str] = []
    for prop in getattr(metadata, "key_props", None) or []:
        name = str(getattr(prop, "name", "") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _prop_state_maps(
    prompts: Dict[str, AIVideoPrompt],
    fragments: Optional[List[Any]],
    parsed_script: Any,
) -> Dict[str, Dict[str, str]]:
    """按片段顺序推导每个道具的状态，返回 道具名 -> {片段ID: 状态}

    与 ``backfill_usage`` 共用 ``advance_prop_state`` 的单向状态机：
    frag_007 揉成团后，后续片段即使文本仍写“皱巴巴”也保持 balled。
    """
    names = _prop_names(parsed_script)
    if not names:
        return {}

    ordered: List[tuple[str, str]] = []
    for fragment in fragments or []:
        fragment_id = str(getattr(fragment, "id", "") or "")
        prompt = prompts.get(fragment_id)
        if not fragment_id or prompt is None:
            continue
        description = str(getattr(fragment, "description", "") or "")
        ordered.append((fragment_id, f"{description} {prompt.prompt}".strip()))

    result: Dict[str, Dict[str, str]] = {}
    for name in names:
        current = ""
        states: Dict[str, str] = {}
        for fragment_id, text in ordered:
            if not mentions_prop(text, name):
                continue
            current = advance_prop_state(current, text, name)
            if current:
                states[fragment_id] = current
        result[name] = states
    return result


def should_use_image_to_video(prompt: AIVideoPrompt, contract: Any = None) -> bool:
    """是否应优先使用「文生图 -> 图生视频」两段式生成"""
    if has_critical_text(prompt.prompt):
        return True
    return _character_has_anchors(prompt, contract)


def apply_image_to_video_routing(
    packages: List[AdaptedPromptPackage],
    instructions: AIVideoInstructions,
    contract: Any = None,
    manifest: Any = None,
    fragments: Optional[List[Any]] = None,
    shots: Optional[List[Any]] = None,
    parsed_script: Any = None,
) -> int:
    """为满足条件的片段标注两段式路由，返回触发片段数（FR-010/011/016）

    规则（M3）：
    - ``critical_text``：片段含精确文字/屏幕内容；
    - ``high_consistency``：片段主角色在契约中登记了外观锚点。

    命中后写入片段专属首帧提示词（场景 + 外观 + 景别 + 动作 + 风格）与
    声明式引用：角色三视图只作 ``identity_reference``，场景锚点作唯一首帧。
    ``asset_ref`` 只承载**下游回填清单中的场景首帧绑定**，角色三视图的真实
    引用不会写入 ``asset_ref``。

    Args:
        packages: 目标模型适配后的提示词包（原地修改）
        instructions: 片段提示词指令集
        contract: 全局一致性契约；提供场景、外观与资产锚点
        manifest: 下游回填清单；场景首帧 ``asset_ref`` 的唯一来源
        fragments: 可选片段序列；用于解析片段所属镜头与场景
        shots: 可选镜头序列；配合 ``fragments`` 定位场景锚点
        parsed_script: 可选剧本解析结果；按 ``appears_in`` 约束道具引用

    Returns:
        触发两段式生成的片段数
    """
    prompts: Dict[str, AIVideoPrompt] = {
        fragment.fragment_id: fragment for fragment in instructions.fragments
    }
    fragment_index = {
        str(
            getattr(fragment, "id", "") or getattr(fragment, "fragment_id", "")
        ): fragment
        for fragment in fragments or []
    }
    shot_index = {
        str(getattr(shot, "id", "")): shot
        for shot in shots or []
        if getattr(shot, "id", "")
    }
    prop_scene_map = _props_by_scene(parsed_script)
    prop_state_maps = _prop_state_maps(prompts, fragments, parsed_script)

    triggered = 0
    for package in packages:
        prompt = prompts.get(package.fragment_id)
        if prompt is None:
            continue

        fragment = fragment_index.get(package.fragment_id)
        scene = _resolve_scene(contract, fragment, shot_index)

        critical = has_critical_text(prompt.prompt)
        anchors = _character_has_anchors(prompt, contract)
        # 场景资产已覆盖该片段时同样具备可用的首帧视觉锚点，不应退化为纯文生视频
        has_scene_frame = _find_scene_asset(contract, scene) is not None
        if not critical and not anchors and not has_scene_frame:
            continue

        # 高一致性片段既缺角色三视图又无场景首帧时无法兑现身份约束，回退文生视频
        if anchors and not critical and not has_scene_frame:
            if _find_character_asset(contract, prompt.main_character or "") is None:
                continue

        allowed_props = None
        if prop_scene_map:
            scene_id = _fragment_scene_id(fragment, shot_index)
            if scene_id:
                allowed_props = sorted(prop_scene_map.get(scene_id, set()))

        package.mode = RouteMode.IMAGE_TO_VIDEO
        prop_states = {
            name: states[package.fragment_id]
            for name, states in prop_state_maps.items()
            if package.fragment_id in states
        }
        package.references = build_package_references(
            prompt,
            contract,
            scene=scene,
            fragment=fragment,
            prop_names=allowed_props,
            prop_states=prop_states,
        )
        package.image_prompt = build_first_frame_prompt(
            prompt, contract, scene=scene, fragment=fragment
        )
        package.motion_prompt = build_motion_prompt(prompt, fragment)
        motion_text = package.motion_prompt or prompt.prompt

        scene_reference = next(
            (
                reference
                for reference in package.references
                if reference.role == "first_frame" and reference.as_first_frame
            ),
            None,
        )
        # 0.4.5 任务 7：片段场景与首帧场景资产不一致时自动替换或阻断
        if scene_reference is not None:
            resolution = resolve_scene_anchor(
                prompt,
                contract,
                scene=scene,
                fragment=fragment,
                first_frame_asset_id=scene_reference.asset_id,
            )
            if resolution is not None:
                package.warnings.append(resolution.message)
                if resolution.reason == "auto_replace" and resolution.target_asset_id:
                    scene_reference.asset_id = resolution.target_asset_id
                    # 首帧提示词必须与替换后的场景资产同源，避免“资产是教室、提示词写走廊”
                    package.image_prompt = build_first_frame_prompt(
                        prompt,
                        contract,
                        scene=_scene_for_asset(contract, resolution.target_asset_id),
                        fragment=fragment,
                    )
                    info(f"场景锚定已自动替换: {resolution.message}")
                else:
                    package.status = "needs_manual_fix"
                    warning(f"场景锚定已阻断: {resolution.message}")

        scene_asset_ref = (
            _manifest_ref(manifest, scene_reference.asset_id)
            if scene_reference is not None
            else None
        )
        if scene_asset_ref:
            package.asset_ref = scene_asset_ref
            package.first_frame_instruction = (
                f"Use reference image {scene_asset_ref} as the first frame; "
                f"animate: {motion_text}"
            )
        else:
            # 场景首帧尚未回填时保留声明式首帧提示词，由下游生成后再作首帧
            package.asset_ref = ""
            package.first_frame_instruction = (
                f"Generate first frame with prompt: {package.image_prompt}; "
                f"then use it as the first frame and animate: {motion_text}"
            )
        triggered += 1

    return triggered
