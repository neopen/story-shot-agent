"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

提示词地点重写与冲突阻断（0.4.7 T-102，FR-098/FR-098a）。

以镜头计划场景为唯一事实源：提示词里出现非计划场景的地点词时，只做
确定性的地点短语替换（如 ``classroom background`` → ``corridor background``），
保留动作、人物与构图；若冲突子句包含计划场景无法承载的具体陈设
（如走廊镜头里的课桌椅、黑板），则不改写并记为阻断项，由路由阶段
标记 ``needs_manual_fix``。引号内台词提到其他地点不视为冲突。
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from penshot.logger import debug, info
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    _QUOTED_RE,
    _SCENE_LOCATION_GLOSSARY,
    _SCENE_LOCATION_SYNONYMS,
    _scene_location_terms,
    _split_clauses,
    _strip_quoted_content,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
)

_SCENE_ID_PATTERN = re.compile(r"scene_[A-Za-z0-9]+")
_LOCATION_SPLIT_PATTERN = re.compile(r"[/、·,，]")

# 场景专有陈设：冲突子句命中且计划地点不含同一陈设时必须阻断
_VENUE_FURNISHINGS: Dict[str, Tuple[str, ...]] = {
    "教室": (
        "课桌椅",
        "课桌",
        "黑板",
        "讲台",
        "desks",
        "desk",
        "blackboard",
        "chalkboard",
        "podium",
    ),
    "客厅": (
        "沙发",
        "电视",
        "茶几",
        "sofa",
        "couch",
        "television",
        "coffee table",
    ),
    "卧室": ("床", "衣柜", "bed", "wardrobe", "closet"),
    "厨房": ("灶台", "冰箱", "stove", "fridge", "refrigerator"),
    "办公室": ("办公桌", "电脑", "office desk", "computer", "laptop"),
}


@dataclass(frozen=True)
class SceneConflict:
    """未能确定性消除的地点冲突，供路由阶段阻断"""

    fragment_id: str
    term: str
    language: str
    clause: str
    reason: str
    plan_location: str = ""


@dataclass
class SceneRealignResult:
    """单片段地点重写结果"""

    prompt: str
    replaced: List[Tuple[str, str]] = field(default_factory=list)
    conflicts: List[SceneConflict] = field(default_factory=list)


# 非地点的固定搭配：地点词只作为道具/物件名出现（library card=借阅卡），
# 检测前先屏蔽这些短语，避免把道具名当成场景证据
_NON_LOCATION_COLLOCATIONS = (
    "library card",
    "library stamp",
    "library barcode",
    "street lamp",
    "street light",
    "street sign",
)


def _strip_non_location_collocations(text: str) -> str:
    """屏蔽非地点的地点词固定搭配，仅用于冲突检测，不改写原文"""
    stripped = text
    for phrase in _NON_LOCATION_COLLOCATIONS:
        stripped = re.sub(
            rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])",
            " ",
            stripped,
            flags=re.IGNORECASE,
        )
    return stripped


