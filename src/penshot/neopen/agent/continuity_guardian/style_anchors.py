"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: style_anchors.py
@Description: 风格锚点构建 - 将剧本元数据归一化为英文风格前缀
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/3
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# 风格六维模型（FR-020）：渲染时每维最多一个值
STYLE_DIMENSIONS: Tuple[str, ...] = (
    "genre",
    "lighting",
    "palette",
    "mood",
    "framing",
    "grade",
)

# 规范题材的六维取值；未声明的维度保持空值，渲染时跳过
GENRE_DIMENSIONS: Dict[str, Dict[str, str]] = {
    "action": {
        "lighting": "dynamic lighting",
        "palette": "vibrant palette",
        "mood": "energetic",
        "framing": "dynamic framing",
        "grade": "high saturation grade",
    },
    "thriller": {
        "lighting": "high contrast lighting",
        "palette": "desaturated palette",
        "mood": "tense",
        "framing": "shadowed framing",
    },
    "horror": {
        "lighting": "low-key lighting",
        "palette": "dark muted palette",
        "mood": "dark",
        "framing": "unsettling angles",
        "grade": "desaturated grade",
    },
    "romance": {
        "lighting": "soft warm lighting",
        "palette": "warm palette",
        "mood": "romantic",
        "framing": "intimate framing",
    },
    "comedy": {
        "lighting": "bright even lighting",
        "palette": "bright colors",
        "mood": "playful",
    },
    "sci-fi": {
        "lighting": "cool neon lighting",
        "palette": "sleek palette",
        "mood": "futuristic",
        "framing": "wide framing",
        "grade": "teal-orange grade",
    },
    "crime": {
        "lighting": "moody low-key lighting",
        "palette": "desaturated palette",
        "mood": "gritty",
        "framing": "handheld framing",
    },
    "documentary": {
        "lighting": "natural lighting",
        "palette": "neutral palette",
        "mood": "observational",
        "framing": "handheld realism",
    },
    "youth": {
        "lighting": "natural lighting",
        "palette": "fresh pastel palette",
        "mood": "hopeful",
        "framing": "coming-of-age framing",
        "grade": "soft pastel grade",
    },
    "drama": {
        "lighting": "naturalistic lighting",
        "palette": "muted colors",
        "mood": "emotional",
    },
}

# 显式元数据允许的题材别名（仅精确匹配，避免 "cinematic realism" 之类被误收）
GENRE_ALIASES: Dict[str, str] = {
    "action": "action",
    "thriller": "thriller",
    "suspense": "thriller",
    "horror": "horror",
    "romance": "romance",
    "comedy": "comedy",
    "sci-fi": "sci-fi",
    "science fiction": "sci-fi",
    "crime": "crime",
    "documentary": "documentary",
    "youth": "youth",
    "drama": "drama",
    "动作": "action",
    "惊悚": "thriller",
    "悬疑": "thriller",
    "恐怖": "horror",
    "爱情": "romance",
    "浪漫": "romance",
    "喜剧": "comedy",
    "科幻": "sci-fi",
    "犯罪": "crime",
    "纪录片": "documentary",
    "青春": "youth",
    "校园": "youth",
    "剧情": "drama",
}

# 旧版 genre -> 英文风格描述映射（兼容保留，新代码请使用 GENRE_DIMENSIONS）
GENRE_STYLE_MAP: Dict[str, str] = {
    "action": "dynamic cinematography, fast-paced editing",
    "thriller": "tense atmosphere, high contrast lighting",
    "horror": "dark atmosphere, unsettling angles",
    "romance": "soft warm lighting, intimate framing",
    "comedy": "bright colors, lively camera work",
    "sci-fi": "futuristic aesthetic, sleek design",
    "crime": "gritty tone, moody desaturated palette",
    "documentary": "handheld realism, natural lighting",
    "youth": "natural lighting, coming-of-age tone",
    "drama": "naturalistic lighting, emotional depth",
}

