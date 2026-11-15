"""质量审查读取契约校验告警的测试（0.4.5 任务：修复"契约已告警而审查满分"的割裂）。

覆盖：规则审查新增的契约一致性复核检查（计入评分与状态）、qa_process
合并后的状态与分数、LLM 深度审查提示词中的契约警告区块、审计回路传回的
BasicViolation 包装契约违规在分镜修复器中的确定性收敛、审计节点的
历史+复检违规合并接线。
"""

from types import SimpleNamespace
from unittest.mock import Mock

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
    CameraControl,
)
from penshot.neopen.agent.quality_auditor.llm_quality_auditor import (
    LLMQualityAuditor,
)
from penshot.neopen.agent.quality_auditor_agent import (
    QualityAuditorAgent,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    AuditStatus,
    BasicViolation,
    IssueType,
    QualityAuditReport,
    SeverityLevel,
)
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import (
    RuleQualityAuditor,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
)
from penshot.neopen.agent.shot_segmenter_agent import ShotSegmenterAgent
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.shot_config import ShotConfig

PROMPT = (
    "close-up of a young man in a yellow raincoat standing by the cafe window at dusk"
)

UNKNOWN_CHARACTER = {
    "type": "unknown_character",
    "stage": "segment_shot",
    "shot_id": "shot_013",
    "character": "门口黑影",
    "message": "镜头 shot_013 的角色 门口黑影 不在一致性契约中",
}

ORPHAN_FRAGMENT = {
    "type": "orphan_fragment",
    "stage": "split_video",
    "fragment_id": "frag_009",
    "shot_id": "shot_099",
    "message": "片段 frag_009 关联的镜头 shot_099 不存在",
}


def _auditor() -> RuleQualityAuditor:
    return RuleQualityAuditor(ShotConfig())


def _contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("陈默", 1)
    return contract


def _fragment(**overrides) -> AIVideoPrompt:
    payload = {
        "fragment_id": "frag_001",
        "prompt": PROMPT,
        "duration": 3.0,
        "style": "cinematic",
        "camera": CameraControl(shot_type="close_up"),
    }
    payload.update(overrides)
    return AIVideoPrompt(**payload)


def _instructions() -> AIVideoInstructions:
    return AIVideoInstructions(fragments=[_fragment()])


def _continuity_violations(report):
    return [
        v
        for v in report.violations
        if v.issue_type == IssueType.CONTINUITY
        and v.issue_code in {"unknown_character", "orphan_fragment"}
    ]


def test_rule_audit_flags_contract_violations_as_major():
    """契约违规项必须计入规则审查报告并按 MAJOR 计，状态不再是 PASSED"""
    report = _auditor().audit(
        _instructions(),
        contract=_contract(),
        contract_violations=[UNKNOWN_CHARACTER, ORPHAN_FRAGMENT],
    )

    violations = _continuity_violations(report)
    assert len(violations) == 2
    assert {v.issue_code for v in violations} == {
        "unknown_character",
        "orphan_fragment",
    }
    for violation in violations:
        assert violation.severity == SeverityLevel.MAJOR
        assert violation.source_node in (
            PipelineNode.SEGMENT_SHOT,
            PipelineNode.SPLIT_VIDEO,
        )

    unknown = next(v for v in violations if v.issue_code == "unknown_character")
    assert unknown.issue_value == UNKNOWN_CHARACTER
    assert "补登记契约锚点" in unknown.suggestion

    check = next(c for c in report.checks if c["name"] == "契约一致性复核检查")
    assert check["status"] == "failed"
    assert report.status == AuditStatus.MAJOR_ISSUES


def test_rule_audit_passes_without_contract_violations():
    """契约存在且违规为空时复核检查通过，不产生连续性违规"""
    report = _auditor().audit(
        _instructions(), contract=_contract(), contract_violations=[]
    )

    check = next(c for c in report.checks if c["name"] == "契约一致性复核检查")
    assert check["status"] == "passed"
    assert _continuity_violations(report) == []


def test_rule_audit_skips_without_contract():
    """缺少契约时跳过复核，不误报"""
    report = _auditor().audit(
        _instructions(),
        contract=None,
        contract_violations=[UNKNOWN_CHARACTER],
    )

    check = next(c for c in report.checks if c["name"] == "契约一致性复核检查")
    assert check["status"] == "skipped"
    assert _continuity_violations(report) == []


def test_qa_process_scores_contract_violations():
    """qa_process 合并契约违规后：状态降级为 MAJOR_ISSUES，分数跌破 100"""
    agent = QualityAuditorAgent(llm=None, config=ShotConfig(enable_llm=False))

    report = agent.qa_process(
        _instructions(),
        {},
        None,
        contract=_contract(),
        contract_violations=[UNKNOWN_CHARACTER],
    )

    continuity = [
        v
        for v in report.violations
        if v.issue_type == IssueType.CONTINUITY and v.issue_code == "unknown_character"
    ]
    assert len(continuity) == 1
    assert continuity[0].severity == SeverityLevel.MAJOR
    assert report.status == AuditStatus.MAJOR_ISSUES
    assert report.stats.get("major", 0) == 1
    assert report.score <= 75


