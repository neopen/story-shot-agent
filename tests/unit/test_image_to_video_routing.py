"""M0.4.2 图生视频优先路由测试。

验证 critical_text / high_consistency 片段会被标注为两段式
「文生图 -> 图生视频」，并挂载契约中的 asset_ref。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter import (
    AdaptedPromptPackage,
    PROMPT_SCHEMA_VERSION,
    PromptOverride,
    PromptReference,
    RouteMode,
    RoutePlan,
    apply_image_to_video_routing,
    apply_overrides,
    has_critical_text,
    should_use_image_to_video,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)


def _contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "他穿着黑色西装")
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="林然",
            asset_ref="/tmp/assets/char_001.png",
            image_prompt="character reference sheet of 林然",
            status="generated",
        )
    )
    return contract


def _instructions() -> AIVideoInstructions:
    return AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="f1",
                prompt="Detective reads a newspaper with a headline",
                duration=3.0,
                main_character="林然",
            ),
            AIVideoPrompt(
                fragment_id="f2",
                prompt="A man walks through the rain",
                duration=3.0,
                main_character="林然",
            ),
            AIVideoPrompt(
                fragment_id="f3",
                prompt="Empty street at night",
                duration=3.0,
            ),
        ]
    )


def _packages() -> list[AdaptedPromptPackage]:
    return [
        AdaptedPromptPackage(
            fragment_id=fid,
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
        for fid in ("f1", "f2", "f3")
    ]


def test_has_critical_text_detects_text_signals():
    assert has_critical_text("a poster with a book title") is True
    assert has_critical_text("他举起写有文字的招牌") is True
    assert has_critical_text("a man walks in the rain") is False


def test_should_use_image_to_video_for_high_consistency():
    contract = _contract()
    prompt = AIVideoPrompt(
        fragment_id="f1",
        prompt="A man walks through the rain",
        duration=3.0,
        main_character="林然",
    )
    assert should_use_image_to_video(prompt, contract) is True
    assert should_use_image_to_video(prompt, None) is False


def test_apply_routing_marks_two_stage_and_builds_first_frame():
    """T-303：触发两段式，但角色三视图不再写入 asset_ref/首帧提示词"""
    contract = _contract()
    packages = _packages()
    triggered = apply_image_to_video_routing(packages, _instructions(), contract)

    assert triggered == 2
    first, second, third = packages

    assert first.mode == RouteMode.IMAGE_TO_VIDEO
    assert first.asset_ref == ""
    assert first.image_prompt != "character reference sheet of 林然"
    assert "character reference sheet" not in first.image_prompt
    assert first.references[0].role == "identity_reference"
    assert first.references[0].as_first_frame is False
    assert first.first_frame_instruction.startswith("Generate first frame with prompt:")

    assert second.mode == RouteMode.IMAGE_TO_VIDEO
    assert second.asset_ref == ""

    assert third.mode == RouteMode.TEXT_TO_VIDEO
    assert third.asset_ref == ""
    assert third.image_prompt == ""


def test_apply_routing_with_pending_character_asset_still_emits_image_prompt():
    """三视图尚未落盘时仍产出首帧提示词，由下游文生图补齐"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "他穿着黑色西装")
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="林然",
            image_prompt="character reference sheet of 林然",
            status="pending",
        )
    )

    packages = _packages()
    triggered = apply_image_to_video_routing(packages, _instructions(), contract)

    assert triggered == 2
    assert packages[0].mode == RouteMode.IMAGE_TO_VIDEO
    assert packages[0].asset_ref == ""
    assert packages[0].image_prompt


def test_scene_first_frame_manifest_binding_fills_asset_ref():
    """FR-016：asset_ref 只承载清单中的场景首帧绑定"""
    contract = _contract()
    contract.register_scene(
        SceneContract(scene_num=1, location="街角咖啡店", time_of_day="day")
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="街角咖啡店",
            image_prompt="establishing shot still of 街角咖啡店",
            status="pending",
        )
    )
    manifest = {
        "task_id": "t1",
        "bindings": [
            {
                "asset_id": "scene_001",
                "asset_ref": "/tmp/downstream/scene_001.png",
                "source": "downstream",
            }
        ],
        "asset_id_map": {},
    }
    fragments = [SimpleNamespace(id="f1", shot_id="shot_001", description="")]
    shots = [
        SimpleNamespace(id="shot_001", scene_id="scene_001", main_character="林然")
    ]

    packages = _packages()[:1]
    apply_image_to_video_routing(
        packages,
        _instructions(),
        contract,
        manifest,
        fragments=fragments,
        shots=shots,
    )

    first = packages[0]
    assert first.mode == RouteMode.IMAGE_TO_VIDEO
    assert first.asset_ref == "/tmp/downstream/scene_001.png"
    assert first.first_frame_instruction.startswith(
        "Use reference image /tmp/downstream/scene_001.png"
    )
    by_role = {reference.role: reference for reference in first.references}
    assert by_role["identity_reference"].asset_id == "char_001"
    assert by_role["identity_reference"].as_first_frame is False
    assert by_role["first_frame"].asset_id == "scene_001"
    assert by_role["first_frame"].as_first_frame is True


