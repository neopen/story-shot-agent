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
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

APPEARANCE_FIELDS = (
    "age",
    "gender",
    "body",
    "hair",
    "face",
    "clothing",
    "accessories",
)

# 情绪 / 表情 / 表演 / 动作 / 道具词汇：命中即整句排除
EXCLUDE_KEYWORDS = frozenset(
    {
        "神情",
        "表情",
        "眼神",
        "焦急",
        "惊喜",
        "紧张",
        "微笑",
        "哭",
        "笑",
        "喊",
        "说",
        "道",
        "动作",
        "骑",
        "掏出",
        "拿出",
        "手持",
        "手拿",
        "拿着",
        "握",
        "抱",
        "推",
        "拉",
        "抓",
        "跑",
        "走",
        "蹲",
        "站",
        "坐",
        "擦",
        "低头",
        "抬头",
        "转身",
        "湿漉",
    }
)

# 具体服装名词：用于识别“服装子句”，模糊的“装扮”不算
GARMENT_NOUNS = (
    "外套",
    "大衣",
    "雨衣",
    "夹克",
    "风衣",
    "衬衫",
    "T恤",
    "卫衣",
    "毛衣",
    "背心",
    "西装",
    "制服",
    "长裤",
    "短裤",
    "裤",
    "裙",
    "鞋",
    "靴",
    "袜",
    "帽",
    "围巾",
    "手套",
)

# 外观状态词：湿/干/破损/褪色等，用于保留“肩头微湿”这类状态子句
STATE_KEYWORDS = ("湿", "干", "破", "脏", "褶皱", "褪色", "颜色", "色")

_HAIR_KEYWORDS = ("头发", "发型", "短发", "长发", "马尾", "辫", "刘海")
_FACE_KEYWORDS = ("脸", "面容", "面庞", "五官", "肤色", "皮肤", "眼", "眉", "唇")
_BODY_KEYWORDS = ("身材", "体型", "高挑", "魁梧", "瘦", "胖", "匀称")
_ACCESSORY_KEYWORDS = (
    "眼镜",
    "耳环",
    "项链",
    "手链",
    "戒指",
    "围巾",
    "手套",
    "帽子",
    "背包",
    "挎包",
    "发带",
)

# 服装域与配饰域重叠的“围巾/手套/帽子”统一归服装，避免同一服饰被判成两个语义域
_ACCESSORY_ONLY_KEYWORDS = tuple(
    keyword for keyword in _ACCESSORY_KEYWORDS if keyword not in GARMENT_NOUNS
)

# 语义域 -> 关键词；顺序即返回顺序
_ANCHOR_DOMAIN_KEYWORDS = (
    ("hair", _HAIR_KEYWORDS),
    ("face", _FACE_KEYWORDS),
    ("body", _BODY_KEYWORDS),
    ("accessories", _ACCESSORY_ONLY_KEYWORDS),
    ("clothing", GARMENT_NOUNS),
)

_AGE_RE = re.compile(r"\d{1,3}\s*岁")
_CLAUSE_SPLIT_RE = re.compile(r"[，。；！？\n\r]+")
# “因雨水”属于场景成因，剔除后保留外观状态本身
_CAUSE_RE = re.compile(r"因(?:雨水|雨淋|雨|雪|水|汗)")
_CLAUSE_EDGE_RE = re.compile(r"^[\s，,。；;、:：\-—]+|[\s，,。；;、:：\-—]+$")
_GENDER_RE = re.compile(r"[男女]")


def split_clauses(text: str) -> List[str]:
    """按中文标点与换行切分子句，保留原文顺序"""
    if not text:
        return []
    return [clause for clause in _CLAUSE_SPLIT_RE.split(str(text)) if clause.strip()]


def normalize_clause(text: str) -> str:
    """去掉子句首尾标点与多余空白，不改动子句内部内容"""
    return _CLAUSE_EDGE_RE.sub("", str(text or "").strip())


