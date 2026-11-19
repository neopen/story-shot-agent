"""景别归一与探测器收紧（0.4.7 T-105，FR-104~FR-106a / AC-080）。

覆盖规范景别短语映射、提示词开头景别归一（含中英对照段与 ``[Style:]``
前缀）、探测与归一共用别名表、运镜词不再判为景别，以及审计在归一后不再
报 ``shot_type_prompt_mismatch``。
"""

from penshot.neopen.agent.prompt_converter.camera_builder import (
    SHOT_PHRASE_MAP,
    build_camera_control,
    detect_shot_type_from_text,
    normalize_instructions_shot_phrases,
    normalize_prompt_shot_phrase,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
    CameraControl,
    CameraMotion,
)
from penshot.neopen.agent.prompt_converter.template_prompt_converter import (
    TemplatePromptConverter,
)
from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    BasicViolation,
    RuleType,
    SeverityLevel,
)
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import (
    RuleQualityAuditor,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig


def _fragment(prompt: str, **overrides) -> AIVideoPrompt:
    payload = {
        "fragment_id": "frag_001",
        "prompt": prompt,
        "duration": 3.0,
        "camera": CameraControl(shot_type="close_up", source_shot_type="close_up"),
    }
    payload.update(overrides)
    return AIVideoPrompt(**payload)


def _shot_mismatches(report):
    return [v for v in report.violations if v.issue_code == "shot_type_prompt_mismatch"]


def test_phrase_map_covers_eight_shot_types():
    """FR-105：映射表覆盖八种景别，中英短语齐全"""
    assert set(SHOT_PHRASE_MAP) == {
        "close_up",
        "extreme_close_up",
        "medium_shot",
        "wide_shot",
        "long_shot",
        "two_shot",
        "over_shoulder",
        "pov",
    }
    assert SHOT_PHRASE_MAP["close_up"] == ("close-up shot", "特写镜头")
    assert SHOT_PHRASE_MAP["over_shoulder"] == ("over-the-shoulder shot", "过肩镜头")
    assert SHOT_PHRASE_MAP["pov"] == ("POV shot", "主观镜头")


def test_mismatched_opening_phrase_is_replaced_and_motion_kept():
    """FR-104：只改开头景别短语，构图与运动描述保留"""
    prompt = "wide shot, slow push-in towards the note"

    updated, applied = normalize_prompt_shot_phrase(prompt, "close_up")

    assert updated == "close-up shot, slow push-in towards the note"
    assert applied == "close-up shot"
    assert detect_shot_type_from_text(updated) == "close_up"


def test_missing_phrase_is_inserted_without_changing_shot_size():
    """FR-105：缺开头景别时插入目标短语，不猜成其他景别"""
    updated, applied = normalize_prompt_shot_phrase(
        "A man walks down the corridor", "medium_shot"
    )

    assert updated == "medium shot, A man walks down the corridor"
    assert applied == "medium shot"


def test_consistent_phrase_is_left_untouched():
    """一致时保持原措辞，避免把 POV tracking shot 压平成 POV shot"""
    prompt = "POV tracking shot, low angle, walking forward"

    assert normalize_prompt_shot_phrase(prompt, "pov") == (prompt, None)


def test_style_prefix_is_preserved():
    """FR-104：``[Style: ...]`` 前缀内容不参与归一"""
    updated, applied = normalize_prompt_shot_phrase(
        "[Style: cinematic, wide shot framing] wide shot of the empty street",
        "close_up",
    )

    assert updated == (
        "[Style: cinematic, wide shot framing] close-up shot of the empty street"
    )
    assert applied == "close-up shot"


def test_chinese_counterpart_paragraph_is_normalized_in_sync():
    """FR-104：``\\n\\n`` 之后的中文对照段同步归一，英文段不混入中文"""
    prompt = "wide shot of the empty classroom\n\n全景镜头，空荡的教室"

    updated, applied = normalize_prompt_shot_phrase(prompt, "close_up")

    english, chinese = updated.split("\n\n")
    assert english == "close-up shot of the empty classroom"
    assert chinese == "特写镜头，空荡的教室"
    assert applied == "close-up shot"


def test_chinese_only_prompt_uses_chinese_phrase():
    """中文提示词只插入/替换中文短语"""
    updated, applied = normalize_prompt_shot_phrase("李明站在教室门口", "wide_shot")

    assert updated == "全景镜头，李明站在教室门口"
    assert applied == "全景镜头"


def test_unknown_or_empty_shot_type_is_skipped():
    """FR-106a：空值或不在映射表内的景别跳过，不改写、不告警"""
    prompt = "zoom shot on the pocket watch"

    assert normalize_prompt_shot_phrase(prompt, "") == (prompt, None)
    assert normalize_prompt_shot_phrase(prompt, "zoom") == (prompt, None)
    assert normalize_prompt_shot_phrase(prompt, "following_shot") == (prompt, None)


def test_detector_ignores_style_prefix():
    """FR-104/FR-106：``[Style: ...]`` 前缀里的措辞不参与景别探测"""
    prompt = "[Style: cinematic, wide shot framing] close-up of her face"

    assert detect_shot_type_from_text(prompt) == "close_up"


def test_zoom_is_motion_not_shot_type():
    """FR-106：探测不再把运镜词判为景别，运镜仍记入 camera.motion"""
    camera = build_camera_control("zoom shot on the pocket watch", None)

    assert detect_shot_type_from_text("zoom shot on the pocket watch") == ""
    assert detect_shot_type_from_text("缓慢变焦") == ""
    assert detect_shot_type_from_text("镜头推拉") == ""
    assert camera.shot_type == "medium_shot"
    assert camera.motion.value == CameraMotion.ZOOM.value


def test_structured_zoom_source_is_still_normalized():
    """结构化来源值 zoom 仍按精确别名保留，不受文本别名收紧影响"""
    assert build_camera_control("slow pan", "zoom").shot_type == "zoom"


def test_source_shot_type_wins_during_normalization():
    """归一以计划景别为准：camera.shot_type 与来源不一致时采用来源"""
    prompt = _fragment(
        "medium shot, a woman waits",
        camera=CameraControl(shot_type="medium_shot", source_shot_type="close_up"),
    )
    instructions = AIVideoInstructions(fragments=[prompt])

    changes = normalize_instructions_shot_phrases(instructions)

    assert prompt.prompt.startswith("close-up shot")
    assert changes == [
        {
            "fragment_id": "frag_001",
            "shot_type": "close_up",
            "applied_phrase": "close-up shot",
        }
    ]


def test_fragment_without_camera_is_skipped():
    """无 camera 的片段不参与归一"""
    prompt = _fragment("wide shot of the street", camera=None)
    instructions = AIVideoInstructions(fragments=[prompt])

    assert normalize_instructions_shot_phrases(instructions) == []
    assert prompt.prompt == "wide shot of the street"


def test_audit_reports_no_mismatch_after_normalization():
    """FR-106 共用探测器：归一后审计不再报景别不一致"""
    fragment = _fragment("wide shot of the city street at dusk while rain falls")
    instructions = AIVideoInstructions(fragments=[fragment])
    assert (
        len(_shot_mismatches(RuleQualityAuditor(ShotConfig()).audit(instructions))) == 1
    )

    normalize_instructions_shot_phrases(instructions)

    report = RuleQualityAuditor(ShotConfig()).audit(instructions)
    assert _shot_mismatches(report) == []


def test_repair_branch_normalizes_shot_mismatch():
    """AC-082：提示词修复器按 issue_code 确定性改写景别并记录真实动作"""
    agent = PromptConverterAgent(llm=None, config=ShotConfig(enable_llm=False))
    instructions = AIVideoInstructions(
        fragments=[
            _fragment(
                "wide shot of the city street at dusk",
                camera=CameraControl(shot_type="close_up", source_shot_type="close_up"),
            )
        ]
    )
    issue = BasicViolation.create_violation(
        rule_type=RuleType.SHOT_TYPE_PROMPT_MISMATCH,
        severity=SeverityLevel.WARNING,
        fragment_id="frag_001",
        source_node=PipelineNode.CONVERT_PROMPT,
    )

    repaired = agent.repair_prompts(
        instructions,
        [issue],
        FragmentSequence(fragments=[]),
    )

    assert repaired.fragments[0].prompt.startswith("close-up shot")
    assert repaired.metadata["repair_status"] == "repaired"
    actions = repaired.metadata["repair_history"][-1]["actions"]
    assert any("归一景别表述" in action for action in actions)


def test_template_converter_post_process_normalizes_prompt():
    """规则转换器的 post_process 同样执行景别归一"""
    converter = TemplatePromptConverter(ShotConfig())
    fragment = VideoFragment(
        id="frag_001",
        shot_id="shot_001",
        duration=3.0,
        description="slow pan across the empty street",
        shot_type="over_shoulder",
    )

    instructions = converter.convert(
        FragmentSequence(fragments=[fragment]),
        None,
        None,
        None,
    )

    assert instructions.fragments[0].prompt.startswith("over-the-shoulder shot")
