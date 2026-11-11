"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: style_anchors.py
@Description: 风格锚点构建 - 将剧本元数据归一化为英文风格前缀
@Author: neopen
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
    "fresh": "bright natural lighting, clean tones",
    "healing": "warm gentle lighting, soothing tone",
}

# 氛围 -> 六维补充取值；题材维度优先，氛围只填补空缺（FR-022）
ATMOSPHERE_DIMENSIONS: Dict[str, Dict[str, str]] = {
    "tense": {"lighting": "high contrast lighting", "framing": "shadowed framing"},
    "suspenseful": {
        "lighting": "low-key lighting",
        "framing": "shadowed framing",
    },
    "calm": {
        "lighting": "soft natural lighting",
        "palette": "natural palette",
        "framing": "serene composition",
    },
    "peaceful": {
        "lighting": "soft natural lighting",
        "palette": "natural palette",
        "framing": "serene composition",
    },
    "sad": {"lighting": "diffused lighting", "palette": "muted colors"},
    "melancholic": {"lighting": "diffused lighting", "palette": "muted colors"},
    "happy": {"lighting": "warm bright lighting", "palette": "warm palette"},
    "joyful": {"lighting": "warm bright lighting", "palette": "warm palette"},
    "romantic": {"lighting": "soft warm lighting", "framing": "intimate framing"},
    "dark": {"lighting": "low-key lighting", "palette": "dark muted palette"},
    "energetic": {
        "lighting": "dynamic lighting",
        "framing": "dynamic framing",
    },
    "fresh": {"lighting": "bright natural lighting", "palette": "clean palette"},
    "healing": {"lighting": "warm gentle lighting", "palette": "soft palette"},
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
    # FR-023 要求的样本氛围词；放在末尾以保持既有优先级不变
    "fresh": ["清新", "fresh"],
    "healing": ["治愈", "healing"],
}

# 气氛类题材词：出现在标题/场景/要点中属于氛围证据（由 mood 维度处理），
# 不能单独决定 genre；音频氛围本身是弱证据，仍允许命中。
WEAK_GENRE_KEYWORDS = frozenset({"幽默", "搞笑", "浪漫"})

# 打光冲突族（FR-024）：同一前缀只允许保留一个打光短语
LIGHTING_FAMILY_MARKERS: Tuple[str, ...] = (
    "soft warm",
    "high contrast",
    "low-key",
    "natural",
)

# 旧描述短语所属维度（FR-021）：已由锚点声明的维度不再接收旧短语
_PHRASE_DIMENSION_MARKERS: Dict[str, frozenset] = {
    "lighting": frozenset({"lighting", "light"}),
    "palette": frozenset({"palette", "color", "colors", "colour", "colours", "tones"}),
    "mood": frozenset({"mood", "tone", "atmosphere"}),
    "framing": frozenset({"framing", "composition", "angle", "angles"}),
    "grade": frozenset({"grade", "grading"}),
}

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


@dataclass
class MoodEvidence:
    """氛围证据采集结果（FR-023）

    ``resolved_by`` 记录决议依据：显式音频氛围或一阶关键词扫描，供
    provenance 输出与冲突排查使用。
    """

    mood: str = ""
    source: str = ""
    keyword: str = ""
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    resolved_by: str = ""


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


def _scan_atmosphere_keyword(text: str) -> Tuple[str, str]:
    """按中/英关键词扫描氛围，返回氛围键与命中的原始词"""
    lowered = str(text or "").lower()
    for atmosphere, keywords in ATMOSPHERE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return atmosphere, keyword
    return "", ""


def _atmosphere_from_explicit(text: str) -> Tuple[str, str]:
    """解析显式音频氛围：先按英文氛围键精确匹配，再退回关键词扫描"""
    value = str(text or "").strip()
    if not value:
        return "", ""
    exact = value.lower()
    if exact in ATMOSPHERE_STYLE_MAP:
        return exact, value
    return _scan_atmosphere_keyword(value)


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


