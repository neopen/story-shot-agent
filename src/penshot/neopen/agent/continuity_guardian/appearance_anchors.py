"""
@FileName: appearance_anchors.py
@Description: 角色外观锚点共享模块 - 子句切分、白名单分类、规范化与子句边界截断
@Author: HiPeng
@Time: 2026/11/9

设计约束（0.4.4 Spec FR-001..FR-005）：
    - 结构化的 `character_outfits` 优先于角色自由文本；
    - 自由文本只保留外观类子句，排除情绪/表情/表演/动作/道具/场景子句；
    - 只允许白名单字段，同一字段首值优先（保证跨片段一致）；
    - 长度限制只在子句边界生效，禁止字符级截断产生半截词。

中英文支持：
    - 词表按语言分组维护在 `constants.appearance`；
    - 中文按子串匹配，英文按单词边界匹配并容忍常见屈折后缀；
    - 切句、规范化、拼接按文本语言自动选择分隔符（中文“，”/ 英文“, ”）。
"""

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from penshot.neopen.constants.appearance import (
    ACCESSORY_KEYWORDS,
    ACCESSORY_ONLY_KEYWORDS,
    BODY_KEYWORDS,
    EXCLUDE_KEYWORDS,
    FACE_KEYWORDS,
    GARMENT_NOUNS,
    HAIR_KEYWORDS,
    STATE_KEYWORDS,
)

APPEARANCE_FIELDS = (
    "age",
    "gender",
    "body",
    "hair",
    "face",
    "clothing",
    "accessories",
)

# 语义域 -> 关键词；顺序即返回顺序
_ANCHOR_DOMAIN_KEYWORDS = (
    ("hair", HAIR_KEYWORDS),
    ("face", FACE_KEYWORDS),
    ("body", BODY_KEYWORDS),
    ("accessories", ACCESSORY_ONLY_KEYWORDS),
    ("clothing", GARMENT_NOUNS),
)

_AGE_RE = re.compile(r"\d{1,3}[\s-]*(?:岁|years?[\s-]old)", re.IGNORECASE)
_GENDER_RE = re.compile(r"[男女]|\b(?:male|female|man|woman|boy|girl)\b", re.IGNORECASE)
# 中文标点全切；英文句点只在后接空白/结尾时切，避免切碎 1.75m 之类的数值
_CLAUSE_SPLIT_RE = re.compile(r"[，。；！？\n\r,;!?]+|\.(?=\s|$)")
# “因雨水”“from the rain”属于场景成因，剔除后保留外观状态本身
_CAUSE_RE = re.compile(
    r"因(?:雨水|雨淋|雨|雪|水|汗)"
    r"|\s+(?:from|due to|because of)\s+(?:the\s+)?(?:rain|snow|water|sweat)\b",
    re.IGNORECASE,
)
_CLAUSE_EDGE_RE = re.compile(
    r"""^[\s，,。；;、:：\-—.!?"'“”‘’]+|[\s，,。；;、:：\-—.!?"'“”‘’]+$"""
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CLOTHING_PREFIX_RE = re.compile(
    r"^(?:wearing|dressed\s+in|clad\s+in)\s+", re.IGNORECASE
)
_ARTICLE_RE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)

# 英文关键词按单词边界匹配，并容忍常见屈折后缀（smile/smiling、glasses 等）
_EN_KEYWORD_PATTERNS: Dict[str, re.Pattern] = {}


def _keyword_pattern(keyword: str) -> re.Pattern:
    """缓存英文关键词的正则，避免热路径重复编译"""
    pattern = _EN_KEYWORD_PATTERNS.get(keyword)
    if pattern is None:
        pattern = re.compile(
            rf"(?<![A-Za-z]){re.escape(keyword)}(?:s|es|ed|ing)?(?![A-Za-z])",
            re.IGNORECASE,
        )
        _EN_KEYWORD_PATTERNS[keyword] = pattern
    return pattern


def contains_keyword(text: str, keywords: Iterable[str]) -> bool:
    """判断文本是否命中关键词：中文按子串，英文按单词边界"""
    if not text:
        return False
    for keyword in keywords:
        if keyword.isascii():
            if _keyword_pattern(keyword).search(text):
                return True
        elif keyword in text:
            return True
    return False


def _clause_separator(text: str) -> str:
    """按文本语言选择子句分隔符：含中日韩字符用中文逗号，否则用英文逗号+空格"""
    return "，" if _CJK_RE.search(text or "") else ", "


def split_clauses(text: str) -> List[str]:
    """按中英文标点与换行切分子句，保留原文顺序"""
    if not text:
        return []
    return [clause for clause in _CLAUSE_SPLIT_RE.split(str(text)) if clause.strip()]


def normalize_clause(text: str) -> str:
    """去掉子句首尾标点与多余空白，不改动子句内部内容"""
    return _CLAUSE_EDGE_RE.sub("", str(text or "").strip())


