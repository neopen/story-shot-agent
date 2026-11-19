"""T-112 运镜规则：冲突标记与运镜词表对齐，同族运镜不告警。

覆盖：
- ``镜头跟随`` / ``camera follow`` / ``camera track`` 能探测为 dolly 族运镜，
  不再被判定为 static 并触发冲突告警；
- ``pull-back`` 与 ``zoom`` 同属 dolly 族，不产生关键词冲突；
- 跨族运镜（pan 与 zoom）仍如实告警。
"""

import logging

from penshot.neopen.agent.prompt_converter.camera_builder import (
    build_camera_control,
    check_motion_consistency,
    detect_motion_from_text,
    repair_motion_conflict,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    CameraMotion,
)


def _warnings(caplog) -> str:
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


def test_follow_phrase_detected_as_dolly_family():
    """镜头跟随属于 dolly 族，不再被误判为 static"""
    motion, keyword = detect_motion_from_text("镜头跟随主角穿过走廊")

    assert motion == CameraMotion.DOLLY
    assert keyword == "镜头跟随"


def test_follow_phrase_does_not_trigger_static_conflict(caplog):
    """镜头跟随已入运镜词表，构镜时不得再报 static 冲突"""
    caplog.set_level(logging.WARNING, logger="PenShot")

    camera = build_camera_control("镜头跟随主角穿过走廊")

    assert camera.motion == CameraMotion.DOLLY
    assert "运镜判定为 static" not in _warnings(caplog)


def test_english_follow_phrases_detected():
    """camera follow / camera track / camera pull 归入 dolly 族"""
    for text in (
        "camera follow the runner down the alley",
        "camera track beside the car",
        "camera pull back from the window",
    ):
        motion, keyword = detect_motion_from_text(text)
        assert motion == CameraMotion.DOLLY, (text, motion, keyword)


def test_same_family_motions_do_not_warn(caplog):
    """pull-back 与 zoom 同属 dolly 族，不产生关键词冲突"""
    caplog.set_level(logging.WARNING, logger="PenShot")

    camera = build_camera_control("slow pull-back then zoom in on her face")

    assert camera.motion in {CameraMotion.DOLLY, CameraMotion.ZOOM}
    assert "运镜关键词冲突" not in _warnings(caplog)


def test_cross_family_motions_still_warn(caplog):
    """跨族运镜仍需如实告警，规则收紧不得吞掉真实冲突"""
    caplog.set_level(logging.WARNING, logger="PenShot")

    build_camera_control("pan left then zoom in on the door")

    assert "运镜关键词冲突" in _warnings(caplog)


def test_static_motion_with_follow_text_is_consistency_warning():
    """结构化为 static 但提示词写跟随，反向校验仍应告警"""
    result = check_motion_consistency("镜头跟随主角", CameraMotion.STATIC)

    assert result is not None
    level, message = result
    assert level == "warning"
    assert "镜头跟随" in message


def test_repair_motion_conflict_follows_follow_phrase():
    """运镜冲突修复按提示词具体短语收敛到 dolly"""
    repaired = repair_motion_conflict("镜头跟随主角", CameraMotion.STATIC)

    assert repaired is not None
    motion, detail = repaired
    assert motion == CameraMotion.DOLLY
    assert "镜头跟随" in detail