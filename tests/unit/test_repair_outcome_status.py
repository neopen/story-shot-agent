"""T-111 修复状态口径：同轮多次记录不被覆盖，状态与人工项同源。

覆盖：
- 同阶段先后记录 ``no_action_taken`` 与 ``manual_required`` 时保留更严重状态；
- 问题以字典传入时仍能命中自动策略并生成人工项；
- 审计节点聚合时 ``manual_required`` 必须伴随人工项，缺失则从修复参数补全或降级；
- 状态聚合只统计本轮新增记录，历史轮次状态不重复生效。
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
from penshot.neopen.agent.repair_outcome import (
    REPAIR_STATUS_MANUAL,
    REPAIR_STATUS_NO_ACTION,
    REPAIR_STATUS_PARTIAL,
    REPAIR_STATUS_REPAIRED,
    record_repair_outcome,
    select_repair_status,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _issue(code: str, fragment_id: str = "frag_001") -> SimpleNamespace:
    return SimpleNamespace(
        issue_code=code,
        fragment_id=fragment_id,
        issue_type=SimpleNamespace(value="format"),
        suggestion="请人工补齐",
    )


def test_later_manual_record_does_not_override_no_action():
    """同轮先空转后人工时，不能被后者覆盖成 manual_required"""
    metadata = {}

    record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("prompt_empty")],
        [],
        auto_codes={"prompt_empty"},
    )
    record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("character_outfit_missing")],
        [],
        auto_codes={"prompt_empty"},
    )

    assert metadata["repair_status"] == REPAIR_STATUS_NO_ACTION
    assert [entry["status"] for entry in metadata["repair_status_history"]] == [
        REPAIR_STATUS_NO_ACTION,
        REPAIR_STATUS_MANUAL,
    ]
    assert {item["issue_code"] for item in metadata["requires_manual_fix"]} == {
        "prompt_empty",
        "character_outfit_missing",
    }


def test_dict_issue_hits_auto_strategy_and_builds_entry():
    """字典形式的问题也要识别 issue_code，不能退化成人工处理"""
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [{"issue_code": "prompt_empty", "fragment_id": "frag_002"}],
        [],
        auto_codes={"prompt_empty"},
    )

    assert status == REPAIR_STATUS_NO_ACTION
    entry = metadata["requires_manual_fix"][0]
    assert entry["issue_code"] == "prompt_empty"
    assert entry["fragment_id"] == "frag_002"


def test_dict_issue_matches_auto_type_value():
    """字典形式的问题也要识别 issue_type 枚举的 value"""
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "剧本解析",
        [{"issue_type": IssueType.FORMAT, "fragment_id": "frag_003"}],
        [],
        auto_types={IssueType.FORMAT.value},
    )

    assert status == REPAIR_STATUS_NO_ACTION
    assert metadata["requires_manual_fix"][0]["fragment_id"] == "frag_003"


def test_manual_status_always_carries_manual_items():
    """manual_required 必须与人工项同源落盘"""
    metadata = {}

    status = record_repair_outcome(
        metadata,
        "提示词转换",
        [_issue("character_outfit_missing")],
        [],
        auto_codes={"prompt_empty"},
    )

    assert status == REPAIR_STATUS_MANUAL
    assert metadata["requires_manual_fix"]


def test_select_repair_status_follows_priority():
    """聚合优先级：no_action_taken > manual_required > partial > repaired > no_issues"""
    assert (
        select_repair_status([REPAIR_STATUS_REPAIRED, REPAIR_STATUS_PARTIAL])
        == REPAIR_STATUS_PARTIAL
    )
    assert (
        select_repair_status([REPAIR_STATUS_PARTIAL, REPAIR_STATUS_MANUAL])
        == REPAIR_STATUS_MANUAL
    )
    assert (
        select_repair_status([REPAIR_STATUS_MANUAL, REPAIR_STATUS_NO_ACTION])
        == REPAIR_STATUS_NO_ACTION
    )
    assert select_repair_status([]) == ""


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


def _report(repair_params) -> QualityAuditReport:
    report = QualityAuditReport(
        status=AuditStatus.MINOR_ISSUES, score=81.0, violations=[]
    )
    report.detection_score = 81.0
    report.post_repair_score = 81.0
    report.repair_params = repair_params
    return report


def _repair_params(issue_count: int = 1, issues=None) -> dict:
    if issues is None:
        issues = [
            BasicViolation.create(
                "character_outfit_missing",
                IssueType.CHARACTER,
                "角色服装缺失",
                severity=SeverityLevel.WARNING,
                fragment_id="frag_001",
                source_node=PipelineNode.CONVERT_PROMPT,
            )
        ]
    return {
        PipelineNode.CONVERT_PROMPT: QualityRepairParams(
            fix_needed=True,
            issue_count=issue_count,
            issue_codes=["character_outfit_missing"],
            issues=issues,
        )
    }


def _nodes(report: QualityAuditReport, repair_result) -> WorkflowNodes:
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
    nodes.prompt_converter = SimpleNamespace(repair_result=repair_result)
    return nodes


def _state() -> WorkflowState:
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_STATUS"
    state.input.task_id = "TSK_STATUS"
    state.domain.instructions = _instructions()
    return state


def test_audit_node_rebuilds_missing_manual_items_from_repair_params():
    """阶段只写 manual_required 未落人工项时，从修复参数补全，人工项不得为 0"""

    def _repair_result(inst, issues, fragments):
        inst.metadata.setdefault("repair_history", []).append(
            {"fixed_issues": 0, "actions": []}
        )
        inst.metadata["repair_status"] = REPAIR_STATUS_MANUAL
        return inst

    report = _report(_repair_params())
    nodes = _nodes(report, _repair_result)

    nodes.quality_audit_node(_state())

    assert report.metadata["repair_status"] == REPAIR_STATUS_MANUAL
    manual = report.metadata["requires_manual_fix"]
    assert [item["issue_code"] for item in manual] == ["character_outfit_missing"]
    assert report.post_repair_score == report.detection_score == 81.0


def test_audit_node_downgrades_manual_without_manual_items():
    """人工状态既无落盘项也无法从修复参数补全时，按空转暴露"""

    def _repair_result(inst, issues, fragments):
        inst.metadata.setdefault("repair_history", []).append(
            {"fixed_issues": 0, "actions": []}
        )
        inst.metadata["repair_status"] = REPAIR_STATUS_MANUAL
        return inst

    report = _report(_repair_params(issue_count=1, issues=[]))
    nodes = _nodes(report, _repair_result)

    nodes.quality_audit_node(_state())

    assert report.metadata["repair_status"] == REPAIR_STATUS_NO_ACTION
    assert "requires_manual_fix" not in report.metadata
    assert report.post_repair_score == report.detection_score == 81.0


def test_round_aggregation_ignores_previous_round_status():
    """上一轮 no_action_taken 不得污染本轮 repaired 结论"""
    state = _state()
    state.domain.instructions.metadata.update(
        {
            "repair_status": REPAIR_STATUS_NO_ACTION,
            "repair_status_history": [
                {"stage": "提示词转换", "status": REPAIR_STATUS_NO_ACTION}
            ],
            "repair_history": [{"fixed_issues": 0, "actions": []}],
        }
    )

    def _repair_result(inst, issues, fragments):
        record_repair_outcome(
            inst.metadata,
            "提示词转换",
            [{"issue_code": "prompt_empty"}],
            ["补齐空提示词"],
            auto_codes={"prompt_empty"},
        )
        inst.metadata["repair_history"].append(
            {"fixed_issues": 2, "actions": ["补齐空提示词"]}
        )
        return inst

    report = _report(_repair_params())
    nodes = _nodes(report, _repair_result)

    nodes.quality_audit_node(state)

    assert report.metadata["stage_repair_statuses"] == [REPAIR_STATUS_REPAIRED]
    assert report.metadata["repair_status"] == REPAIR_STATUS_REPAIRED
    assert report.metadata["repair_action_count"] == 2


def test_resolved_issues_are_excluded_from_manual_entries():
    """T-114：上游已收敛的问题不计入人工项，也不触发 no_action_taken"""
    metadata = {}
    violation = {
        "type": "unknown_character",
        "shot_id": "shot_001",
        "character": "门口黑影",
    }

    record_repair_outcome(
        metadata,
        "分镜生成",
        [violation],
        [],
        auto_codes={"shot_repetitive"},
        resolved_issues=[violation],
    )

    assert metadata["repair_status"] == "no_issues"
    assert "requires_manual_fix" not in metadata


def test_partially_resolved_issues_keep_only_unresolved_manual_entries():
    """T-114：仅未收敛的问题进入人工项，已清理问题不再重复暴露"""
    metadata = {}
    resolved = {
        "type": "unknown_character",
        "shot_id": "shot_001",
        "character": "神秘人",
    }
    unresolved = {
        "type": "unknown_character",
        "shot_id": "shot_002",
        "character": "黑影甲",
    }

    status = record_repair_outcome(
        metadata,
        "分镜生成",
        [resolved, unresolved],
        ["清除契约外角色主角色标注: shot_001「神秘人」"],
        auto_codes={"shot_repetitive"},
        resolved_issues=[resolved],
    )

    assert status == "partial"
    assert [
        (entry["fragment_id"], entry["reason"])
        for entry in metadata["requires_manual_fix"]
    ] == [("", "修复器无对应策略")]
