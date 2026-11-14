"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: script_language.py
@Description: 剧本语言推断与音频提示词语言归一（FR-084~087）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

import re
from typing import Any, List, Literal, Optional, Tuple

from penshot.logger import warning
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIAudioPrompt,
)

# 元数据显式语言优先；未声明时按正文 CJK 占比判断（FR-085）
CJK_RATIO_THRESHOLD = 0.3
# CJK 占比低于该值时视为英文剧本，介于两者之间按默认中文处理
NEGLIGIBLE_CJK_RATIO = 0.05

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 英文引号句（含 don't 之类词内撇号），用于识别英文台词原文
_EN_QUOTED_RE = re.compile(
    r"\"[^\"]*\""
    r"|(?<![A-Za-z])'(?:[^']|(?<=[A-Za-z])'(?=[A-Za-z]))*'(?![A-Za-z])"
)

# 英文台词段中的中文对照片段（含中文标点与引号）
_CJK_TEXT_RUN_RE = re.compile(
    r"[ \t]*[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"“”‘’「」『』（）【】《》：；，。！？、…—-]*"
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"“”‘’「」『』（）【】《》：；，。！？、…—-]*"
)

# 中文音色兜底：英文 voice_description 按 voice_type + emotion 映射为中文
_ZH_VOICE_TYPE = {
    "character_dialogue": "角色对白",
    "narration": "旁白",
    "announcer": "播报",
    "creative": "创意人声",
}
_ZH_EMOTION = {
    "neutral": "平静",
    "happy": "愉悦",
    "sad": "悲伤",
    "melancholic": "忧郁",
    "angry": "愤怒",
    "tense": "紧张",
    "fear": "恐惧",
    "anxious": "焦虑",
    "excited": "兴奋",
    "calm": "平静",
    "tender": "温柔",
    "hesitant": "犹豫",
    "crying": "哭腔",
    "whisper": "低语",
    "heavy": "沉重",
    "resigned": "无奈",
    "resolute": "坚定",
    "nostalgic": "怀旧",
    "dramatic": "戏剧化",
    "tired": "疲惫",
}

_CLAUSE_BOUNDARIES = ",，;；。\n"


def _attr(source: Any, name: str, default: Any = None) -> Any:
    """读取 dataclass / 字典字段"""
    if source is None:
        return default
    value = getattr(source, name, None)
    if value is None and isinstance(source, dict):
        value = source.get(name)
    return default if value is None else value


def _has_cjk(text: str) -> bool:
    """文本是否包含中文字符"""
    return bool(_CJK_RE.search(str(text or "")))


def _metadata_language(parsed_script: Any) -> Literal["zh", "en", ""]:
    """读取解析元数据中的显式语言声明，无法识别时返回空串"""
    metadata = _attr(parsed_script, "metadata", None)
    declared = (
        str(
            _attr(metadata, "language", "")
            or _attr(metadata, "script_language", "")
            or ""
        )
        .strip()
        .lower()
    )
    if not declared:
        return ""
    if declared.startswith("zh") or declared in {"chinese", "中文", "汉语"}:
        return "zh"
    if declared.startswith("en") or declared in {"english", "英文", "英语"}:
        return "en"
    return ""


def _collect_script_text(parsed_script: Any) -> str:
    """汇总可用于语言判断的剧本正文（标题、场景、元素、角色描述）"""
    parts: List[str] = []
    for field in ("title",):
        value = _attr(parsed_script, field, "")
        if value:
            parts.append(str(value))

    for scene in _attr(parsed_script, "scenes", []) or []:
        for field in ("location", "description"):
            value = _attr(scene, field, "")
            if value:
                parts.append(str(value))
        for element in _attr(scene, "elements", []) or []:
            for field in ("content", "description"):
                value = _attr(element, field, "")
                if value:
                    parts.append(str(value))

    for character in _attr(parsed_script, "characters", []) or []:
        parts.append(str(_attr(character, "name", "")))
        description = _attr(character, "description", "")
        if description:
            parts.append(str(description))
        for trait in _attr(character, "key_traits", []) or []:
            parts.append(str(trait))

    return "\n".join(part for part in parts if part)


def detect_script_language(parsed_script: Any) -> Literal["zh", "en"]:
    """推断剧本语言（FR-085）

    优先级：解析元数据显式语言 > 正文 CJK 字符占比阈值 > 默认 ``zh``。
    正文以 CJK 与拉丁字母总数作为分母，纯中文约 1.0、纯英文约 0.0。

    Args:
        parsed_script: ``ParsedScript`` 或具备同名属性的对象/字典

    Returns:
        ``"zh"`` 或 ``"en"``
    """
    declared = _metadata_language(parsed_script)
    if declared:
        return declared

    text = _collect_script_text(parsed_script)
    cjk_count = len(_CJK_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))
    total = cjk_count + latin_count
    if total == 0:
        return "zh"

    ratio = cjk_count / total
    if ratio >= CJK_RATIO_THRESHOLD:
        return "zh"
    if ratio <= NEGLIGIBLE_CJK_RATIO:
        return "en"
    # 中英混杂且不足以判定时保持默认中文，避免误把中文剧本当英文
    return "zh"


