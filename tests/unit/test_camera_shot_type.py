"""景别一致性单元测试（0.4.4 T-401~T-404，0.4.5 景别映射修正）。

覆盖 ShotType 全值别名、长词优先匹配、探测顺序（来源景别 > 最终 prompt >
默认值）、扩展景别保留、未知景别告警、来源景别溯源字段，以及两个转换器
均优先采用来源镜头景别。
"""

import pytest

from penshot.neopen.agent.prompt_converter import camera_builder
from penshot.neopen.agent.prompt_converter.camera_builder import (
    build_camera_control,
    check_motion_consistency,
    detect_motion_from_text,
    detect_shot_type_from_text,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import CameraMotion
from penshot.neopen.agent.prompt_converter.template_prompt_converter import (
    TemplatePromptConverter,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotType
from penshot.neopen.agent.video_splitter.video_splitter_models import VideoFragment
from penshot.neopen.shot_config import ShotConfig


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("全景", "wide_shot"),
        ("远景", "long_shot"),
        ("中景", "medium_shot"),
        ("近景", "close_up"),
        ("特写", "close_up"),
        ("极特写", "extreme_close_up"),
        ("过肩", "over_shoulder"),
        ("主观", "pov"),
        ("双人", "two_shot"),
        ("跟拍", "following_shot"),
        ("wide shot", "wide_shot"),
        ("long shot", "long_shot"),
        ("medium shot", "medium_shot"),
        ("close-up", "close_up"),
        ("extreme close-up", "extreme_close_up"),
        ("over-the-shoulder", "over_shoulder"),
        ("point of view", "pov"),
        ("two shot", "two_shot"),
    ],
)
def test_shot_type_aliases_cover_chinese_and_english(alias, expected):
    """FR-030：中文与英文别名都能归一化到 ShotType 值"""
    camera = build_camera_control(f"{alias} of the scene")

    assert camera.shot_type == expected


@pytest.mark.parametrize("value", [shot_type.value for shot_type in ShotType])
def test_every_enum_value_is_recognized(value):
    """FR-030：别名表覆盖 ShotType 枚举全部值"""
    camera = build_camera_control("", value)

    assert camera.shot_type == value


def test_longest_alias_wins_for_extreme_close_up():
    """T-401：长词优先，extreme close-up 不被 close-up 截胡"""
    camera = build_camera_control("extreme close-up on the pocket watch")

    assert camera.shot_type == "extreme_close_up"


def test_source_shot_type_wins_over_prompt_text():
    """0.4.5：来源景别是镜头计划事实源，提示词短语不得把结构化景别升级/降级"""
    camera = build_camera_control("wide shot of the empty street", "close_up")

    assert camera.shot_type == "close_up"


def test_source_shot_type_used_when_prompt_has_no_marker():
    """FR-031：提示词无景别词时回退来源镜头景别"""
    camera = build_camera_control("slow pan across the room", "over_shoulder")

    assert camera.shot_type == "over_shoulder"


def test_missing_signal_falls_back_to_medium():
    """FR-031：文本与来源都缺失时才使用默认景别"""
    camera = build_camera_control("slow pan across the room", None)

    assert camera.shot_type == "medium_shot"


def test_extended_shot_type_is_not_downgraded():
    """FR-032/AC-030/AC-031：扩展景别原样保留"""
    for value in (
        "over_shoulder",
        "extreme_close_up",
        "pov",
        "two_shot",
        "following_shot",
    ):
        assert build_camera_control("", value).shot_type == value


def test_unknown_shot_type_is_kept_with_warning(monkeypatch):
    """FR-033/AC-033：未知景别保留原值并告警，不静默降级"""
    warnings = []
    monkeypatch.setattr(camera_builder, "warning", warnings.append)

    camera = build_camera_control("slow pan", "dutch_angle")

    assert camera.shot_type == "dutch_angle"
    assert warnings
    assert "dutch_angle" in warnings[0]


def test_source_shot_type_tracks_normalized_and_raw_values():
    """FR-034/AC-030：来源景别同时保留归一化值与原始值"""
    camera = build_camera_control("slow pan across the room", "过肩")

    assert camera.shot_type == "over_shoulder"
    assert camera.source_shot_type == "over_shoulder"
    assert camera.shot_type_raw == "过肩"


