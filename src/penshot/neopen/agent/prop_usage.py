"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: prop_usage.py
@Description: 道具引用判定与状态推导（P0-1：匹配键、着装道具聚焦收敛、状态变体）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

import re
from typing import List, Optional

# 着装类道具：围巾/饰品只在该片段真正聚焦于它时才需要独立参考图，
# 其余片段它们只是角色服装描述的一部分，不应占用独立道具引用。
ACCESSORY_KEYWORDS = (
    "围巾",
    "项链",
    "戒指",
    "耳环",
    "手链",
    "手镯",
    "领带",
    "领结",
    "帽子",
    "眼镜",
    "手套",
    "胸针",
    "发卡",
    "头饰",
    "scarf",
    "necklace",
    "ring",
    "earring",
    "bracelet",
    "tie",
    "hat",
    "glove",
    "brooch",
    "glasses",
)

# 着装动词：命中说明道具被穿戴在身上，而非独立出现在画面中
_WEAR_CUES = (
    "身穿",
    "穿着",
    "围着",
    "戴着",
    "佩戴",
    "系着",
    "披着",
    "套着",
    "wearing",
    "dressed in",
    "clad in",
    "wrapped in",
)

# 聚焦线索：聚焦/细节/飘动等作用于道具本身的描述。
# “特写”只是景别，可能对着角色的脸，不能单独证明镜头聚焦于道具，
# 因此不计入这里，由 ``_is_close_up`` 另行校验景别。
_FOCAL_CUES = (
    "聚焦",
    "焦点",
    "细节",
    "飘动",
    "颤动",
    "吹起",
    "飘起",
    "抖动",
    "一角",
    "focus",
    "detail",
    "flutter",
    "trembl",
)

_CLOSE_UP_TYPES = {"close_up", "extreme_close_up", "closeup", "extreme close up"}

# 状态词表：只允许 crumpled -> balled 的单向推进，后续文本残留“皱”不回退
_BALLED_CUES = (
    "揉成团",
    "揉成一团",
    "揉成球",
    "捏成团",
    "团成一团",
    "balled",
    "into a ball",
    "ball of",
)
_CRUMPLED_CUES = (
    "皱巴巴",
    "揉皱",
    "攥皱",
    "揉得皱",
    "crumpled",
    "wrinkled",
    "creased",
)

_CLAUSE_SEPARATORS = "，,。！？!?；;\n"


def prop_match_keys(name: str) -> List[str]:
    """把道具名展开为可在文本中检索的键

    中文道具名常见“修饰语 + 的 + 核心名词”结构（如“皱巴巴的纸条”），
    片段正文往往只写核心名词（“纸条”），因此除整体名外再补核心名词。
    """
    folded = str(name or "").strip()
    if not folded:
        return []
    keys = [folded]
    if "的" in folded:
        core = folded.rsplit("的", 1)[-1].strip()
        if len(core) >= 2:
            keys.append(core)
    return list(dict.fromkeys(keys))


def _term_in_text(text: str, term: str) -> bool:
    """英文按整词匹配，中文按子串匹配（与外观/场景词表口径一致）"""
    if not term:
        return False
    if term.isascii():
        pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
        return re.search(pattern, text, re.IGNORECASE) is not None
    return term in text


def mentions_prop(text: str, name: str) -> bool:
    """片段文本是否提及该道具（含核心名词展开）"""
    return any(_term_in_text(text, key) for key in prop_match_keys(name))


def is_accessory_prop(name: str) -> bool:
    """是否为围巾/饰品等著装类道具"""
    lowered = str(name or "").lower()
    return any(keyword in lowered for keyword in ACCESSORY_KEYWORDS)


def _clauses(text: str) -> List[str]:
    """按标点切分子句，用于判断着装/聚焦线索是否与道具同句"""
    result: List[str] = []
    buffer: List[str] = []
    for char in str(text or ""):
        if char in _CLAUSE_SEPARATORS:
            result.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    result.append("".join(buffer))
    return [clause for clause in result if clause.strip()]


def _prop_clauses(text: str, name: str) -> List[str]:
    """包含该道具（或核心名词）的子句"""
    keys = prop_match_keys(name)
    return [
        clause
        for clause in _clauses(text)
        if any(_term_in_text(clause, key) for key in keys)
    ]


def is_worn_prop(text: str, name: str) -> bool:
    """道具是否以着装方式出现（同句含着装动词）"""
    return any(
        any(cue in clause.lower() for cue in _WEAR_CUES)
        for clause in _prop_clauses(text, name)
    )


def is_focal_on_prop(text: str, name: str) -> bool:
    """镜头是否聚焦于该道具（同句含焦点/细节/飘动等作用于道具本身的线索）"""
    return any(
        any(cue in clause.lower() for cue in _FOCAL_CUES)
        for clause in _prop_clauses(text, name)
    )


def _is_close_up(shot_type: str) -> bool:
    """景别是否为特写/极特写（允许缺失，缺失时不作为排除依据）"""
    normalized = str(shot_type or "").strip().lower().replace("-", "_")
    return not normalized or normalized in _CLOSE_UP_TYPES


def should_reference_prop(text: str, name: str, shot_type: str = "") -> bool:
    """片段是否需要为该道具挂载独立参考图

    - 普通道具：文本提及即引用；
    - 着装类道具：仅当片段以特写景别聚焦于它时引用，避免服装描述把围巾等
      耳饰类道具扩成整场引用（P0-1 过度引用根因）。
    """
    if not mentions_prop(text, name):
        return False
    if not is_accessory_prop(name):
        return True
    # 围巾/饰品以独立方式出现时照常引用；只有作为着装描述的一部分时，
    # 才要求镜头真正聚焦于它，避免服装句把道具引用扩成整场。
    if not is_worn_prop(text, name):
        return True
    return is_focal_on_prop(text, name) and _is_close_up(shot_type)


def advance_prop_state(previous: Optional[str], text: str, name: str = "") -> str:
    """按片段顺序推进道具状态；只允许 crumpled -> balled 单向变化

    传入 ``name`` 时只检查提及该道具的子句，避免同片段里“把纸条揉成一团”
    被误记成围巾等其它道具的状态。
    """
    scoped = ("，".join(_prop_clauses(text, name)) if name else str(text or "")).lower()
    if any(cue in scoped for cue in _BALLED_CUES):
        return "balled"
    if previous == "balled":
        return "balled"
    if any(cue in scoped for cue in _CRUMPLED_CUES):
        return "crumpled"
    return previous or ""
