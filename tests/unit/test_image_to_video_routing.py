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
    CameraControl,
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


def test_has_critical_text_ignores_environmental_signage():
    """环境招牌/屏幕/材质纹理不构成可读文字渲染需求（0.4.5 稳定版误报修复）"""
    assert has_critical_text("green emergency exit sign glowing in the dark") is False
    assert has_critical_text("uniform with polyester texture") is False
    assert has_critical_text("TV screen flickering with blue static snow") is False
    assert has_critical_text("subtitle displays the address") is True


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


def test_scene_coverage_triggers_image_to_video_without_character() -> None:
    """场景资产已覆盖片段时，无主角色也走图生视频并以场景首帧引用"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(scene_num=2, location="走廊/班级记忆墙", time_of_day="傍晚")
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_002",
            asset_type="scene",
            owner_name="走廊/班级记忆墙",
            image_prompt="establishing shot still of 走廊/班级记忆墙",
            status="pending",
        )
    )
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="f3",
                prompt="Wide shot of the hallway at dusk",
                duration=3.9,
                camera=CameraControl(shot_type="wide_shot"),
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="f3", target_model="runway_gen4", prompt="adapted", duration=3.9
        )
    ]
    fragments = [SimpleNamespace(id="f3", shot_id="shot_014", description="镜头拉远")]
    shots = [SimpleNamespace(id="shot_014", scene_id="scene_002", main_character="")]

    triggered = apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    assert triggered == 1
    package = packages[0]
    assert package.mode == RouteMode.IMAGE_TO_VIDEO
    assert package.asset_ref == ""
    by_role = {reference.role: reference for reference in package.references}
    assert by_role["first_frame"].asset_id == "scene_002"
    assert by_role["first_frame"].as_first_frame is True
    assert package.image_prompt
    assert "镜头" not in package.image_prompt
    assert "action:" not in package.image_prompt
    assert package.image_prompt.startswith("wide shot")
    assert "empty scene, no people" in package.image_prompt
    assert package.first_frame_instruction.startswith(
        "Generate first frame with prompt:"
    )


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
    """T-303/0.4.5：道具引用需“场景命中 + 文本提及”，与 usage 同口径（FR-013）"""
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
        SimpleNamespace(id="f1", shot_id="shot_001", description="电影票根露出了一角")
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


def test_prop_references_require_text_mention():
    """同场景但片段未提及的道具不挂引用（0.4.5 任务 4 根因）"""
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
        SimpleNamespace(id="f1", shot_id="shot_001", description="她低头看着桌面")
    ]
    shots = [
        SimpleNamespace(id="shot_001", scene_id="scene_001", main_character="林然")
    ]
    parsed_script = SimpleNamespace(
        global_metadata=SimpleNamespace(
            key_props=[SimpleNamespace(name="电影票根", appears_in=["scene_001"])]
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

    assert "prop_001" not in {ref.asset_id for ref in packages[0].references}


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


# ======================== 0.4.5 任务 7：场景锚定一致性 ========================


def _scene_contract() -> GlobalConsistencyContract:
    """教室 + 走廊两个场景，镜头映射到走廊但提示词描述教室"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("张晨", 1, "他穿着蓝白相间棉质校服")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="教室",
            time_of_day="afternoon",
            characters_in_scene=["张晨"],
        )
    )
    contract.register_scene(
        SceneContract(
            scene_num=2,
            location="走廊/班级记忆墙",
            time_of_day="dusk",
            characters_in_scene=["张晨"],
        )
    )
    for asset_id, owner_name in (
        ("scene_001", "教室"),
        ("scene_002", "走廊/班级记忆墙"),
    ):
        contract.register_asset(
            AssetContract(
                asset_id=asset_id,
                asset_type="scene",
                owner_name=owner_name,
                asset_ref=f"/tmp/assets/{asset_id}.png",
                image_prompt=f"establishing shot of {owner_name}",
                status="generated",
            )
        )
    return contract


def _scene_prompt(fragment_id: str, prompt: str) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id=fragment_id,
        prompt=prompt,
        duration=3.0,
        main_character="张晨",
    )


