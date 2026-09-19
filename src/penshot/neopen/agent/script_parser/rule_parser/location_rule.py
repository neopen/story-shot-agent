"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: location_rule.py
@Description: 地点规则 - 汇总各场景地点并抽取视觉特征
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import List

from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import EntityRule
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    LocationCandidate,
    ParseContext,
)
from penshot.neopen.agent.script_parser.rule_parser.scene_attribute_rules import (
    UNSPECIFIED_LOCATION,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import split_sentences

# 每个地点保留的视觉特征条数上限
_MAX_VISUAL_CUES = 4


class LocationRule(EntityRule[LocationCandidate]):
    """地点抽取规则

    地点名来自场景属性规则的结果，视觉特征来自视觉线索词与含线索词的原句。
    """

    @property
    def name(self) -> str:
        return "location"

    @property
    def entity_type(self) -> str:
        return "location"

    def extract(self, context: ParseContext) -> List[LocationCandidate]:
        candidates: List[LocationCandidate] = []
        for scene in context.scenes:
            if not scene.location or scene.location == UNSPECIFIED_LOCATION:
                continue
            candidates.append(
                LocationCandidate(
                    name=scene.location,
                    scene_id=scene.id,
                    description=scene.description or scene.location,
                    visual_cues=self._visual_cues(scene, context),
                )
            )
        return candidates

    def _visual_cues(self, scene, context: ParseContext) -> List[str]:
        """视觉线索：先记命中词，再补充含线索词的原句"""
        words = context.vocabulary.visual_cue_words
        text = f"{scene.body_text} {scene.meta_text}"
        cues: List[str] = []
        for word in words:
            if word and word in text and word not in cues:
                cues.append(word)
            if len(cues) >= _MAX_VISUAL_CUES:
                return cues

        for sentence in split_sentences(scene.body_text):
            if len(cues) >= _MAX_VISUAL_CUES:
                break
            if (
                any(word and word in sentence for word in words)
                and sentence not in cues
            ):
                cues.append(sentence)
        return cues[:_MAX_VISUAL_CUES]


def default_location_rule() -> LocationRule:
    """默认地点规则"""
    return LocationRule()
