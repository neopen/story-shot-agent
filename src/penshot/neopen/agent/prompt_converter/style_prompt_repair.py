"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

提示词风格确定性修复（0.4.7 T-115）。

风格不一致由连续性检查或 LLM 审查检出，但收敛不应依赖再次调用 LLM：
- 以多数片段的 ``prompt.style`` 为目标风格（生成期由契约风格锚点渲染）；
- 把 ``[Style: ...]`` 前缀统一为目标风格并补齐缺失片段；
- 移除与目标风格冲突的已知风格维度短语。
无任何风格来源时返回未收敛问题，由修复结论直接转人工，不做无效重试。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    DEFAULT_STYLE_DIMENSIONS,
    GENRE_DIMENSIONS,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import IssueType

_STYLE_PREFIX_RE = re.compile(r"\[Style:[^\]]*\]", re.IGNORECASE)

# 需要确定性风格修复的问题码；续写前缀兼容 ``continuity_style_inconsistent``
_STYLE_ISSUE_CODES = (
    "style_inconsistent",
    "style_missing",
    "style_invalid",
    "style_sudden_change",
    "lighting_change",
    "color_inconsistent",
)


def _known_style_phrases() -> List[str]:
    """全部已知风格维度短语，长词优先以避免部分覆盖

    只保留多词短语：单字 mood 值（dark/tense 等）与叙事形容词无法区分，
    直接删除会破坏画面内容，因此交给人工判断。
    """
    phrases = set(DEFAULT_STYLE_DIMENSIONS.values())
    for dimensions in GENRE_DIMENSIONS.values():
        phrases.update(value for value in dimensions.values() if value)
    return sorted(
        (phrase for phrase in phrases if " " in phrase), key=len, reverse=True
    )


_KNOWN_STYLE_PHRASES = _known_style_phrases()


@dataclass
class StyleRepairResult:
    """确定性风格修复结果"""

    target_style: str = ""
    actions: List[str] = field(default_factory=list)
    resolved: List[Any] = field(default_factory=list)
    unresolved: List[Any] = field(default_factory=list)


def is_style_issue(issue: Any) -> bool:
    """判断问题是否属于风格类，需要走确定性风格修复"""
    if getattr(issue, "issue_type", None) == IssueType.STYLE:
        return True
    code = str(getattr(issue, "issue_code", "") or "")
    return any(code == suffix or code.endswith(suffix) for suffix in _STYLE_ISSUE_CODES)


def resolve_target_style(instructions: AIVideoInstructions) -> str:
    """取多数片段的既有风格作为统一目标；无风格来源时返回空串"""
    counts: Dict[str, int] = {}
    for prompt in instructions.fragments:
        style = str(getattr(prompt, "style", "") or "").strip()
        if style:
            counts[style] = counts.get(style, 0) + 1
    if not counts:
        return ""
    # 计数相同时保留首次出现的风格，保证结果稳定可复现
    return max(counts, key=lambda style: counts[style])


def _remove_phrase(text: str, phrase: str) -> str:
    """移除提示词中的风格短语并清理残留分隔符"""
    pattern = re.compile(
        rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", re.IGNORECASE
    )
    updated = pattern.sub("", text)
    if updated == text:
        return text
    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"\s*,\s*", ", ", updated)
    updated = re.sub(r"(,\s*)+", ", ", updated)
    return updated.strip(" ,")


def _repair_prompt_text(text: str, target_style: str) -> tuple[str, List[str]]:
    """把风格前缀统一为目标风格并移除冲突风格短语"""
    stripped = _STYLE_PREFIX_RE.sub("", text or "").strip()
    stripped = re.sub(r"\s{2,}", " ", stripped)

    removed: List[str] = []
    for phrase in _KNOWN_STYLE_PHRASES:
        if phrase.lower() in target_style.lower():
            continue
        updated = _remove_phrase(stripped, phrase)
        if updated != stripped:
            stripped = updated
            removed.append(phrase)

    prefix = f"[Style: {target_style}]"
    return (f"{prefix} {stripped}".strip() if stripped else prefix), removed


def repair_prompt_styles(
    instructions: AIVideoInstructions,
    issues: Optional[Sequence[Any]] = None,
) -> StyleRepairResult:
    """对提示词执行确定性风格收敛

    Args:
        instructions: 提示词指令集（原地修改）
        issues: 触发本次修复的问题列表；为 None 时按全局风格收敛全部片段

    Returns:
        修复动作、已收敛问题与未收敛问题。目标风格缺失时全部问题保持未收敛，
        由调用方按人工处理记录，不做无效重试。
    """
    result = StyleRepairResult()
    style_issues = (
        [issue for issue in issues if is_style_issue(issue)]
        if issues is not None
        else []
    )
    if issues is not None and not style_issues:
        return result

    target_style = resolve_target_style(instructions)
    result.target_style = target_style
    if not target_style:
        result.unresolved = list(style_issues)
        return result

    available_ids = {prompt.fragment_id for prompt in instructions.fragments}
    flagged_ids = {
        str(getattr(issue, "fragment_id", "") or "")
        for issue in style_issues
        if getattr(issue, "fragment_id", None)
    }
    result.unresolved = [
        issue
        for issue in style_issues
        if getattr(issue, "fragment_id", None)
        and str(issue.fragment_id) not in available_ids
    ]
    unresolved_ids = {id(issue) for issue in result.unresolved}
    result.resolved = [
        issue for issue in style_issues if id(issue) not in unresolved_ids
    ]

    for prompt in instructions.fragments:
        if flagged_ids and prompt.fragment_id not in flagged_ids:
            continue
        old_style = str(getattr(prompt, "style", "") or "")
        text, removed = _repair_prompt_text(prompt.prompt or "", target_style)
        changed = text != (prompt.prompt or "") or old_style != target_style
        prompt.prompt = text
        prompt.style = target_style
        if not changed:
            continue
        detail = f"统一风格: {prompt.fragment_id} -> {target_style}"
        if removed:
            detail = f"{detail}（移除冲突短语: {', '.join(removed)}）"
        result.actions.append(detail)

    return result


def repair_style_from_codes(
    instructions: AIVideoInstructions, issue_codes: Iterable[str]
) -> StyleRepairResult:
    """按修复参数中的风格问题码触发全局风格收敛（供生成路径复用）"""
    codes = [str(code) for code in issue_codes or ()]
    if not any(
        code == suffix or code.endswith(suffix)
        for code in codes
        for suffix in _STYLE_ISSUE_CODES
    ):
        return StyleRepairResult()
    return repair_prompt_styles(instructions)
