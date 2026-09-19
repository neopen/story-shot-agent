"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: scene_attribute_rules.py
@Description: 场景属性规则 - 逐个补齐场景的地点、时间、天气、氛围与音频上下文
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

import re
from typing import Dict, List, Optional, Sequence, Tuple

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import (
    SceneAttributeRule,
)
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    ParseContext,
    SceneDraft,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import clean_text
from penshot.neopen.config.script_parser_config import ScriptParserConfig

# 地点缺失时的占位值，SceneInfo.location 是必填字段
UNSPECIFIED_LOCATION = "未指定地点"

# 时段别名，统一为中文时段
_TIME_ALIASES: Dict[str, str] = {
    "day": "白天",
    "DAY": "白天",
    "白天": "白天",
    "日间": "白天",
    "日": "白天",
    "night": "夜晚",
    "NIGHT": "夜晚",
    "夜晚": "夜晚",
    "夜间": "夜晚",
    "夜": "夜晚",
    "dawn": "清晨",
    "DAWN": "清晨",
    "清晨": "清晨",
    "凌晨": "凌晨",
    "早晨": "清晨",
    "晨": "清晨",
    "morning": "早晨",
    "中午": "中午",
    "noon": "中午",
    "afternoon": "下午",
    "下午": "下午",
    "dusk": "黄昏",
    "DUSK": "黄昏",
    "黄昏": "黄昏",
    "傍晚": "黄昏",
    "昏": "黄昏",
    "evening": "晚上",
    "晚上": "晚上",
    "深夜": "深夜",
}

# 地点行里被误并入的时段词
_LOCATION_TIME_WORDS = frozenset(_TIME_ALIASES)

# 判定内景的场景标志词
_INDOOR_MARKERS = (
    "教室",
    "室内",
    "走廊",
    "房间",
    "卧室",
    "客厅",
    "办公室",
    "咖啡厅",
    "咖啡店",
    "大厅",
    "食堂",
    "图书馆",
    "商店",
    "店铺",
    "车厢",
    "车内",
)

_MAX_DESCRIPTION_LENGTH = 120


def _excluded_spans(text: str, exclusions: Sequence[str]) -> List[Tuple[int, int]]:
    """排除词在文本中占据的区间，用于避免「风格」被判成有风"""
    spans: List[Tuple[int, int]] = []
    for word in exclusions:
        if not word:
            continue
        start = text.find(word)
        while start >= 0:
            spans.append((start, start + len(word)))
            start = text.find(word, start + 1)
    return spans


def _is_excluded(position: int, length: int, spans: Sequence[Tuple[int, int]]) -> bool:
    """关键字出现位置是否完全落在排除词内部"""
    return any(start <= position and position + length <= end for start, end in spans)


def _is_time_note(raw: str) -> bool:
    """判断标题末尾的括注是否为时段说明，如「教室（黄昏）」"""
    match = re.search(r"[（(]([^）)]{1,10})[）)]$", raw)
    if not match:
        return False
    inner = match.group(1).strip()
    return inner in _TIME_ALIASES or any(
        word and word in inner for word in _TIME_ALIASES
    )


def _scene_text(scene: SceneDraft) -> str:
    """场景所有可见文本：标题 + 正文 + 场记值"""
    return f"{scene.heading} {scene.body_text} {scene.meta_text}"


class LocationAttributeRule(SceneAttributeRule):
    """场景地点：标题命名组 → 地点词表 → 未指定地点

    不用 ``ScriptParserConfig.extract_location_from_text``：它的模式会从
    「走进来」「在阳光里」里抽出「来」「阳光」，噪声远大于收益。
    """

    @property
    def name(self) -> str:
        return "location"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        location = self._from_heading(scene) or self._from_keywords(scene, context)
        scene.location = location or UNSPECIFIED_LOCATION

    @staticmethod
    def _from_heading(scene: SceneDraft) -> str:
        """标题命名组里的地点，去掉误并入的时段词与时段括注"""
        raw = (scene.heading_payload.get("location") or "").strip()
        if not raw:
            return ""
        raw = re.sub(r"[（(][^）)]{1,10}[）)]$", "", raw) if _is_time_note(raw) else raw
        kept = [
            part for part in raw.split() if part and part not in _LOCATION_TIME_WORDS
        ]
        return " ".join(kept).strip(" -–—")

    @staticmethod
    def _from_keywords(scene: SceneDraft, context: ParseContext) -> str:
        """在标题、正文与场记值里找已知地点，长词优先"""
        haystack = _scene_text(scene)
        keywords = context.vocabulary.location_keywords
        for word in sorted(keywords, key=len, reverse=True):
            if word and word in haystack:
                return word
        return ""


