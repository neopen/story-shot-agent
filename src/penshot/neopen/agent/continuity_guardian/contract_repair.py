"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: contract_repair.py
@Description: 契约驱动修复 - 将 Validator 违规项与契约锚点转换为 Repairer 修复参数
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/3
"""

from typing import Any, Dict, List, Optional

from penshot.neopen.agent.character_names import normalize_character_name
from penshot.neopen.agent.continuity_guardian.anchor_recall import (
    _scene_num_from_id,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import build_style_prefix
from penshot.neopen.agent.quality_auditor.quality_auditor_enum import SeverityLevel
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityRepairParams,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode

# 单个修复键最多保留的建议条数，避免重复问题让 prompt 过度膨胀
_MAX_SUGGESTIONS_PER_KEY = 5
# 契约违规项审计列表上限（保留最近 N 条）
_MAX_VIOLATIONS = 50
# 建议中最多列举的角色/镜头数量
_MAX_LISTED_ITEMS = 8

# Validator 违规项中的阶段名 -> 工作流节点
_CONTRACT_STAGE_MAP: Dict[str, PipelineNode] = {
    PipelineNode.PARSE_SCRIPT.value: PipelineNode.PARSE_SCRIPT,
    PipelineNode.SEGMENT_SHOT.value: PipelineNode.SEGMENT_SHOT,
    PipelineNode.SPLIT_VIDEO.value: PipelineNode.SPLIT_VIDEO,
    PipelineNode.CONVERT_PROMPT.value: PipelineNode.CONVERT_PROMPT,
}


def _text(value: Any) -> str:
    """安全读取文本（非字符串返回空串）"""
    return value.strip() if isinstance(value, str) else ""


def _known_characters(contract: Any) -> List[str]:
    """提取契约中已登记的角色名（保持稳定排序，便于提示词复现）"""
    characters = getattr(contract, "characters", {}) or {}
    return sorted(name for name in characters if _text(name))


def _shot_ids(shot_sequence: Any) -> List[str]:
    """提取镜头序列中的有效镜头 ID"""
    return [
        _text(getattr(shot, "id", None))
        for shot in getattr(shot_sequence, "shots", []) or []
        if _text(getattr(shot, "id", None))
    ]


def _violation_key(violation: Dict[str, Any]) -> tuple:
    """契约违规项去重键"""
    return (
        _text(violation.get("type")),
        _text(violation.get("shot_id")),
        _text(violation.get("fragment_id")),
        _text(violation.get("character")),
    )


def describe_character_anchors(contract: Any, character: Any) -> str:
    """把角色契约中的外观锚点描述为修复约束文本

    Args:
        contract: 全局一致性契约
        character: 角色名

    Returns:
        契约约束文本；无角色契约或无可用锚点时返回空串
    """
    name = _text(character)
    if not name or contract is None:
        return ""

    char_contract = (getattr(contract, "characters", {}) or {}).get(name)
    if char_contract is None:
        return ""

    anchors = getattr(char_contract, "appearance_anchors", {}) or {}
    anchor_text = "、".join(f"{key}={value}" for key, value in anchors.items() if value)

    asset_ref = ""
    for asset in (getattr(contract, "assets", {}) or {}).values():
        if (
            getattr(asset, "asset_type", "") == "character_sheet"
            and getattr(asset, "owner_name", "") == name
        ):
            asset_ref = _text(getattr(asset, "asset_ref", ""))
            if asset_ref:
                break

    parts: List[str] = []
    if anchor_text:
        parts.append(f"外观：{anchor_text}")
    if asset_ref:
        parts.append(f"参考资产：{asset_ref}")
    if not parts:
        return ""
    return f"角色「{name}」契约锚点（{'，'.join(parts)}），所有片段必须保持一致"


def describe_style_anchors(contract: Any) -> str:
    """把契约风格锚点描述为修复约束文本"""
    if contract is None:
        return ""
    prefix = build_style_prefix(getattr(contract, "style_anchor", None))
    if not prefix:
        return ""
    return f"风格契约锚点 {prefix}，所有片段视觉风格必须统一"


def describe_scene_anchors(contract: Any, scene_id: Any) -> str:
    """把契约场景锚点描述为修复约束文本"""
    if contract is None:
        return ""
    scenes = getattr(contract, "scenes", {}) or {}
    scene = scenes.get(_scene_num_from_id(scene_id))
    if scene is None:
        return ""

    location = _text(getattr(scene, "location", ""))
    time_of_day = _text(getattr(scene, "time_of_day", ""))
    if not location:
        return ""
    label = f"{location}（{time_of_day}）" if time_of_day else location
    return f"场景契约锚点「{label}」，地点与时间必须保持一致"


def describe_prop_anchors(contract: Any, description: Any) -> str:
    """把契约中的道具资产锚点描述为修复约束文本

    仅当问题描述中出现已登记道具名时才返回约束，避免无关注入。
    """
    text = _text(description)
    if not text or contract is None:
        return ""

    for asset in (getattr(contract, "assets", {}) or {}).values():
        if getattr(asset, "asset_type", "") != "prop":
            continue
        owner = _text(getattr(asset, "owner_name", ""))
        if not owner or owner not in text:
            continue
        ref = _text(getattr(asset, "asset_ref", "")) or _text(
            getattr(asset, "image_prompt", "")
        )
        hint = f"道具「{owner}」契约锚点"
        if ref:
            hint = f"{hint}（{ref}）"
        return f"{hint}，外观与状态必须保持一致"
    return ""


def merge_violations(
    existing: Optional[List[Dict[str, Any]]],
    new: Optional[List[Dict[str, Any]]],
    max_items: int = _MAX_VIOLATIONS,
) -> List[Dict[str, Any]]:
    """合并契约违规项并去重（相同类型/镜头/片段/角色视为同一条）"""
    merged: List[Dict[str, Any]] = list(existing or [])
    seen = {_violation_key(violation) for violation in merged}
    for violation in new or []:
        key = _violation_key(violation)
        if key in seen:
            continue
        seen.add(key)
        merged.append(violation)
    return merged[-max_items:]


def group_violations_by_stage(
    violations: Optional[List[Dict[str, Any]]],
) -> Dict[PipelineNode, List[Dict[str, Any]]]:
    """按违规项中的 stage 字段分组，供各阶段消费修复参数"""
    grouped: Dict[PipelineNode, List[Dict[str, Any]]] = {}
    for violation in violations or []:
        stage = _CONTRACT_STAGE_MAP.get(_text(violation.get("stage")))
        if stage is None:
            continue
        grouped.setdefault(stage, []).append(violation)
    return grouped


def _suggestion_key(violation: Dict[str, Any]) -> str:
    """修复建议的键：优先片段 ID，其次镜头 ID，否则 global"""
    return (
        _text(violation.get("fragment_id"))
        or _text(violation.get("shot_id"))
        or "global"
    )


def _build_suggestion(
    violation: Dict[str, Any],
    contract: Any,
    shot_sequence: Any,
    parsed_script: Any = None,
) -> str:
    """针对单条契约违规项构建可执行的修复建议"""
    violation_type = _text(violation.get("type"))
    key = _suggestion_key(violation)
    prefix = f"{key}：" if key != "global" else ""

    if violation_type == "unknown_character":
        character = _text(violation.get("character")) or "未知角色"
        known = _known_characters(contract)
        known_text = "、".join(known[:_MAX_LISTED_ITEMS]) if known else "无"
        parts = [f"{prefix}角色「{character}」未登记到一致性契约"]
        if known:
            parts.append(f"仅允许使用契约角色：{known_text}")
        anchor = describe_character_anchors(contract, character)
        if anchor:
            parts.append(anchor)
        if parsed_script is not None:
            parsed_names = {
                normalize_character_name(getattr(char, "name", None))
                for char in getattr(parsed_script, "characters", []) or []
            }
            if character in parsed_names:
                parts.append("该角色已在剧本角色表中，将补登记进契约并保留")
            else:
                parts.append(
                    "该角色不在剧本角色表中，属分镜生成幻觉；修复时将清除其主角色"
                    "标注，画面描述中的形象予以保留"
                )
        else:
            parts.append("如需保留该角色，应先补充契约角色登记与外观锚点")
        return "；".join(parts)

    if violation_type == "orphan_fragment":
        fragment_id = _text(violation.get("fragment_id")) or "未知片段"
        shot_id = _text(violation.get("shot_id")) or "未知镜头"
        valid = _shot_ids(shot_sequence)
        valid_text = "、".join(valid[:_MAX_LISTED_ITEMS]) if valid else "无"
        return (
            f"片段 {fragment_id} 关联的镜头 {shot_id} 不存在；"
            f"请重新关联到有效镜头：{valid_text}"
        )

    message = _text(violation.get("message"))
    if message:
        return f"{prefix}{message}"
    return f"{prefix}违反一致性契约，请按契约角色/场景/风格锚点修复"


def build_contract_repair_params(
    violations: Optional[List[Dict[str, Any]]],
    stage: PipelineNode,
    contract: Any = None,
    shot_sequence: Any = None,
    parsed_script: Any = None,
) -> Optional[QualityRepairParams]:
    """把契约违规项转换为 Repairer 可直接消费的修复参数

    Args:
        violations: Validator 产出的违规项字典列表
        stage: 目标修复阶段
        contract: 全局一致性契约（用于补充角色/场景/风格锚点）
        shot_sequence: 镜头序列（用于列举有效镜头，修复孤立片段）
        parsed_script: 结构化剧本（用于区分剧本真实角色与生成幻觉，给出准确建议）

    Returns:
        修复参数；无违规项时返回 None
    """
    if not violations:
        return None

    issue_types: List[str] = []
    fragments: List[str] = []
    suggestions: Dict[str, List[str]] = {}

    for violation in violations:
        issue_type = _text(violation.get("type")) or "contract_violation"
        if issue_type not in issue_types:
            issue_types.append(issue_type)

        key = _suggestion_key(violation)
        fragment_id = _text(violation.get("fragment_id"))
        if fragment_id and fragment_id not in fragments:
            fragments.append(fragment_id)

        suggestion = _build_suggestion(
            violation, contract, shot_sequence, parsed_script
        )
        bucket = suggestions.setdefault(key, [])
        if suggestion and suggestion not in bucket:
            if len(bucket) < _MAX_SUGGESTIONS_PER_KEY:
                bucket.append(suggestion)

    return QualityRepairParams(
        fix_needed=True,
        issue_count=len(violations),
        issue_types=issue_types,
        issues=list(violations),
        fragments=fragments,
        suggestions=suggestions,
        severity_summary={SeverityLevel.MODERATE.value: len(violations)},
    )


def merge_repair_params(
    base: Optional[QualityRepairParams], extra: Optional[QualityRepairParams]
) -> Optional[QualityRepairParams]:
    """合并两份修复参数（问题类型/片段/建议去重，计数累加）"""
    if base is None:
        return extra
    if extra is None:
        return base

    suggestions: Dict[str, List[str]] = {}
    for source in (base.suggestions or {}, extra.suggestions or {}):
        for key, values in source.items():
            bucket = suggestions.setdefault(key, [])
            for value in values or []:
                if value and value not in bucket:
                    bucket.append(value)

    severity_summary: Dict[str, int] = {}
    for source in (base.severity_summary or {}, extra.severity_summary or {}):
        for key, value in source.items():
            severity_summary[key] = severity_summary.get(key, 0) + (value or 0)

    return QualityRepairParams(
        fix_needed=bool(base.fix_needed or extra.fix_needed),
        issue_count=(base.issue_count or 0) + (extra.issue_count or 0),
        issue_types=list(
            dict.fromkeys([*(base.issue_types or []), *(extra.issue_types or [])])
        ),
        issues=list(base.issues or []) + list(extra.issues or []),
        fragments=list(
            dict.fromkeys([*(base.fragments or []), *(extra.fragments or [])])
        ),
        suggestions=suggestions,
        severity_summary=severity_summary,
    )
