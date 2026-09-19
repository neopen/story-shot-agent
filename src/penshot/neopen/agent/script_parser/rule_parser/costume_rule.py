"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE For Details.

@FileName: costume_rule.py
@Description: 服装规则 - 从服装词表与穿着描述句里抽取角色服装
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import Dict, List, Optional, Tuple

from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import EntityRule
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    OutfitCandidate,
    ParseContext,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import (
    find_nearest_subject,
    split_sentences,
)

# 描述穿着状态的动词，出现在角色名与服装之间
_WEAR_MARKERS = ("穿着", "戴着", "围着", "披着", "换上", "套着")
# 描述内容截断长度
_MAX_DESCRIPTION_LENGTH = 40


class CostumeRule(EntityRule[OutfitCandidate]):
    """服装抽取规则

    对每句话先定位穿着主体，再取出服装词或穿着短语；找不到主体时归给
    该场景的主要说话人，避免服装信息丢失。
    """

    @property
    def name(self) -> str:
        return "costume"

    @property
    def entity_type(self) -> str:
        return "costume"

    def extract(self, context: ParseContext) -> List[OutfitCandidate]:
        candidates: List[OutfitCandidate] = []
        for scene in context.scenes:
            speaker = self._primary_speaker(scene)
            for sentence in split_sentences(scene.body_text):
                candidates.extend(
                    self._from_sentence(sentence, scene.id, speaker, context)
                )
        return self._dedupe(candidates)

    # ---------------------------- 单句处理 ----------------------------
    def _from_sentence(
        self,
        sentence: str,
        scene_id: str,
        speaker: Optional[str],
        context: ParseContext,
    ) -> List[OutfitCandidate]:
        keyword = self._match_keyword(sentence, context)
        wear_phrase = self._wear_phrase(sentence)
        if not keyword and not wear_phrase:
            return []

        character = self._find_character(sentence, context) or speaker
        if not character:
            return []

        description = (
            context.vocabulary.costume_keywords.get(keyword)
            if keyword and context.vocabulary.costume_keywords.get(keyword)
            else (wear_phrase or keyword or "")
        )
        return [
            OutfitCandidate(
                character=character,
                description=description,
                scene_id=scene_id,
                color=self._find_color(sentence, context),
                style=self._find_word(sentence, context.vocabulary.costume_style_words),
                material=self._find_word(
                    sentence, context.vocabulary.costume_material_words
                ),
                keyword=keyword,
            )
        ]

    def _match_keyword(self, sentence: str, context: ParseContext) -> Optional[str]:
        """命中服装词表，长词优先避免「校服」被「服」抢先"""
        keywords = context.vocabulary.costume_keywords
        for word in sorted(keywords, key=len, reverse=True):
            if word and word in sentence:
                return word
        return None

    @staticmethod
    def _wear_phrase(sentence: str) -> str:
        """「穿着洗得发白的校服」这类穿着短语"""
        for marker in _WEAR_MARKERS:
            position = sentence.find(marker)
            if position < 0:
                continue
            tail = sentence[position : position + _MAX_DESCRIPTION_LENGTH]
            return tail.split("，")[0].strip("。！？；")
        return ""

    def _find_character(self, sentence: str, context: ParseContext) -> Optional[str]:
        """穿着主体：回溯小句主语，如「张晨抱着篮球，校服敞开」"""
        return find_nearest_subject(
            sentence, len(sentence), context.vocabulary.subject_verbs, strict=False
        )

    @staticmethod
    def _find_color(sentence: str, context: ParseContext) -> Optional[str]:
        for color in context.vocabulary.color_words:
            if color and color in sentence:
                return color
        return None

    @staticmethod
    def _find_word(sentence: str, words: List[str]) -> Optional[str]:
        for word in words:
            if word and word in sentence:
                return word
        return None

    @staticmethod
    def _primary_speaker(scene) -> Optional[str]:
        """场景里台词最多的角色"""
        counts: Dict[str, int] = {}
        for draft in scene.drafts:
            if draft.character:
                counts[draft.character] = counts.get(draft.character, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _dedupe(candidates: List[OutfitCandidate]) -> List[OutfitCandidate]:
        """同一角色同一服装词只保留一条"""
        seen: Dict[Tuple[str, str], OutfitCandidate] = {}
        result: List[OutfitCandidate] = []
        for candidate in candidates:
            key = (candidate.character, candidate.keyword or candidate.description)
            if key in seen:
                existing = seen[key]
                if candidate.scene_id != existing.scene_id:
                    existing.description = existing.description or candidate.description
                continue
            seen[key] = candidate
            result.append(candidate)
        return result


def default_costume_rule() -> CostumeRule:
    """默认服装规则"""
    return CostumeRule()
