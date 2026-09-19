"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: element_builder.py
@Description: 元素构建 - 把元素草稿补齐时长/情绪/强度后落成 BaseElement
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import Sequence

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
    RuleVocabulary,
)
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    ElementDraft,
    SceneDraft,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import char_count
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    EmotionType,
)

# 语速基准：对话每秒 6 字，动作每秒 12 字
_DIALOGUE_CHARS_PER_SECOND = 6.0
_ACTION_CHARS_PER_SECOND = 12.0
# 元素时长上下限，下限不能低于 BaseElement.duration 的 0.5
_MIN_DURATION = 1.0
_MAX_DURATION = 10.0
# 强度词命中后的强度取值
_HIGH_INTENSITY = 0.8
_LOW_INTENSITY = 0.3
_DEFAULT_INTENSITY = 0.5


def element_id(sequence: int) -> str:
    """元素 id，与全局 sequence 一致，保证全剧唯一"""
    return f"elem_{sequence:03d}"


class SequenceCounter:
    """跨场景全局递增的 sequence 计数器"""

    def __init__(self, start: int = 0) -> None:
        self._value = start

    @property
    def value(self) -> int:
        return self._value

    def next(self) -> int:
        self._value += 1
        return self._value


class InferenceHelper:
    """元素推断的模板方法：时长、情绪与强度

    子类可覆写 ``duration``/``emotion``/``intensity`` 中的任意一项替换推断策略。
    """

    def __init__(self, vocabulary: RuleVocabulary) -> None:
        self._vocabulary = vocabulary

    def intensity(self, draft: ElementDraft) -> float:
        """按强度词表判定强度"""
        text = f"{draft.content} {draft.description or ''}"
        if any(
            word and word in text for word in self._vocabulary.intensity_high_keywords
        ):
            return _HIGH_INTENSITY
        if any(
            word and word in text for word in self._vocabulary.intensity_low_keywords
        ):
            return _LOW_INTENSITY
        return _DEFAULT_INTENSITY

    def duration(self, draft: ElementDraft) -> float:
        """按字数与语速估算时长，强度越大语速影响后的时长越长"""
        length = char_count(draft.content)
        rate = (
            _DIALOGUE_CHARS_PER_SECOND
            if draft.type is ElementType.DIALOGUE
            else _ACTION_CHARS_PER_SECOND
        )
        seconds = length / rate * (0.75 + self.intensity(draft))
        return round(min(max(seconds, _MIN_DURATION), _MAX_DURATION), 1)

    def emotion(self, draft: ElementDraft) -> str:
        """情绪优先级：括号提示 → 情绪词表 → neutral"""
        cued = self._cued_emotion(draft.description)
        if cued:
            return cued
        return self._keyword_emotion(draft.content)

    def _cued_emotion(self, description: str | None) -> str | None:
        """把「（温和地）」这类表演提示映射为情绪值"""
        if not description:
            return None
        text = description.strip("（）()")
        for cue, emotion in self._vocabulary.cue_emotion_map.items():
            if cue and cue in text:
                return emotion
        return None

    def _keyword_emotion(self, content: str) -> str:
        """先扫非平静类情绪词，平静词表过宽，只在没有其他命中时才采用"""
        calm = EmotionType.CALM.value
        fallback: str | None = None
        for emotion, words in self._vocabulary.emotion_keywords.items():
            if not any(word and word in content for word in words):
                continue
            if emotion == calm:
                fallback = calm
                continue
            return emotion
        return fallback or EmotionType.NEUTRAL.value


class ElementBuilder:
    """把场景内的元素草稿转成 BaseElement 列表"""

    def __init__(
        self, vocabulary: RuleVocabulary, inference: InferenceHelper | None = None
    ) -> None:
        self._vocabulary = vocabulary
        self._inference = inference or InferenceHelper(vocabulary)

    def build(self, scenes: Sequence[SceneDraft], counter: SequenceCounter) -> None:
        """就地填充每个场景的 elements，sequence 全局连续"""
        for scene in scenes:
            scene.elements = [
                self._create(draft, scene, counter.next()) for draft in scene.drafts
            ]

    def _create(
        self, draft: ElementDraft, scene: SceneDraft, sequence: int
    ) -> BaseElement:
        return BaseElement(
            id=element_id(sequence),
            type=draft.type,
            sequence=sequence,
            duration=self._inference.duration(draft),
            confidence=draft.confidence,
            content=draft.content,
            character=draft.character,
            target_character=draft.target_character,
            description=self._describe(draft),
            intensity=self._inference.intensity(draft),
            emotion=self._inference.emotion(draft),
        )

    @staticmethod
    def _describe(draft: ElementDraft) -> str:
        """description 必须是字符串；模型声明为 str，显式传 None 会校验失败"""
        return draft.description or ""


def default_element_builder(vocabulary: RuleVocabulary) -> ElementBuilder:
    """默认元素构建器"""
    return ElementBuilder(vocabulary)