def normalize_clothing_value(text: str) -> str:
    """规范化服装文本：去“穿着/身穿”、括号转逗号、去成因、去重、去尾标点"""
    value = str(text or "").strip()
    for prefix in ("身穿", "穿着", "身着"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break

    value = (
        value.replace("（", "，")
        .replace("）", "，")
        .replace("(", "，")
        .replace(")", "，")
    )
    value = _CAUSE_RE.sub("", value)

    clauses: List[str] = []
    for raw in _CLAUSE_SPLIT_RE.split(value):
        clause = normalize_clause(raw)
        if clause and clause not in clauses:
            clauses.append(clause)
    return "，".join(clauses)


def truncate_at_clause_boundary(text: str, max_length: int) -> str:
    """只在子句边界截断；单子句超限时整句保留，绝不截出半截词"""
    value = str(text or "")
    if max_length <= 0 or len(value) <= max_length:
        return value

    clauses = [clause for clause in value.split("，") if clause]
    kept: List[str] = []
    for clause in clauses:
        candidate = "，".join(kept + [clause])
        if len(candidate) > max_length:
            break
        kept.append(clause)
    if kept:
        return "，".join(kept)
    # 没有任何完整子句能放进上限：保留首个子句，保证语义完整
    return clauses[0] if clauses else value


def is_appearance_clause(clause: str) -> bool:
    """判断子句是否属于外观描述（不含情绪、动作、道具、场景成因）"""
    value = normalize_clause(clause)
    if not value:
        return False
    if any(keyword in value for keyword in EXCLUDE_KEYWORDS):
        return False
    return _contains_appearance_signal(value)


def _contains_appearance_signal(clause: str) -> bool:
    """子句是否包含具体服装词或外观状态词"""
    if any(noun in clause for noun in GARMENT_NOUNS):
        return True
    return any(keyword in clause for keyword in STATE_KEYWORDS)


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
        if any(keyword in text for keyword in keywords)
    ]


def _split_tokens(value: Any) -> List[str]:
    """拆分结构化字段中的多值（如“素色/浅灰”“棉质/混纺”）"""
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
    """
    if not colors:
        return clause
    first_color = colors[0]
    if not clause.startswith(first_color):
        return clause
    if any(material in clause for material in materials):
        return clause

    remainder = clause[len(first_color) :]
    prefix = "".join(colors)
    if materials:
        prefix += materials[0]
    return f"{prefix}{remainder}"


def extract_appearance_from_outfit(
    outfit: Mapping[str, Any], max_length: Optional[int] = None
) -> Dict[str, str]:
    """从结构化 `character_outfits` 记录提取服装锚点

    Args:
        outfit: 含 description / color / style / material 的服装记录
        max_length: 可选的子句边界长度上限

    Returns:
        仅包含 `clothing` 的锚点字典（无有效服装时为空）
    """
    description = str(outfit.get("description") or "")
    colors = _split_tokens(outfit.get("color"))
    materials = _split_tokens(outfit.get("material"))

    garment_clauses: List[str] = []
    residual_clauses: List[str] = []
    for raw in split_clauses(description):
        clause = normalize_clause(raw)
        if not clause or not is_appearance_clause(clause):
            continue
        if any(noun in clause for noun in GARMENT_NOUNS):
            garment_clauses.append(_enrich_garment(clause, colors, materials))
        else:
            residual_clauses.append(clause)

    clothing = normalize_clothing_value("，".join(garment_clauses + residual_clauses))
    if not clothing:
        # 缺少 description 时退回结构化颜色 + 材质，仍不拼凑无意义文本
        clothing = normalize_clothing_value(
            "".join(colors) + (materials[0] if materials else "")
        )
    if not clothing:
        return {}

    if max_length:
        clothing = truncate_at_clause_boundary(clothing, max_length)
    return {"clothing": clothing}


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
        if not clause or any(keyword in clause for keyword in EXCLUDE_KEYWORDS):
            continue

        _collect_scalar_anchor(anchors, "age", clause, _AGE_RE.search(clause))
        if "gender" not in anchors:
            gender = _GENDER_RE.search(clause)
            if gender:
                anchors["gender"] = gender.group(0)
        _collect_keyword_anchor(anchors, "hair", clause, _HAIR_KEYWORDS)
        _collect_keyword_anchor(anchors, "face", clause, _FACE_KEYWORDS)
        _collect_keyword_anchor(anchors, "body", clause, _BODY_KEYWORDS)
        _collect_keyword_anchor(anchors, "accessories", clause, _ACCESSORY_KEYWORDS)

        if _contains_appearance_signal(clause):
            clothing_clauses.append(clause)

    if clothing_clauses:
        clothing = normalize_clothing_value("，".join(clothing_clauses))
        if clothing:
            anchors["clothing"] = (
                truncate_at_clause_boundary(clothing, max_length)
                if max_length
                else clothing
            )
    return anchors


def _collect_scalar_anchor(
    anchors: Dict[str, str], field_name: str, clause: str, match: Any
) -> None:
    """写入不可再分的标量锚点（如年龄），首值优先"""
    if field_name in anchors or match is None:
        return
    anchors[field_name] = match.group(0).replace(" ", "")


def _collect_keyword_anchor(
    anchors: Dict[str, str],
    field_name: str,
    clause: str,
    keywords: Sequence[str],
) -> None:
    """按关键词归类到白名单字段，同一字段首值优先"""
    if field_name in anchors:
        return
    if any(keyword in clause for keyword in keywords):
        anchors[field_name] = clause


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
