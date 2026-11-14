"""0.4.5 P0 修复测试：道具引用、首帧静态化、Gate 1 质检（P0-1/P0-2/P0-4）。"""

from types import SimpleNamespace

from penshot.neopen.agent.asset_generator.asset_generator_agent import (
    backfill_usage,
)
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetPlanDocument,
    AssetSpec,
    AssetType,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
)
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    build_first_frame_prompt,
    build_motion_prompt,
    build_package_references,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    RouteMode,
)
from penshot.neopen.agent.model_adapter.quality_gate import apply_quality_gate
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIAudioPrompt,
    AIVideoInstructions,
    AIVideoPrompt,
    CameraControl,
)
from penshot.neopen.agent.prop_usage import (
    advance_prop_state,
    prop_match_keys,
    should_reference_prop,
)

SCENE = SimpleNamespace(location="城市地铁站台", time_of_day="深夜", weather="")
EMPTY_SCENE_MARKER = "empty scene, no people"


def _fragment(
    index: int, description: str, shot_type: str = "wide_shot"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"frag_{index:03d}",
        shot_id=f"shot_{index:03d}",
        description=description,
        shot_type=shot_type,
        continuity_notes={},
    )


def _shots(count: int = 10) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=f"shot_{index:03d}",
            scene_id="scene_001",
            main_character="林晚",
        )
        for index in range(1, count + 1)
    ]


def _parsed_script(*props: tuple[str, list[str]]) -> SimpleNamespace:
    return SimpleNamespace(
        scenes=[SimpleNamespace(id="scene_001", location="城市地铁站台")],
        global_metadata=SimpleNamespace(
            key_props=[
                SimpleNamespace(name=name, appears_in=appears_in)
                for name, appears_in in props
            ]
        ),
    )


def _plan(*props: tuple[str, str]) -> AssetPlanDocument:
    return AssetPlanDocument(
        task_id="t1",
        script_id="s1",
        assets=[
            AssetSpec(
                asset_id=asset_id,
                asset_type=AssetType.PROP,
                owner_name=owner_name,
                image_prompt=f"product still of {owner_name}",
            )
            for asset_id, owner_name in props
        ],
    )


# ======================== P0-1 道具引用 ========================


def test_prop_match_keys_expands_core_noun() -> None:
    """“皱巴巴的纸条”同时按整体名与核心名词“纸条”匹配"""
    assert prop_match_keys("皱巴巴的纸条") == ["皱巴巴的纸条", "纸条"]


def test_worn_accessory_requires_focal_close_up() -> None:
    """着装围巾只在特写聚焦时引用；普通陈述与中景服装句不引用"""
    scarf = "红围巾"
    wide_costume = "林晚身穿深灰色长款大衣，围着洗得发白的红围巾"
    medium_costume = "Lin Wan in a dark coat and faded red scarf"
    close_costume = "特写镜头：林晚侧脸苍白，围着洗得发白的红围巾"
    focal = "穿堂风吹起她颈间洗得发白的红围巾一角"

    assert should_reference_prop(wide_costume, scarf, "wide_shot") is False
    assert should_reference_prop(medium_costume, scarf, "medium_shot") is False
    assert should_reference_prop(close_costume, scarf, "close_up") is False
    assert should_reference_prop(focal, scarf, "extreme_close_up") is True


def test_backfill_usage_matches_core_noun_and_tracks_states() -> None:
    """纸条按核心名词回填，并推导 crumpled -> balled 状态变体"""
    plan = _plan(("prop_001", "皱巴巴的纸条"))
    fragments = [
        _fragment(1, "她手里攥着一张皱巴巴的白色纸条", "wide_shot"),
        _fragment(2, "她低头凝视皱巴巴的纸条", "medium_shot"),
        _fragment(7, "她将纸条用力揉成一团", "extreme_close_up"),
        _fragment(10, "她握着纸条走上列车", "medium_shot"),
    ]

    result = backfill_usage(
        plan,
        fragments=fragments,
        shots=_shots(),
        parsed_script=_parsed_script(("皱巴巴的纸条", ["scene_001"])),
    )
    prop = result.assets[0]

    assert prop.usage.fragments == ["frag_001", "frag_002", "frag_007", "frag_010"]
    variants = {variant.state: variant.fragments for variant in prop.state_variants}
    assert variants == {
        "crumpled": ["frag_001", "frag_002"],
        "balled": ["frag_007", "frag_010"],
    }