def test_scene_anchor_mismatch_auto_replaces_first_frame():
    """片段写教室但镜头映射到走廊首帧时自动替换为匹配场景资产"""
    contract = _scene_contract()
    instructions = AIVideoInstructions(
        fragments=[
            _scene_prompt(
                "frag_001",
                "medium two-shot, Zhang Chen in a high school classroom, "
                "wearing blue and white cotton uniform",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_001",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_001", shot_id="shot_001", description="")]
    shots = [SimpleNamespace(id="shot_001", scene_id="scene_002")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    package = packages[0]
    assert package.status == "ready"
    assert package.warnings
    message = package.warnings[0]
    assert "已自动替换" in message
    assert "教室" in message
    assert "scene_001" in message
    assert "走廊" in message
    first_frame = next(ref for ref in package.references if ref.role == "first_frame")
    assert first_frame.asset_id == "scene_001"
    assert "at 教室" in package.image_prompt


def test_scene_anchor_skips_prompt_without_location():
    """提示词没有明确场景描述时不误报"""
    contract = _scene_contract()
    instructions = AIVideoInstructions(
        fragments=[_scene_prompt("frag_002", "A man runs through the rain")]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_002",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_002", shot_id="shot_002", description="")]
    shots = [SimpleNamespace(id="shot_002", scene_id="scene_002")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    assert packages[0].warnings == []


def _hallway_contract() -> GlobalConsistencyContract:
    """场景资产写成“楼道”，提示词常用“走廊/corridor”，两者是同一地点"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("陈默", 1)
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="老式居民楼楼道",
            time_of_day="night",
            characters_in_scene=["陈默"],
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="老式居民楼楼道",
            asset_ref="/tmp/assets/scene_001.png",
            image_prompt="establishing shot of an old residential hallway",
            status="generated",
        )
    )
    return contract


def test_scene_anchor_treats_hallway_synonyms_as_same_scene():
    """楼道与走廊是同一语义，不得判为另一场景而阻断（P0-5）"""
    contract = _hallway_contract()
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="dark corridor in an old residential building, dim light",
                duration=3.0,
                main_character="陈默",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_001",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_001", shot_id="shot_001", description="")]
    shots = [SimpleNamespace(id="shot_001", scene_id="scene_001")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    assert packages[0].status == "ready"
    assert packages[0].warnings == []
    first_frame = next(
        ref for ref in packages[0].references if ref.role == "first_frame"
    )
    assert first_frame.asset_id == "scene_001"


def test_scene_anchor_accepts_matching_location():
    """提示词与首帧场景一致时不告警（英文别名词表生效）"""
    contract = _scene_contract()
    instructions = AIVideoInstructions(
        fragments=[
            _scene_prompt(
                "frag_003",
                "Zhang Chen leans on the corridor wall next to the memory wall",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_003",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_003", shot_id="shot_003", description="")]
    shots = [SimpleNamespace(id="shot_003", scene_id="scene_002")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    assert packages[0].warnings == []


def test_scene_anchor_ignores_location_in_dialogue():
    """台词里提到另一场景不算画面锚定错误，避免误报"""
    contract = _scene_contract()
    instructions = AIVideoInstructions(
        fragments=[
            _scene_prompt(
                "frag_004",
                "extreme close-up of a teacher, speaking softly: "
                "'go take a look in the hallway.'",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_004",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_004", shot_id="shot_004", description="")]
    shots = [SimpleNamespace(id="shot_004", scene_id="scene_001")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    assert packages[0].warnings == []


def test_scene_anchor_ambiguous_blocks_fragment():
    """片段同时提到多个其他场景时无法唯一匹配，标记 needs_manual_fix 阻断"""
    contract = _scene_contract()
    contract.register_scene(
        SceneContract(
            scene_num=3,
            location="操场",
            time_of_day="noon",
            characters_in_scene=["张晨"],
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_003",
            asset_type="scene",
            owner_name="操场",
            asset_ref="/tmp/assets/scene_003.png",
            image_prompt="establishing shot of 操场",
            status="generated",
        )
    )
    instructions = AIVideoInstructions(
        fragments=[
            _scene_prompt(
                "frag_005",
                "Zhang Chen runs from the classroom toward the playground",
            )
        ]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_005",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_005", shot_id="shot_005", description="")]
    shots = [SimpleNamespace(id="shot_005", scene_id="scene_002")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    package = packages[0]
    assert package.status == "needs_manual_fix"
    assert "已阻断" in package.warnings[0]


def test_scene_anchor_without_matching_asset_blocks_fragment():
    """片段提到契约中不存在的场景时同样阻断，不能静默沿用错误首帧"""
    contract = _scene_contract()
    instructions = AIVideoInstructions(
        fragments=[_scene_prompt("frag_006", "a lonely figure crosses the playground")]
    )
    packages = [
        AdaptedPromptPackage(
            fragment_id="frag_006",
            target_model="runway_gen4",
            prompt="adapted",
            duration=3.0,
        )
    ]
    fragments = [SimpleNamespace(id="frag_006", shot_id="shot_006", description="")]
    shots = [SimpleNamespace(id="shot_006", scene_id="scene_002")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    package = packages[0]
    assert package.status == "needs_manual_fix"
    assert "已阻断" in package.warnings[0]