def _term_spans(text: str, term: str) -> List[Tuple[int, int]]:
    """返回地点词的全部命中区间（英文整词忽略大小写，中文子串）"""
    if not text or not term:
        return []
    if term.isascii():
        pattern = re.compile(
            rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE
        )
        return [match.span() for match in pattern.finditer(text)]
    spans: List[Tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return spans
        spans.append((index, index + len(term)))
        start = index + len(term)


def _span_covered(span: Tuple[int, int], covered: List[Tuple[int, int]]) -> bool:
    """命中区间是否已被更长的地点词覆盖（coffee shop 内的 shop）"""
    start, end = span
    return any(left <= start and end <= right for left, right in covered)


def _contains_term(text: str, term: str) -> bool:
    """英文整词匹配且忽略大小写，中文按子串匹配"""
    return bool(_term_spans(text, term))


def _location_family(plan_location: str) -> set[str]:
    """计划地点的同族词：中文原词、英文别名与同义别称闭环展开"""
    family = set(_scene_location_terms(plan_location))
    expanded = True
    while expanded:
        expanded = False
        groups = list(_SCENE_LOCATION_GLOSSARY.items()) + list(
            _SCENE_LOCATION_SYNONYMS.items()
        )
        for key, members in groups:
            group = {key, *members}
            if group & family and not group <= family:
                family |= group
                expanded = True
    return family


def _conflict_terms(family: set[str]) -> List[str]:
    """计划地点之外的全部已知地点词，按长词优先返回"""
    terms: set[str] = set()
    groups = list(_SCENE_LOCATION_GLOSSARY.items()) + list(
        _SCENE_LOCATION_SYNONYMS.items()
    )
    for key, members in groups:
        group = {key, *members}
        if group & family:
            continue
        terms |= group
    return sorted(terms, key=len, reverse=True)


def _plan_segments(plan_location: str) -> List[str]:
    """拆分计划的原始地点段，保留书写顺序"""
    return [
        token.strip()
        for token in _LOCATION_SPLIT_PATTERN.split(str(plan_location or ""))
        if token.strip()
    ]


def _plan_phrase(plan_location: str, family: set[str], language: str) -> Optional[str]:
    """取与冲突词同语言的计划地点短语；无法同语言表达时返回 None"""
    segments = _plan_segments(plan_location)
    if language == "zh":
        for segment in segments:
            if not segment.isascii():
                return segment
        return next((term for term in family if not term.isascii()), None)

    for segment in segments:
        if segment.isascii():
            return segment
        for key, aliases in _SCENE_LOCATION_GLOSSARY.items():
            if key == segment or (len(key) > 1 and key in segment):
                if aliases:
                    return aliases[0]
    return next((term for term in family if term.isascii()), None)


def _venue_key(term: str) -> str:
    """把地点词反查回场景词表的主键（用于专有陈设判定）"""
    for key, aliases in _SCENE_LOCATION_GLOSSARY.items():
        if term == key or term in aliases:
            return key
    for key, synonyms in _SCENE_LOCATION_SYNONYMS.items():
        if term in (key, *synonyms):
            return key
    return ""


def _clause_conflicts_with_furnishing(
    clause: str, term: str, plan_location: str
) -> bool:
    """冲突子句里的陈设是否超出计划地点承载范围"""
    furnishings = _VENUE_FURNISHINGS.get(_venue_key(term), ())
    return any(
        _contains_term(clause, item) and not _contains_term(plan_location, item)
        for item in furnishings
    )


def _replace_term_outside_quotes(text: str, term: str, replacement: str) -> str:
    """只替换引号外的地点短语，台词里的地点保持不变"""
    parts: List[str] = []
    last = 0
    for match in _QUOTED_RE.finditer(text):
        parts.append(_replace_term(text[last : match.start()], term, replacement))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_replace_term(text[last:], term, replacement))
    return "".join(parts)


