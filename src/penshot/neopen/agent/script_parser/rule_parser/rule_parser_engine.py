"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: rule_parser_engine.py
@Description: 规则解析引擎 - 按固定流水线组装分段、属性与实体规则并产出 ParsedScript
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import Any, List, Optional, Sequence

from penshot.logger import debug, info
from penshot.neopen.agent.script_parser.rule_parser.character_rule import (
    default_character_rule,
)
from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
    RuleVocabulary,
)
from penshot.neopen.agent.script_parser.rule_parser.costume_rule import (
    default_costume_rule,
)
from penshot.neopen.agent.script_parser.rule_parser.element_builder import (
    ElementBuilder,
    SequenceCounter,
    default_element_builder,
)
from penshot.neopen.agent.script_parser.rule_parser.global_aggregator import (
    GlobalAggregator,
)
from penshot.neopen.agent.script_parser.rule_parser.line_classifiers import (
    LineClassifierChain,
    ScriptTokenizer,
    default_line_classifiers,
)
from penshot.neopen.agent.script_parser.rule_parser.location_rule import (
    default_location_rule,
)
from penshot.neopen.agent.script_parser.rule_parser.prop_rule import default_prop_rule
from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import (
    EntityRule,
    RuleRegistry,
    SceneAttributeRule,
)
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    ParseContext,
    RuleDiagnostics,
)
from penshot.neopen.agent.script_parser.rule_parser.scene_attribute_rules import (
    default_scene_attribute_rules,
)
from penshot.neopen.agent.script_parser.rule_parser.scene_segmenter import (
    SceneSegmenter,
)
from penshot.neopen.agent.script_parser.rule_parser.script_builder import (
    ParsedScriptBuilder,
)
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript

# 实体规则的名称即其产出的实体类型，聚合器按此取用各规则的结果
_ENTITY_CHARACTER = "character"
_ENTITY_PROP = "prop"
_ENTITY_COSTUME = "costume"
_ENTITY_LOCATION = "location"


def default_entity_rules(vocabulary: RuleVocabulary) -> List[EntityRule[Any]]:
    """默认实体规则：角色、道具、服装、地点各司其职"""
    return [
        default_character_rule(),
        default_prop_rule(),
        default_costume_rule(),
        default_location_rule(),
    ]


class RuleParserEngine:
    """规则解析引擎（Facade）

    固定流水线：断行分类 → 场景分段 → 场景属性 → 元素构建 → 实体抽取 →
    全局聚合 → 结果组装。每一步的规则集合都可以在构造时替换，
    因此扩展只需注册新规则，不必改动引擎本身。
    """

    def __init__(
        self,
        vocabulary: Optional[RuleVocabulary] = None,
        classifier_chain: Optional[LineClassifierChain] = None,
        segmenter: Optional[SceneSegmenter] = None,
        scene_rules: Optional[Sequence[SceneAttributeRule]] = None,
        entity_rules: Optional[Sequence[EntityRule[Any]]] = None,
        element_builder: Optional[ElementBuilder] = None,
        aggregator: Optional[GlobalAggregator] = None,
        builder: Optional[ParsedScriptBuilder] = None,
    ) -> None:
        self._vocabulary = vocabulary or RuleVocabulary()
        self._chain = classifier_chain or LineClassifierChain(
            default_line_classifiers()
        )
        self._segmenter = segmenter or SceneSegmenter(self._vocabulary)

        self._scene_rules: RuleRegistry[SceneAttributeRule] = RuleRegistry[
            SceneAttributeRule
        ](SceneAttributeRule)
        self._scene_rules.register_all(
            list(scene_rules or default_scene_attribute_rules())
        )

        self._entity_rules: RuleRegistry[EntityRule[Any]] = RuleRegistry[
            EntityRule[Any]
        ](EntityRule)
        self._entity_rules.register_all(
            list(entity_rules or default_entity_rules(self._vocabulary))
        )

        self._element_builder = element_builder or default_element_builder(
            self._vocabulary
        )
        self._aggregator = aggregator or GlobalAggregator()
        self._builder = builder or ParsedScriptBuilder()

    @property
    def vocabulary(self) -> RuleVocabulary:
        """引擎使用的词表，便于调用方定制后重建引擎"""
        return self._vocabulary

    @property
    def entity_rule_names(self) -> List[str]:
        """已注册的实体规则名称"""
        return self._entity_rules.names()

    @property
    def scene_rule_names(self) -> List[str]:
        """已注册的场景属性规则名称"""
        return self._scene_rules.names()

    def parse(self, script_text: str) -> ParsedScript:
        """解析剧本文本，任何情况下都返回 ParsedScript

        文本为空或未识别到场景时返回带 ``failed`` 标记的兜底结果，
        由调用方决定是否降级，不在此处抛异常。
        """
        text = script_text if isinstance(script_text, str) else ""
        if not text.strip():
            info("规则解析：输入文本为空")
            return self._builder.build_fallback(reason="输入文本为空")

        context = self._segment(text)
        if not context.scenes:
            info("规则解析：未识别到任何场景")
            return self._builder.build_fallback(
                title=context.title, reason="未识别到任何场景"
            )

        self._apply_scene_rules(context)
        self._element_builder.build(context.scenes, SequenceCounter())

        characters = self._extract(context, _ENTITY_CHARACTER)
        global_metadata = self._aggregator.aggregate(
            context,
            self._extract(context, _ENTITY_PROP),
            self._extract(context, _ENTITY_COSTUME),
            self._extract(context, _ENTITY_LOCATION),
        )
        parsed = self._builder.build(context, characters, global_metadata)
        info(
            f"规则解析完成: {len(parsed.scenes)} 个场景, "
            f"{len(parsed.characters)} 个角色, {parsed.stats['total_elements']} 个元素"
        )
        debug(f"规则解析诊断: {context.diagnostics.classifier_hits}")
        return parsed

    # ---------------------------- 流水线各步 ----------------------------
    def _segment(self, text: str) -> ParseContext:
        """断行、分类并切分场景"""
        diagnostics = RuleDiagnostics()
        tokens = self._chain.classify_all(
            ScriptTokenizer().tokenize(text), self._vocabulary, diagnostics
        )
        result = self._segmenter.segment(tokens, diagnostics)
        debug(
            f"规则解析：{diagnostics.lines_total} 行, {len(result.scenes)} 个场景, "
            f"标题 {result.title!r}"
        )
        return ParseContext(
            raw_text=text,
            vocabulary=self._vocabulary,
            title=result.title,
            scenes=result.scenes,
            tokens=tokens,
            diagnostics=diagnostics,
        )

    def _apply_scene_rules(self, context: ParseContext) -> None:
        """逐场景补齐地点、时间、天气、氛围等属性"""
        for scene in context.scenes:
            for rule in self._scene_rules.all():
                rule.apply(scene, context)

    def _extract(self, context: ParseContext, entity_type: str) -> List[Any]:
        """按实体类型取用对应规则的结果"""
        rule = self._entity_rules.get(entity_type)
        if rule is None:
            return []
        return list(rule.extract(context))


def default_engine() -> RuleParserEngine:
    """默认规则解析引擎"""
    return RuleParserEngine()


def parse_with_rules(script_text: str) -> ParsedScript:
    """便捷入口：用默认引擎解析一段剧本文本"""
    return RuleParserEngine().parse(script_text)
