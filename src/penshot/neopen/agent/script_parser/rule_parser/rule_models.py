"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: rule_models.py
@Description: 规则解析器内部工作模型
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.script_parser_models import BaseElement

if TYPE_CHECKING:
    from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
        RuleVocabulary,
    )


class LineKind(str, Enum):
    """剧本行的语法角色"""

    SCENE_HEADING = "scene_heading"
    CHARACTER = "character"
    TRANSITION = "transition"
    PARENTHETICAL = "parenthetical"
    ACTION = "action"
    EMPTY = "empty"


@dataclass
class LineToken:
    """预处理后的剧本行"""

    index: int
    raw: str
    text: str
    kind: LineKind = LineKind.ACTION
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_blank(self) -> bool:
        return not self.text


@dataclass
class LineMatch:
    """行分类命中结果，由 LineClassifier 返回"""

    kind: LineKind
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8


@dataclass
class ElementDraft:
    """元素草稿 - 分段阶段产出，随后由 ElementBuilder 转换为 BaseElement"""

    type: ElementType
    content: str
    source_line: int = 0
    character: Optional[str] = None
    target_character: Optional[str] = None
    description: Optional[str] = None
    emotion: Optional[str] = None
    intensity: Optional[float] = None
    duration: Optional[float] = None
    confidence: float = 0.8


@dataclass
class SceneDraft:
    """场景草稿 - 分段阶段产出的中间场景，供属性规则和实体规则扫描"""

    index: int
    id: str
    heading: str = ""
    heading_payload: Dict[str, Any] = field(default_factory=dict)
    location: str = ""
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    atmosphere: str = "neutral"
    scene_type: str = "outdoor"
    description: Optional[str] = None
    drafts: List[ElementDraft] = field(default_factory=list)
    elements: List[BaseElement] = field(default_factory=list)
    body_text: str = ""
    meta_text: str = ""
    has_dialogue: bool = False
    has_voiceover: bool = False
    env_sounds: List[str] = field(default_factory=list)


@dataclass
class SegmentResult:
    """分段结果"""

    scenes: List[SceneDraft] = field(default_factory=list)
    title: Optional[str] = None
    diagnostics: "RuleDiagnostics" = field(default_factory=lambda: RuleDiagnostics())


@dataclass
class PropCandidate:
    """道具候选 - 同一道具在多个场景命中后合并为 PropItem"""

    name: str
    scene_id: str
    description: str = ""
    color: Optional[str] = None
    importance: str = "medium"
    marker: Optional[str] = None
    appears_in: List[str] = field(default_factory=list)


@dataclass
class OutfitCandidate:
    """服装候选 - 同一角色的同类服装合并为 CharacterOutfit"""

    character: str
    description: str
    scene_id: str
    color: Optional[str] = None
    style: Optional[str] = None
    material: Optional[str] = None
    keyword: Optional[str] = None


@dataclass
class LocationCandidate:
    """地点候选 - 同一地点合并为 LocationItem"""

    name: str
    scene_id: str
    description: str = ""
    visual_cues: List[str] = field(default_factory=list)


@dataclass
class RuleDiagnostics:
    """规则解析诊断信息 - 用于调试与质量审计，不进入 ParsedScript 模型"""

    lines_total: int = 0
    classifier_hits: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def record_hit(self, kind: LineKind) -> None:
        """记录一次行分类命中"""
        self.classifier_hits[kind.value] = self.classifier_hits.get(kind.value, 0) + 1

    def note(self, message: str) -> None:
        """记录一条诊断说明"""
        self.notes.append(message)


@dataclass
class ParseContext:
    """解析上下文 - 在各规则之间传递的共享状态"""

    raw_text: str
    vocabulary: "RuleVocabulary"
    title: Optional[str] = None
    scenes: List[SceneDraft] = field(default_factory=list)
    tokens: List[LineToken] = field(default_factory=list)
    diagnostics: RuleDiagnostics = field(default_factory=lambda: RuleDiagnostics())

    def scene_texts(self) -> List[str]:
        """所有场景正文，用于全局实体抽取"""
        return [scene.body_text for scene in self.scenes]

    def scene_texts_with_meta(self) -> List[str]:
        """场景正文与场记值，用于抽取「关键道具：」这类场记里提到的实体"""
        return [f"{scene.body_text} {scene.meta_text}" for scene in self.scenes]

    def scene_of_line(self, line_index: int) -> Optional[SceneDraft]:
        """按元素来源行号反查所属场景"""
        for scene in self.scenes:
            if any(draft.source_line == line_index for draft in scene.drafts):
                return scene
        return None