def _replace_term(segment: str, term: str, replacement: str) -> str:
    """在无引号片段内替换地点词，英文保持首字母大小写风格"""
    if not term.isascii():
        return segment.replace(term, replacement)

    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)

    def substitute(match: "re.Match[str]") -> str:
        original = match.group(0)
        if original[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    return pattern.sub(substitute, segment)


def _first_clause_with_term(text: str, term: str) -> str:
    """定位冲突词所在子句，供陈设阻断与溯源使用"""
    for clause in _split_clauses(text):
        if _contains_term(clause, term):
            return clause.strip()
    return ""


def realign_scene_prompt(
    prompt: str, plan_location: str, *, fragment_id: str = ""
) -> SceneRealignResult:
    """按计划地点重写提示词中的非计划地点短语（FR-098/FR-098a）

    - 计划地点词已出现时视为一致，不做任何改写；
    - 只替换地点短语，动作、人物、构图与运镜保持原样；
    - 冲突子句含超出计划地点承载范围的专有陈设时不改写，记
      ``venue_furnishing``；
    - 计划地点无法用冲突词同语言表达时记 ``rewrite_failed``。
    """
    if not prompt or not plan_location:
        return SceneRealignResult(prompt=prompt)

    family = _location_family(plan_location)
    unquoted = _strip_non_location_collocations(_strip_quoted_content(prompt))
    # 主地点已出现时视为一致，避免把“走廊里看向教室门”改成“走廊里看向走廊门”；
    # 多段计划（如“走廊/班级记忆墙前”）只以首段作为主地点判定。
    primary = (_plan_segments(plan_location) or [plan_location])[0]
    primary_family = _location_family(primary)
    if any(_contains_term(unquoted, term) for term in primary_family):
        return SceneRealignResult(prompt=prompt)

    conflicts: List[SceneConflict] = []
    replaced: List[Tuple[str, str]] = []
    rewritten_clauses: set[str] = set()
    handled_spans: List[Tuple[int, int]] = []
    updated = prompt

    for term in _conflict_terms(family):
        # 只处理未被更长地点词覆盖的命中：coffee shop 里的 shop 不应再算一次
        spans = [
            span
            for span in _term_spans(unquoted, term)
            if not _span_covered(span, handled_spans)
        ]
        if not spans:
            continue
        handled_spans.extend(_term_spans(unquoted, term))

        clause = _first_clause_with_term(unquoted, term)
        language = "en" if term.isascii() else "zh"
        if _clause_conflicts_with_furnishing(clause, term, plan_location):
            conflicts.append(
                SceneConflict(
                    fragment_id=fragment_id,
                    term=term,
                    language=language,
                    clause=clause,
                    reason="venue_furnishing",
                    plan_location=plan_location,
                )
            )
            continue

        target = _plan_phrase(plan_location, family, language)
        if not target or target == term or clause in rewritten_clauses:
            conflicts.append(
                SceneConflict(
                    fragment_id=fragment_id,
                    term=term,
                    language=language,
                    clause=clause,
                    reason="rewrite_failed",
                    plan_location=plan_location,
                )
            )
            continue

        candidate = _replace_term_outside_quotes(updated, term, target)
        if candidate == updated:
            conflicts.append(
                SceneConflict(
                    fragment_id=fragment_id,
                    term=term,
                    language=language,
                    clause=clause,
                    reason="rewrite_failed",
                    plan_location=plan_location,
                )
            )
            continue

        updated = candidate
        replaced.append((term, target))
        rewritten_clauses.add(clause)

    return SceneRealignResult(prompt=updated, replaced=replaced, conflicts=conflicts)


def _scene_location_by_id(parsed_script: Any, scene_id: str) -> str:
    """按场景 ID 从剧本取地点"""
    getter = getattr(parsed_script, "get_scene_by_id", None)
    if not scene_id or not callable(getter):
        return ""
    scene = getter(scene_id)
    return str(getattr(scene, "location", "") or "").strip() if scene else ""


def _unique_scene_location(parsed_script: Any, hint: str) -> str:
    """地点名在剧本中唯一命中时返回完整地点，歧义或未命中返回空"""
    scenes = getattr(parsed_script, "scenes", None) or []
    if not hint or not scenes:
        return ""
    locations = {str(getattr(scene, "location", "") or "").strip() for scene in scenes}
    matches = {
        location
        for location in locations
        if location and (hint == location or hint in location or location in hint)
    }
    return next(iter(matches)) if len(matches) == 1 else ""


def _resolve_plan_location(fragment: Any, parsed_script: Any) -> str:
    """解析片段所属计划场景地点

    解析顺序：片段 ``scene_id`` → continuity_notes 的 scene_id → 剧本中
    唯一命中的地点名。任一命中即返回，均未命中返回空串。
    """
    if parsed_script is None:
        return ""

    scene_id = str(getattr(fragment, "scene_id", "") or "").strip()
    location = _scene_location_by_id(parsed_script, scene_id)
    if location:
        return location

    notes = getattr(fragment, "continuity_notes", None)
    hint = (
        str(notes.get("location", "") or "").strip() if isinstance(notes, dict) else ""
    )
    match = _SCENE_ID_PATTERN.search(hint)
    if match is not None:
        location = _scene_location_by_id(parsed_script, match.group(0))
        if location:
            return location
    return _unique_scene_location(parsed_script, hint)


def apply_scene_prompt_realignment(
    instructions: AIVideoInstructions,
    fragments: List[Any],
    parsed_script: Any,
) -> Dict[str, int]:
    """对指令集全部片段执行地点重写，结果写入 ``instructions.metadata``

    Returns:
        统计字典：``realigned``（发生替换的片段数）、``conflicts``（仍冲突的
        片段数）、``skipped``（计划地点无法解析而跳过的片段数）
    """
    fragment_index = {
        str(getattr(fragment, "id", "")): fragment for fragment in fragments or []
    }
    realigned_records: List[Dict[str, str]] = []
    conflict_records: Dict[str, List[Dict[str, str]]] = {}
    skipped_ids: List[str] = []
    stats = {"realigned": 0, "conflicts": 0, "skipped": 0}

    for prompt in instructions.fragments:
        fragment = fragment_index.get(prompt.fragment_id)
        plan_location = (
            _resolve_plan_location(fragment, parsed_script) if fragment else ""
        )
        if not plan_location:
            debug(f"地点重写跳过: {prompt.fragment_id} 计划场景地点无法解析")
            skipped_ids.append(prompt.fragment_id)
            stats["skipped"] += 1
            continue

        result = realign_scene_prompt(
            prompt.prompt, plan_location, fragment_id=prompt.fragment_id
        )
        if result.replaced:
            prompt.prompt = result.prompt
            stats["realigned"] += 1
            realigned_records.extend(
                {
                    "fragment_id": prompt.fragment_id,
                    "from": source,
                    "to": target,
                }
                for source, target in result.replaced
            )
        if result.conflicts:
            stats["conflicts"] += 1
            conflict_records[prompt.fragment_id] = [
                asdict(conflict) for conflict in result.conflicts
            ]

    instructions.metadata["scene_prompt_realigned"] = realigned_records
    instructions.metadata["scene_prompt_conflicts"] = conflict_records
    instructions.metadata["scene_prompt_realign_summary"] = {
        **stats,
        "skipped_fragment_ids": skipped_ids,
    }
    info(
        f"地点重写汇总: 改写={stats['realigned']}个片段，"
        f"冲突={stats['conflicts']}个片段，跳过={stats['skipped']}个片段"
    )
    return stats
