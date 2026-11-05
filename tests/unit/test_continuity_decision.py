"""连续性决策回归测试。

覆盖 ``decide_after_continuity`` 从 ``DomainState.continuity_issues`` 读取结果、
按来源阶段动态路由、以及重试耗尽/轻微问题的兜底决策。
"""

from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _state() -> WorkflowState:
    """构造最小工作流状态"""
    return WorkflowState.from_raw_script("测试剧本内容")


def _issue(severity: ContinuitySeverity) -> ContinuityIssue:
    """构造连续性问题"""
    return ContinuityIssue(
        id="issue_001",
        type=ContinuityIssueType.STYLE_INCONSISTENT,
        description="片段风格不一致",
        fragment_id="frag_001",
        severity=severity,
    )


class TestDecideAfterContinuity:
    """连续性检查后的决策"""

    def test_routes_to_source_stage_when_repair_ready(self):
        """节点已准备修复参数时，按 current_node 返回来源阶段节点名"""
        decision = PipelineDecision()
        state = _state()
        state.domain.continuity_issues = [_issue(ContinuitySeverity.MODERATE)]
        state.domain.needs_continuity_repair = True
        state.domain.continuity_retry_count = 1
        state.execution.current_node = PipelineNode.SEGMENT_SHOT

        result = decision.decide_after_continuity(state)

        assert result == PipelineNode.SEGMENT_SHOT.value

    def test_no_issues_returns_success_and_resets_retry(self):
        """无连续性问题时返回 SUCCESS 并重置重试计数"""
        decision = PipelineDecision()
        state = _state()
        state.domain.continuity_retry_count = 2
        state.execution.stage_current_retries[PipelineNode.CONTINUITY_CHECK] = 2

        result = decision.decide_after_continuity(state)

        assert result == PipelineState.SUCCESS
        assert state.domain.continuity_retry_count == 0
        assert state.execution.stage_current_retries[PipelineNode.CONTINUITY_CHECK] == 0

    def test_retry_exhausted_returns_needs_human(self):
        """修复重试耗尽且仍有严重问题时转人工干预"""
        decision = PipelineDecision()
        state = _state()
        state.domain.continuity_issues = [_issue(ContinuitySeverity.CRITICAL)]
        state.domain.continuity_retry_count = 3
        state.domain.max_continuity_retries = 3
        state.domain.needs_continuity_repair = False

        result = decision.decide_after_continuity(state)

        assert result == PipelineState.NEEDS_HUMAN

    def test_minor_issue_without_repair_returns_valid(self):
        """仅轻微问题且未准备修复时，允许继续执行"""
        decision = PipelineDecision()
        state = _state()
        state.domain.continuity_issues = [_issue(ContinuitySeverity.MINOR)]
        state.domain.continuity_retry_count = 1
        state.domain.needs_continuity_repair = False

        result = decision.decide_after_continuity(state)

        assert result == PipelineState.VALID

    def test_repair_flag_without_target_falls_back(self):
        """需要修复但未选定有效阶段时按严重性兜底"""
        decision = PipelineDecision()
        state = _state()
        state.domain.continuity_issues = [_issue(ContinuitySeverity.MODERATE)]
        state.domain.needs_continuity_repair = True
        state.domain.continuity_retry_count = 1
        state.execution.current_node = PipelineNode.CONTINUITY_CHECK

        result = decision.decide_after_continuity(state)

        assert result == PipelineState.NEEDS_HUMAN
