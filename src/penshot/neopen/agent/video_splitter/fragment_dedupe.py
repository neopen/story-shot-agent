"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: fragment_dedupe.py
@Description: 片段疑似重复检测与合并（0.4.5 FR-070~FR-074）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

import difflib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from penshot.logger import debug, warning
from penshot.neopen.agent.shot_segmenter.estimator.action_nodes import (
    compute_duration_from_text,
    count_text_dialogue_chars,
    extract_action_nodes,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)

# 相邻片段文本相似度兜底阈值（FR-070，plan 3.1）
SIMILARITY_THRESHOLD = 0.85
DEFAULT_MAX_DURATION = 5.0

# 四项结构化判定（FR-070）
CRITERIA_SHOT_TYPE = "shot_type"
CRITERIA_CHARACTER = "main_character"
CRITERIA_ACTION = "action"
CRITERIA_SCENE = "scene"

# 命中方式
MATCHED_BY_STRUCTURED = "structured"
MATCHED_BY_TEXT_SIMILARITY = "text_similarity"

# 超长片段处理动作与原因（FR-072/FR-073/FR-073a）
ACTION_RESPLIT = "resplit"
ACTION_TRUNCATE = "truncate"
REASON_ACTION_BOUNDARY = "action_boundary"
REASON_NO_BOUNDARY = "no_boundary"
REASON_DENSITY = "density"
DENSITY_WARNING = "动作密度过高导致无法在 5s 内完整保留"