def collect_mood_evidence(parsed_script: Any) -> MoodEvidence:
    """按 FR-023 采集氛围证据

    mood 维度以显式 ``audio_atmosphere`` 为准，它 MUST 优先于场景文本的
    一阶关键词扫描；其余字段只在显式氛围无信号时按 标题 > 场景 > 连续性
    要点 回退。

    Args:
        parsed_script: 剧本解析结果（可为 None）

    Returns:
        氛围证据，含 resolved mood、来源字段、命中词与全部候选
    """
    evidence = MoodEvidence()
    if parsed_script is None:
        return evidence

    global_metadata = getattr(parsed_script, "global_metadata", None)
    explicit_mood, explicit_keyword = _atmosphere_from_explicit(
        str(getattr(global_metadata, "audio_atmosphere", "") or "")
    )
    if explicit_mood:
        evidence.candidates.append(
            {
                "field": "audio_atmosphere",
                "mood": explicit_mood,
                "keyword": explicit_keyword,
            }
        )

    for field_name, text in (
        ("title", str(getattr(parsed_script, "title", "") or "")),
        ("scene", _scene_text(parsed_script)),
        (
            "continuity_notes",
            str(getattr(global_metadata, "continuity_notes", "") or ""),
        ),
    ):
        mood, keyword = _scan_atmosphere_keyword(text)
        if mood:
            evidence.candidates.append(
                {"field": field_name, "mood": mood, "keyword": keyword}
            )

    if explicit_mood:
        evidence.mood = explicit_mood
        evidence.source = "audio_atmosphere"
        evidence.keyword = explicit_keyword
        evidence.resolved_by = "explicit_audio_atmosphere"
    elif evidence.candidates:
        first = evidence.candidates[0]
        evidence.mood = str(first["mood"])
        evidence.source = str(first["field"])
        evidence.keyword = str(first["keyword"])
        evidence.resolved_by = "keyword_scan"
    return evidence


def _resolve_style_dimensions(
    genre: str, mood_evidence: MoodEvidence
) -> StyleDimensions:
    """合并题材维度与氛围维度：题材优先，氛围只填补空缺（FR-022）"""
    dimensions = resolve_genre_dimensions(genre)
    atmosphere = ATMOSPHERE_DIMENSIONS.get(mood_evidence.mood, {})
    for name, value in atmosphere.items():
        if not getattr(dimensions, name):
            setattr(dimensions, name, value)
    if mood_evidence.mood and not dimensions.mood:
        dimensions.mood = mood_evidence.mood
    return dimensions


def _build_provenance(
    genre_evidence: GenreEvidence, mood_evidence: MoodEvidence
) -> Dict[str, Any]:
    """组装 FR-029 provenance；``discarded`` 由渲染层消解冲突时补充"""
    genres = {str(item["genre"]) for item in genre_evidence.candidates}
    mood_candidates: List[str] = []
    for item in mood_evidence.candidates:
        mood = str(item["mood"])
        if mood and mood not in mood_candidates:
            mood_candidates.append(mood)

    if genre_evidence.genre:
        resolved_by = "field_priority"
    elif mood_evidence.mood:
        resolved_by = "mood_only"
    else:
        resolved_by = "no_signal"

    return {
        "genre_source": genre_evidence.source or None,
        "genre_keyword": genre_evidence.keyword or None,
        "genre_candidates": list(genre_evidence.candidates),
        "genre_rejected": list(genre_evidence.rejected),
        "genre_conflict": len(genres) > 1,
        "mood_source": mood_evidence.source or None,
        "mood_candidates": mood_candidates,
        "resolved_by": resolved_by,
        "discarded": [],
        "confidence": genre_evidence.confidence or None,
    }