# genre 关键词（中/英）；按声明顺序匹配，越靠前优先级越高
GENRE_KEYWORDS: Dict[str, List[str]] = {
    "action": ["打斗", "追车", "爆炸", "武打", "action"],
    "thriller": ["悬疑", "惊悚", "推理", "危机", "thriller", "suspense"],
    "horror": ["恐怖", "灵异", "鬼怪", "horror"],
    "romance": ["爱情", "浪漫", "恋爱", "romance"],
    "comedy": ["喜剧", "搞笑", "幽默", "comedy"],
    "sci-fi": ["科幻", "未来世界", "太空", "机器人", "sci-fi", "science fiction"],
    "crime": ["犯罪", "警匪", "黑帮", "谋杀", "crime"],
    "documentary": ["纪录片", "纪实", "documentary"],
    "youth": [
        "校园",
        "青春",
        "学生",
        "毕业",
        "同学",
        "教室",
        "校服",
        "school",
        "youth",
    ],
    "drama": ["剧情", "情感", "家庭", "成长", "drama"],
}

# 英文氛围 -> 视觉风格描述
ATMOSPHERE_STYLE_MAP: Dict[str, str] = {
    "tense": "tense atmosphere, high contrast lighting",
    "suspenseful": "slow-burn tension, shadowed framing",
    "calm": "soft natural lighting, serene composition",
    "peaceful": "soft natural lighting, serene composition",
    "sad": "muted colors, melancholic tone",
    "melancholic": "muted colors, melancholic tone",
    "happy": "warm bright lighting, uplifting tone",
    "joyful": "warm bright lighting, uplifting tone",
    "romantic": "soft warm lighting, intimate framing",
    "dark": "low-key lighting, deep shadows",
    "energetic": "dynamic camera movement, vibrant colors",
}

# 氛围关键词（中/英）-> 英文氛围键；按声明顺序匹配，越靠前优先级越高
ATMOSPHERE_KEYWORDS: Dict[str, List[str]] = {
    "melancholic": ["怀旧", "惆怅", "忧伤", "忧郁", "回忆", "nostalgic"],
    "sad": ["悲伤", "失落", "孤独", "寂寞", "压抑", "沉重", "sad"],
    "tense": ["紧张", "悬疑", "危机", "tense", "suspense"],
    "dark": ["黑暗", "阴森", "恐怖", "dark"],
    "romantic": ["浪漫", "温柔", "romantic"],
    "happy": ["欢快", "开心", "希望", "幸福", "温暖", "感动", "happy", "joyful"],
    "energetic": ["活力", "动感", "热烈", "热血", "energetic"],
    "calm": ["安静", "宁静", "平静", "寂静", "calm", "peaceful"],
}

# 气氛类题材词：出现在标题/场景/要点中属于氛围证据（由 mood 维度处理），
# 不能单独决定 genre；音频氛围本身是弱证据，仍允许命中。
WEAK_GENRE_KEYWORDS = frozenset({"幽默", "搞笑", "浪漫"})

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_MAX_DESCRIPTION_LENGTH = 50


@dataclass
class StyleDimensions:
    """风格六维模型：空值表示该维度无信号，渲染时跳过"""

    genre: str = ""
    lighting: str = ""
    palette: str = ""
    mood: str = ""
    framing: str = ""
    grade: str = ""

    def to_dict(self) -> Dict[str, Optional[str]]:
        """序列化为六维字典，空值统一为 None"""
        return {name: getattr(self, name) or None for name in STYLE_DIMENSIONS}