def test_source_fields_stay_recorded_when_prompt_text_differs():
    """FR-034：结构化景别与来源一致，提示词差异只体现在文本中"""
    camera = build_camera_control("extreme close-up on the pocket watch", "close_up")

    assert camera.shot_type == "close_up"
    assert camera.source_shot_type == "close_up"
    assert camera.shot_type_raw == "close_up"


def test_source_fields_empty_without_source_shot_type():
    """FR-034：无来源景别时溯源字段为空"""
    camera = build_camera_control("slow pan across the room", None)

    assert camera.shot_type == "medium_shot"
    assert camera.source_shot_type == ""
    assert camera.shot_type_raw == ""


def test_template_converter_keeps_source_shot_type():
    """0.4.5：模板转换器保留来源镜头景别，不被推断模板改写"""
    converter = TemplatePromptConverter(ShotConfig())
    fragment = VideoFragment(
        id="frag_001",
        shot_id="shot_001",
        duration=3.0,
        description="slow pan across the empty street",
        shot_type="over_shoulder",
    )

    prompt = converter.convert_fragment(fragment)

    assert "Medium shot" in prompt.prompt
    assert prompt.camera.shot_type == "over_shoulder"
    assert prompt.camera.source_shot_type == "over_shoulder"
    assert prompt.camera.shot_type_raw == "over_shoulder"


def test_llm_converter_keeps_source_shot_type(monkeypatch):
    """0.4.5：LLM 转换器保留来源镜头景别，提示词措辞漂移不改结构化字段"""
    from penshot.neopen.agent.prompt_converter.llm_prompt_converter import (
        LLMPromptConverter,
    )

    converter = object.__new__(LLMPromptConverter)
    converter.config = ShotConfig()
    converter.system_prompt = "system"
    converter.user_prompt_template = (
        "{fragment_id}{description}{duration}{character}{location}"
        "{original_language}{dm_model}{video_style}{max_length}{min_length}"
        "{global_context}{scene_info}{element_info}{full_script_context}"
        "{audio_context}{characters_json}{repair_hint}{history_hint}"
    )
    converter.global_metadata = None
    converter.script_language = "en"
    converter.current_repair_params = None
    converter.last_audio_id = None
    converter._detect_original_language = lambda fragment: "en"
    converter._get_scene_info_for_fragment = lambda fragment: ""
    converter._get_element_info_for_fragment = lambda fragment: ""
    converter._format_global_context = lambda metadata: ""
    converter._get_full_script_context = lambda fragment: ""
    converter._get_audio_context_for_fragment = lambda fragment: {}
    converter._get_character_info_json = lambda: "[]"
    converter._build_history_hint = lambda context: ""
    converter._call_llm_parse_with_retry = lambda system, user: {
        "prompt": "An over-the-shoulder shot follows her gaze.",
        "original_prompt": "过肩镜头跟随她的视线。",
    }
    converter._build_audio_prompt_from_llm_result = lambda result, fragment: None

    fragment = VideoFragment(
        id="frag_008",
        shot_id="shot_008",
        duration=3.0,
        description="slow pan across the room",
        shot_type="close_up",
    )

    prompt = converter._convert_fragment_with_llm(fragment, None)

    assert "over-the-shoulder" in prompt.prompt
    assert prompt.camera.shot_type == "close_up"
    assert prompt.camera.source_shot_type == "close_up"
    assert prompt.camera.shot_type_raw == "close_up"


# ======================== 0.4.5 景别映射修正：POV 与位置优先 ========================


def test_text_detection_prefers_earliest_shot_marker():
    """靠后的 close-up 不能截胡开头的 POV（frag_007 根因）"""
    prompt = (
        "POV tracking shot, low angle, walking forward to bypass the sofa, "
        "then a close-up on the trembling hands"
    )

    assert detect_shot_type_from_text(prompt) == "pov"


def test_pov_source_is_not_collapsed_into_close_up():
    """来源为 pov 时结构化景别保持 pov，不因提示词含 close-up 被吞掉"""
    camera = build_camera_control(
        "POV tracking shot, low angle, then a close-up on the trembling hands",
        "pov",
    )

    assert camera.shot_type == "pov"
    assert camera.source_shot_type == "pov"