def infer_style_anchor_with_provenance(
    parsed_script: Any,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """推断六维风格锚点并输出 FR-029 provenance

    题材按 FR-028 字段优先级采集（非规范显式值只进 ``genre_rejected``），
    六维取值以题材维度为主、氛围维度补空缺；氛围证据按 FR-023 以显式
    ``audio_atmosphere`` 为准。无题材信号时 ``genre`` 为空，MUST NOT 用
    默认题材补位（FR-029、AC-029）。

    Args:
        parsed_script: 剧本解析结果（ParsedScript，可为 None）

    Returns:
        ``(anchor, provenance)``；``anchor`` 只包含非空维度与可选
        ``description``，``provenance`` 为可 JSON 序列化的溯源字典
    """
    if parsed_script is None:
        return {}, {}

    genre_evidence = collect_genre_evidence(parsed_script)
    mood_evidence = collect_mood_evidence(parsed_script)
    dimensions = _resolve_style_dimensions(genre_evidence.genre, mood_evidence)

    metadata = getattr(parsed_script, "metadata", None)
    description = ""
    explicit_description = _metadata_text(metadata, "style_description")
    if is_english_text(explicit_description):
        description = explicit_description
    elif mood_evidence.mood:
        description = ATMOSPHERE_STYLE_MAP.get(mood_evidence.mood, "")

    anchor: Dict[str, str] = {
        name: value for name, value in dimensions.to_dict().items() if value
    }
    if description and len(description) < _MAX_DESCRIPTION_LENGTH:
        anchor["description"] = description
    return anchor, _build_provenance(genre_evidence, mood_evidence)


def infer_style_anchor(parsed_script: Any) -> Dict[str, str]:
    """兼容包装：只返回风格锚点

    provenance 由 :func:`infer_style_anchor_with_provenance` 提供，本函数
    保持既有调用方签名不变（PLAN D3）。
    """
    anchor, _ = infer_style_anchor_with_provenance(parsed_script)
    return anchor


def _lighting_family(value: str) -> str:
    """返回打光短语所属冲突族标记，非打光短语返回空串"""
    lowered = str(value or "").lower()
    for marker in LIGHTING_FAMILY_MARKERS:
        if marker in lowered:
            return marker
    return ""


def _resolve_anchor_dimensions(anchor: Dict[str, Any]) -> Dict[str, str]:
    """读取锚点维度，并用规范题材/氛围补齐空缺（兼容旧入参）"""
    dimensions: Dict[str, str] = {}
    for name in STYLE_DIMENSIONS:
        value = anchor.get(name)
        if not isinstance(value, str) or not value.strip():
            continue
        if name == "genre":
            normalized = normalize_genre(value)
            dimensions[name] = normalized or value.strip()
        else:
            dimensions[name] = value.strip()

    genre_style = resolve_genre_dimensions(dimensions.get("genre", ""))
    for name, value in genre_style.to_dict().items():
        if value and name not in dimensions:
            dimensions[name] = value

    atmosphere = str(anchor.get("atmosphere") or "").strip().lower()
    for name, value in ATMOSPHERE_DIMENSIONS.get(atmosphere, {}).items():
        if name not in dimensions:
            dimensions[name] = value
    if atmosphere in ATMOSPHERE_DIMENSIONS and "mood" not in dimensions:
        dimensions["mood"] = atmosphere
    return dimensions


def _legacy_phrases(style_anchor: Dict[str, Any]) -> List[Tuple[str, str]]:
    """收集旧 ``description`` / ``atmosphere`` 的英文短语及来源

    氛围键已能映射为维度时不再重复输出短语，避免同一信息出现两次。
    """
    phrases: List[Tuple[str, str]] = []

    description = style_anchor.get("description")
    if is_english_text(description) and len(str(description)) < _MAX_DESCRIPTION_LENGTH:
        for part in str(description).split(","):
            phrase = part.strip()
            if phrase:
                phrases.append((phrase, "description"))

    atmosphere = str(style_anchor.get("atmosphere") or "").strip().lower()
    if is_english_text(atmosphere) and atmosphere not in ATMOSPHERE_DIMENSIONS:
        for part in ATMOSPHERE_STYLE_MAP.get(atmosphere, "").split(","):
            phrase = part.strip()
            if phrase:
                phrases.append((phrase, "atmosphere"))
    return phrases


def _duplicates_dimension(phrase: str, dimensions: Dict[str, str]) -> bool:
    """判断短语是否已由某个已决议维度表达（避免同一信息重复渲染）"""
    lowered = phrase.lower()
    for name, value in dimensions.items():
        if name == "genre" or not value:
            continue
        lowered_value = value.lower()
        if lowered_value in lowered or lowered in lowered_value:
            return True
        if any(
            word in lowered
            for word in re.split(r"[\s\-]+", lowered_value)
            if len(word) > 2
        ):
            return True
    return False


def _phrase_dimension(phrase: str) -> str:
    """判断旧描述短语属于哪个风格维度；无法判定时返回空串"""
    tokens = set(re.split(r"[^a-z]+", str(phrase or "").lower()))
    for dimension in ("lighting", "palette", "mood", "framing", "grade"):
        if tokens & _PHRASE_DIMENSION_MARKERS[dimension]:
            return dimension
    return ""


def _record_discarded(
    provenance: Optional[Dict[str, Any]],
    value: str,
    source: str,
    dimension: str = "lighting",
) -> None:
    """记录被丢弃的冲突短语（FR-024/FR-029）"""
    if provenance is None:
        return
    discarded = provenance.setdefault("discarded", [])
    item = {"dimension": dimension, "value": value, "source": source}
    if item not in discarded:
        discarded.append(item)


def build_style_text(
    style_anchor: Optional[Dict[str, Any]],
    provenance: Optional[Dict[str, Any]] = None,
) -> str:
    """渲染六维英文风格文本（FR-021/024）

    维度按 ``genre → lighting → palette → mood → framing → grade`` 固定
    顺序输出，每维最多一个值；旧 ``genre`` / ``description`` /
    ``atmosphere`` 入参继续兼容。打光互斥时保留已决议的维度值，被丢弃的
    短语写入 ``provenance["discarded"]``。

    与 :func:`build_style_prefix` 同源，供 ``fragment.style`` 复用同一
    渲染结果（FR-025），避免再生成一套打光声明。

    Args:
        style_anchor: 契约中的 ``style_anchor`` 字典
        provenance: 可选溯源字典；传入时记录冲突丢弃项

    Returns:
        逗号分隔的英文风格文本；无可用内容时返回空串
    """
    if not style_anchor:
        return ""

    dimensions = _resolve_anchor_dimensions(style_anchor)
    parts: List[str] = []
    lighting_family = ""

    for name in STYLE_DIMENSIONS:
        value = dimensions.get(name, "")
        if not value or value in parts:
            continue
        if name == "lighting":
            lighting_family = _lighting_family(value)
        parts.append(value)

    # 非规范英文题材原样保留（旧入参兼容）；中文题材由维度承接或跳过
    genre_raw = str(style_anchor.get("genre") or "").strip().lower()
    if genre_raw and genre_raw not in GENRE_DIMENSIONS:
        if is_english_text(genre_raw) and genre_raw not in parts:
            parts.insert(0, genre_raw)

    for phrase, source in _legacy_phrases(style_anchor):
        if phrase in parts:
            continue
        dimension = _phrase_dimension(phrase)
        if dimension and dimensions.get(dimension):
            _record_discarded(provenance, phrase, source, dimension)
            continue
        marker = _lighting_family(phrase)
        if marker and lighting_family:
            _record_discarded(provenance, phrase, source)
            continue
        if _duplicates_dimension(phrase, dimensions):
            continue
        if marker:
            lighting_family = marker
        parts.append(phrase)

    return ", ".join(parts)


def build_style_prefix(
    style_anchor: Optional[Dict[str, Any]],
    provenance: Optional[Dict[str, Any]] = None,
) -> str:
    """渲染 ``[Style: ...]`` 前缀，内容与 :func:`build_style_text` 同源

    Args:
        style_anchor: 契约中的 ``style_anchor`` 字典
        provenance: 可选溯源字典；传入时记录冲突丢弃项

    Returns:
        形如 ``[Style: ...]`` 的英文前缀；无可用内容时返回空串
    """
    style_text = build_style_text(style_anchor, provenance)
    return f"[Style: {style_text}]" if style_text else ""
