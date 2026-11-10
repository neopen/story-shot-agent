"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: contract_validator.py
@Description: 一致性契约校验器（Validator）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/3
"""

from typing import Any, Dict, List

from penshot.neopen.agent.character_names import normalize_character_name


def _known_characters(contract: Any) -> set[str]:
    """提取契约中已登记的角色名集合（已归一化）"""
    characters = getattr(contract, "characters", {}) or {}
    known = {normalize_character_name(name) for name in characters}
    known.discard("")
    return known


def validate_shot_sequence(shot_sequence: Any, contract: Any) -> List[Dict[str, Any]]:
    """校验镜头序列是否违反一致性契约

    当前校验项：镜头主角色必须属于契约已登记的角色集合，否则视为"未知角色"
    （典型为 LLM 幻觉出的新角色，会破坏跨片段一致性）。

    Args:
        shot_sequence: 镜头序列（ShotSequence）
        contract: 全局一致性契约（GlobalConsistencyContract，可为 None）

    Returns:
        违规项列表，每项为可序列化字典
    """
    issues: List[Dict[str, Any]] = []
    if contract is None or shot_sequence is None:
        return issues

    known_characters = _known_characters(contract)
    for shot in getattr(shot_sequence, "shots", []) or []:
        character = normalize_character_name(getattr(shot, "main_character", None))
        if character and character not in known_characters:
            shot_id = getattr(shot, "id", None)
            issues.append(
                {
                    "type": "unknown_character",
                    "stage": "segment_shot",
                    "shot_id": shot_id,
                    "character": character,
                    "message": f"镜头 {shot_id} 的角色 {character} 不在一致性契约中",
                }
            )
    return issues


def validate_fragment_sequence(
    fragment_sequence: Any, shot_sequence: Any, contract: Any
) -> List[Dict[str, Any]]:
    """校验片段序列是否违反一致性契约

    校验项：
    1. orphan_fragment：片段必须能关联到有效镜头
    2. unknown_character：片段所属镜头的主角色必须属于契约角色集合

    Args:
        fragment_sequence: 片段序列（FragmentSequence）
        shot_sequence: 镜头序列（用于按 shot_id 反查主角色）
        contract: 全局一致性契约（可为 None）

    Returns:
        违规项列表
    """
    issues: List[Dict[str, Any]] = []
    if contract is None or fragment_sequence is None:
        return issues

    known_characters = _known_characters(contract)
    shot_by_id = {
        getattr(shot, "id", None): shot
        for shot in getattr(shot_sequence, "shots", []) or []
    }

    for fragment in getattr(fragment_sequence, "fragments", []) or []:
        shot_id = getattr(fragment, "shot_id", None)
        fragment_id = getattr(fragment, "id", None)

        shot = shot_by_id.get(shot_id)
        if shot is None:
            issues.append(
                {
                    "type": "orphan_fragment",
                    "stage": "split_video",
                    "fragment_id": fragment_id,
                    "shot_id": shot_id,
                    "message": f"片段 {fragment_id} 关联的镜头 {shot_id} 不存在",
                }
            )
            continue

        character = normalize_character_name(getattr(shot, "main_character", None))
        if character and character not in known_characters:
            issues.append(
                {
                    "type": "unknown_character",
                    "stage": "split_video",
                    "fragment_id": fragment_id,
                    "character": character,
                    "message": f"片段 {fragment_id} 的角色 {character} 不在一致性契约中",
                }
            )
    return issues