def test_prop_state_only_reads_its_own_clauses() -> None:
    """同片段里纸条被揉成团，不应把围巾也标成 balled"""
    text = "她将那张皱巴巴的白色纸条揉成一团，颈间的红围巾被风吹起一角"

    assert advance_prop_state("", text, "皱巴巴的纸条") == "balled"
    assert advance_prop_state("", text, "红围巾") == ""


def test_backfill_usage_converges_worn_scarf_to_focal_fragment() -> None:
    """红围巾只保留真正聚焦的 frag_007，不再扩成整场引用"""
    plan = _plan(("prop_001", "红围巾"))
    fragments = [
        _fragment(1, "林晚围着洗得发白的红围巾", "wide_shot"),
        _fragment(2, "林晚围着红围巾，红围巾在冷风中微微颤动", "medium_shot"),
        _fragment(6, "特写镜头：林晚围着红围巾，侧脸苍白", "close_up"),
        _fragment(7, "穿堂风吹起她颈间红围巾一角", "extreme_close_up"),
        _fragment(10, "林晚围着红围巾走上列车", "medium_shot"),
    ]

    result = backfill_usage(
        plan,
        fragments=fragments,
        shots=_shots(),
        parsed_script=_parsed_script(("红围巾", ["scene_001"])),
    )

    assert result.assets[0].usage.fragments == ["frag_007"]


# ======================== P0-2 首帧静态化 ========================


def test_split_static_motion_isolates_action_sequence() -> None:
    """列车进站片段：静态首帧不含动作，动作序列进入 motion_prompt"""
    description = (
        "全景镜头：深夜地铁站台，列车头灯从隧道深处亮起，"
        "列车缓缓驶入站台，车门打开，车厢内空无一人。林晚站在原地。"
    )
    fragment = _fragment(8, description, "wide_shot")
    prompt = AIVideoPrompt(
        fragment_id="frag_008",
        prompt="wide shot, late night subway platform",
        duration=3.3,
        main_character="林晚",
        camera=CameraControl(shot_type="wide_shot"),
    )

    first_frame = build_first_frame_prompt(prompt, scene=SCENE, fragment=fragment)
    motion = build_motion_prompt(prompt, fragment)

    for verb in ("亮起", "驶入", "打开"):
        assert verb not in first_frame
        assert verb in motion
    assert "深夜地铁站台" in first_frame
    assert EMPTY_SCENE_MARKER not in first_frame


def test_static_frame_drops_negated_motion_clause() -> None:
    """“没有回头”是静态状态，但字面含动作词，需从首帧剔除（验收按关键词检查）"""
    description = "林晚没有回头，依旧望着隧道方向，神情落寞。"
    fragment = _fragment(7, description, "close_up")
    prompt = AIVideoPrompt(
        fragment_id="frag_007",
        prompt="close-up of Lin Wan",
        duration=3.0,
        main_character="林晚",
        camera=CameraControl(shot_type="close_up"),
    )

    first_frame = build_first_frame_prompt(prompt, scene=SCENE, fragment=fragment)

    assert "回头" not in first_frame
    assert "依旧望着隧道方向" in first_frame


def test_static_frame_keeps_pre_action_pose() -> None:
    """动作开始前的姿态与道具保留在首帧，后续回头/关门/渐黑被剥离"""
    description = (
        "中景转全景镜头，林晚身穿深灰色羊毛大衣，手持皱巴巴的白色纸条，"
        "迈步走上列车，回头看向站台，车门合拢，画面渐黑。"
    )
    fragment = _fragment(10, description, "medium_shot")
    prompt = AIVideoPrompt(
        fragment_id="frag_010",
        prompt="medium shot, subway platform",
        duration=4.4,
        main_character="林晚",
        camera=CameraControl(shot_type="medium_shot"),
    )

    first_frame = build_first_frame_prompt(prompt, scene=SCENE, fragment=fragment)

    assert "林晚身穿深灰色羊毛大衣" in first_frame
    assert "白色纸条" in first_frame
    for verb in ("迈步", "回头", "合拢", "渐黑"):
        assert verb not in first_frame