_CAMERA_LEAD_RE = re.compile(
    r"^\s*[^：:\n]{0,16}(?:镜头|shot|view|angle)\s*[：:]\s*",
    re.IGNORECASE,
)
_CAMERA_MOTION_RE = re.compile(
    r"\b(?:slow|fast|smooth)?\s*"
    r"(?:push[- ]?in|pull[- ]?back|dolly(?:[ -]in|[ -]out)?|"
    r"zoom(?:[ -]in|[ -]out)?|pan(?:ning)?|tilt(?:ing)?|tracking|"
    r"handheld|crane|orbit)\b"
    r"|推镜|拉镜|跟拍|摇镜|变焦|环绕|升降|固定机位",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[\s，。、；：！？,.;:!?·…\"'“”‘’（）()\[\]【】—\-]+")

_CJK_TERMINALS = "。！？；：…」』”"
_ASCII_TERMINALS = ".!?;:"

# 重切使用的句读边界；引号内的分隔符不参与切分（FR-074）
_BOUNDARY_CHARS = frozenset("，,、；;。！？!?\n")
_QUOTE_PAIRS: Dict[str, str] = {"“": "”", '"': '"', "「": "」", "『": "』"}
_QUOTED_TEXT_RE = re.compile(r"[“\"「『]([^”\"」』]+)[”\"」』]")


@dataclass(frozen=True)
class DuplicateCandidate:
    """一对相邻片段的疑似重复判定结果"""

    prev_index: int
    index: int
    matched_by: str
    criteria: Tuple[str, ...] = ()
    similarity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典，供操作报告落盘"""
        data: Dict[str, Any] = {
            "prev_index": self.prev_index,
            "index": self.index,
            "matched_by": self.matched_by,
            "criteria": list(self.criteria),
        }
        if self.similarity is not None:
            data["similarity"] = self.similarity
        return data


@dataclass(frozen=True)
class ResplitOutcome:
    """超长疑似重复片段的处理结果"""

    fragments: List[VideoFragment]
    action: str
    reason: str
    warnings: Tuple[str, ...] = ()
    dropped_duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典，供操作报告落盘"""
        return {
            "action": self.action,
            "reason": self.reason,
            "fragment_ids": [fragment.id for fragment in self.fragments],
            "durations": [fragment.duration for fragment in self.fragments],
            "warnings": list(self.warnings),
            "dropped_duration": self.dropped_duration,
        }


def _as_optional_str(value: Any) -> Optional[str]:
    """把枚举或任意值归一为去空白字符串"""
    if value is None:
        return None
    normalized = str(getattr(value, "value", value)).strip()
    return normalized or None


def _shot_map(shots: Optional[Sequence[ShotInfo]]) -> Dict[str, ShotInfo]:
    return {shot.id: shot for shot in shots or ()}


def _resolve_context(
    fragment: VideoFragment,
    shot: Optional[ShotInfo],
) -> Tuple[Optional[str], Optional[str], Optional[str], set]:
    """解析片段的景别、角色、场景锚点与动作集合

    优先使用镜头反查结果，缺失时退回 ``continuity_notes``。
    """
    notes = fragment.continuity_notes or {}

    shot_type = _as_optional_str(fragment.shot_type)
    if shot_type is None and shot is not None:
        shot_type = _as_optional_str(shot.shot_type)

    main_character = _as_optional_str(shot.main_character) if shot else None
    if main_character is None:
        main_character = _as_optional_str(notes.get("main_character"))

    scene_id = _as_optional_str(shot.scene_id) if shot else None
    if scene_id is None:
        scene_id = _as_optional_str(notes.get("scene_id")) or _as_optional_str(
            notes.get("location")
        )

    actions = set(extract_action_nodes(fragment.description))
    if not actions:
        actions = set(
            extract_action_nodes(_as_optional_str(notes.get("main_action")) or "")
        )

    return shot_type, main_character, scene_id, actions


def _match_criteria(
    previous: Tuple[Optional[str], Optional[str], Optional[str], set],
    current: Tuple[Optional[str], Optional[str], Optional[str], set],
) -> Tuple[str, ...]:
    """按 FR-070 四项条件比较两个片段的上下文"""
    prev_type, prev_character, prev_scene, prev_actions = previous
    curr_type, curr_character, curr_scene, curr_actions = current

    criteria: List[str] = []
    if prev_type and curr_type and prev_type == curr_type:
        criteria.append(CRITERIA_SHOT_TYPE)
    if prev_character and curr_character and prev_character == curr_character:
        criteria.append(CRITERIA_CHARACTER)
    if prev_actions & curr_actions:
        criteria.append(CRITERIA_ACTION)
    if prev_scene and curr_scene and prev_scene == curr_scene:
        criteria.append(CRITERIA_SCENE)
    return tuple(criteria)


def normalize_text_for_similarity(text: str) -> str:
    """剥离景别与运镜短语，归一化提示词文本（plan 3.1 文本兜底）"""
    normalized = _CAMERA_LEAD_RE.sub("", str(text or ""))
    normalized = _CAMERA_MOTION_RE.sub(" ", normalized)
    normalized = _PUNCT_RE.sub(" ", normalized).lower()
    return " ".join(normalized.split())


def compute_text_similarity(first: str, second: str) -> float:
    """计算两个片段描述剥离运镜后的文本相似度"""
    return difflib.SequenceMatcher(
        None,
        normalize_text_for_similarity(first),
        normalize_text_for_similarity(second),
    ).ratio()


def find_duplicate_candidates(
    fragments: Sequence[VideoFragment],
    shots: Optional[Sequence[ShotInfo]] = None,
    *,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> List[DuplicateCandidate]:
    """检测相邻片段的疑似重复（FR-070）

    四项结构化条件满足任意两条即判定为候选；跨场景片段直接排除。
    当场景锚点无法解析时，退化为相邻片段文本相似度兜底。

    Args:
        fragments: 按时间顺序排列的片段列表
        shots: 来源镜头列表，用于反查景别、角色与场景锚点
        similarity_threshold: 文本兜底阈值

    Returns:
        疑似重复候选列表，索引指向 ``fragments`` 中的相邻两项
    """
    shot_lookup = _shot_map(shots)
    candidates: List[DuplicateCandidate] = []

    for index in range(1, len(fragments)):
        previous = fragments[index - 1]
        current = fragments[index]
        prev_context = _resolve_context(previous, shot_lookup.get(previous.shot_id))
        curr_context = _resolve_context(current, shot_lookup.get(current.shot_id))

        prev_scene, curr_scene = prev_context[2], curr_context[2]
        if prev_scene and curr_scene and prev_scene != curr_scene:
            # FR-070 前置条件：同属一个场景
            continue

        criteria = _match_criteria(prev_context, curr_context)
        if len(criteria) >= 2:
            candidates.append(
                DuplicateCandidate(
                    prev_index=index - 1,
                    index=index,
                    matched_by=MATCHED_BY_STRUCTURED,
                    criteria=criteria,
                )
            )
            continue

        if prev_scene and curr_scene:
            # 场景已知但结构化证据不足，不再用文本相似度放宽判定
            continue

        similarity = compute_text_similarity(previous.description, current.description)
        if similarity >= similarity_threshold:
            debug(
                f"片段{previous.id}/{current.id}文本相似度{similarity:.2f}，标记疑似重复"
            )
            candidates.append(
                DuplicateCandidate(
                    prev_index=index - 1,
                    index=index,
                    matched_by=MATCHED_BY_TEXT_SIMILARITY,
                    criteria=(MATCHED_BY_TEXT_SIMILARITY,),
                    similarity=round(similarity, 4),
                )
            )

    return candidates


def _join_descriptions(first: str, second: str) -> str:
    """按时间顺序拼接描述，保持台词跨片段时不被插入分隔符"""
    first = str(first or "").strip()
    second = str(second or "").strip()
    if not first:
        return second
    if not second:
        return first

    last = first[-1]
    if last in _CJK_TERMINALS:
        return first + second
    if last in _ASCII_TERMINALS:
        return f"{first} {second}"
    if last.isascii() and last.isalnum():
        return f"{first} {second}"
    return first + second


def _union_element_ids(
    previous: Sequence[str],
    current: Sequence[str],
) -> List[str]:
    """按出现顺序合并元素 ID，保持去重"""
    return list(dict.fromkeys([*previous, *current]))


def merge_fragments(
    previous: VideoFragment,
    current: VideoFragment,
    *,
    max_duration: float = DEFAULT_MAX_DURATION,
) -> Optional[VideoFragment]:
    """合并一对疑似重复片段（FR-071/FR-074）

    仅在两段时长之和不超过 ``max_duration`` 时合并；超限返回 ``None``，
    由重切逻辑（T-005）处理。

    Args:
        previous: 前一个片段
        current: 后一个片段
        max_duration: 合并后时长上限

    Returns:
        合并后的片段；超限时为 ``None``
    """
    total_duration = round(previous.duration + current.duration, 2)
    if total_duration > max_duration:
        return None

    metadata = dict(previous.metadata or {})
    metadata.update(
        {
            "merged_from": [previous.id, current.id],
            "merge_count": int(metadata.get("merge_count", 1))
            + int((current.metadata or {}).get("merge_count", 1)),
            "merge_total_duration": total_duration,
        }
    )

    continuity_notes = dict(previous.continuity_notes or {})
    for key, value in (current.continuity_notes or {}).items():
        continuity_notes.setdefault(key, value)

    merged = VideoFragment(
        metadata=metadata,
        id=previous.id,
        shot_id=previous.shot_id,
        element_ids=_union_element_ids(previous.element_ids, current.element_ids),
        start_time=previous.start_time,
        duration=total_duration,
        description=_join_descriptions(previous.description, current.description),
        shot_type=previous.shot_type or current.shot_type,
        continuity_notes=continuity_notes,
        requires_special_attention=(
            previous.requires_special_attention or current.requires_special_attention
        ),
    )
    debug(f"合并片段{previous.id}+{current.id}，时长{total_duration:.2f}秒")
    return merged


def merge_over_limit_warning(
    previous: VideoFragment,
    current: VideoFragment,
    *,
    max_duration: float = DEFAULT_MAX_DURATION,
) -> str:
    """生成合并超限提示，交由重切或截断流程处理"""
    total_duration = round(previous.duration + current.duration, 2)
    message = (
        f"片段{previous.id}+{current.id}疑似重复，合并时长{total_duration:.2f}秒"
        f"超过{max_duration:.1f}秒，转入重切流程"
    )
    warning(message)
    return message


def split_text_units(text: str) -> List[str]:
    """按句读边界切分文本单元，引号内的分隔符不切分

    返回的单元按顺序拼接可还原原文，用于在保持台词完整的前提下重切
    （FR-072/FR-074）。

    Args:
        text: 待切分文本

    Returns:
        文本单元列表，单元保留原句读符号
    """
    units: List[str] = []
    buffer: List[str] = []
    closing: Optional[str] = None

    for char in str(text or ""):
        buffer.append(char)
        if closing:
            if char == closing:
                closing = None
            continue
        if char in _QUOTE_PAIRS:
            closing = _QUOTE_PAIRS[char]
        elif char in _BOUNDARY_CHARS:
            unit = "".join(buffer)
            if unit.strip():
                units.append(unit)
            buffer = []

    tail = "".join(buffer)
    if tail.strip():
        units.append(tail)
    return units


def _count_quoted_chars(text: str) -> int:
    """统计引号内台词字数，供时长公式使用"""
    return count_text_dialogue_chars(text)


def _raw_duration(text: str) -> float:
    """按公式计算未夹取的时长，用于重切分组与下限判定"""
    return compute_duration_from_text(
        text,
        dialogue_chars=_count_quoted_chars(text),
        max_duration=float("inf"),
        min_duration=0.0,
    )


def _pack_units(units: Sequence[str], *, max_duration: float) -> List[List[str]]:
    """贪心装包：相邻单元累计不超过上限时归入同一子段"""
    groups: List[List[str]] = []
    current: List[str] = []

    for unit in units:
        candidate = [*current, unit]
        if current and _raw_duration("".join(candidate)) > max_duration:
            groups.append(current)
            current = [unit]
        else:
            current = candidate

    if current:
        groups.append(current)
    return groups


def _first_action(text: str) -> Optional[str]:
    actions = extract_action_nodes(text)
    return actions[0] if actions else None


def _last_action(text: str) -> Optional[str]:
    actions = extract_action_nodes(text)
    return actions[-1] if actions else None


def _boundary_actions_differ(left_text: str, right_text: str) -> bool:
    """相邻子段的核心动作是否不同（FR-072）"""
    left_action = _last_action(left_text)
    right_action = _first_action(right_text)
    if left_action is None or right_action is None:
        return True
    return left_action != right_action


def _fix_equal_action_boundaries(
    groups: List[List[str]],
    *,
    max_duration: float,
    min_duration: float,
) -> List[List[str]]:
    """边界两侧核心动作相同时，尝试移动一个单元错开（FR-072）"""
    for index in range(len(groups) - 1):
        left_text = "".join(groups[index])
        right_text = "".join(groups[index + 1])
        if _boundary_actions_differ(left_text, right_text):
            continue

        if len(groups[index + 1]) > 1:
            candidate_left = [*groups[index], groups[index + 1][0]]
            candidate_right = groups[index + 1][1:]
            if (
                _raw_duration("".join(candidate_left)) <= max_duration
                and _raw_duration("".join(candidate_right)) >= min_duration
            ):
                groups[index] = candidate_left
                groups[index + 1] = candidate_right
                continue

        if len(groups[index]) > 1:
            candidate_left = groups[index][:-1]
            candidate_right = [groups[index][-1], *groups[index + 1]]
            if (
                _raw_duration("".join(candidate_right)) <= max_duration
                and _raw_duration("".join(candidate_left)) >= min_duration
            ):
                groups[index] = candidate_left
                groups[index + 1] = candidate_right

    return groups


def _merge_short_groups(
    groups: List[List[str]],
    *,
    max_duration: float,
    min_duration: float,
) -> Optional[List[List[str]]]:
    """把低于下限的子段并入相邻同场景子段（FR-073a）

    合并后仍超上限时返回 ``None``，由调用方回退到截断逻辑。
    """
    while len(groups) > 1:
        short_index = next(
            (
                index
                for index, group in enumerate(groups)
                if _raw_duration("".join(group)) < min_duration
            ),
            None,
        )
        if short_index is None:
            return groups

        group = groups[short_index]
        merged = False

        if short_index > 0:
            combined = [*groups[short_index - 1], *group]
            if _raw_duration("".join(combined)) <= max_duration:
                groups[short_index - 1 : short_index + 1] = [combined]
                merged = True

        if not merged and short_index + 1 < len(groups):
            combined = [*group, *groups[short_index + 1]]
            if _raw_duration("".join(combined)) <= max_duration:
                groups[short_index : short_index + 2] = [combined]
                merged = True

        if not merged:
            return None

    return groups


def _source_text(
    previous: VideoFragment,
    current: VideoFragment,
    shot: Optional[ShotInfo],
) -> str:
    """优先使用同一来源镜头的原始描述，跨镜头时拼接两个片段描述"""
    if (
        shot is not None
        and previous.shot_id == current.shot_id == shot.id
        and str(shot.description or "").strip()
    ):
        return str(shot.description).strip()
    return _join_descriptions(previous.description, current.description)


def _merge_context_notes(
    previous: VideoFragment,
    current: VideoFragment,
) -> Dict[str, Any]:
    notes = dict(previous.continuity_notes or {})
    for key, value in (current.continuity_notes or {}).items():
        notes.setdefault(key, value)
    return notes


def _truncate_outcome(
    previous: VideoFragment,
    current: VideoFragment,
    *,
    source_text: str,
    total_duration: float,
    max_duration: float,
    reason: str,
    message: str,
) -> ResplitOutcome:
    """按 FR-073 保留单片段并截断超出时长"""
    kept_duration = round(min(total_duration, max_duration), 2)
    dropped_duration = round(max(0.0, total_duration - kept_duration), 2)

    metadata = dict(previous.metadata or {})
    metadata.update(
        {
            "resplit_from": [previous.id, current.id],
            "truncated_from": total_duration,
            "truncated_to": kept_duration,
            "truncate_reason": reason,
        }
    )

    fragment = VideoFragment(
        metadata=metadata,
        id=previous.id,
        shot_id=previous.shot_id,
        element_ids=_union_element_ids(previous.element_ids, current.element_ids),
        start_time=previous.start_time,
        duration=kept_duration,
        description=str(source_text or "").strip(),
        shot_type=previous.shot_type or current.shot_type,
        continuity_notes=_merge_context_notes(previous, current),
        requires_special_attention=(
            previous.requires_special_attention or current.requires_special_attention
        ),
    )
    warning(message)
    return ResplitOutcome(
        fragments=[fragment],
        action=ACTION_TRUNCATE,
        reason=reason,
        warnings=(message,),
        dropped_duration=dropped_duration,
    )


def resplit_duplicate_pair(
    previous: VideoFragment,
    current: VideoFragment,
    *,
    shot: Optional[ShotInfo] = None,
    max_duration: float = DEFAULT_MAX_DURATION,
    min_duration: float = 2.5,
) -> ResplitOutcome:
    """重切超长疑似重复片段（FR-072/FR-073/FR-073a）

    按动作、视线或台词边界重切原镜头；子段低于下限时先与相邻子段合并，
    仍无法满足时回退为截断单片段。引号内台词不参与切分。

    Args:
        previous: 前一个片段
        current: 后一个片段
        shot: 来源镜头，用于取原镜头描述
        max_duration: 子段时长上限
        min_duration: 子段时长下限

    Returns:
        重切或截断结果
    """
    total_duration = round(previous.duration + current.duration, 2)
    source_text = _source_text(previous, current, shot)
    units = split_text_units(source_text)
    meaningful = [
        unit
        for unit in units
        if extract_action_nodes(unit) or _QUOTED_TEXT_RE.search(unit)
    ]

    if len(units) < 2 or len(meaningful) < 2:
        kept_duration = round(min(total_duration, max_duration), 2)
        dropped_duration = round(max(0.0, total_duration - kept_duration), 2)
        message = (
            f"片段{previous.id}+{current.id}为超长镜头且无可识别的动作/视线/台词边界，"
            f"截断为{kept_duration:.1f}秒，丢弃{dropped_duration:.1f}秒尾部画面"
        )
        return _truncate_outcome(
            previous,
            current,
            source_text=source_text,
            total_duration=total_duration,
            max_duration=max_duration,
            reason=REASON_NO_BOUNDARY,
            message=message,
        )

    groups = _pack_units(units, max_duration=max_duration)
    groups = _fix_equal_action_boundaries(
        groups,
        max_duration=max_duration,
        min_duration=min_duration,
    )
    merged_groups = _merge_short_groups(
        groups,
        max_duration=max_duration,
        min_duration=min_duration,
    )

    if merged_groups is None:
        kept_duration = round(min(total_duration, max_duration), 2)
        dropped_duration = round(max(0.0, total_duration - kept_duration), 2)
        message = (
            f"片段{previous.id}+{current.id}{DENSITY_WARNING}，"
            f"截断为{kept_duration:.1f}秒，丢弃{dropped_duration:.1f}秒尾部画面"
        )
        return _truncate_outcome(
            previous,
            current,
            source_text=source_text,
            total_duration=total_duration,
            max_duration=max_duration,
            reason=REASON_DENSITY,
            message=message,
        )

    element_ids = _union_element_ids(previous.element_ids, current.element_ids)
    continuity_notes = _merge_context_notes(previous, current)
    fragments: List[VideoFragment] = []
    cursor = previous.start_time

    for index, group in enumerate(merged_groups):
        description = "".join(group).strip()
        duration = compute_duration_from_text(
            description,
            dialogue_chars=_count_quoted_chars(description),
            max_duration=max_duration,
            min_duration=min_duration,
        )
        metadata = dict(previous.metadata or {})
        metadata.update(
            {
                "resplit_from": [previous.id, current.id],
                "resplit_index": index + 1,
                "resplit_total": len(merged_groups),
            }
        )
        fragments.append(
            VideoFragment(
                metadata=metadata,
                id=f"{previous.id}_r{index + 1}",
                shot_id=previous.shot_id,
                element_ids=list(element_ids),
                start_time=round(cursor, 2),
                duration=duration,
                description=description,
                shot_type=previous.shot_type or current.shot_type,
                continuity_notes=dict(continuity_notes),
                requires_special_attention=(
                    previous.requires_special_attention
                    or current.requires_special_attention
                ),
            )
        )
        cursor += duration

    debug(
        f"重切片段{previous.id}+{current.id}为{len(fragments)}段，"
        f"总时长{round(cursor - previous.start_time, 2):.2f}秒"
    )
    return ResplitOutcome(
        fragments=fragments,
        action=ACTION_RESPLIT,
        reason=REASON_ACTION_BOUNDARY,
    )


def lookup_fragment_origin(
    fragment_sequence: FragmentSequence,
    fragment_id: str,
) -> Optional[Dict[str, Any]]:
    """按重编号后的片段 ID 反查来源镜头与原始片段

    Args:
        fragment_sequence: 已完成重编号的片段序列
        fragment_id: 重编号后的片段 ID（如 ``frag_001``）

    Returns:
        来源信息字典；未找到时为 ``None``
    """
    mapping = (fragment_sequence.metadata or {}).get("fragment_id_map") or {}
    return mapping.get(fragment_id)


__all__ = [
    "ACTION_RESPLIT",
    "ACTION_TRUNCATE",
    "CRITERIA_ACTION",
    "CRITERIA_CHARACTER",
    "CRITERIA_SCENE",
    "CRITERIA_SHOT_TYPE",
    "DEFAULT_MAX_DURATION",
    "DENSITY_WARNING",
    "DuplicateCandidate",
    "MATCHED_BY_STRUCTURED",
    "MATCHED_BY_TEXT_SIMILARITY",
    "REASON_ACTION_BOUNDARY",
    "REASON_DENSITY",
    "REASON_NO_BOUNDARY",
    "ResplitOutcome",
    "SIMILARITY_THRESHOLD",
    "compute_text_similarity",
    "find_duplicate_candidates",
    "lookup_fragment_origin",
    "merge_fragments",
    "merge_over_limit_warning",
    "normalize_text_for_similarity",
    "resplit_duplicate_pair",
    "split_text_units",
]
