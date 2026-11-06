"""人工干预决策回归测试。

覆盖人工选择 ABORT 后被循环计数误判为 FAILED、错误处理器超限后
默认回到剧本解析导致无限重启的问题。
"""

from langgraph.graph import END

from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _state() -> WorkflowState:
    """构造最小工作流状态"""
    return WorkflowState.from_raw_script("测试剧本内容")


class TestHumanInterventionDecision:
    """人工干预后的决策"""

    def test_abort_is_honored_even_if_loop_count_exceeded(self):
        """人工选择 ABORT 时，不应被人工节点循环计数覆盖为 FAILED"""
        decision = PipelineDecision()
        state = _state()
        state.execution.human_feedback = {"decision": "ABORT"}
        state.execution.node_current_loops[PipelineNode.HUMAN_INTERVENTION] = 10

        result = decision.decide_after_human(state)

        assert result == PipelineState.ABORT
        assert state.execution.should_abort is True
        assert state.execution.recovery_flags["should_abort"] is True

    def test_repeated_abort_stays_terminal(self):
        """重复选择 ABORT 时仍应返回中止，而不是再次转人工"""
        decision = PipelineDecision()
        state = _state()
        state.execution.human_feedback = {"decision": "ABORT"}

        first = decision.decide_after_human(state)
        second = decision.decide_after_human(state)

        assert first == PipelineState.ABORT
        assert second == PipelineState.ABORT

    def test_first_continue_is_not_treated_as_loop_exceeded(self):
        """首次选择 CONTINUE 不应因 HUMAN_INTERVENTION 上限被误判超限"""
        decision = PipelineDecision()
        state = _state()
        state.execution.human_feedback = {"decision": "CONTINUE"}

        result = decision.decide_after_human(state)

        assert result == PipelineState.SUCCESS

    def test_error_handler_exhausted_ends_workflow(self):
        """错误处理器循环超限后应终止流程，不能回到剧本解析"""
        decision = PipelineDecision()
        state = _state()
        state.execution.node_current_loops[PipelineNode.ERROR_HANDLER] = 5
        state.errors.error_messages = ["剧本解析节点循环检查失败"]

        result = decision.decide_next_after_error(state)

        assert result == END

    def test_abort_flag_takes_priority_over_retry_limit(self):
        """已标记中止时，即使总重试耗尽也应返回 ABORT"""
        decision = PipelineDecision()
        state = _state()
        state.execution.total_retries = 100
        state.execution.recovery_flags["should_abort"] = True

        result = decision.decide_after_error(state)

        assert result == PipelineState.ABORT
