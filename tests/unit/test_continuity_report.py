"""连续性检查报告单元测试。

覆盖问题结构化、单轮记录、修复前后对比与修复历史聚合。
"""

from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.continuity_guardian.continuity_report import (
    build_continuity_report,
    build_repair_entries,
    build_repair_history,
    build_round_record,
    issue_to_dict,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityRepairParams,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode


def _issue(
    issue_type: ContinuityIssueType = ContinuityIssueType.STYLE_INCONSISTENT,
    severity: ContinuitySeverity = ContinuitySeverity.MODERATE,
    fragment_id: str = "frag_001",
) -> ContinuityIssue:
    """构造连续性问题"""
    return ContinuityIssue(
        id=f"{issue_type.value}_{fragment_id}",
        type=issue_type,
        description="角色外观在片段中发生变化",
        severity=severity,
        fragment_id=fragment_id,
        shot_id="shot_001",
        source_stage=PipelineNode.CONVERT_PROMPT,
    )


def _result(issues) -> ContinuityCheckResult:
    """构造连续性检查结果"""
    result = ContinuityCheckResult()
    for issue in issues:
        result.add_issue(issue)
    return result


def _repair_params() -> QualityRepairParams:
    """构造修复参数"""
    return QualityRepairParams(
        fix_needed=True,
        issue_count=1,
        issue_types=["style_inconsistent"],
        fragments=["frag_001"],
        suggestions={"frag_001": ["统一风格契约锚点"]},
        severity_summary={"moderate": 1},
    )


def test_issue_to_dict_serializes_enums():
    """问题结构化为可 JSON 序列化的字典"""
    data = issue_to_dict(_issue())

    assert data["type"] == "style_inconsistent"
    assert data["severity"] == "moderate"
    assert data["fragment_id"] == "frag_001"
    assert data["source_stage"] == "convert_prompt"
    assert data["description"] == "角色外观在片段中发生变化"


def test_build_round_record_counts_and_contract():
    """单轮记录包含问题统计、来源阶段与契约违规摘要"""
    result = _result([_issue()])
    violations = [
        {
            "type": "unknown_character",
            "stage": "segment_shot",
            "shot_id": "shot_002",
            "character": "小红",
        }
    ]

    record = build_round_record(
        result,
        round_index=1,
        retry_count=0,
        max_retries=3,
        phase="needs_repair",
        issues_by_stage={"convert_prompt": 1},
        repair_stages=["convert_prompt"],
        contract_violations=violations,
    )

    assert record["phase"] == "needs_repair"
    assert record["total_issues"] == 1
    assert record["issues_by_type"] == {"style_inconsistent": 1}
    assert record["issues_by_stage"] == {"convert_prompt": 1}
    assert record["contract_violations"]["total"] == 1
    assert record["contract_violations"]["by_stage"] == {"segment_shot": 1}
    assert record["issues"][0]["fragment_id"] == "frag_001"


def test_report_passed_after_repair():
    """修复后通过时报告包含前后对比与修复动作"""
    failed_round = build_round_record(
        _result([_issue()]),
        round_index=1,
        retry_count=0,
        max_retries=3,
        phase="needs_repair",
        issues_by_stage={"convert_prompt": 1},
        repairs=build_repair_entries({PipelineNode.CONVERT_PROMPT: _repair_params()}),
        repair_stages=["convert_prompt"],
    )
    passed_round = build_round_record(
        _result([]),
        round_index=2,
        retry_count=1,
        max_retries=3,
        phase="passed",
    )

    report = build_continuity_report(
        task_id="task_1",
        script_id="script_1",
        rounds=[failed_round, passed_round],
        current_issues=[],
        repair_params={PipelineNode.CONVERT_PROMPT: _repair_params()},
        continuity_passed=True,
        retry_count=0,
        max_retries=3,
    )

    assert report["final_status"] == "passed_after_repair"
    assert report["passed"] is True
    assert report["round_count"] == 2
    assert report["comparison"]["initial_issue_count"] == 1
    assert report["comparison"]["final_issue_count"] == 0
    assert report["comparison"]["resolved_issue_count"] == 1
    assert report["comparison"]["issue_count_trend"] == [1, 0]
    assert report["comparison"]["resolved_types"] == ["style_inconsistent"]
    assert report["detected_issue_count"] == 1
    assert report["detected_issues_by_type"] == {"style_inconsistent": 1}
    assert report["remaining_issues_by_type"] == {}
    assert report["repair_count"] == 1
    assert report["repairs"][0]["stage"] == "convert_prompt"
    assert report["repairs"][0]["round"] == 1
    assert report["continuity_retry_count"] == 1


def test_report_retry_exhausted_needs_human():
    """重试耗尽时最终状态为需人工处理"""
    failed_round = build_round_record(
        _result([_issue(severity=ContinuitySeverity.MAJOR)]),
        round_index=4,
        retry_count=3,
        max_retries=3,
        phase="retry_exhausted",
        issues_by_stage={"convert_prompt": 1},
    )

    report = build_continuity_report(
        task_id="task_1",
        script_id="script_1",
        rounds=[failed_round],
        current_issues=[_issue()],
        continuity_passed=False,
        retry_count=3,
        max_retries=3,
    )

    assert report["final_status"] == "needs_human_review"
    assert report["passed"] is False
    assert report["total_continuity_issues"] == 1
    assert report["issues_by_severity"] == {"moderate": 1}
    assert report["comparison"]["final_issue_count"] == 1


def test_repair_history_groups_actions_by_stage():
    """修复历史按阶段聚合修复动作"""
    failed_round = build_round_record(
        _result([_issue()]),
        round_index=1,
        retry_count=0,
        max_retries=3,
        phase="needs_repair",
        repairs=build_repair_entries({PipelineNode.CONVERT_PROMPT: _repair_params()}),
    )

    history = build_repair_history(
        task_id="task_1",
        script_id="script_1",
        rounds=[failed_round],
        repair_params={PipelineNode.CONVERT_PROMPT: _repair_params()},
    )

    assert history["repair_count"] == 1
    assert history["repairs"]["convert_prompt"]["count"] == 1
    assert history["repairs"]["convert_prompt"]["actions"][0]["round"] == 1
    assert history["repairs"]["convert_prompt"]["latest_params"]["issue_count"] == 1
    assert history["summary"]["stages"] == ["convert_prompt"]
