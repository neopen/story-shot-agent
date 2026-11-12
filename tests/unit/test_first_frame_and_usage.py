"""M3 首帧语义与引用语义测试（T-301/T-302/T-303/T-304）。

覆盖 AC-010（角色三视图只作身份参考、场景锚点作首帧、道具非首帧）、
AC-011（片段专属首帧提示词不等于三视图提示词，且包含场景/动作要素）
与 AC-012..016（资产使用范围回填与引用覆盖）。
"""

from types import SimpleNamespace
from typing import Optional

from penshot.neopen.agent.asset_generator.asset_generator_agent import (
    backfill_usage,
)
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetPlanDocument,
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    build_first_frame_prompt,
    build_package_references,
)
from penshot.neopen.agent.model_adapter.model_models import PromptReference
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
    main_character: Optional[str] = "林然",
) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id="frag_001",
        prompt=text,
        duration=3.0,
        main_character=main_character,
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


def test_first_frame_prompt_drops_placeholder_subject():
    """frag_013 缺陷回归：main_character 为“无”时不再拼出 of 无"""
    contract = _contract()

    first_frame = build_first_frame_prompt(
        _prompt(main_character="无"), contract, scene=contract.scenes[1]
    )

    assert "无" not in first_frame
    assert "of the scene" not in first_frame
    assert first_frame.startswith("close-up shot, at ")


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


# ======================== T-304 usage 回填（AC-012..016） ========================

CAFE = "城市街角咖啡店外长椅旁"
EAVES = "城市街角屋檐下"

# 与 AC fixture 对齐：11 个片段 -> 镜头的场景/主角映射
FRAGMENT_SCENES = {
    1: "scene_001",
    2: "scene_001",
    3: "scene_002",
    4: "scene_002",
    5: "scene_003",
    6: "scene_003",
    7: "scene_003",
    8: "scene_003",
    9: "scene_004",
    10: "scene_004",
    11: "scene_004",
}
FRAGMENT_MAIN = {
    1: "林小雨",
    2: "林小雨",
    3: "陈阳",
    4: "陈阳",
    5: None,
    6: "林小雨",
    7: "陈阳",
    8: "陈阳",
    9: "林小雨",
    10: "陈阳",
    11: "林小雨",
}
PROPS = {
    "《飞鸟集》": ["scene_001", "scene_002", "scene_003", "scene_004"],
    "借阅卡": ["scene_003"],
    "电影票根": ["scene_004"],
    "黄色雨衣": ["scene_002", "scene_003", "scene_004"],
}


def _usage_contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    for scene_num in (1, 2, 3):
        contract.register_scene(
            SceneContract(scene_num=scene_num, location=CAFE, time_of_day="day")
        )
    contract.register_scene(
        SceneContract(scene_num=4, location=EAVES, time_of_day="dusk")
    )
    return contract


def _usage_plan() -> AssetPlanDocument:
    return AssetPlanDocument(
        task_id="t1",
        script_id="s1",
        assets=[
            AssetSpec(
                asset_id="char_001",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name="林小雨",
                image_prompt="character reference sheet of 林小雨",
                usage=AssetUsage(characters=["林小雨"]),
            ),
            AssetSpec(
                asset_id="char_002",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name="陈阳",
                image_prompt="character reference sheet of 陈阳",
                usage=AssetUsage(characters=["陈阳"]),
            ),
            AssetSpec(
                asset_id="scene_001",
                asset_type=AssetType.SCENE,
                owner_name=CAFE,
                image_prompt=f"establishing shot still of {CAFE}",
                usage=AssetUsage(scenes=[CAFE]),
            ),
            AssetSpec(
                asset_id="scene_002",
                asset_type=AssetType.SCENE,
                owner_name=EAVES,
                image_prompt=f"establishing shot still of {EAVES}",
                usage=AssetUsage(scenes=[EAVES]),
            ),
            AssetSpec(
                asset_id="prop_001",
                asset_type=AssetType.PROP,
                owner_name="《飞鸟集》",
                image_prompt="product still of 《飞鸟集》",
            ),
            AssetSpec(
                asset_id="prop_002",
                asset_type=AssetType.PROP,
                owner_name="借阅卡",
                image_prompt="product still of 借阅卡",
            ),
            AssetSpec(
                asset_id="prop_003",
                asset_type=AssetType.PROP,
                owner_name="电影票根",
                image_prompt="product still of 电影票根",
            ),
            AssetSpec(
                asset_id="prop_004",
                asset_type=AssetType.PROP,
                owner_name="黄色雨衣",
                image_prompt="product still of 黄色雨衣",
            ),
        ],
    )


# 片段描述中的道具提及：道具 usage 必须“场景命中 + 文本提及”双条件
USAGE_MENTIONS = {
    2: "《飞鸟集》摊开在膝上",
    3: "她披着黄色雨衣，手里捏着借阅卡",
    4: "电影票根从口袋滑落",
    5: "借阅卡被递回柜台",
    6: "他合上《飞鸟集》",
    9: "《飞鸟集》被放回书架",
    10: "黄色雨衣滴着水，电影票根攥在手心",
}


