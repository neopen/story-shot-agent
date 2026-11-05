"""M0.4.1 连续性修复回路验收测试。

在真实 LangGraph 编排下串联「连续性检查 -> 修复来源阶段 -> 再检查 -> 输出报告」，
并验证 continuity_report.json / repair_history.json 确实落盘且内容完整。
"""

import json

from langgraph.graph import END

from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import (
    ContinuityRepairGenerator,
)
from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_orchestrator import WorkflowOrchestrator
from penshot.neopen.agent.workflow.workflow_output import WorkflowOutputWriter
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.tools.result_storage_tool import ResultStorage


class _SequencedChecker:
    """按调用顺序返回预设结果的连续性检查器"""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def check_all_continuity(self, context):
        """返回当前轮次对应的结果"""
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[index]


class _FakeMemory:
    """满足输出写入器读取接口的最小记忆对象"""

    def get(self, key, level=None, default=None):
        """报告中的记忆键统一返回默认值"""
        return default

    def get_stats(self, script_id=None):
        """返回空记忆统计"""
        return {"short_term": {}, "medium_term": {}, "long_term": {}}


def _issue() -> ContinuityIssue:
    """构造提示词阶段的连续性问题"""
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


def _build_nodes() -> WorkflowNodes:
    """构造仅依赖连续性检查所需属性的节点集合"""
    nodes = object.__new__(WorkflowNodes)
    nodes.checker = _SequencedChecker([_failed_result(), ContinuityCheckResult()])
    nodes.generator = ContinuityRepairGenerator()
    nodes.knowledge_manager = None
    nodes.task_manager = None
    return nodes


def _build_graph(nodes: WorkflowNodes, writer: WorkflowOutputWriter):
    """构建最小可执行的连续性修复回路图"""
    attempts = {"repair": 0}
    futures = []

    def parse_script_node(state: WorkflowState) -> WorkflowState:
        """入口占位节点"""
        return state

    def convert_prompt_node(state: WorkflowState) -> WorkflowState:
        """模拟提示词阶段消费修复参数"""
        params = state.domain.repair_params.get(PipelineNode.CONVERT_PROMPT)
        assert params is not None and params.fix_needed is True
        attempts["repair"] += 1
        return state

    def generate_output_node(state: WorkflowState) -> WorkflowState:
        """生成输出报告，并模拟生产代码清理连续性问题"""
        future = writer.save_all_reports(state)
        futures.append(future)
        # 与 generate_output_node 一致：报告快照生成后清空当前问题
        state.domain.continuity_issues = []
        return state

    orchestrator = WorkflowOrchestrator()
    orchestrator.add_node(PipelineNode.PARSE_SCRIPT.value, parse_script_node)
    orchestrator.add_node(
        PipelineNode.CONTINUITY_CHECK.value, nodes.continuity_check_node
    )
    orchestrator.add_node(PipelineNode.CONVERT_PROMPT.value, convert_prompt_node)
    orchestrator.add_node(PipelineNode.GENERATE_OUTPUT.value, generate_output_node)

    orchestrator.add_edge(
        PipelineNode.PARSE_SCRIPT.value, PipelineNode.CONTINUITY_CHECK.value
    )
    orchestrator.add_edge(
        PipelineNode.CONVERT_PROMPT.value, PipelineNode.CONTINUITY_CHECK.value
    )
    orchestrator.add_edge(PipelineNode.GENERATE_OUTPUT.value, END)

    orchestrator.add_conditional_edge(
        PipelineNode.CONTINUITY_CHECK.value,
        PipelineDecision().decide_after_continuity,
        {
            PipelineState.SUCCESS: PipelineNode.GENERATE_OUTPUT.value,
            PipelineState.VALID: PipelineNode.GENERATE_OUTPUT.value,
            PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT.value,
            PipelineNode.PARSE_SCRIPT.value: PipelineNode.PARSE_SCRIPT.value,
            PipelineNode.CONVERT_PROMPT.value: PipelineNode.CONVERT_PROMPT.value,
        },
    )
    orchestrator.build()
    return orchestrator, attempts, futures


def test_continuity_repair_loop_writes_reports(tmp_path):
    """连续性修复回路可回到来源阶段，并向磁盘写入完整报告"""
    nodes = _build_nodes()
    storage = ResultStorage(str(tmp_path))
    writer = WorkflowOutputWriter(storage, _FakeMemory())
    orchestrator, attempts, futures = _build_graph(nodes, writer)

    state = WorkflowState.from_raw_script("测试剧本：角色在雨中等候")
    state.domain.max_continuity_retries = 2
    result = orchestrator.run(state)

    final_state = result if hasattr(result, "domain") else state
    assert attempts["repair"] == 1, "修复参数应驱动提示词阶段重新执行一次"
    assert final_state.domain.continuity_passed is True
    assert len(final_state.domain.continuity_rounds) == 2
    assert final_state.domain.continuity_rounds[0]["phase"] == "needs_repair"
    assert final_state.domain.continuity_rounds[1]["phase"] == "passed"

    for future in futures:
        assert future is not None
        future.result(timeout=30)
    writer.shutdown()

    continuity_path = storage.get_result_path(
        state.input.script_id, state.input.task_id, "continuity_report.json"
    )
    with open(continuity_path, "r", encoding="utf-8") as f:
        continuity_report = json.load(f)

    assert continuity_report["final_status"] == "passed_after_repair"
    assert continuity_report["round_count"] == 2
    assert continuity_report["comparison"]["initial_issue_count"] == 1
    assert continuity_report["comparison"]["final_issue_count"] == 0
    assert continuity_report["comparison"]["resolved_issue_count"] == 1
    assert continuity_report["detected_issue_count"] == 1
    assert continuity_report["detected_issues_by_type"] == {"style_inconsistent": 1}
    assert continuity_report["repair_count"] == 1
    assert continuity_report["repairs"][0]["stage"] == "convert_prompt"
    assert continuity_report["issues"] == []

    repair_path = storage.get_result_path(
        state.input.script_id, state.input.task_id, "repair_history.json"
    )
    with open(repair_path, "r", encoding="utf-8") as f:
        repair_history = json.load(f)

    assert repair_history["repair_count"] == 1
    assert repair_history["repairs"]["convert_prompt"]["count"] == 1
    assert repair_history["repairs"]["convert_prompt"]["actions"][0]["round"] == 1