class TimeOfDayAttributeRule(SceneAttributeRule):
    """场景时间：标题时段命名组 → 正文时段扫描"""

    @property
    def name(self) -> str:
        return "time_of_day"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        scene.time_of_day = self.normalize(
            scene.heading_payload.get("time")
        ) or self._scan(scene)

    @staticmethod
    def normalize(raw: Optional[str]) -> Optional[str]:
        """统一时段写法为中文时段"""
        if not raw:
            return None
        text = raw.strip()
        if text in _TIME_ALIASES:
            return _TIME_ALIASES[text]
        keywords = ScriptParserConfig.DEFAULT_TIME_KEYWORDS
        for word, normalized in keywords.items():
            if word in text:
                return normalized
        for word, normalized in _TIME_ALIASES.items():
            if len(word) > 1 and word in text:
                return normalized
        return text or None

    def _scan(self, scene: SceneDraft) -> Optional[str]:
        """正文中出现的时段词"""
        haystack = f"{scene.heading} {scene.body_text}"
        for word in sorted(_TIME_ALIASES, key=len, reverse=True):
            if len(word) > 1 and word in haystack:
                return _TIME_ALIASES[word]
        return None


class WeatherAttributeRule(SceneAttributeRule):
    """场景天气：命中天气词且不在排除词内部"""

    @property
    def name(self) -> str:
        return "weather"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        text = _scene_text(scene)
        exclusions = _excluded_spans(text, context.vocabulary.weather_exclusions)
        for word, weather in context.vocabulary.weather_keywords.items():
            if not word:
                continue
            position = text.find(word)
            while position >= 0:
                if not _is_excluded(position, len(word), exclusions):
                    scene.weather = weather
                    return
                position = text.find(word, position + 1)


class AtmosphereAttributeRule(SceneAttributeRule):
    """场景氛围：按氛围词表命中数量取最高的一项"""

    @property
    def name(self) -> str:
        return "atmosphere"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        text = _scene_text(scene)
        best_label: Optional[str] = None
        best_hits = 0
        for label, words in context.vocabulary.atmosphere_keywords.items():
            hits = sum(1 for word in words if word and word in text)
            if hits > best_hits:
                best_label, best_hits = label, hits
        if best_label:
            scene.atmosphere = best_label


class SceneTypeAttributeRule(SceneAttributeRule):
    """内外景：标题的内/外景命名组 → 英文前缀 → 内景标志词"""

    @property
    def name(self) -> str:
        return "scene_type"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        inout = scene.heading_payload.get("inout") or ""
        if "内" in inout:
            scene.scene_type = "indoor"
            return
        if "外" in inout:
            scene.scene_type = "outdoor"
            return

        prefix = (scene.heading_payload.get("prefix") or "").upper()
        if prefix.startswith("EXT"):
            scene.scene_type = "outdoor"
            return
        if prefix.startswith(("INT", "I/E")):
            scene.scene_type = "indoor"
            return

        haystack = f"{scene.location} {_scene_text(scene)}"
        if any(marker in haystack for marker in _INDOOR_MARKERS):
            scene.scene_type = "indoor"


class SceneMetadataAttributeRule(SceneAttributeRule):
    """场景音频上下文元数据：有无对话/旁白、环境音素材"""

    @property
    def name(self) -> str:
        return "scene_metadata"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        scene.has_dialogue = any(
            draft.character and draft.type is ElementType.DIALOGUE
            for draft in scene.drafts
        )
        markers = context.vocabulary.voiceover_markers
        scene.has_voiceover = any(
            marker and marker in (draft.description or "")
            for draft in scene.drafts
            for marker in markers
        )
        scene.env_sounds = self._env_sounds(scene, context)

    @staticmethod
    def _env_sounds(scene: SceneDraft, context: ParseContext) -> List[str]:
        """正文里出现的重复音效词，最多取 3 个"""
        found: List[str] = []
        for word in context.vocabulary.recurring_sound_words:
            if word and word in scene.body_text and word not in found:
                found.append(word)
            if len(found) >= 3:
                break
        return found


class DescriptionAttributeRule(SceneAttributeRule):
    """场景描述：正文清洗后截断，正文为空时退化为地点"""

    @property
    def name(self) -> str:
        return "description"

    def apply(self, scene: SceneDraft, context: ParseContext) -> None:
        text = clean_text(scene.body_text)
        if not text:
            scene.description = scene.location
            return
        if len(text) > _MAX_DESCRIPTION_LENGTH:
            text = f"{text[:_MAX_DESCRIPTION_LENGTH]}…"
        scene.description = text


def default_scene_attribute_rules() -> List[SceneAttributeRule]:
    """默认场景属性规则链，顺序即依赖顺序，description 最后执行"""
    return [
        LocationAttributeRule(),
        TimeOfDayAttributeRule(),
        WeatherAttributeRule(),
        SceneTypeAttributeRule(),
        AtmosphereAttributeRule(),
        SceneMetadataAttributeRule(),
        DescriptionAttributeRule(),
    ]
