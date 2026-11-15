"""P0-3 质量门标记：below_threshold 放行但必须留下可见标记。

覆盖：审计节点写入 ``quality_gate``（blocking=False）；生成输出节点把质量门、
人工处理项与阻断片段写入最终输出的顶层 ``warnings`` 和 ``metadata``。
"""

from types import SimpleNamespace

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    AuditStatus,
    QualityAuditReport,
)
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.prompts.ingestion_policy import REASON_BELOW_THRESHOLD


def _instructions() -> AIVideoInstructions:
    return AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="close-up of a woman by the cafe window at dusk",
                duration=3.0,
            )
        ]
    )


def _report(
    score: float,
    status: AuditStatus = AuditStatus.MINOR_ISSUES,
) -> QualityAuditReport:
    report = QualityAuditReport(status=status, score=score, violations=[])
    report.detection_score = score
    report.post_repair_score = score
    return report


def _nodes(report: QualityAuditReport):
    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.workflow_memory = SimpleNamespace(
        get_memory_list=lambda *args, **kwargs: [],
        store_short_term_memory=lambda *args, **kwargs: None,
    )
    nodes.quality_auditor = SimpleNamespace(qa_process=lambda *args, **kwargs: report)
    nodes.knowledge_manager = SimpleNamespace(
        count_active_templates=lambda script_id=None: 1,
        save_successful_prompt=lambda **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    nodes.prompt_converter = None
    return nodes


def _state() -> WorkflowState:
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_P0"
    state.input.task_id = "TSK_P0"
    state.domain.instructions = _instructions()
    return state


def test_below_threshold_writes_quality_gate_metadata():
    """below_threshold 放行时写入 quality_gate，blocking=False"""
    state = _state()
    report = _report(85.0)
    nodes = _nodes(report)

    nodes.quality_audit_node(state)

    gate = report.metadata["quality_gate"]
    assert gate["status"] == REASON_BELOW_THRESHOLD
    assert gate["score"] == 85.0
    assert gate["blocking"] is False
    assert gate["ingestion_allowed"] is False


def test_generate_output_writes_gate_and_manual_warnings():
    """最终输出顶层 warnings 覆盖质量门、人工项与阻断片段"""
    state = _state()
    state.domain.instructions.metadata["requires_manual_fix"] = [
        {
            "stage": "提示词转换",
            "issue_code": "character_outfit_missing",
            "fragment_id": "frag_001",
            "reason": "角色服装信息缺失",
        }
    ]
    state.domain.instructions.route_plan = {"blocked_fragments": ["frag_004"]}
    state.domain.audit_report = QualityAuditReport(
        metadata={
            "quality_gate": {
                "status": REASON_BELOW_THRESHOLD,
                "score": 85.0,
                "blocking": False,
                "ingestion_allowed": False,
            }
        }
    )

    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.output_writer = SimpleNamespace(save_all_reports=lambda state: None)
    nodes._memory = SimpleNamespace(clear_script=lambda *args, **kwargs: None)
    for agent in (
        "script_parser",
        "shot_segmenter",
        "video_splitter",
        "prompt_converter",
    ):
        setattr(
            nodes,
            agent,
            SimpleNamespace(clear_all_state=lambda: None),
        )

    nodes.generate_output_node(state)

    output = state.output.final_output
    assert output["metadata"]["quality_gate"]["status"] == REASON_BELOW_THRESHOLD
    types = {warning.get("type") for warning in output["warnings"]}
    assert {"quality_gate", "blocked_fragment"} <= types
    manual = [
        warning
        for warning in output["warnings"]
        if warning.get("issue_code") == "character_outfit_missing"
    ]
    assert manual
    gate_warning = next(
        warning
        for warning in output["warnings"]
        if warning.get("type") == "quality_gate"
    )
    assert gate_warning["reason"] == "本结果未达入库标准，仅供预览"
    assert output["status"] == "completed"
