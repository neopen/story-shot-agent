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
from typing import Any, Dict, List, Optional

# 英文 genre -> 英文视觉风格描述
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

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_MAX_DESCRIPTION_LENGTH = 50


def is_english_text(value: Any) -> bool:
    """判断文本是否为可用英文（非空且不含中日韩字符）"""
    if not isinstance(value, str) or not value.strip():
        return False
    return not _CJK_PATTERN.search(value)


def _scan_genre(text: str) -> str:
    """按关键词扫描推断英文 genre，未命中返回空串"""
    lowered = text.lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return genre
    return ""


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


def infer_style_anchor(parsed_script: Any) -> Dict[str, str]:
    """从剧本解析结果推断英文风格锚点

    优先级：显式元数据（metadata.genre/style） → 关键词扫描（标题、场景、
    连续性要点、音频氛围） → 氛围映射。返回值只包含非空且有意义的
    ``genre`` / ``description``，供 prompt_converter 拼接英文风格前缀。

    Args:
        parsed_script: 剧本解析结果（ParsedScript，可为 None）

    Returns:
        英文风格锚点字典，如 ``{"genre": "thriller", "description": "..."}``
    """
    if parsed_script is None:
        return {}

    metadata = getattr(parsed_script, "metadata", None)
    genre = ""
    for key in ("genre", "style", "category"):
        value = _metadata_text(metadata, key)
        if is_english_text(value):
            genre = value.lower()
            break

    global_metadata = getattr(parsed_script, "global_metadata", None)
    notes = getattr(global_metadata, "continuity_notes", "") or ""
    atmosphere = getattr(global_metadata, "audio_atmosphere", "") or ""
    title = getattr(parsed_script, "title", "") or ""
    scenes = _scene_text(parsed_script)
    source_text = f"{title} {scenes} {notes} {atmosphere}"

    # 无显式 genre 时，从标题/场景/连续性要点/氛围中扫描关键词
    if not genre:
        genre = _scan_genre(source_text)

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
