"""连续性加固测试：快照、结构化锚点、seed、关键词误报与风格守护。"""

import json
from types import SimpleNamespace

import pytest
from llama_index.core.embeddings import MockEmbedding

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    CharacterContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import (
    ContinuityGuardianChecker,
)
from penshot.neopen.agent.continuity_guardian.cross_chunk_validator import (
    CrossChunkValidator,
)
from penshot.neopen.agent.continuity_guardian.long_script_chunker import (
    LongScriptChunker,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssueType,
    StateSnapshot,
    StateTimeline,
)
from penshot.neopen.agent.continuity_guardian.prompt_style_guardian import (
    PromptStyleGuardian,
)
from penshot.neopen.agent.model_adapter.model_adapter_factory import get_adapter
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed
from penshot.neopen.constants import (
    ACTION_SYNONYM_GROUPS_ZH,
    HOLDING_VERBS_ZH,
    get_action_synonym_groups,
    get_holding_verbs,
    get_prop_object_pattern_template,
)
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager
from penshot.neopen.shot_config import ShotConfig


# ============================ 快照 ============================


def test_get_snapshot_at_time_returns_nearest_snapshot():
    timeline = StateTimeline()
    for index, timestamp in enumerate([0.0, 10.0, 20.0]):
        timeline.add_snapshot(
            StateSnapshot(timestamp=timestamp, snapshot_id=f"snapshot_{index}")
        )

    assert timeline.get_snapshot_at_time(4.0).snapshot_id == "snapshot_0"
    assert timeline.get_snapshot_at_time(6.0).snapshot_id == "snapshot_1"
    assert (
        timeline.get_snapshot_at_time(15.0).snapshot_id == "snapshot_1"
    )  # 距离相同取较早
    assert timeline.get_snapshot_at_time(19.0).snapshot_id == "snapshot_2"


def test_take_snapshot_records_fragment_reference():
    checker = ContinuityGuardianChecker()
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="a", duration=2),
            AIVideoPrompt(fragment_id="frag_002", prompt="b", duration=2),
        ]
    )

    snapshot = checker.take_snapshot({"instructions": instructions})

    assert snapshot.references["fragment_id"] == "frag_002"
    assert snapshot.global_state["fragment_count"] == 2
    assert checker.timeline.get_latest_snapshot() is snapshot


# ===================== 动作/道具关键词误报 =====================


def _shot(shot_id, description, character="小明", scene_id="scene_001"):
    return SimpleNamespace(
        id=shot_id,
        description=description,
        main_character=character,
        scene_id=scene_id,
        shot_type="medium_shot",
        is_transition=False,
    )


def test_continuity_word_lists_fall_back_to_default_language():
    """未配置语言时回退 zh，新增语言只需扩展 constants.continuity 的映射"""
    assert get_action_synonym_groups("en") == ACTION_SYNONYM_GROUPS_ZH
    assert get_holding_verbs("unknown") == HOLDING_VERBS_ZH
    assert "{verbs}" in get_prop_object_pattern_template("unknown")


def test_action_synonyms_do_not_raise_action_break():
    checker = ContinuityGuardianChecker()
    shots = SimpleNamespace(
        shots=[_shot("s1", "小明向前走"), _shot("s2", "小明继续步行")]
    )
    result = ContinuityCheckResult()
    checker.check_action_continuity({"shot_sequence": shots}, result)

    assert result.issues_by_type.get(ContinuityIssueType.ACTION_BREAK.value, []) == []


def test_action_change_still_reports_break():
    checker = ContinuityGuardianChecker()
    shots = SimpleNamespace(
        shots=[_shot("s1", "小明向前走"), _shot("s2", "小明转身跑开")]
    )
    result = ContinuityCheckResult()
    checker.check_action_continuity({"shot_sequence": shots}, result)

    assert result.issues_by_type.get(ContinuityIssueType.ACTION_BREAK.value)