def _strip_clothing_prefix(text: str) -> str:
    """去掉“身穿/穿着”或“wearing/dressed in”等服装引导词与冠词"""
    value = str(text or "").strip()
    for prefix in ("身穿", "穿着", "身着"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        match = _CLOTHING_PREFIX_RE.match(value)
        if match:
            value = value[match.end() :]
    value = value.strip()
    if value[:1].isascii():
        value = _ARTICLE_RE.sub("", value)
    return value


def normalize_clothing_value(text: str) -> str:
    """规范化服装文本：去引导词/冠词、括号转分隔符、去成因、去重、去尾标点"""
    value = str(text or "").strip()
    separator = _clause_separator(value)
    value = (
        value.replace("（", separator)
        .replace("）", separator)
        .replace("(", separator)
        .replace(")", separator)
    )
    value = _CAUSE_RE.sub("", value)

    clauses: List[str] = []
    for raw in _CLAUSE_SPLIT_RE.split(value):
        clause = normalize_clause(_strip_clothing_prefix(raw))
        if clause and clause not in clauses:
            clauses.append(clause)
    return separator.join(clauses)


def truncate_at_clause_boundary(text: str, max_length: int) -> str:
    """只在子句边界截断；单子句超限时整句保留，绝不截出半截词"""
    value = str(text or "")
    if max_length <= 0 or len(value) <= max_length:
        return value

    separator = _clause_separator(value)
    clauses = [
        clause
        for clause in (normalize_clause(part) for part in re.split(r"[，,]", value))
        if clause
    ]
    kept: List[str] = []
    for clause in clauses:
        candidate = separator.join(kept + [clause])
        if len(candidate) > max_length:
            break
        kept.append(clause)
    if kept:
        return separator.join(kept)
    # 没有任何完整子句能放进上限：保留首个子句，保证语义完整
    return clauses[0] if clauses else value


def is_appearance_clause(clause: str) -> bool:
    """判断子句是否属于外观描述（不含情绪、动作、道具、场景成因）"""
    value = normalize_clause(clause)
    if not value:
        return False
    if contains_keyword(value, EXCLUDE_KEYWORDS):
        return False
    return _contains_appearance_signal(value)


def _contains_appearance_signal(clause: str) -> bool:
    """子句是否包含具体服装词或外观状态词"""
    if contains_keyword(clause, GARMENT_NOUNS):
        return True
    return contains_keyword(clause, STATE_KEYWORDS)


def classify_anchor_domains(value: Any) -> List[str]:
    """把锚点文本归类到外观语义域（FR-060 混域检测）

    返回命中的域列表，可能为空；长度 ≥2 表示同一锚点混入了多个语义域。
    """
    text = str(value or "")
    if not text:
        return []
    return [
        domain
        for domain, keywords in _ANCHOR_DOMAIN_KEYWORDS
        if contains_keyword(text, keywords)
    ]


def _split_tokens(value: Any) -> List[str]:
    """拆分结构化字段中的多值（如“素色/浅灰”“beige/light blue”）"""
    if value is None:
        return []
    return [
        token.strip() for token in re.split(r"[/、,，]", str(value)) if token.strip()
    ]


def _enrich_garment(
    clause: str, colors: Sequence[str], materials: Sequence[str]
) -> str:
    """结构化 color/material 只补全“以首色词开头且缺材质”的服装子句

    例：素色外套 + color=素色/浅灰 + material=棉质/混纺 → 素色浅灰棉质外套；
    已含具体颜色与款式（如“亮黄色连帽雨衣”）的子句保持原样。
    英文按空格拼接（yellow raincoat + material=PVC → yellow PVC raincoat）。
    """
    if not colors:
        return clause
    first_color = colors[0]
    if not clause.startswith(first_color):
        return clause
    if materials and contains_keyword(clause, materials):
        return clause

    remainder = clause[len(first_color) :]
    if first_color.isascii():
        prefix = " ".join([*colors, *materials[:1]])
        remainder = remainder.strip()
        return f"{prefix} {remainder}" if remainder else prefix

    prefix = "".join(colors)
    if materials:
        prefix += materials[0]
    return f"{prefix}{remainder}"


def _join_color_material(colors: Sequence[str], materials: Sequence[str]) -> str:
    """缺少 description 时用结构化颜色/材质兜底，按语言选择拼接方式"""
    parts = [*colors, *materials[:1]]
    if not parts:
        return ""
    return " ".join(parts) if all(part.isascii() for part in parts) else "".join(parts)


def extract_appearance_from_outfit(
    outfit: Mapping[str, Any], max_length: Optional[int] = None
) -> Dict[str, str]:
    """从结构化 `character_outfits` 记录提取服装与配饰锚点

    Args:
        outfit: 含 description / color / style / material 的服装记录
        max_length: 可选的子句边界长度上限

    Returns:
        仅包含 `clothing` / `accessories` 的锚点字典（无有效内容时为空）
    """
    description = str(outfit.get("description") or "")
    colors = _split_tokens(outfit.get("color"))
    materials = _split_tokens(outfit.get("material"))
    separator = _clause_separator(description)

    garment_clauses: List[str] = []
    accessory_clauses: List[str] = []
    residual_clauses: List[str] = []
    for raw in split_clauses(description):
        clause = normalize_clause(raw)
        if not clause or contains_keyword(clause, EXCLUDE_KEYWORDS):
            continue
        has_accessory = contains_keyword(clause, ACCESSORY_KEYWORDS)
        if not is_appearance_clause(clause) and not has_accessory:
            continue
        if contains_keyword(clause, GARMENT_NOUNS):
            garment_clauses.append(_enrich_garment(clause, colors, materials))
        elif has_accessory:
            accessory_clauses.append(clause)
        else:
            residual_clauses.append(clause)

    anchors: Dict[str, str] = {}
    clothing = normalize_clothing_value(
        separator.join(garment_clauses + residual_clauses)
    )
    if not clothing:
        # 缺少 description 时退回结构化颜色 + 材质，仍不拼凑无意义文本
        clothing = normalize_clothing_value(_join_color_material(colors, materials))
    if clothing:
        anchors["clothing"] = (
            truncate_at_clause_boundary(clothing, max_length)
            if max_length
            else clothing
        )

    accessories = normalize_clothing_value(separator.join(accessory_clauses))
    if accessories:
        anchors["accessories"] = (
            truncate_at_clause_boundary(accessories, max_length)
            if max_length
            else accessories
        )
    return anchors


def extract_appearance_from_text(
    description: str, max_length: Optional[int] = None
) -> Dict[str, str]:
    """从角色自由文本描述提取外观锚点（FR-002 的回退路径）

    只保留外观类子句；年龄/性别等白名单字段按首值优先提取。
    """
    anchors: Dict[str, str] = {}
    clothing_clauses: List[str] = []

    for raw in split_clauses(description):
        clause = normalize_clause(raw)
        if not clause or contains_keyword(clause, EXCLUDE_KEYWORDS):
            continue

        _collect_age_anchor(anchors, clause)
        if "gender" not in anchors:
            gender = _GENDER_RE.search(clause)
            if gender:
                anchors["gender"] = gender.group(0)
        _collect_keyword_anchor(anchors, "hair", clause, HAIR_KEYWORDS)
        _collect_keyword_anchor(anchors, "face", clause, FACE_KEYWORDS)
        _collect_keyword_anchor(anchors, "body", clause, BODY_KEYWORDS)
        _collect_keyword_anchor(anchors, "accessories", clause, ACCESSORY_KEYWORDS)

        if _contains_appearance_signal(clause):
            clothing_clauses.append(clause)

    if clothing_clauses:
        clothing = normalize_clothing_value(
            _clause_separator(description).join(clothing_clauses)
        )
        if clothing:
            anchors["clothing"] = (
                truncate_at_clause_boundary(clothing, max_length)
                if max_length
                else clothing
            )
    return anchors


def _collect_age_anchor(anchors: Dict[str, str], clause: str) -> None:
    """提取年龄并统一格式：中文“20岁”，英文“25-year-old”，首值优先"""
    if "age" in anchors:
        return
    match = _AGE_RE.search(clause)
    if match is None:
        return
    digits = re.search(r"\d{1,3}", match.group(0))
    if digits is None:
        return
    number = digits.group(0)
    anchors["age"] = f"{number}岁" if "岁" in match.group(0) else f"{number}-year-old"


def _collect_keyword_anchor(
    anchors: Dict[str, str],
    field_name: str,
    clause: str,
    keywords: Iterable[str],
) -> None:
    """按关键词归类到白名单字段，同一字段首值优先"""
    if field_name in anchors:
        return
    if contains_keyword(clause, keywords):
        value = clause
        if field_name == "accessories":
            value = normalize_clause(_strip_clothing_prefix(clause))
        anchors[field_name] = value


def merge_appearance_anchors(
    existing: Mapping[str, Any], incoming: Mapping[str, Any]
) -> Dict[str, Any]:
    """合并外观锚点：同字段首值优先，保证跨片段完全一致（FR-005）"""
    merged: Dict[str, Any] = dict(existing or {})
    for key, value in (incoming or {}).items():
        if key not in APPEARANCE_FIELDS or not value:
            continue
        if not merged.get(key):
            merged[key] = value
    return merged


def extract_appearance_anchors(
    description: str = "",
    outfit: Optional[Mapping[str, Any]] = None,
    max_length: Optional[int] = None,
) -> Dict[str, str]:
    """统一入口：结构化服装存在时仅用其生成锚点，缺失时才回退自由文本

    FR-001/FR-002 把结构化服装定义为优先来源、自由文本定义为回退路径；
    两者混用会引入自由文本里的年龄/性别等噪声，导致同一角色后缀不稳定。
    """
    if outfit:
        structured = extract_appearance_from_outfit(outfit, max_length=max_length)
        if structured:
            return {
                key: value
                for key, value in structured.items()
                if key in APPEARANCE_FIELDS and value
            }

    anchors = extract_appearance_from_text(description, max_length=max_length)
    return {key: value for key, value in anchors.items() if key in APPEARANCE_FIELDS}
