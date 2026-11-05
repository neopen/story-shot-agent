"""连续性检查节点记录测试。

验证节点把每轮检查与修复动作写入 State，并可供报告直接消费。
"""

from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import (
    ContinuityRepairGenerator,
)
from penshot.neopen.agent.continuity_guardian.continuity_report import (
    build_continuity_report,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


class _FakeChecker:
    """固定返回指定检查结果的连续性检查器"""

    def __init__(self, result: ContinuityCheckResult):
        self.result = result

    def check_all_continuity(self, context):
        """忽略上下文，返回预设结果"""
        return self.result


def _nodes(result: ContinuityCheckResult) -> WorkflowNodes:
    """构造只依赖连续性检查所需属性节点实例"""
    nodes = object.__new__(WorkflowNodes)
    nodes.checker = _FakeChecker(result)
    nodes.generator = ContinuityRepairGenerator()
    nodes.knowledge_manager = None
    nodes.task_manager = None
    return nodes


def _issue() -> ContinuityIssue:
    """构造可定位到提示词阶段的问题"""
    return ContinuityIssue(
        id="style_inconsistent_1",
        type=ContinuityIssueType.STYLE_INCONSISTENT,
        description="片段风格与全局契约不一致",
        severity=ContinuitySeverity.MODERATE,
        fragment_id="frag_001",
        shot_id="shot_001",
        source_stage=PipelineNode.CONVERT_PROMPT,
    )


def _failed_result() -> ContinuityCheckResult:
    """构造包含一个问题的检查结果"""
    result = ContinuityCheckResult()
    result.add_issue(_issue())
    return result


def test_continuity_node_records_passed_round():
    """检查通过时记录一条 passed 轮次"""
    nodes = _nodes(ContinuityCheckResult())
    state = WorkflowState.from_raw_script("测试剧本")

    nodes.continuity_check_node(state)

    assert state.domain.continuity_passed is True
    assert len(state.domain.continuity_rounds) == 1
    assert state.domain.continuity_rounds[0]["phase"] == "passed"
    assert state.domain.continuity_rounds[0]["total_issues"] == 0


def test_continuity_node_records_repair_round():
    """发现问题时记录修复轮次、修复动作并路由到来源阶段"""
    nodes = _nodes(_failed_result())
    state = WorkflowState.from_raw_script("测试剧本")

    nodes.continuity_check_node(state)

    record = state.domain.continuity_rounds[-1]
    assert record["phase"] == "needs_repair"
    assert record["issues_by_stage"] == {"convert_prompt": 1}
    assert record["repair_stages"] == ["convert_prompt"]
    assert record["repairs"][0]["stage"] == "convert_prompt"
    assert state.domain.continuity_retry_count == 1
    assert state.domain.needs_continuity_repair is True
    assert state.execution.current_node == PipelineNode.CONVERT_PROMPT
    assert state.domain.repair_params[PipelineNode.CONVERT_PROMPT].fix_needed is True


def test_continuity_node_records_retry_exhausted_round():
    """重试耗尽时记录 exhausted 轮次并转人工"""
    nodes = _nodes(_failed_result())
    state = WorkflowState.from_raw_script("测试剧本")
    state.domain.continuity_retry_count = 3
    state.domain.max_continuity_retries = 3

    nodes.continuity_check_node(state)

    record = state.domain.continuity_rounds[-1]
    assert record["phase"] == "retry_exhausted"
    assert record["retry_count"] == 3
    assert state.execution.needs_human_review is True


def test_report_uses_state_rounds_after_repair_pass():
    """修复后通过时，报告可从 State 轮次得到通过结论"""
    nodes = _nodes(_failed_result())
    state = WorkflowState.from_raw_script("测试剧本")

    nodes.continuity_check_node(state)
    nodes.checker = _FakeChecker(ContinuityCheckResult())
    nodes.continuity_check_node(state)

    report = build_continuity_report(
        task_id=state.input.task_id,
        script_id=state.input.script_id,
        rounds=state.domain.continuity_rounds,
        current_issues=state.domain.continuity_issues,
        repair_params=state.domain.repair_params,
        continuity_passed=state.domain.continuity_passed,
        retry_count=state.domain.continuity_retry_count,
        max_retries=state.domain.max_continuity_retries,
    )

    assert report["final_status"] == "passed_after_repair"
    assert report["comparison"]["initial_issue_count"] == 1
    assert report["comparison"]["final_issue_count"] == 0
    assert report["repair_count"] == 1