def test_style_check_runs_alongside_character_check():
    checker = ContinuityGuardianChecker()
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="f1",
                prompt="a",
                duration=2,
                main_character="小明",
                style="cinematic",
            ),
            AIVideoPrompt(fragment_id="f2", prompt="b", duration=2, style="anime"),
            AIVideoPrompt(fragment_id="f3", prompt="c", duration=2, style="realistic"),
        ]
    )
    context = {
        "parsed_script": SimpleNamespace(
            characters=[SimpleNamespace(name="小明")], scenes=[]
        ),
        "shot_sequence": SimpleNamespace(
            shots=[_shot("s1", "小明坐下", character="小明")]
        ),
        "instructions": instructions,
    }
    result = ContinuityCheckResult()

    checker.check_character_continuity(context, result)
    checker.check_style_continuity(context, result)

    assert result.issues_by_type.get(ContinuityIssueType.STYLE_INCONSISTENT.value)


def test_style_sudden_change_between_adjacent_fragments():
    checker = ContinuityGuardianChecker()
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="f1", prompt="a", duration=2, style="cinematic"),
            AIVideoPrompt(fragment_id="f2", prompt="b", duration=2, style="anime"),
        ]
    )
    result = ContinuityCheckResult()

    checker.check_style_continuity({"instructions": instructions}, result)

    assert result.issues_by_type.get(ContinuityIssueType.STYLE_SUDDEN_CHANGE.value)


def test_same_garment_color_drift_is_reported():
    checker = ContinuityGuardianChecker()
    result = ContinuityCheckResult()

    checker._check_character_appearance_continuity(
        "小明", "medium shot, wearing a red raincoat", 0, "f1", result
    )
    checker._check_character_appearance_continuity(
        "小明", "medium shot, wearing a blue raincoat", 1, "f2", result
    )

    assert result.issues_by_type.get(ContinuityIssueType.COLOR_INCONSISTENT.value)


def _prop_script(contents):
    elements = [
        SimpleNamespace(
            character="小明", content=content, sequence=index, id=f"elem_{index}"
        )
        for index, content in enumerate(contents, start=1)
    ]
    scene = SimpleNamespace(id="scene_001", location="街道", elements=elements)
    return SimpleNamespace(scenes=[scene], characters=[])


def test_prop_verb_change_without_object_change_is_ignored():
    checker = ContinuityGuardianChecker()
    parsed = _prop_script(["他拿起照片", "他握着照片"])
    result = ContinuityCheckResult()
    checker.check_prop_continuity({"parsed_script": parsed}, result)

    assert result.issues_by_type.get(ContinuityIssueType.PROP_CHANGE.value, []) == []


def test_prop_object_change_is_reported():
    checker = ContinuityGuardianChecker()
    parsed = _prop_script(["他拿起照片", "他握着钥匙"])
    result = ContinuityCheckResult()
    checker.check_prop_continuity({"parsed_script": parsed}, result)

    issues = result.issues_by_type.get(ContinuityIssueType.PROP_CHANGE.value)
    assert issues
    assert issues[0].auto_fixable is False


# ===================== 契约主链与结构化锚点 ======================


def _fragment(fragment_id, start_time, duration):
    return SimpleNamespace(id=fragment_id, start_time=start_time, duration=duration)


def _contract_with_style():
    contract = GlobalConsistencyContract(script_id="S", task_id="T")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="咖啡店",
            time_of_day="day",
            characters_in_scene=["小明"],
        )
    )
    contract.set_style_anchor("lighting", "soft lighting")
    contract.set_style_anchor("palette", "warm palette")
    return contract