@dataclass
class GenreEvidence:
    """题材证据采集结果（FR-028）"""

    genre: str = ""
    source: str = ""
    keyword: str = ""
    confidence: str = ""
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 provenance 可用结构"""
        return {
            "genre": self.genre or None,
            "genre_source": self.source or None,
            "genre_keyword": self.keyword or None,
            "confidence": self.confidence or None,
            "genre_candidates": list(self.candidates),
            "genre_rejected": list(self.rejected),
        }


def normalize_genre(value: Any) -> str:
    """把显式题材值归一化为规范键；非规范值返回空串（FR-027）"""
    folded = str(value or "").strip().lower()
    if not folded:
        return ""
    if folded in GENRE_DIMENSIONS:
        return folded
    return GENRE_ALIASES.get(folded, "")


def resolve_genre_dimensions(genre: str) -> StyleDimensions:
    """按规范题材解析六维取值；未知题材返回全空模型"""
    key = str(genre or "").strip().lower()
    values = GENRE_DIMENSIONS.get(key)
    if not values:
        return StyleDimensions()
    return StyleDimensions(
        genre=key,
        lighting=values.get("lighting", ""),
        palette=values.get("palette", ""),
        mood=values.get("mood", ""),
        framing=values.get("framing", ""),
        grade=values.get("grade", ""),
    )


def is_english_text(value: Any) -> bool:
    """判断文本是否为可用英文（非空且不含中日韩字符）"""
    if not isinstance(value, str) or not value.strip():
        return False
    return not _CJK_PATTERN.search(value)


def _scan_genre_keyword(text: str, allow_weak: bool = True) -> Tuple[str, str]:
    """按关键词扫描题材，返回命中的 genre 与原始关键词

    ``allow_weak=False`` 时跳过气氛类题材词，避免场景里的“幽默”等
    氛围描述被误判为题材。
    """
    lowered = str(text or "").lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        for keyword in keywords:
            if not allow_weak and keyword in WEAK_GENRE_KEYWORDS:
                continue
            if keyword.lower() in lowered:
                return genre, keyword
    return "", ""


def _scan_atmosphere(text: str) -> str:
    """按中/英关键词扫描氛围，返回英文氛围键，未命中返回空串"""
    lowered = text.lower()
    for atmosphere, keywords in ATMOSPHERE_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return atmosphere
    return ""


def _scene_text(parsed_script: Any, limit: int = 3) -> str:
    """拼接前几个场景的地点/描述文本，用于 genre 推断"""
    scenes = getattr(parsed_script, "scenes", []) or []
    parts: List[str] = []
    for scene in scenes[:limit]:
        location = getattr(scene, "location", "") or ""
        description = getattr(scene, "description", "") or ""
        parts.append(f"{location} {description}")
    return " ".join(parts)


def _metadata_text(metadata: Any, key: str) -> str:
    """安全读取解析元数据中的文本字段"""
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _append_genre_candidate(
    evidence: GenreEvidence,
    text: str,
    source: str,
    confidence: str,
    allow_weak: bool = False,
) -> None:
    """扫描文本并把命中结果追加为候选（不改变已有决议）"""
    genre, keyword = _scan_genre_keyword(text, allow_weak=allow_weak)
    if not genre:
        return
    evidence.candidates.append(
        {
            "field": source,
            "genre": genre,
            "keyword": keyword,
            "confidence": confidence,
        }
    )


def collect_genre_evidence(parsed_script: Any) -> GenreEvidence:
    """按字段优先级采集题材证据（FR-028）

    优先级：显式元数据 > 标题 > 场景地点/描述 > 连续性要点 > 音频氛围。
    显式元数据只接受规范题材或精确别名，其余记入 ``rejected``（FR-027）；
    音频氛围为弱证据，单独命中时 ``confidence=low``。

    Args:
        parsed_script: 剧本解析结果（可为 None）

    Returns:
        题材证据，含 resolved genre、来源字段、命中词与候选/拒绝列表
    """
    evidence = GenreEvidence()
    if parsed_script is None:
        return evidence

    metadata = getattr(parsed_script, "metadata", None)
    for key in ("genre", "style", "category"):
        raw_value = _metadata_text(metadata, key)
        if not raw_value:
            continue
        normalized = normalize_genre(raw_value)
        if normalized:
            evidence.candidates.append(
                {
                    "field": f"metadata.{key}",
                    "genre": normalized,
                    "keyword": raw_value,
                    "confidence": "high",
                }
            )
        else:
            evidence.rejected.append({"field": f"metadata.{key}", "value": raw_value})

    global_metadata = getattr(parsed_script, "global_metadata", None)
    _append_genre_candidate(
        evidence, str(getattr(parsed_script, "title", "") or ""), "title", "medium"
    )
    _append_genre_candidate(evidence, _scene_text(parsed_script), "scene", "medium")
    _append_genre_candidate(
        evidence,
        str(getattr(global_metadata, "continuity_notes", "") or ""),
        "continuity_notes",
        "medium",
    )
    _append_genre_candidate(
        evidence,
        str(getattr(global_metadata, "audio_atmosphere", "") or ""),
        "audio_atmosphere",
        "low",
        allow_weak=True,
    )

    if evidence.candidates:
        resolved = evidence.candidates[0]
        evidence.genre = str(resolved["genre"])
        evidence.source = str(resolved["field"])
        evidence.keyword = str(resolved["keyword"])
        evidence.confidence = str(resolved["confidence"])
    return evidence


def infer_style_anchor(parsed_script: Any) -> Dict[str, str]:
    """从剧本解析结果推断英文风格锚点

    题材按 FR-028 字段优先级采集：显式元数据（仅规范题材）→ 标题 → 场景 →
    连续性要点 → 音频氛围（弱证据）；非规范显式值只记入 rejected，不写入
    ``genre``。描述维度保持原有氛围映射逻辑。

    Args:
        parsed_script: 剧本解析结果（ParsedScript，可为 None）

    Returns:
        英文风格锚点字典，如 ``{"genre": "thriller", "description": "..."}``
    """
    if parsed_script is None:
        return {}

    metadata = getattr(parsed_script, "metadata", None)
    genre = collect_genre_evidence(parsed_script).genre

    global_metadata = getattr(parsed_script, "global_metadata", None)
    notes = getattr(global_metadata, "continuity_notes", "") or ""
    atmosphere = getattr(global_metadata, "audio_atmosphere", "") or ""
    title = getattr(parsed_script, "title", "") or ""
    scenes = _scene_text(parsed_script)
    source_text = f"{title} {scenes} {notes} {atmosphere}"

    description = ""
    explicit_description = _metadata_text(metadata, "style_description")
    if is_english_text(explicit_description):
        description = explicit_description
    elif is_english_text(atmosphere):
        description = ATMOSPHERE_STYLE_MAP.get(atmosphere.strip().lower(), "")
    if not description:
        # 中文氛围/要点：按关键词映射为英文氛围描述
        scanned = _scan_atmosphere(source_text)
        description = ATMOSPHERE_STYLE_MAP.get(scanned, "")

    result: Dict[str, str] = {}
    if genre:
        result["genre"] = genre
    if description and len(description) < _MAX_DESCRIPTION_LENGTH:
        result["description"] = description
    return result


def build_style_prefix(style_anchor: Optional[Dict[str, Any]]) -> str:
    """根据契约风格锚点构建英文风格前缀

    只接受英文内容（中文描述会被跳过），并按出现顺序去重，避免同一风格
    描述重复注入。

    Args:
        style_anchor: 契约中的 ``style_anchor`` 字典

    Returns:
        形如 ``[Style: ...]`` 的英文前缀；无可用内容时返回空串
    """
    if not style_anchor:
        return ""

    parts: List[str] = []

    genre = str(style_anchor.get("genre") or "").strip().lower()
    if genre:
        genre_style = GENRE_STYLE_MAP.get(genre)
        if not genre_style and is_english_text(genre):
            genre_style = genre
        if genre_style:
            parts.append(genre_style)

    description = style_anchor.get("description")
    if is_english_text(description) and len(description) < _MAX_DESCRIPTION_LENGTH:
        parts.append(description.strip())

    atmosphere = style_anchor.get("atmosphere")
    if is_english_text(atmosphere):
        atmosphere_style = ATMOSPHERE_STYLE_MAP.get(atmosphere.strip().lower())
        if atmosphere_style:
            parts.append(atmosphere_style)

    deduped: List[str] = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)

    return f"[Style: {', '.join(deduped)}]" if deduped else ""
