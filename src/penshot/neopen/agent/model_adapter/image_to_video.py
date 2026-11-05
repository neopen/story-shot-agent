"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: image_to_video.py
@Description: 图生视频优先路由（M0.4.2）：按 asset_id 解析声明式资产引用
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, List, Optional

from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    PromptReference,
    RouteMode,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)

# 文字/屏幕内容特征：这些片段的文字渲染最容易出错，优先走文生图 -> 图生视频
CRITICAL_TEXT_MARKERS = (
    "text",
    "subtitle",
    "sign",
    "signage",
    "poster",
    "logo",
    "book title",
    "newspaper",
    "letter",
    "screen",
    "menu",
    "handwriting",
    "文字",
    "字幕",
    "招牌",
    "标牌",
    "海报",
    "书名",
    "报纸",
    "书信",
    "手机屏幕",
    "屏幕",
    "标题",
    "手写",
)


def has_critical_text(prompt: str) -> bool:
    """判断片段是否包含需要精确渲染的文字/屏幕内容"""
    lowered = (prompt or "").lower()
    return any(marker in lowered for marker in CRITICAL_TEXT_MARKERS)


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
) -> int:
    """为满足条件的片段标注两段式路由，返回触发片段数

    规则（M0.4.2）：
    - ``critical_text``：片段含精确文字/屏幕内容；
    - ``high_consistency``：片段主角色在契约中登记了外观锚点。
    命中后把 ``mode`` 设为 ``image_to_video``，写入 ``references`` / ``asset_ref`` /
    ``image_prompt`` / ``first_frame_instruction``，供下游直接消费。

    资产引用按 ``asset_id`` 解析：优先使用下游回填的 ``manifest``，其次使用契约
    中已有的 ``asset_ref``；仅当高一致性片段缺失必需的角色资产引用时回退到
    文生视频，避免下游拿到无法兑现的身份约束。
    """
    prompts: Dict[str, AIVideoPrompt] = {
        fragment.fragment_id: fragment for fragment in instructions.fragments
    }

    triggered = 0
    for package in packages:
        prompt = prompts.get(package.fragment_id)
        if prompt is None:
            continue

        critical = has_critical_text(prompt.prompt)
        anchors = _character_has_anchors(prompt, contract)
        if not critical and not anchors:
            continue

        asset = _find_character_asset(contract, prompt.main_character or "")
        if asset is not None:
            asset_id = str(getattr(asset, "asset_id", "") or "")
            manifest_ref = _manifest_ref(manifest, asset_id)
            contract_ref = str(getattr(asset, "asset_ref", "") or "")
            # 清单已声明该资产时以其为准；未声明才回退契约中的旧引用
            ref = contract_ref if manifest_ref is None else manifest_ref
            package.mode = RouteMode.IMAGE_TO_VIDEO
            package.references = [
                PromptReference(
                    asset_id=asset_id,
                    role="character",
                    view="front",
                    as_first_frame=True,
                    required=anchors,
                )
            ]
            package.image_prompt = str(
                getattr(asset, "image_prompt", "") or ""
            ) or f"First frame still: {prompt.prompt}"
            if ref:
                package.asset_ref = ref
                package.first_frame_instruction = (
                    f"Use reference image {ref} as the first frame; "
                    f"animate: {prompt.prompt}"
                )
            else:
                # 资产尚未落盘时保留声明式引用，由下游按 asset_id 生成后再作首帧
                package.asset_ref = ""
                package.first_frame_instruction = (
                    f"Generate asset {asset_id} with prompt: {package.image_prompt}; "
                    f"then use it as the first frame and animate: {prompt.prompt}"
                )
            triggered += 1
        elif critical:
            # 无角色资产但含关键文字：仍按首帧提示词声明，由下游生成首帧
            package.mode = RouteMode.IMAGE_TO_VIDEO
            package.references = []
            package.image_prompt = (
                f"First frame still: {prompt.prompt}. "
                "Keep character identity and composition stable."
            )
            package.first_frame_instruction = package.image_prompt
            triggered += 1
        # 仅高一致性但缺少必需角色资产：回退文生视频，不输出不可兑现的引用

    return triggered