def test_check_with_contract_runs_all_checks_and_registers_anchors():
    checker = ContinuityGuardianChecker()
    contract = _contract_with_style()

    context = {
        "shot_sequence": SimpleNamespace(
            shots=[_shot("s1", "小明坐着"), _shot("s2", "小明看向门口")]
        ),
        # 首尾不相接：验证六项基础检查（时间连续）仍然执行
        "fragment_sequence": SimpleNamespace(
            fragments=[
                _fragment("frag_001", 0.0, 2.0),
                _fragment("frag_002", 5.0, 2.0),
            ]
        ),
        "instructions": AIVideoInstructions(
            fragments=[AIVideoPrompt(fragment_id="frag_001", prompt="a", duration=2)]
        ),
    }

    result = checker.check_with_contract(context, contract)

    assert "style" in {
        a["anchor_type"] for a in checker.timeline.continuity_anchors.values()
    }
    assert result.issues_by_type.get(ContinuityIssueType.TIME_GAP.value)
    # 片段缺失风格且契约存在风格锚点时应被提示
    assert result.issues_by_type.get(ContinuityIssueType.STYLE_INCONSISTENT.value)


def test_contract_captures_scene_weather_and_props():
    parsed = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="图书馆",
                time_of_day="night",
                weather="rainy",
                elements=[SimpleNamespace(character="小明", content="翻书")],
            )
        ],
        characters=[],
        global_metadata=SimpleNamespace(
            key_props=[
                SimpleNamespace(
                    name="借阅卡",
                    description="泛黄的借阅卡",
                    color=None,
                    appears_in=["scene_001"],
                )
            ],
            character_outfits=[],
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
    )

    contract = build_contract_from_parsed(parsed, script_id="SN_SCENE")

    scene = contract.scenes[1]
    assert scene.weather == "rainy"
    assert scene.props_in_scene == {"借阅卡": "泛黄的借阅卡"}


def test_scene_anchors_detect_unknown_scene_and_time_conflict():
    contract = GlobalConsistencyContract(script_id="S", task_id="T")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="咖啡店",
            time_of_day="day",
            characters_in_scene=["小明"],
        )
    )
    contract.register_scene(
        SceneContract(
            scene_num=2,
            location="咖啡店",
            time_of_day="night",
            characters_in_scene=["小明"],
        )
    )
    unknown_shot = _shot("s_unknown", "小明推门", scene_id="scene_009")

    result = ContinuityGuardianChecker().check_with_contract(
        {"shot_sequence": SimpleNamespace(shots=[unknown_shot])}, contract
    )

    descriptions = [issue.description for issue in result.issues]
    assert any("scene_009" in text for text in descriptions)
    assert any("时间不一致" in text for text in descriptions)


def test_character_anchor_detects_first_fragment_conflict():
    contract = GlobalConsistencyContract(script_id="S", task_id="T")
    contract.characters["小明"] = CharacterContract(
        name="小明", appearance_anchors={"clothing": "红色雨衣"}
    )
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="medium shot, wearing a blue coat",
                duration=2,
                main_character="小明",
            )
        ]
    )

    result = ContinuityGuardianChecker().check_with_contract(
        {"instructions": instructions}, contract
    )

    assert result.issues_by_type.get(ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE.value)


def test_time_reverse_is_reported():
    checker = ContinuityGuardianChecker()
    result = ContinuityCheckResult()
    fragments = SimpleNamespace(
        fragments=[
            _fragment("frag_001", 5.0, 2.0),
            _fragment("frag_002", 4.0, 2.0),
        ]
    )

    checker.check_time_continuity({"fragment_sequence": fragments}, result)

    assert result.issues_by_type.get(ContinuityIssueType.TIME_REVERSE.value)


def test_long_script_chunker_uses_scene_ids_for_boundaries():
    scenes = [
        SimpleNamespace(id=f"scene_{index:03d}", elements=[])
        for index in range(1, 32)
    ]
    chunks = LongScriptChunker().chunk_script(SimpleNamespace(scenes=scenes))

    assert len(chunks) >= 2
    assert chunks[0].start_scene == 1
    assert chunks[-1].end_scene == 31


