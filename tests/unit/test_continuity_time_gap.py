"""连续性 time_gap 修复链路回归测试。

覆盖：连续性问题码到分割器问题码的映射、分割器时间重排，以及
连续性检查节点的枚举引用。
"""

from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import (
    ContinuityRepairGenerator,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityRepairParams,
)
from penshot.neopen.agent.video_splitter.llm_video_splitter import LLMVideoSplitter
from penshot.neopen.agent.video_splitter.video_splitter_models import VideoFragment
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes


def _time_gap_issue() -> ContinuityIssue:
    """构造时间间隙问题"""
    return ContinuityIssue(
        id="time_gap_0001",
        type=ContinuityIssueType.TIME_GAP,
        description="片段间存在时间间隙: 0.20秒 (frag_001 -> frag_002)",
        severity=ContinuitySeverity.MAJOR,
        fragment_id="frag_001",
        suggestion="修复时间连续性，确保片段首尾相接",
        source_stage=PipelineNode.SPLIT_VIDEO,
    )


def test_time_gap_issue_maps_to_splitter_code():
    params = ContinuityRepairGenerator().generate_repair_params(
        [_time_gap_issue()], PipelineNode.SPLIT_VIDEO
    )

    assert params.issue_types == ["fragment_time_gap"]
    assert params.fix_needed is True
    assert "frag_001" in params.suggestions


def test_splitter_reflows_timeline_for_time_gap_repair():
    fragments = [
        VideoFragment(id="frag_001", shot_id="shot_001", start_time=0.0, duration=2.0),
        VideoFragment(id="frag_002", shot_id="shot_001", start_time=2.2, duration=2.0),
        VideoFragment(id="frag_003", shot_id="shot_002", start_time=4.4, duration=2.0),
    ]
    splitter = object.__new__(LLMVideoSplitter)
    splitter.current_repair_params = QualityRepairParams(
        fix_needed=True,
        issue_count=1,
        issue_types=["time_gap"],
    )

    repaired = splitter._apply_repair_params(fragments, None)

    expected_start = 0.0
    for fragment in repaired:
        assert fragment.start_time == expected_start
        expected_start += fragment.duration
    # 相邻片段首尾相接，无时间间隙
    assert repaired[1].start_time == repaired[0].start_time + repaired[0].duration


def test_clamp_rebuilds_timeline_without_gap():
    fragments = [
        VideoFragment(id="frag_001", shot_id="shot_001", start_time=0.0, duration=5.2),
        VideoFragment(id="frag_002", shot_id="shot_002", start_time=5.2, duration=2.0),
    ]
    nodes = object.__new__(WorkflowNodes)

    assert nodes._clamp_fragments_timeline(fragments, 5.0) is True
    assert fragments[0].duration == 5.0
    # 截断 0.2 秒后重建时间轴，避免产生 0.20 秒间隙
    assert fragments[1].start_time == 5.0


def test_clamp_keeps_timeline_when_no_adjustment():
    fragments = [
        VideoFragment(id="frag_001", shot_id="shot_001", start_time=0.0, duration=2.0),
        VideoFragment(id="frag_002", shot_id="shot_001", start_time=2.4, duration=2.0),
    ]
    nodes = object.__new__(WorkflowNodes)

    assert nodes._clamp_fragments_timeline(fragments, 5.0) is False
    # 未发生截断时不主动改写已有时间轴
    assert fragments[1].start_time == 2.4


def test_continuity_check_node_enum_exists():
    assert PipelineNode.CONTINUITY_CHECK.value == "continuity_check"