def _split_translation(prompt: str) -> Tuple[str, str]:
    """拆分台词描述段与 ``\\n\\n`` 之后的中文对照注释段"""
    head, separator, tail = str(prompt or "").partition("\n\n")
    return head, tail if separator else ""


def _is_english_quote(span: str) -> bool:
    """引号内容是否为英文台词原文（含拉丁字母且不含中文）"""
    return bool(_LATIN_RE.search(span)) and not _has_cjk(span)


def _contains_english_dialogue(text: str) -> bool:
    """文本中是否存在英文台词引号句"""
    return any(
        _is_english_quote(match.group(0)) for match in _EN_QUOTED_RE.finditer(text)
    )


def _strip_english_dialogue(text: str) -> str:
    """剔除英文台词引号句及其说话人前缀子句"""
    matches = [
        match
        for match in _EN_QUOTED_RE.finditer(text)
        if _is_english_quote(match.group(0))
    ]
    if not matches:
        return text

    characters = list(text)
    for match in reversed(matches):
        start = match.start()
        boundary = max(text.rfind(sep, 0, start) for sep in _CLAUSE_BOUNDARIES) + 1
        end = match.end()
        while end < len(text) and text[end] in "，,。.;； ":
            end += 1
        characters[boundary:end] = " "

    cleaned = re.sub(r"\s{2,}", " ", "".join(characters))
    return cleaned.strip(" ,，;；.")


def _zh_voice_description(audio: AIAudioPrompt) -> Optional[str]:
    """英文 voice_description 按 voice_type + emotion 映射为中文"""
    description = str(audio.voice_description or "").strip()
    if not description or _has_cjk(description):
        return audio.voice_description
    voice_type = getattr(audio.voice_type, "value", audio.voice_type)
    type_text = _ZH_VOICE_TYPE.get(str(voice_type or ""), "人声")
    emotion = str(audio.emotion or "").strip().lower()
    emotion_text = _ZH_EMOTION.get(emotion, "自然")
    return f"{type_text}，{emotion_text}的语调"


def _normalize_zh_prompt(prompt: str) -> str:
    """中文剧本：移除英文台词原文，优先保留 ``\\n\\n`` 后的中文台词段"""
    head, tail = _split_translation(prompt)
    if tail and _has_cjk(tail) and _contains_english_dialogue(head):
        # 中文对照段已包含台词全文，直接丢弃英文段避免英文台词残留
        return tail.strip()
    return _strip_english_dialogue(prompt).strip()


def _normalize_en_prompt(prompt: str) -> str:
    """英文剧本：中文对照只保留在 ``\\n\\n`` 之后，不进入台词描述段"""
    head, tail = _split_translation(prompt)
    moved = [match.group(0) for match in _CJK_TEXT_RUN_RE.finditer(head)]
    if not moved:
        return prompt

    cleaned_head = _CJK_TEXT_RUN_RE.sub(" ", head)
    cleaned_head = re.sub(r"\s{2,}", " ", cleaned_head).strip(" ,，;；.")
    if not cleaned_head:
        warning("英文剧本音频提示词缺少英文台词段，保留原文以便人工修正")
        return prompt

    comment_parts = [part.strip(" ，；;") for part in moved]
    if tail.strip():
        comment_parts.append(tail.strip())
    comment = "；".join(part for part in comment_parts if part)
    return f"{cleaned_head}\n\n{comment}"


def normalize_video_prompt_language(prompt: str, language: str) -> str:
    """按剧本语言归一视频提示词（FR-086 对视频提示词的延伸）

    中文剧本的视频提示词由英文描述段与中文对照段拼成，LLM 常把中文台词改写
    成英文引号句，导致画面提示词语言与台词语言（zh）不一致。这里只清洗
    ``\\n\\n`` 之前的英文描述段：剔除英文台词引号句及其说话人前缀，动作与
    镜头描述保留；中文对照段原样不动。英文剧本不做改写。

    Args:
        prompt: 视频提示词；已含中文对照时按 ``\\n\\n`` 拆分
        language: ``detect_script_language`` 的推断结果

    Returns:
        清洗后的提示词；非中文剧本或本来不含英文台词时原样返回
    """
    normalized = str(language or "").strip().lower()
    if normalized.startswith("en"):
        return prompt

    head, tail = _split_translation(prompt)
    cleaned = _strip_english_dialogue(head)
    if not tail:
        return cleaned
    return f"{cleaned}\n\n{tail}" if cleaned else tail


def normalize_audio_language(audio: AIAudioPrompt, language: str) -> AIAudioPrompt:
    """按剧本语言归一音频提示词（FR-086/FR-087）

    - ``zh``：移除英文台词引号句；``voice_description`` 非中文时按
      ``emotion + voice_type`` 映射为中文。
    - ``en``：保留英文台词段，中文对照只移入 ``\\n\\n`` 之后的注释段。

    Args:
        audio: 待归一化的音频提示词
        language: ``detect_script_language`` 的推断结果

    Returns:
        归一化后的音频提示词副本，不修改入参
    """
    result = audio.model_copy(deep=True)
    normalized = "en" if str(language or "").strip().lower().startswith("en") else "zh"

    if normalized == "zh":
        result.prompt = _normalize_zh_prompt(result.prompt)
        result.voice_description = _zh_voice_description(result)
    else:
        result.prompt = _normalize_en_prompt(result.prompt)

    return result