def _usage_inputs():
    fragments = [
        SimpleNamespace(
            id=f"frag_{index:03d}",
            shot_id=f"shot_{index:03d}",
            description=USAGE_MENTIONS.get(index, "两人对视，沉默片刻"),
            continuity_notes={},
        )
        for index in range(1, 12)
    ]
    shots = [
        SimpleNamespace(
            id=f"shot_{index:03d}",
            scene_id=FRAGMENT_SCENES[index],
            main_character=FRAGMENT_MAIN[index],
        )
        for index in range(1, 12)
    ]
    parsed_script = SimpleNamespace(
        scenes=[
            SimpleNamespace(id=scene_id, location=location)
            for scene_id, location in [
                ("scene_001", CAFE),
                ("scene_002", CAFE),
                ("scene_003", CAFE),
                ("scene_004", EAVES),
            ]
        ],
        global_metadata=SimpleNamespace(
            key_props=[
                SimpleNamespace(name=name, appears_in=scenes)
                for name, scenes in PROPS.items()
            ]
        ),
    )
    return {
        "fragments": fragments,
        "shots": shots,
        "parsed_script": parsed_script,
    }


def test_backfill_usage_matches_ac012_to_ac015():
    """AC-012..015：角色按主角、场景按地点、道具按场景 + 文本提及回填"""
    plan = backfill_usage(
        _usage_plan(),
        contract=_usage_contract(),
        **_usage_inputs(),
    )
    usage = {spec.asset_id: spec.usage.fragments for spec in plan.assets}

    assert usage["char_001"] == [
        "frag_001",
        "frag_002",
        "frag_006",
        "frag_009",
        "frag_011",
    ]
    assert usage["char_002"] == [
        "frag_003",
        "frag_004",
        "frag_007",
        "frag_008",
        "frag_010",
    ]
    assert usage["scene_001"] == [f"frag_{index:03d}" for index in range(1, 9)]
    assert usage["scene_002"] == ["frag_009", "frag_010", "frag_011"]
    assert usage["prop_001"] == ["frag_002", "frag_006", "frag_009"]
    assert usage["prop_002"] == ["frag_005"]
    assert usage["prop_003"] == ["frag_010"]
    assert usage["prop_004"] == ["frag_003", "frag_010"]
    # 同场景但片段未提及的道具不得进入使用范围（0.4.5 任务 4）
    assert "frag_008" not in usage["prop_002"]
    assert "frag_004" not in usage["prop_004"]


def test_backfill_usage_covers_route_plan_references():
    """AC-016：route_plan 合法引用必须落在对应资产使用范围内"""
    route_plan = SimpleNamespace(
        adapted_packages=[
            SimpleNamespace(
                fragment_id="frag_001",
                references=[
                    PromptReference(asset_id="char_002", role="identity_reference")
                ],
            ),
            SimpleNamespace(
                fragment_id="frag_002",
                references=[PromptReference(asset_id="prop_001", role="prop")],
            ),
        ]
    )

    plan = backfill_usage(
        _usage_plan(),
        contract=_usage_contract(),
        route_plan=route_plan,
        **_usage_inputs(),
    )
    usage = {spec.asset_id: spec.usage.fragments for spec in plan.assets}

    # 角色口径不变：路由引用可补入非主角色片段
    assert "frag_001" in usage["char_002"]
    assert "frag_002" in usage["prop_001"]

    for package in route_plan.adapted_packages:
        for reference in package.references:
            assert package.fragment_id in usage[reference.asset_id]


def test_backfill_usage_drops_stale_prop_references():
    """道具引用未通过文本提及判定时不得并入，避免 refs 撑大 usage"""
    route_plan = SimpleNamespace(
        adapted_packages=[
            SimpleNamespace(
                fragment_id="frag_005",
                references=[PromptReference(asset_id="prop_003", role="prop")],
            )
        ]
    )

    plan = backfill_usage(
        _usage_plan(),
        contract=_usage_contract(),
        route_plan=route_plan,
        **_usage_inputs(),
    )
    prop_003 = next(spec for spec in plan.assets if spec.asset_id == "prop_003")

    assert prop_003.usage.fragments == ["frag_010"]


def test_backfill_usage_reads_prompt_text_for_props():
    """提示词正文里的道具提及同样计入（描述为空时）"""
    inputs = _usage_inputs()
    for fragment in inputs["fragments"]:
        fragment.description = ""
    instructions = SimpleNamespace(
        fragments=[
            SimpleNamespace(
                fragment_id="frag_010",
                prompt="she clutches the 电影票根 tightly",
            )
        ]
    )

    plan = backfill_usage(
        _usage_plan(),
        contract=_usage_contract(),
        instructions=instructions,
        **inputs,
    )
    prop_003 = next(spec for spec in plan.assets if spec.asset_id == "prop_003")

    assert prop_003.usage.fragments == ["frag_010"]


def test_backfill_usage_does_not_match_english_synonyms():
    """英文同义词不等于道具名：movie ticket 不代表“电影票根”"""
    inputs = _usage_inputs()
    for fragment in inputs["fragments"]:
        fragment.description = ""
    instructions = SimpleNamespace(
        fragments=[
            SimpleNamespace(
                fragment_id="frag_010",
                prompt="a movie ticket slips from his pocket",
            )
        ]
    )

    plan = backfill_usage(
        _usage_plan(),
        contract=_usage_contract(),
        instructions=instructions,
        **inputs,
    )
    usage = {spec.asset_id: spec.usage.fragments for spec in plan.assets}

    assert usage["prop_003"] == []
    assert usage["prop_001"] == []


def test_backfill_usage_accepts_dict_plan():
    """字典形式资产计划也能回填（节点内 state.domain.asset_plan 为 dict）"""
    plan = backfill_usage(
        _usage_plan().to_dict(),
        contract=_usage_contract(),
        **_usage_inputs(),
    )

    char_001 = next(spec for spec in plan.assets if spec.asset_id == "char_001")
    assert char_001.usage.fragments[0] == "frag_001"
