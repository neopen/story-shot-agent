"""P0-2 审计节点接线：零修复必须显式标记，分数不得凭空上升。

覆盖：审计节点零修复时写 ``repair_status=no_action_taken`` 且 post 分不得高于
检测分；有真实修复动作时按规则复检给出 ``post_repair_score`` 并标注口径。
"""

from types import SimpleNamespace

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    AuditStatus,
    BasicViolation,
    IssueType,
    QualityAuditReport,
    QualityRepairParams,
    SeverityLevel,
)
from penshot.neopen.agent.repair_outcome import REPAIR_STATUS_NO_ACTION
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


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
    repair_params=None,
    status: AuditStatus = AuditStatus.MINOR_ISSUES,
) -> QualityAuditReport:
    report = QualityAuditReport(status=status, score=score, violations=[])
    report.detection_score = score
    report.post_repair_score = score
    report.repair_params = repair_params
    return report


def _repair_params(issue_count: int = 2) -> dict:
    return {
        PipelineNode.CONVERT_PROMPT: QualityRepairParams(
            fix_needed=True,
            issue_count=issue_count,
            issue_types=["format"],
            issues=[
                BasicViolation.create(
                    "prompt_empty",
                    IssueType.FORMAT,
                    "提示词为空",
                    severity=SeverityLevel.WARNING,
                    fragment_id="frag_001",
                    source_node=PipelineNode.CONVERT_PROMPT,
                )
            ],
        )
    }


def _nodes(report: QualityAuditReport, prompt_converter=None, recheck_score=None):
    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.workflow_memory = SimpleNamespace(
        get_memory_list=lambda *args, **kwargs: [],
        store_short_term_memory=lambda *args, **kwargs: None,
    )
    nodes.quality_auditor = SimpleNamespace(
        qa_process=lambda *args, **kwargs: report,
        recheck_rule_score=(
            (lambda *args, **kwargs: recheck_score)
            if recheck_score is not None
            else None
        ),
    )
    nodes.knowledge_manager = SimpleNamespace(
        count_active_templates=lambda script_id=None: 1,
        save_successful_prompt=lambda **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    nodes.prompt_converter = prompt_converter
    return nodes


def _state() -> WorkflowState:
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_P0"
    state.input.task_id = "TSK_P0"
    state.domain.instructions = _instructions()
    return state


def test_zero_repair_actions_are_marked_and_score_not_raised():
    """发现问题但零修复时必须标记 no_action_taken，post 分不得高于检测分"""

    def _repair_result(instructions, issues, fragments):
        return instructions

    state = _state()
    report = _report(81.0, _repair_params(issue_count=2))
    nodes = _nodes(
        report,
        prompt_converter=SimpleNamespace(repair_result=_repair_result),
    )

    nodes.quality_audit_node(state)

    assert report.metadata["repair_status"] == REPAIR_STATUS_NO_ACTION
    assert report.metadata["repair_issue_count"] == 2
    assert report.metadata["repair_action_count"] == 0
    assert report.post_repair_score == report.detection_score == 81.0


def test_repair_actions_use_rule_recheck_score():
    """有真实修复动作时按规则复检分列，并标注复检口径"""

    def _repair_result(instructions, issues, fragments):
        instructions.metadata.setdefault("repair_history", []).append(
            {"fixed_issues": 2, "actions": ["补齐空提示词"]}
        )
        return instructions

    state = _state()
    report = _report(81.0, _repair_params(issue_count=2))
    nodes = _nodes(
        report,
        prompt_converter=SimpleNamespace(repair_result=_repair_result),
        recheck_score=95.0,
    )

    nodes.quality_audit_node(state)

    assert report.metadata["repair_action_count"] == 2
    assert report.metadata["repair_status"] == "repaired"
    assert report.metadata["post_repair_score_basis"] == "rule_recheck"
    assert report.post_repair_score == 95.0
