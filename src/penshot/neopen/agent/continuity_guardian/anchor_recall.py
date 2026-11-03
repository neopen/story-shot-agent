"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: anchor_recall.py
@Description: 锚点召回 - 用一致性契约的角色/场景锚点构建向量检索查询
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/3
"""

from typing import Any, List, Optional


def _scene_num_from_id(scene_id: Any) -> Optional[int]:
    """从 scene_id（如 scene_003）提取场景序号"""
    if not isinstance(scene_id, str):
        return None
    digits = "".join(ch for ch in scene_id if ch.isdigit())
    return int(digits) if digits else None


def _find_shot(shot_id: Any, shot_sequence: Any) -> Any:
    """按 shot_id 查找镜头"""
    if not shot_id:
        return None
    for shot in getattr(shot_sequence, "shots", []) or []:
        if getattr(shot, "id", None) == shot_id:
            return shot
    return None


def _find_fragment(fragment_id: Any, fragment_sequence: Any) -> Any:
    """按 fragment_id 查找片段"""
    if not fragment_id:
        return None
    for fragment in getattr(fragment_sequence, "fragments", []) or []:
        if getattr(fragment, "id", None) == fragment_id:
            return fragment
    return None


def _character_parts(character: Any, contract: Any) -> List[str]:
    """构建角色名 + 契约外观锚点的查询片段"""
    if not isinstance(character, str) or not character.strip():
        return []
    name = character.strip()
    parts = [f"角色: {name}"]

    characters = getattr(contract, "characters", {}) or {}
    char_contract = characters.get(name)
    anchors = getattr(char_contract, "appearance_anchors", {}) or {}
    anchor_text = "; ".join(
        f"{key}: {value}" for key, value in anchors.items() if value
    )
    if anchor_text:
        parts.append(f"外观: {anchor_text}")
    return parts


def _scene_parts(scene_num: Optional[int], contract: Any) -> List[str]:
    """构建场景地点/时间的查询片段"""
    if scene_num is None:
        return []
    scenes = getattr(contract, "scenes", {}) or {}
    scene = scenes.get(scene_num)
    if scene is None:
        return []
    location = (getattr(scene, "location", "") or "").strip()
    time_of_day = (getattr(scene, "time_of_day", "") or "").strip()
    if not location:
        return []
    label = f"{location}（{time_of_day}）" if time_of_day else location
    return [f"场景: {label}"]


def _dedupe(parts: List[str]) -> List[str]:
    """按出现顺序去重查询片段"""
    deduped: List[str] = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return deduped


def build_fragment_anchor_query(
    fragment: Any, shot_sequence: Any, contract: Any
) -> str:
    """按片段主角色外观 + 所属场景地点/时间构建检索查询

    查询用于从剧本级提示词模板知识库召回相似的历史成功提示词，因此优先使用
    稳定锚点（角色外观、场景），再补充片段描述。

    Args:
        fragment: 视频片段（VideoFragment）
        shot_sequence: 镜头序列（用于按 shot_id 反查场景）
        contract: 全局一致性契约

    Returns:
        锚点查询文本；无契约或无可用锚点时返回空串
    """
    if fragment is None or contract is None:
        return ""

    notes = getattr(fragment, "continuity_notes", {}) or {}
    character = notes.get("main_character") if isinstance(notes, dict) else None

    parts: List[str] = []
    parts.extend(_character_parts(character, contract))

    shot = _find_shot(getattr(fragment, "shot_id", None), shot_sequence)
    if shot is not None:
        parts.extend(
            _scene_parts(_scene_num_from_id(getattr(shot, "scene_id", None)), contract)
        )

    description = (getattr(fragment, "description", "") or "").strip()
    if description:
        parts.append(f"片段: {description[:120]}")

    return " | ".join(_dedupe(parts))


def build_issue_anchor_query(
    issue: Any, fragment_sequence: Any, shot_sequence: Any, contract: Any
) -> str:
    """按连续性问题关联的角色/场景锚点构建检索查询

    在问题描述的基础上补充问题所在片段/镜头的角色外观与场景锚点，
    让历史解决方案的召回更贴近真实冲突点（而非仅依赖问题文本）。

    Args:
        issue: 连续性问题（ContinuityIssue）
        fragment_sequence: 片段序列
        shot_sequence: 镜头序列
        contract: 全局一致性契约（可为 None）

    Returns:
        锚点查询文本；问题描述本身始终保留
    """
    description = (getattr(issue, "description", "") or str(issue)).strip()
    parts: List[str] = [f"问题: {description[:200]}"] if description else []

    if contract is not None:
        fragment = _find_fragment(
            getattr(issue, "fragment_id", None), fragment_sequence
        )
        if fragment is not None:
            parts.append(build_fragment_anchor_query(fragment, shot_sequence, contract))
        else:
            shot = _find_shot(getattr(issue, "shot_id", None), shot_sequence)
            if shot is not None:
                parts.extend(
                    _character_parts(getattr(shot, "main_character", None), contract)
                )
                parts.extend(
                    _scene_parts(
                        _scene_num_from_id(getattr(shot, "scene_id", None)), contract
                    )
                )

        parts.extend(
            _scene_parts(_scene_num_from_id(getattr(issue, "scene_id", None)), contract)
        )

    return " | ".join(_dedupe(parts))