def test_package_references_use_core_noun_and_state() -> None:
    """道具引用按核心名词匹配，并携带当前片段状态"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_asset(
        AssetContract(
            asset_id="prop_001",
            asset_type="prop",
            owner_name="皱巴巴的纸条",
            image_prompt="product still of 皱巴巴的纸条",
        )
    )
    fragment = _fragment(7, "她将这张白色纸条揉成一团", "extreme_close_up")
    prompt = AIVideoPrompt(
        fragment_id="frag_007",
        prompt="extreme close-up of hands",
        duration=2.7,
        main_character="林晚",
        camera=CameraControl(shot_type="extreme_close_up"),
    )

    references = build_package_references(
        prompt,
        contract,
        fragment=fragment,
        prop_states={"皱巴巴的纸条": "balled"},
    )

    prop = next(ref for ref in references if ref.asset_id == "prop_001")
    assert prop.role == "prop"
    assert prop.state == "balled"


# ======================== P0-4 Gate 1 质检 ========================


def _quality_inputs() -> tuple[list[AdaptedPromptPackage], AIVideoInstructions]:
    prompt = AIVideoPrompt(
        fragment_id="frag_001",
        prompt="a poster with a book title, a woman says 'The last train is arriving.'",
        duration=3.0,
        main_character="林晚",
        camera=CameraControl(shot_type="extreme_close_up", source_shot_type="close_up"),
        audio=AIAudioPrompt(
            audio_id="frag_001",
            prompt="中文台词：末班车即将进站。",
            dialogue_language="zh",
        ),
    )
    instructions = AIVideoInstructions(
        fragments=[prompt],
        metadata={
            "duration_report": {
                "total_duration": 30.0,
                "shot_duration": 37.35,
                "element_duration": 37.08,
            },
            "style_anchor_provenance": {
                "lighting_source": "audio_atmosphere",
                "lighting_keyword": "压抑",
            },
        },
    )
    package = AdaptedPromptPackage(
        fragment_id="frag_001",
        target_model="runway_gen4",
        prompt="adapted",
        duration=3.0,
        mode=RouteMode.IMAGE_TO_VIDEO,
        image_prompt="wide shot, train slowly entering station, doors opening",
    )
    return [package], instructions


def test_quality_gate_reports_structural_issues() -> None:
    """结构问题必须回写 warnings，并置位特殊关注标记"""
    packages, instructions = _quality_inputs()
    plan = _plan(("prop_001", "纸条"))
    plan.assets[0].usage.fragments = ["frag_001"]
    fragments = [_fragment(1, "她展开那张纸条")]

    global_warnings = apply_quality_gate(
        packages, instructions, asset_plan=plan, fragments=fragments
    )

    joined = "\n".join(packages[0].warnings)
    assert "首帧提示词包含动作序列" in joined
    assert "景别不一致" in joined
    assert "critical_text" in joined
    assert "英文对白" in joined
    assert "缺少道具引用" in joined
    assert instructions.fragments[0].requires_special_attention is True

    global_joined = "\n".join(global_warnings)
    assert "交付时长偏离镜头计划" in global_joined
    assert "打光证据来源=audio_atmosphere" in global_joined


def test_quality_gate_clean_package_stays_empty() -> None:
    """无结构问题时 Gate 保持静默，不制造噪声"""
    prompt = AIVideoPrompt(
        fragment_id="frag_002",
        prompt="medium shot of a woman standing by the platform",
        duration=3.0,
        main_character="林晚",
        camera=CameraControl(shot_type="medium_shot", source_shot_type="medium_shot"),
    )
    instructions = AIVideoInstructions(
        fragments=[prompt],
        metadata={
            "duration_report": {
                "total_duration": 10.0,
                "shot_duration": 10.0,
                "element_duration": 10.0,
            },
            "style_anchor_provenance": {"lighting_source": "lighting_keyword"},
        },
    )
    package = AdaptedPromptPackage(
        fragment_id="frag_002",
        target_model="runway_gen4",
        prompt="adapted",
        duration=3.0,
        mode=RouteMode.IMAGE_TO_VIDEO,
        image_prompt="medium shot of 林晚, at 城市地铁站台",
    )

    global_warnings = apply_quality_gate([package], instructions)

    assert package.warnings == []
    assert global_warnings == []
    assert prompt.requires_special_attention is False


def test_quality_gate_accepts_normal_duration_semantic_gap() -> None:
    """三套时长口径语义不同：正常重算差异与元素推算值不产生交付偏差告警"""
    prompt = AIVideoPrompt(fragment_id="frag_004", prompt="a woman waits", duration=3.0)
    instructions = AIVideoInstructions(
        fragments=[prompt],
        metadata={
            "duration_report": {
                "total_duration": 34.7,
                "shot_duration": 37.2,
                "element_duration": 36.9,
            }
        },
    )
    package = AdaptedPromptPackage(
        fragment_id="frag_004",
        target_model="runway_gen4",
        prompt="adapted",
        duration=3.0,
    )

    global_warnings = apply_quality_gate([package], instructions)

    assert global_warnings == []
