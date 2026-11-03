"""M0.4.1 连续性契约前置约束的回归测试。

覆盖 AssetContract 注册与序列化、契约从场景填充角色，以及 DomainState
新增的 contract 一等公民字段，防止契约未接线或字段漂移。
"""

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)


def test_register_asset_and_serialize():
    """资产锚点注册后可在 to_dict 中序列化"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_asset(
        AssetContract(
            asset_id="char_xiaoming_sheet",
            asset_type="character_sheet",
            owner_name="小明",
            image_prompt="three-view character sheet",
        )
    )
    assert "char_xiaoming_sheet" in contract.assets
    data = contract.to_dict()
    assert data["assets"]["char_xiaoming_sheet"]["asset_type"] == "character_sheet"
    assert data["assets"]["char_xiaoming_sheet"]["status"] == "pending"


def test_register_scene_fills_characters():
    """注册场景时同步填充出场角色"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="公寓客厅",
            time_of_day="night",
            characters_in_scene=["小明", "小红"],
        )
    )
    assert 1 in contract.scenes
    assert set(contract.characters.keys()) == {"小明", "小红"}
    assert contract.characters["小明"].appearance_scenes == [1]


def test_set_style_anchor():
    """风格锚点写入并进入序列化"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.set_style_anchor("genre", "drama")
    assert contract.style_anchor["genre"] == "drama"
    assert contract.to_dict()["style_anchor"]["genre"] == "drama"


def test_domain_state_has_contract_field():
    """DomainState 提供 contract 一等公民字段，默认 None"""
    from penshot.neopen.agent.workflow.workflow_state_types import DomainState

    domain = DomainState()
    assert domain.contract is None


def test_scene_number_from_id_and_fallback():
    """场景序号优先从 scene.id 提取，失败退回顺序号"""
    from types import SimpleNamespace

    from penshot.neopen.agent.script_parser_agent import ScriptParserAgent

    assert ScriptParserAgent._scene_number(SimpleNamespace(id="scene_003"), 1) == 3
    assert ScriptParserAgent._scene_number(SimpleNamespace(id=""), 5) == 5


def test_scene_characters_dedup():
    """从场景元素提取角色并去重保序"""
    from types import SimpleNamespace

    from penshot.neopen.agent.script_parser_agent import ScriptParserAgent

    scene = SimpleNamespace(
        elements=[
            SimpleNamespace(character="小明"),
            SimpleNamespace(character=None),
            SimpleNamespace(character="小红"),
            SimpleNamespace(character="小明"),
        ]
    )
    assert ScriptParserAgent._scene_characters(scene) == ["小明", "小红"]


def test_process_with_contract_fills_contract(monkeypatch):
    """process_with_contract 从真实结构填充契约（防 scene.number 之类的字段漂移）"""
    from types import SimpleNamespace

    from penshot.neopen.agent.script_parser_agent import ScriptParserAgent

    agent = object.__new__(ScriptParserAgent)
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="公寓客厅",
                time_of_day="night",
                elements=[
                    SimpleNamespace(character="小明"),
                    SimpleNamespace(character="小红"),
                ],
            )
        ],
        global_metadata=SimpleNamespace(
            continuity_notes="", audio_atmosphere="neutral"
        ),
        title="雨夜来电",
    )
    monkeypatch.setattr(agent, "parser_process", lambda text: parsed)

    result, contract = agent.process_with_contract("剧本")

    assert result is parsed
    assert 1 in contract.scenes
    assert contract.scenes[1].location == "公寓客厅"
    assert set(contract.characters.keys()) == {"小明", "小红"}
    assert contract.style_anchor.get("title") == "雨夜来电"


def test_build_character_anchor_suffix():
    """契约中角色外观锚点生成统一的英文标签后缀"""
    from penshot.neopen.agent.continuity_guardian.consistency_contract import (
        CharacterContract,
    )
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    character = CharacterContract(name="小明")
    character.appearance_anchors = {"clothing": "黑色羽绒服"}
    contract.characters["小明"] = character

    suffix = PromptConverterAgent._build_character_anchor_suffix("小明", contract)
    assert suffix == "[Character consistency: 小明, clothing: 黑色羽绒服]"
    assert PromptConverterAgent._build_character_anchor_suffix("", contract) == ""
    assert PromptConverterAgent._build_character_anchor_suffix("小红", contract) == ""


def test_apply_character_anchors():
    """按片段主角色将契约外观锚点注入 prompt，无锚点角色不注入"""
    from types import SimpleNamespace

    from penshot.neopen.agent.continuity_guardian.consistency_contract import (
        CharacterContract,
    )
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    character = CharacterContract(name="小明")
    character.appearance_anchors = {"clothing": "黑色羽绒服"}
    contract.characters["小明"] = character

    fragment_sequence = SimpleNamespace(
        fragments=[
            SimpleNamespace(id="frag_001", continuity_notes={"main_character": "小明"}),
            SimpleNamespace(id="frag_002", continuity_notes={"main_character": "小红"}),
        ]
    )
    instructions = SimpleNamespace(
        fragments=[
            SimpleNamespace(fragment_id="frag_001", prompt="a woman sits on the sofa"),
            SimpleNamespace(fragment_id="frag_002", prompt="a man walks in"),
        ]
    )

    agent._apply_character_anchors(instructions, fragment_sequence, contract)

    assert "Character consistency: 小明" in instructions.fragments[0].prompt
    assert "Character consistency" not in instructions.fragments[1].prompt
