"""一致性契约校验器（Validator）的回归测试。

覆盖镜头角色归属、片段-镜头关联、以及无契约时的放行行为。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.contract_validator import (
    validate_fragment_sequence,
    validate_shot_sequence,
)
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed


def _contract(character_names):
    """构造最小契约桩"""
    return SimpleNamespace(characters={name: object() for name in character_names})


def test_shot_unknown_character_detected():
    """镜头出现契约外角色时报告 unknown_character"""
    contract = _contract(["小明"])
    shot_sequence = SimpleNamespace(
        shots=[
            SimpleNamespace(id="shot_001", main_character="小明"),
            SimpleNamespace(id="shot_002", main_character="路人甲"),
        ]
    )
    issues = validate_shot_sequence(shot_sequence, contract)
    assert len(issues) == 1
    assert issues[0]["type"] == "unknown_character"
    assert issues[0]["shot_id"] == "shot_002"
    assert issues[0]["character"] == "路人甲"


def test_shot_all_known_passes():
    """镜头角色全部属于契约时无违规"""
    contract = _contract(["小明"])
    shot_sequence = SimpleNamespace(
        shots=[SimpleNamespace(id="shot_001", main_character="小明")]
    )
    assert validate_shot_sequence(shot_sequence, contract) == []


def test_no_contract_no_issues():
    """无契约时放行（不阻塞）"""
    shot_sequence = SimpleNamespace(
        shots=[SimpleNamespace(id="shot_001", main_character="路人甲")]
    )
    assert validate_shot_sequence(shot_sequence, None) == []


def test_placeholder_character_ignored():
    """LLM 误填的非角色占位词（如"场景"）不应被判为违规"""
    contract = _contract(["小明"])
    shot_sequence = SimpleNamespace(
        shots=[
            SimpleNamespace(id="shot_001", main_character="场景"),
            SimpleNamespace(id="shot_002", main_character="  "),
            SimpleNamespace(id="shot_003", main_character="None"),
            SimpleNamespace(id="shot_004", main_character="旁白"),
            SimpleNamespace(id="shot_005", main_character="空镜头"),
        ]
    )
    assert validate_shot_sequence(shot_sequence, contract) == []


def test_character_name_whitespace_normalized():
    """角色名首尾空白应被归一化后再匹配契约"""
    contract = _contract(["小明"])
    shot_sequence = SimpleNamespace(
        shots=[SimpleNamespace(id="shot_001", main_character=" 小明 ")]
    )
    assert validate_shot_sequence(shot_sequence, contract) == []


def test_fragment_orphan_and_unknown():
    """片段检测：孤立片段与契约外角色"""
    contract = _contract(["小明"])
    shot_sequence = SimpleNamespace(
        shots=[SimpleNamespace(id="shot_001", main_character="路人甲")]
    )
    fragment_sequence = SimpleNamespace(
        fragments=[
            SimpleNamespace(id="frag_001", shot_id="shot_001"),
            SimpleNamespace(id="frag_002", shot_id="shot_999"),
        ]
    )
    issues = validate_fragment_sequence(fragment_sequence, shot_sequence, contract)
    issue_types = {issue["type"] for issue in issues}
    assert "unknown_character" in issue_types
    assert "orphan_fragment" in issue_types


def test_contract_from_parsed_registers_scene_absent_characters():
    """剧本角色表中有、场景元素无的角色也必须登记，避免误判契约外角色"""
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="客厅",
                time_of_day="night",
                elements=[SimpleNamespace(character="陈默")],
            )
        ],
        characters=[
            SimpleNamespace(name="陈默", description="青年男子"),
            SimpleNamespace(name="门口黑影", description="门缝外模糊的黑影"),
        ],
        global_metadata=None,
        title="门外的影子",
    )
    contract = build_contract_from_parsed(parsed, script_id="s1")

    assert "门口黑影" in contract.characters
    shot_sequence = SimpleNamespace(
        shots=[SimpleNamespace(id="shot_001", main_character="门口黑影")]
    )
    assert validate_shot_sequence(shot_sequence, contract) == []
