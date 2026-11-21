"""工作流输出报告一致性测试。

验证质量修复汇总能被 repair_history 正确消费。
"""

from types import SimpleNamespace

from penshot.neopen.agent.workflow.workflow_output import WorkflowOutputWriter
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def test_quality_repair_summary_from_audit_report():
    """审计报告中的修复统计可转换为修复历史条目"""
    state = WorkflowState.from_raw_script("测试剧本")
    state.domain.audit_report = SimpleNamespace(
        metadata={
            "repair_issue_count": 2,
            "repair_action_count": 2,
            "repair_status": "repaired",
            "stage_repair_statuses": ["repaired", "repaired"],
        },
        detection_score=90.0,
        post_repair_score=100.0,
    )

    summary = WorkflowOutputWriter._build_quality_repair_summary(state)

    assert summary == {
        "issue_count": 2,
        "action_count": 2,
        "status": "repaired",
        "stage_statuses": ["repaired", "repaired"],
        "detection_score": 90.0,
        "post_repair_score": 100.0,
    }


def test_quality_repair_summary_absent_without_repair():
    """没有修复动作时不输出质量修复条目"""
    state = WorkflowState.from_raw_script("测试剧本")
    state.domain.audit_report = SimpleNamespace(
        metadata={},
        detection_score=100.0,
        post_repair_score=100.0,
    )

    assert WorkflowOutputWriter._build_quality_repair_summary(state) is None
