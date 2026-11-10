"""景别一致性单元测试（0.4.4 T-401/T-402）。

覆盖 ShotType 全值别名、长词优先匹配、探测顺序（最终 prompt > 来源景别 >
默认值）、扩展景别保留与未知景别告警。
"""

import pytest

from penshot.neopen.agent.prompt_converter import camera_builder
from penshot.neopen.agent.prompt_converter.camera_builder import build_camera_control
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotType


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


def test_prompt_text_wins_over_source_shot_type():
    """FR-031：探测顺序以最终提示词文本为准"""
    camera = build_camera_control("wide shot of the empty street", "close_up")

    assert camera.shot_type == "wide_shot"


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
