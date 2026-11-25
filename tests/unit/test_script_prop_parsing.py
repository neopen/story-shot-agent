"""道具结构化解析测试：LLM 输出、规则推断与下游消费。"""

from types import SimpleNamespace

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import (
    ContinuityGuardianChecker,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssueType,
)
from penshot.neopen.agent.script_parser.base_script_parser import BaseScriptParser
from penshot.neopen.agent.script_parser.rule_parser.element_builder import ElementBuilder
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    GlobalMetadata,
    PropItem,
)
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed


def _element(content: str, prop_object=None, character="小明", sequence=1):
    return SimpleNamespace(
        id=f"elem_{sequence:03d}",
        type=ElementType.ACTION,
        character=character,
        content=content,
        description="",
        sequence=sequence,
        prop_object=prop_object,
    )


class _ConcreteParser(BaseScriptParser):
    """只用于测试基类元素构建逻辑的最小实现"""

    def parser(self, script_text, script_format=None, repair_params=None, historical_context=None):
        return None


def test_llm_element_builder_preserves_prop_object():
    parser = _ConcreteParser()

    element = parser._build_element_data(
        {
            "id": "elem_001",
            "type": "action",
            "content": "他拿起钥匙",
            "prop_object": "钥匙",
        },
        0,
        0,
    )

    assert element.prop_object == "钥匙"


def test_bind_prop_objects_backfills_from_key_props():
    element = BaseElement(
        id="elem_001",
        type=ElementType.ACTION,
        sequence=1,
        content="他拿起钥匙",
    )
    scene = SimpleNamespace(elements=[element])
    metadata = GlobalMetadata(
        key_props=[PropItem(name="钥匙", description="铜钥匙")]
    )

    BaseScriptParser._bind_prop_objects([scene], metadata)

    assert element.prop_object == "钥匙"


def test_rule_element_builder_infers_prop_from_vocabulary():
    builder = object.__new__(ElementBuilder)
    builder._vocabulary = SimpleNamespace(
        prop_keywords={"keys": ["钥匙", "手机"]}
    )

    assert builder._infer_prop_object("他拿起钥匙") == "钥匙"
    assert builder._infer_prop_object("他看向窗外") is None


def test_checker_uses_grounded_structured_prop():
    """结构化道具在元素原文中出现时，即使没有持握动词也以结构化字段为准"""
    checker = ContinuityGuardianChecker()
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                elements=[
                    _element("他手里的照片被雨水打湿", "照片", sequence=1),
                    _element("他攥着钥匙站在门口", "钥匙", sequence=2),
                ],
            )
        ]
    )
    result = ContinuityCheckResult()

    checker.check_prop_continuity({"parsed_script": parsed}, result)

    assert result.issues_by_type.get(ContinuityIssueType.PROP_CHANGE.value)


def test_checker_ignores_ungrounded_structured_prop():
    """元素原文未提及的结构化道具不可信（可能是他人/容器里的道具），不参与比较"""
    checker = ContinuityGuardianChecker()
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                elements=[
                    _element("看向窗外", "照片", sequence=1),
                    _element("沉默", "钥匙", sequence=2),
                ],
            )
        ]
    )
    result = ContinuityCheckResult()

    checker.check_prop_continuity({"parsed_script": parsed}, result)

    assert result.issues_by_type.get(ContinuityIssueType.PROP_CHANGE.value, []) == []


def test_contract_merges_element_level_props():
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="书房",
                time_of_day="night",
                weather="clear",
                elements=[_element("拿起钥匙", "钥匙", sequence=1)],
            )
        ],
        characters=[],
        global_metadata=SimpleNamespace(
            key_props=[],
            character_outfits=[],
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
    )

    contract = build_contract_from_parsed(parsed, script_id="SN_PROP")

    assert contract.scenes[1].props_in_scene == {"钥匙": "present"}