def test_character_sheet_manifest_binding_never_becomes_asset_ref():
    """FR-016：即使清单回填了角色三视图，也只能出现在 references 中"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "他穿着黑色西装")
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="林然",
            image_prompt="character reference sheet of 林然",
            status="pending",
        )
    )

    manifest = {
        "task_id": "t1",
        "bindings": [
            {
                "asset_id": "char_001",
                "asset_ref": "/tmp/downstream/char_001.png",
                "source": "downstream",
            }
        ],
        "asset_id_map": {},
    }

    packages = _packages()
    apply_image_to_video_routing(packages, _instructions(), contract, manifest)

    first = packages[0]
    assert first.mode == RouteMode.IMAGE_TO_VIDEO
    assert first.asset_ref == ""
    assert [ref.asset_id for ref in first.references] == ["char_001"]
    assert first.references[0].role == "identity_reference"
    assert first.references[0].as_first_frame is False


def test_missing_character_reference_falls_back_to_text_to_video():
    """高一致性片段缺失必需角色资产时回退文生视频"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "他穿着黑色西装")

    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="f1",
                prompt="A man walks through the rain",
                duration=3.0,
                main_character="林然",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="f1", target_model="runway_gen4", prompt="adapted", duration=3.0
        )
    ]

    triggered = apply_image_to_video_routing(packages, instructions, contract)

    assert triggered == 0
    assert packages[0].mode == RouteMode.TEXT_TO_VIDEO
    assert packages[0].references == []


def test_prop_references_follow_scene_appears_in():
    """T-303：道具引用按 appears_in 场景约束，与 usage 同口径（FR-013）"""
    contract = _contract()
    contract.register_scene(
        SceneContract(scene_num=1, location="街角咖啡店", time_of_day="day")
    )
    contract.register_asset(
        AssetContract(
            asset_id="prop_001",
            asset_type="prop",
            owner_name="电影票根",
            image_prompt="product still of 电影票根",
        )
    )
    fragments = [
        SimpleNamespace(id="f1", shot_id="shot_001", description="票根露出了一角")
    ]
    shots = [
        SimpleNamespace(id="shot_001", scene_id="scene_001", main_character="林然")
    ]

    def _run(appears_in):
        parsed_script = SimpleNamespace(
            global_metadata=SimpleNamespace(
                key_props=[SimpleNamespace(name="电影票根", appears_in=appears_in)]
            )
        )
        packages = _packages()[:1]
        apply_image_to_video_routing(
            packages,
            _instructions(),
            contract,
            fragments=fragments,
            shots=shots,
            parsed_script=parsed_script,
        )
        return {ref.asset_id: ref for ref in packages[0].references}

    assert "prop_001" not in _run(["scene_002"])
    prop_ref = _run(["scene_001"])["prop_001"]
    assert prop_ref.role == "prop"
    assert prop_ref.as_first_frame is False


def test_prompt_overrides_keep_asset_identity_and_provenance():
    """下游可改提示词，但不能改 asset_id/asset_ref，且修订链完整"""
    package = AdaptedPromptPackage(
        fragment_id="f1",
        target_model="runway_gen4",
        prompt="old prompt",
        duration=3.0,
        asset_ref="/assets/char_001.png",
    )
    package.references = [PromptReference(asset_id="char_001", role="character")]

    applied = apply_overrides(
        [package],
        [
            PromptOverride(
                target_id="f1",
                field="prompt",
                value="new prompt",
                source="downstream_repair",
                revision_id="rev-1",
            ),
            # 身份字段不在白名单内，必须被忽略
            PromptOverride(target_id="f1", field="asset_ref", value="renamed.png"),
        ],
    )

    assert applied == 1
    assert package.prompt == "new prompt"
    assert package.asset_ref == "/assets/char_001.png"
    assert package.references[0].asset_id == "char_001"
    assert package.revision_id == "rev-1"
    assert package.revision_source == "downstream_repair"
    assert package.parent_id == "f1"
    assert package.revision == 1
    assert len(package.prompt_overrides) == 1


def test_route_plan_and_instructions_carry_schema_version():
    """路由计划与指令集都带 schema_version，供下游判断兼容性"""
    assert RoutePlan().schema_version == PROMPT_SCHEMA_VERSION
    assert AIVideoInstructions().schema_version == PROMPT_SCHEMA_VERSION