def test_llm_audit_history_hint_mentions_contract_warnings():
    """深度审查提示词必须采信契约校验警告，避免"刚告警的镜头判 0 问题" """
    auditor = LLMQualityAuditor(Mock(), ShotConfig())

    hint = auditor._build_history_hint(
        {"contract_violations": [UNKNOWN_CHARACTER, ORPHAN_FRAGMENT]}
    )

    assert "契约一致性警告" in hint
    assert "门口黑影" in hint
    assert "frag_009" in hint


def test_llm_audit_history_hint_without_violations_stays_quiet():
    """无契约违规时不注入警告区块"""
    auditor = LLMQualityAuditor(Mock(), ShotConfig())
    assert auditor._build_history_hint({"contract_violations": []}) == ""


def test_repair_shots_clears_hallucinated_character_from_audit_violation():
    """审计回路传回的 BasicViolation 包装契约违规同样确定性清除主角色标注"""
    shot_sequence = ShotSequence(
        shots=[
            ShotInfo(
                id="shot_013",
                scene_id="scene_001",
                description="门缝外有黑影晃动",
                duration=3.0,
                main_character="神秘人",
            )
        ]
    )
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="陈默")])
    wrapped = BasicViolation.create(
        issue_code="unknown_character",
        issue_type=IssueType.CONTINUITY,
        issue_desc="镜头 shot_013 的角色 神秘人 不在一致性契约中",
        issue_value={
            "type": "unknown_character",
            "stage": "segment_shot",
            "shot_id": "shot_013",
            "character": "神秘人",
            "message": "镜头 shot_013 的角色 神秘人 不在一致性契约中",
        },
        severity=SeverityLevel.MAJOR,
    )

    segmenter = ShotSegmenterAgent(
        llm=None, config=ShotConfig(enable_llm=False, enable_enhance=False)
    )
    repaired = segmenter.repair_shots(shot_sequence, [wrapped], structured_script)

    assert repaired.shots[0].main_character == ""
    assert repaired.metadata["repair_history"][-1]["fixed_issues"] == 1


# ---------------------------------------------------------------------------
# 审计节点接线：复检最终产物并把历史+复检违规（去重）传给审查器
# ---------------------------------------------------------------------------


def _audit_node_with_recorder(report):
    """构造只含契约接线所需依赖的审查节点，记录 qa_process 收到的契约违规参数"""
    captured = {}

    def _qa_process(
        instructions,
        stage_issues,
        historical_context,
        contract=None,
        contract_violations=None,
    ):
        captured["contract_violations"] = contract_violations
        return report

    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.workflow_memory = SimpleNamespace(
        get_memory_list=lambda *args, **kwargs: [],
        get_memory_dict=lambda *args, **kwargs: {},
        store_short_term_memory=lambda *args, **kwargs: None,
    )
    nodes.quality_auditor = SimpleNamespace(qa_process=_qa_process)
    nodes.knowledge_manager = SimpleNamespace(
        count_active_templates=lambda script_id=None: 0,
        save_successful_prompt=lambda **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    return nodes, captured


def _node_state() -> WorkflowState:
    """构造带契约、幻觉角色镜头与片段的审查状态"""
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_TEST"
    state.input.task_id = "TSK_TEST"
    state.domain.instructions = _instructions()
    state.domain.contract = _contract()
    state.domain.shot_sequence = ShotSequence(
        shots=[
            ShotInfo(
                id="shot_001",
                scene_id="scene_001",
                description="门缝外有黑影晃动",
                duration=3.0,
                main_character="神秘人",
            )
        ]
    )
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[VideoFragment(id="frag_001", shot_id="shot_001", duration=3.0)]
    )
    return state


def test_audit_node_merges_historical_and_fresh_violations():
    """审计节点复检最终产物，历史违规与复检结果去重合并后一并传给审查器"""
    state = _node_state()
    historical = {
        "type": "unknown_character",
        "stage": "segment_shot",
        "shot_id": "shot_001",
        "character": "神秘人",
        "message": "镜头 shot_001 的角色 神秘人 不在一致性契约中",
    }
    state.domain.contract_violations = [dict(historical)]  # 与复检同键，应被去重
    report = QualityAuditReport(
        status=AuditStatus.MINOR_ISSUES, score=85.0, violations=[]
    )
    nodes, captured = _audit_node_with_recorder(report)

    nodes.quality_audit_node(state)

    merged = captured["contract_violations"]
    assert len(merged) == 2
    assert merged[0] == historical
    by_key = {(v["type"], v.get("shot_id"), v.get("fragment_id")) for v in merged}
    assert ("unknown_character", "shot_001", None) in by_key
    assert ("unknown_character", None, "frag_001") in by_key


def test_audit_node_passes_empty_violations_without_contract_products():
    """契约或产物缺失时审计节点不崩溃，传入空违规列表"""
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_TEST"
    state.input.task_id = "TSK_TEST"
    state.domain.instructions = _instructions()
    report = QualityAuditReport(
        status=AuditStatus.MINOR_ISSUES, score=85.0, violations=[]
    )
    nodes, captured = _audit_node_with_recorder(report)

    nodes.quality_audit_node(state)

    assert captured["contract_violations"] == []
