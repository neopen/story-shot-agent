"""P0-2 修复结果核算：零修复必须显式暴露，运镜冲突按具体短语收敛。

覆盖：``record_repair_outcome`` 的四种状态、零动作时人工项落盘，
以及 ``repair_motion_conflict`` 对可判定冲突的确定性修复。
"""

from types import SimpleNamespace

from penshot.neopen.agent.prompt_converter.camera_builder import (
    repair_motion_conflict,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    CameraMotion,
)
from penshot.neopen.agent.repair_outcome import (
    REPAIR_STATUS_NO_ACTION,
    REPAIR_STATUS_NO_ISSUES,
    REPAIR_STATUS_PARTIAL,
    REPAIR_STATUS_REPAIRED,
    record_repair_outcome,
)


def _issue(code: str, fragment_id: str = "frag_001") -> SimpleNamespace:
    return SimpleNamespace(
        issue_code=code,
        fragment_id=fragment_id,
        issue_type=SimpleNamespace(value="format"),
        suggestion="请人工补齐",
    )


def test_zero_actions_with_issues_marks_no_action_and_manual_items():
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("prompt_empty"), _issue("style_missing")],
        [],
        auto_codes={"prompt_empty"},
    )

    assert status == REPAIR_STATUS_NO_ACTION
    assert metadata["repair_status"] == REPAIR_STATUS_NO_ACTION
    manual = metadata["requires_manual_fix"]
    assert len(manual) == 2
    assert {item["issue_code"] for item in manual} == {"prompt_empty", "style_missing"}


def test_actions_with_full_coverage_marks_repaired():
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("prompt_empty")],
        ["补齐空提示词"],
        auto_codes={"prompt_empty"},
    )

    assert status == REPAIR_STATUS_REPAIRED
    assert "requires_manual_fix" not in metadata


def test_actions_with_uncovered_issue_marks_partial_and_keeps_manual_item():
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("prompt_empty"), _issue("character_outfit_missing")],
        ["补齐空提示词"],
        auto_codes={"prompt_empty"},
    )

    assert status == REPAIR_STATUS_PARTIAL
    manual = metadata["requires_manual_fix"]
    assert [item["issue_code"] for item in manual] == ["character_outfit_missing"]


def test_no_issues_marks_no_issues():
    metadata = {}

    status = record_repair_outcome(metadata, "剧本解析", [], [])

    assert status == REPAIR_STATUS_NO_ISSUES
    assert metadata["repair_status"] == REPAIR_STATUS_NO_ISSUES
    assert "requires_manual_fix" not in metadata


def test_manual_issues_override_auto_coverage():
    """命中自动集合但实际无法修复的问题必须转为人工处理"""
    metadata = {}
    unresolved = _issue("camera_motion_prompt_mismatch", "frag_002")

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("prompt_empty"), unresolved],
        ["frag_002 补齐空提示词"],
        auto_codes={"prompt_empty", "camera_motion_prompt_mismatch"},
        manual_issues=[unresolved],
    )

    assert status == REPAIR_STATUS_PARTIAL
    manual = metadata["requires_manual_fix"]
    assert len(manual) == 1
    assert manual[0]["issue_code"] == "camera_motion_prompt_mismatch"
    assert manual[0]["fragment_id"] == "frag_002"


def test_motion_conflict_follows_specific_prompt_phrase():
    """结构化运镜为 static 但提示词明确写摇镜时，取提示词的具体短语"""
    repaired = repair_motion_conflict(
        "static camera, the camera slowly pans across the room",
        CameraMotion.STATIC,
    )

    assert repaired is not None
    motion, detail = repaired
    assert motion == CameraMotion.PAN
    assert "pan" in detail


def test_motion_conflict_follows_static_prompt_marker():
    """结构化运镜为变焦但提示词写死固定机位时，收敛为 static"""
    repaired = repair_motion_conflict(
        "locked-off shot of an empty corridor",
        CameraMotion.ZOOM,
    )

    assert repaired is not None
    motion, detail = repaired
    assert motion == CameraMotion.STATIC
    assert "static" in detail


def test_motion_conflict_no_action_when_families_match():
    """推镜与变焦同属一族，不构成冲突，不产生修复动作"""
    assert (
        repair_motion_conflict("slow zoom in on her face", CameraMotion.DOLLY) is None
    )