# ======================== 0.4.5 任务 5：运镜一致性 ========================


def test_motion_detects_push_in_as_dolly():
    """slow push-in 归为 dolly 而非 static"""
    camera = build_camera_control("wide shot, slow push-in toward the note", None)

    assert camera.motion.value == "dolly"


def test_motion_detects_pull_back_as_dolly():
    """slow pull-back 归为 dolly（旧词表缺失，退化为 zoom 或 static）"""
    camera = build_camera_control("wide shot, slow pull-back camera movement", None)

    assert camera.motion.value == "dolly"


def test_motion_detects_tracking_as_dolly():
    """tracking shot 归为 dolly"""
    camera = build_camera_control("tracking shot through the corridor", None)

    assert camera.motion.value == "dolly"


def test_motion_prefers_specific_phrase_over_short_keyword():
    """多词短语优先：pull-back 不被中文“拉远”（zoom 族）截胡"""
    camera = build_camera_control("wide shot, slow pull-back，缓慢拉远镜头", None)

    assert camera.motion.value == "dolly"


def test_motion_keeps_chinese_zoom_mapping():
    """既有中文映射不变：单说“拉远”仍是 zoom"""
    camera = build_camera_control("全景镜头，缓慢拉远", None)

    assert camera.motion.value == "zoom"


def test_motion_static_for_pure_stillness():
    """纯静态描述仍为 static"""
    camera = build_camera_control("close-up of a still frame on the table", None)

    assert camera.motion.value == "static"


def test_motion_conflict_logs_warning(monkeypatch):
    """命中多个运动族时保留最具体者并告警"""
    messages = []
    monkeypatch.setattr(camera_builder, "warning", messages.append)

    build_camera_control("slow pull-back，缓慢拉远镜头", None)

    assert any("运镜关键词冲突" in message for message in messages)


def test_static_with_camera_verb_logs_warning(monkeypatch):
    """static 与明确运镜动词冲突时不得静默"""
    messages = []
    monkeypatch.setattr(camera_builder, "warning", messages.append)

    camera = build_camera_control("the camera moves slowly along the wall", None)

    assert camera.motion.value == "static"
    assert any("static" in message and "运动表述" in message for message in messages)


def test_motion_consistency_accepts_push_in_with_dolly():
    """frag_015：提示词 slow push-in、motion=dolly 属同一族，不告警"""
    result = check_motion_consistency(
        "wide shot, slow push-in towards a yellow sticky note",
        CameraMotion.DOLLY,
    )

    assert result is None


def test_motion_consistency_warns_push_in_against_static():
    """反向缺失：提示词写推镜、motion 却是 static，必须告警"""
    result = check_motion_consistency(
        "wide shot, slow push-in towards a yellow sticky note",
        CameraMotion.STATIC,
    )

    assert result is not None
    level, message = result
    assert level == "warning"
    assert "static" in message and "push-in" in message


def test_motion_consistency_skips_static_without_motion():
    """frag_010：提示词没有运镜动词、motion=static 属合理，不误报"""
    result = check_motion_consistency(
        "close-up of Li Ming's face, static camera, 35mm lens",
        CameraMotion.STATIC,
    )

    assert result is None


def test_motion_consistency_warns_motion_against_static_prompt():
    """frag_006：提示词明确写 static camera，motion=handheld 时告警"""
    result = check_motion_consistency(
        "wide shot, Li Ming standing still, 35mm lens, static camera",
        CameraMotion.HANDHELD,
    )

    assert result is not None
    level, message = result
    assert level == "warning"
    assert "handheld" in message and "静止镜头" in message


def test_motion_consistency_info_when_prompt_omits_motion():
    """提示词完全没写运镜时不升级为违规，只返回 info"""
    result = check_motion_consistency(
        "medium two-shot, two students talking in a classroom",
        CameraMotion.HANDHELD,
    )

    assert result is not None
    assert result[0] == "info"


def test_holding_object_is_not_detected_as_handheld_motion():
    """“手持白色同学录”是拿道具，不是手持运镜"""
    detected, _ = detect_motion_from_text("远景镜头，李明手持白色毕业同学录，固定机位")

    assert detected is None
