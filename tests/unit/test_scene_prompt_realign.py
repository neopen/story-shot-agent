"""地点重写与冲突阻断（0.4.7 T-102，FR-098/FR-098a / AC-080）。

覆盖计划地点解析、英中地点短语改写、计划地点已出现时不改写、引号台词
不触发、专有陈设阻断、改写保留动作与构图，以及路由阶段对冲突片段的
``needs_manual_fix`` 阻断。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter.image_to_video import (
    apply_image_to_video_routing,
)
from penshot.neopen.agent.model_adapter.model_models import AdaptedPromptPackage
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prompt_converter.scene_prompt_realign import (
    apply_scene_prompt_realignment,
    realign_scene_prompt,
)
from penshot.neopen.agent.script_parser.script_parser_models import (
    ParsedScript,
    SceneInfo,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import VideoFragment


def _script() -> ParsedScript:
    return ParsedScript(
        scenes=[
            SceneInfo(id="scene_001", location="教室"),
            SceneInfo(id="scene_002", location="走廊/班级记忆墙前"),
        ]
    )


def _fragment(fragment_id: str, scene_id: str = "scene_002") -> VideoFragment:
    return VideoFragment(
        id=fragment_id,
        shot_id=f"shot_{fragment_id[-3:]}",
        duration=3.0,
        description="",
        continuity_notes={"location": f"场景{scene_id}"},
    )


def _prompt(fragment_id: str, text: str) -> AIVideoPrompt:
    return AIVideoPrompt(fragment_id=fragment_id, prompt=text, duration=3.0)


def test_english_location_phrase_is_rewritten():
    """FR-098：classroom background → corridor background，动作与构图保留"""
    prompt = (
        "over-the-shoulder shot, classroom background with colorful posters, "
        "holding an orange basketball"
    )

    result = realign_scene_prompt(prompt, "走廊", fragment_id="frag_010")

    assert result.prompt == (
        "over-the-shoulder shot, corridor background with colorful posters, "
        "holding an orange basketball"
    )
    assert result.replaced == [("classroom", "corridor")]
    assert result.conflicts == []


def test_chinese_location_phrase_is_rewritten_to_plan_segment():
    """FR-098：教室记忆墙 → 走廊记忆墙，其余中文内容不变"""
    prompt = "教室记忆墙前，李明站着，手中握着白色同学录"

    result = realign_scene_prompt(prompt, "走廊/班级记忆墙前", fragment_id="frag_002")

    assert result.prompt == "走廊记忆墙前，李明站着，手中握着白色同学录"
    assert result.replaced == [("教室", "走廊")]


def test_plan_location_already_present_is_not_rewritten():
    """计划地点词已出现时视为一致，不做改写"""
    prompt = "school corridor with memory wall covered in photos"

    result = realign_scene_prompt(prompt, "走廊/班级记忆墙前")

    assert result.prompt == prompt
    assert result.replaced == []
    assert result.conflicts == []


def test_location_inside_dialogue_is_ignored():
    """引号台词提到其他地点不触发改写"""
    prompt = 'close-up, he says "Let\'s go back to the classroom"'

    result = realign_scene_prompt(prompt, "走廊", fragment_id="frag_003")

    assert result.prompt == prompt
    assert result.replaced == []
    assert result.conflicts == []


def test_venue_furnishing_blocks_rewrite():
    """FR-098a：走廊镜头里的课桌椅/黑板不改写，记 venue_furnishing"""
    prompt = (
        "over-the-shoulder shot, classroom background with desks and blackboard, "
        "holding an orange basketball"
    )

    result = realign_scene_prompt(prompt, "走廊", fragment_id="frag_010")

    assert result.prompt == prompt
    assert result.replaced == []
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.fragment_id == "frag_010"
    assert conflict.term == "classroom"
    assert conflict.language == "en"
    assert conflict.reason == "venue_furnishing"
    assert "desks" in conflict.clause and "blackboard" in conflict.clause


def test_unknown_plan_location_skips_with_info():
    """计划场景地点无法解析时整段跳过，不产生冲突与改写"""
    instructions = AIVideoInstructions(
        fragments=[_prompt("frag_001", "classroom background with desks")]
    )

    stats = apply_scene_prompt_realignment(
        instructions,
        [VideoFragment(id="frag_001", shot_id="shot_001", duration=3.0)],
        _script(),
    )

    assert stats == {"realigned": 0, "conflicts": 0, "skipped": 1}
    assert instructions.metadata["scene_prompt_realigned"] == []
    assert instructions.metadata["scene_prompt_conflicts"] == {}
    assert instructions.metadata["scene_prompt_realign_summary"] == {
        "realigned": 0,
        "conflicts": 0,
        "skipped": 1,
        "skipped_fragment_ids": ["frag_001"],
    }
    assert instructions.fragments[0].prompt == "classroom background with desks"


def test_fragment_scene_id_takes_precedence_over_notes():
    """T-113：片段自带 scene_id 时直接解析计划地点，不依赖 notes 文本"""
    fragment = SimpleNamespace(id="frag_030", scene_id="scene_001", continuity_notes={})
    instructions = AIVideoInstructions(
        fragments=[_prompt("frag_030", "corridor background with posters")]
    )

    stats = apply_scene_prompt_realignment(instructions, [fragment], _script())

    assert stats["realigned"] == 1
    assert instructions.fragments[0].prompt == "classroom background with posters"


def test_unique_location_name_resolves_when_no_scene_id():
    """T-113：无 scene_id 时按 notes 地点名在剧本中唯一命中解析"""
    fragment = SimpleNamespace(id="frag_031", continuity_notes={"location": "教室"})
    instructions = AIVideoInstructions(
        fragments=[_prompt("frag_031", "corridor background with posters")]
    )

    stats = apply_scene_prompt_realignment(instructions, [fragment], _script())

    assert stats["realigned"] == 1
    assert instructions.fragments[0].prompt == "classroom background with posters"


def test_ambiguous_location_name_skips():
    """T-113：地点名在剧本中命中多个场景时视为无法解析并跳过"""
    script = ParsedScript(
        scenes=[
            SceneInfo(id="scene_001", location="走廊尽头"),
            SceneInfo(id="scene_002", location="走廊/班级记忆墙前"),
        ]
    )
    fragment = SimpleNamespace(id="frag_032", continuity_notes={"location": "走廊"})
    instructions = AIVideoInstructions(
        fragments=[_prompt("frag_032", "classroom background with posters")]
    )

    stats = apply_scene_prompt_realignment(instructions, [fragment], script)

    assert stats == {"realigned": 0, "conflicts": 0, "skipped": 1}
    assert instructions.fragments[0].prompt == "classroom background with posters"


def test_apply_writes_metadata_for_rewrite_and_conflict():
    """apply 汇总改写与冲突，分别写入 scene_prompt_realigned / scene_prompt_conflicts"""
    instructions = AIVideoInstructions(
        fragments=[
            _prompt(
                "frag_020",
                "medium shot, classroom background with posters, a boy stands",
            ),
            _prompt(
                "frag_021",
                "wide shot, classroom background with desks and blackboard",
            ),
        ]
    )

    stats = apply_scene_prompt_realignment(
        instructions, [_fragment("frag_020"), _fragment("frag_021")], _script()
    )

    assert stats == {"realigned": 1, "conflicts": 1, "skipped": 0}
    assert instructions.fragments[0].prompt.startswith("medium shot, corridor")
    assert instructions.metadata["scene_prompt_realigned"] == [
        {"fragment_id": "frag_020", "from": "classroom", "to": "corridor"}
    ]
    conflicts = instructions.metadata["scene_prompt_conflicts"]
    assert list(conflicts) == ["frag_021"]
    assert conflicts["frag_021"][0]["reason"] == "venue_furnishing"
    assert conflicts["frag_021"][0]["plan_location"] == "走廊/班级记忆墙前"


def test_route_blocks_fragment_with_unresolved_location_conflict():
    """FR-098a/AC-080：未消除地点冲突的片段在路由阶段标记 needs_manual_fix"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(scene_num=1, location="走廊", time_of_day="dusk")
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="走廊",
            image_prompt="establishing shot still of 走廊",
            status="pending",
        )
    )
    instructions = AIVideoInstructions(
        fragments=[
            _prompt("frag_010", "wide shot, classroom background with desks"),
            _prompt("frag_011", "wide shot, corridor floor in dusk light"),
        ]
    )
    instructions.metadata["scene_prompt_conflicts"] = {
        "frag_010": [
            {
                "fragment_id": "frag_010",
                "term": "classroom",
                "language": "en",
                "clause": "classroom background with desks",
                "reason": "venue_furnishing",
            }
        ]
    }
    packages = [
        AdaptedPromptPackage(
            fragment_id=fragment_id,
            target_model="kling",
            prompt="adapted",
            duration=3.0,
        )
        for fragment_id in ("frag_010", "frag_011")
    ]
    fragments = [
        SimpleNamespace(id="frag_010", shot_id="shot_001", description=""),
        SimpleNamespace(id="frag_011", shot_id="shot_001", description=""),
    ]
    shots = [SimpleNamespace(id="shot_001", scene_id="scene_001")]

    apply_image_to_video_routing(
        packages, instructions, contract, fragments=fragments, shots=shots
    )

    blocked = packages[0]
    assert blocked.mode.value == "image_to_video"
    assert blocked.status == "needs_manual_fix"
    assert any("地点冲突未解决" in message for message in blocked.warnings)
    blocked_message = next(
        message for message in blocked.warnings if "地点冲突未解决" in message
    )
    assert "计划地点=走廊" in blocked_message
    assert "期望首帧资产=scene_001" in blocked_message
    assert packages[1].status == "ready"
