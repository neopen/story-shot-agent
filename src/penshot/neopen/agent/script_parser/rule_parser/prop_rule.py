"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: prop_rule.py
@Description: 道具规则 - 从道具词表与「关键道具：」场记里抽取贯穿全剧的道具
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

import re
from typing import Dict, List, Optional

from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import EntityRule
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    PropCandidate,
    ParseContext,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import label_values

# 关键道具列表里不可能成为道具名的片段
_NOISE_PARTS = frozenset({"", "无", "略", "同上", "其他"})
# 道具名长度区间
_MIN_PROP_LENGTH = 2
_MAX_PROP_LENGTH = 20
# 列表项分隔符
_LIST_SPLIT_RE = re.compile(r"[-–—•·、,，;；\n]|\d+[.．]")
# 场记里的道具标签
_PROP_LABELS = ("关键道具", "道具", "物品")


class PropRule(EntityRule[PropCandidate]):
    """道具抽取规则

    命中来源：道具词表、``关键道具：`` 场记列表、出现/消失标记词。
    """

    @property
    def name(self) -> str:
        return "prop"

    @property
    def entity_type(self) -> str:
        return "prop"

    def extract(self, context: ParseContext) -> List[PropCandidate]:
        candidates: Dict[str, PropCandidate] = {}
        self._from_keywords(context, candidates)
        self._from_meta_labels(context, candidates)
        self._apply_markers(context, candidates)
        return list(candidates.values())

    # ---------------------------- 来源一：道具词表 ----------------------------
    def _from_keywords(
        self, context: ParseContext, candidates: Dict[str, PropCandidate]
    ) -> None:
        for category, words in context.vocabulary.prop_keywords.items():
            for word in words:
                if not word:
                    continue
                for scene in context.scenes:
                    if word not in f"{scene.body_text} {scene.meta_text}":
                        continue
                    candidate = self._ensure(candidates, word, scene.id, category)
                    if not candidate.color:
                        candidate.color = self._find_color(
                            context, word, scene.body_text
                        )

    # ---------------------------- 来源二：场记标签 ----------------------------
    def _from_meta_labels(
        self, context: ParseContext, candidates: Dict[str, PropCandidate]
    ) -> None:
        """解析「关键道具：」后面列出的道具项"""
        for scene in context.scenes:
            for label in _PROP_LABELS:
                for value in label_values(scene.meta_text, label):
                    for part in _LIST_SPLIT_RE.split(value):
                        name = part.strip(" ：:*-—")
                        if not _is_prop_name(name):
                            continue
                        candidate = self._ensure(candidates, name, scene.id, "meta")
                        if not candidate.description:
                            candidate.description = f"场记标注的关键道具：{name}"

    def _ensure(
        self,
        candidates: Dict[str, PropCandidate],
        name: str,
        scene_id: str,
        category: str,
    ) -> PropCandidate:
        candidate = candidates.get(name)
        if candidate is None:
            candidate = PropCandidate(name=name, scene_id=scene_id, description="")
            candidates[name] = candidate
        if scene_id not in candidate.appears_in:
            candidate.appears_in.append(scene_id)
        return candidate

    # ---------------------------- 来源三：出现/消失标记 ----------------------------
    @staticmethod
    def _apply_markers(
        context: ParseContext, candidates: Dict[str, PropCandidate]
    ) -> None:
        markers = {
            "appear": context.vocabulary.prop_appearance_markers,
            "disappear": context.vocabulary.prop_disappearance_markers,
            "change": context.vocabulary.prop_state_change_markers,
        }
        for candidate in candidates.values():
            for scene in context.scenes:
                if scene.id not in candidate.appears_in:
                    continue
                text = f"{scene.body_text} {scene.meta_text}"
                for marker, patterns in markers.items():
                    if any(_pattern_hit(pattern, text) for pattern in patterns):
                        candidate.marker = marker
                        break
                if candidate.marker:
                    break

    @staticmethod
    def _find_color(context: ParseContext, word: str, text: str) -> Optional[str]:
        """道具名前后 10 字内出现的颜色词"""
        position = text.find(word)
        if position < 0:
            return None
        window = text[max(0, position - 10) : position + len(word) + 10]
        for color in context.vocabulary.color_words:
            if color and color in window:
                return color
        return None


def _is_prop_name(name: str) -> bool:
    if name in _NOISE_PARTS:
        return False
    return _MIN_PROP_LENGTH <= len(name) <= _MAX_PROP_LENGTH


def _pattern_hit(pattern: str, text: str) -> bool:
    """标记词可能带正则（如「从[…]拿出」），编译失败时退化为子串匹配"""
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return pattern in text


def default_prop_rule() -> PropRule:
    """默认道具规则"""
    return PropRule()