def test_cross_chunk_validator_flags_main_character_disappearing():
    issues = CrossChunkValidator().validate_chunk_transition(
        {"characters_in_chunk": ["小明", "小红"], "main_characters": ["小明"]},
        {"characters_in_chunk": ["小红"], "main_characters": ["小明"]},
    )

    assert any(issue["type"] == "character_disappears" for issue in issues)


# ============================ seed ============================


def test_video_prompt_carries_seed_and_adapter_consumes_it():
    prompt = AIVideoPrompt(fragment_id="frag_001", prompt="a", duration=2, seed=42)
    assert prompt.seed == 42
    assert get_adapter("runway_gen4").build_model_config(prompt)["seed"] == 42


def test_prompt_converter_derives_stable_seed_from_script():
    agent = PromptConverterAgent(llm=None, config=ShotConfig(enable_llm=False))
    parsed_script = ParsedScript(title="同一剧本")
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id=f"frag_{i}", prompt="a", duration=2)
            for i in range(3)
        ]
    )

    agent._apply_video_seed(instructions, parsed_script)
    seeds = {fragment.seed for fragment in instructions.fragments}

    assert len(seeds) == 1 and None not in seeds

    second_batch = AIVideoInstructions(
        fragments=[AIVideoPrompt(fragment_id="frag_x", prompt="a", duration=2)]
    )
    agent._apply_video_seed(second_batch, ParsedScript(title="同一剧本"))
    assert second_batch.fragments[0].seed in seeds


def test_explicit_video_seed_overrides_derivation():
    agent = PromptConverterAgent(
        llm=None, config=ShotConfig(enable_llm=False, video_seed=7)
    )
    instructions = AIVideoInstructions(
        fragments=[AIVideoPrompt(fragment_id="frag_1", prompt="a", duration=2)]
    )

    agent._apply_video_seed(instructions, ParsedScript(title="任意剧本"))

    assert instructions.fragments[0].seed == 7


# ========================= 风格守护 =========================


class _KnowledgeWithoutStyleApi:
    pass


def test_style_guardian_falls_back_to_anchor_and_detects_drift():
    guardian = PromptStyleGuardian(_KnowledgeWithoutStyleApi(), None)
    profile = guardian.initialize_style(
        SimpleNamespace(genre="drama"),
        {"lighting": "soft lighting", "palette": "warm palette"},
    )

    assert profile.keywords
    assert guardian.detect_style_drift(["soft lighting, warm palette scene"]) == []
    drift = guardian.detect_style_drift(["dark cold neon alley"])
    assert drift and drift[0]["fragment_index"] == 0


# ==================== 跨剧本模板迁移（显式） ====================


@pytest.fixture
def template_manager(tmp_path):
    return PromptTemplateManager(
        embedding_model=MockEmbedding(embed_dim=8),
        script_id="script_a",
        storage_dir=str(tmp_path),
        min_similarity_score=0.0,
    )


def _write_cache(manager, script_id, prompts, legacy=False):
    entries = [
        {
            "prompt": prompt,
            "hash": manager._generate_template_hash(prompt),
            "metadata": {"schema_version": "legacy" if legacy else "0.4.7"},
            "added_at": "2026-11-20T10:00:00",
        }
        for prompt in prompts
    ]
    with open(manager._get_cache_path(script_id), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False)


def test_import_templates_from_global_copies_active_only(template_manager):
    _write_cache(template_manager, "script_b", ["模板甲", "模板乙"])
    _write_cache(template_manager, "script_c", ["旧模板"], legacy=True)

    imported = template_manager.import_templates_from_global("script_target")

    assert imported == 2
    target_cache = template_manager._caches["script_target"]
    assert {entry["prompt"] for entry in target_cache} == {"模板甲", "模板乙"}
    assert all(
        entry["metadata"]["imported_from"] == "script_b" for entry in target_cache
    )

    # 再次导入不重复
    assert template_manager.import_templates_from_global("script_target") == 0
