"""M3 首帧语义与引用语义测试（T-301/T-302）。

覆盖 AC-010（角色三视图只作身份参考、场景锚点作首帧、道具非首帧）
与 AC-011（片段专属首帧提示词不等于三视图提示词，且包含场景/动作要素）。
"""

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    build_first_frame_prompt,
    build_package_references,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
    CameraControl,
)

CHARACTER_SHEET_PROMPT = (
    "character reference sheet of 林然, black short hair, yellow raincoat, "
    "front view, side view and back view, neutral grey background, "
    "soft even studio lighting"
)

LOCATION = "城市街角咖啡店外长椅旁"


def _contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "25岁男生，穿着黄色连帽雨衣")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location=LOCATION,
            time_of_day="dusk",
            weather="下雨",
            characters_in_scene=["林然"],
        )
    )
    contract.style_anchor = {"genre": "romance"}
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="林然",
            image_prompt=CHARACTER_SHEET_PROMPT,
            status="pending",
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name=LOCATION,
            image_prompt=f"establishing shot still of {LOCATION}",
            status="pending",
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="prop_001",
            asset_type="prop",
            owner_name="《飞鸟集》",
            image_prompt="product still of 《飞鸟集》",
            status="pending",
        )
    )
    return contract


def _prompt(
    text: str = "A young man waits for someone by the coffee shop",
) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id="frag_001",
        prompt=text,
        duration=3.0,
        main_character="林然",
        camera=CameraControl(shot_type="close_up"),
    )


class _Fragment:
    """最小片段桩：只提供首帧构建需要的字段"""

    shot_type = "close_up"
    description = "林然蹲在长椅旁擦拭《飞鸟集》封面上的雨水"


def test_first_frame_prompt_differs_from_character_sheet_and_has_cues():
    """AC-011：首帧提示词不等于三视图，且包含场景与动作要素"""
    contract = _contract()

    first_frame = build_first_frame_prompt(
        _prompt(), contract, scene=contract.scenes[1], fragment=_Fragment()
    )

    assert first_frame != CHARACTER_SHEET_PROMPT
    assert "character reference sheet" not in first_frame
    assert "neutral grey background" not in first_frame
    for cue in ("长椅", "雨", "咖啡店", "蹲", "擦拭"):
        assert cue in first_frame
    assert first_frame.startswith("close-up shot of 林然")
    assert "romance" in first_frame


def test_first_frame_prompt_resolves_scene_from_contract():
    """未显式传场景时，按地点词命中契约场景"""
    contract = _contract()

    first_frame = build_first_frame_prompt(
        _prompt(f"A wide view outside {LOCATION}"), contract
    )

    assert LOCATION in first_frame
    assert "dusk lighting" in first_frame


def test_first_frame_prompt_strips_style_prefix_from_action():
    """回退提示词正文时剥离 [Style:] 前缀，风格只出现一次"""
    contract = _contract()
    prompt = _prompt("[Style: romance, intimate framing] 林然蹲下擦拭雨水")

    first_frame = build_first_frame_prompt(prompt, contract)

    assert first_frame.count("[Style:") == 0
    assert "action: 林然蹲下擦拭雨水" in first_frame


def test_package_references_character_identity_scene_first_frame_prop_non_first():
    """AC-010/FR-010/FR-016：角色身份参考、场景首帧、道具非首帧"""
    contract = _contract()

    references = build_package_references(
        _prompt(), contract, scene=contract.scenes[1], fragment=_Fragment()
    )
    by_id = {reference.asset_id: reference for reference in references}

    character_ref = by_id["char_001"]
    assert character_ref.role == "identity_reference"
    assert character_ref.as_first_frame is False

    scene_ref = by_id["scene_001"]
    assert scene_ref.role == "first_frame"
    assert scene_ref.as_first_frame is True

    prop_ref = by_id["prop_001"]
    assert prop_ref.role == "prop"
    assert prop_ref.as_first_frame is False

    assert [ref.asset_id for ref in references].count("scene_001") == 1


def test_package_references_without_contract_is_empty():
    """无契约时不凭空声明资产引用"""
    assert build_package_references(_prompt()) == []


def test_package_references_ignore_unrelated_props():
    """未在片段文本中出现的道具不进入引用列表"""
    contract = _contract()
    prompt = _prompt("A young man waits by the coffee shop")

    references = build_package_references(prompt, contract)

    assert [ref.asset_id for ref in references] == [
        "char_001",
        "scene_001",
    ]
