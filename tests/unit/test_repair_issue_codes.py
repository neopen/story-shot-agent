"""修复编码契约（T-104）：确定性问题码、真实动作计数与状态闭环。

覆盖：
- ``QualityRepairParams.issue_codes`` 的填充与去重；
- 规则解析器只按问题码触发确定性修复；
- LLM 提示词转换器记录真实改动片段数；
- 空违规在聚合阶段被过滤；
- 审计节点按阶段状态聚合 ``manual_required``。
"""

from types import SimpleNamespace

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.prompt_converter.llm_prompt_converter import (
    LLMPromptConverter,
)
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
from penshot.neopen.agent.quality_auditor_agent import QualityAuditorAgent
from penshot.neopen.agent.repair_outcome import REPAIR_STATUS_MANUAL
from penshot.neopen.agent.script_parser.rule_script_parser import RuleScriptParser
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    ParsedScript,
    SceneInfo,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _instructions() -> AIVideoInstructions:
    return AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="a woman waits",
                duration=3.0,
            )
        ]
    )


def _short_action_script() -> ParsedScript:
    return ParsedScript(
        scenes=[
            SceneInfo(
                id="scene_001",
                location="教室",
                description="下午的教室",
                elements=[
                    BaseElement(
                        id="elem_001",
                        type=ElementType.ACTION,
                        sequence=1,
                        content="她推开门",
                        duration=0.5,
                    )
                ],
            )
        ]
    )


def test_issue_codes_dedupe_and_accept_enum():
    """问题码支持枚举与字符串，重复值只保留一次"""
    params = QualityRepairParams(fix_needed=True)

    params.add_issue_code("prompt_empty")
    params.add_issue_code(IssueType.PROMPT)
    params.add_issue_code("prompt_empty")
    params.add_issue_code("")

    assert params.issue_codes == ["prompt_empty", "prompt"]


def test_rule_parser_repairs_from_issue_codes():
    """确定性修复只认问题码，issue_types 不再触发修复"""
    parser = RuleScriptParser()

    repaired = parser._apply_repair(
        _short_action_script(),
        QualityRepairParams(fix_needed=True, issue_codes=["duration_invalid"]),
    )
    assert repaired.scenes[0].elements[0].duration == 2.0

    untouched = parser._apply_repair(
        _short_action_script(),
        QualityRepairParams(fix_needed=True, issue_types=["duration_invalid"]),
    )
    assert untouched.scenes[0].elements[0].duration == 0.5


def test_llm_converter_records_actual_fixed_fragments():
    """提示词转换器按实际变动片段数写入修复历史"""
    converter = object.__new__(LLMPromptConverter)
    converter.current_repair_params = QualityRepairParams(
        fix_needed=True, issue_codes=["prompt_empty"]
    )
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="", duration=3.0),
            AIVideoPrompt(fragment_id="frag_002", prompt="a woman waits", duration=3.0),
        ]
    )
    sequence = FragmentSequence(
        fragments=[
            VideoFragment(id="frag_001", shot_id="shot_001", description="女人等待"),
            VideoFragment(id="frag_002", shot_id="shot_001", description="女人回头"),
        ]
    )

    result = converter._apply_repair_params(instructions, sequence)

    assert result.fragments[0].prompt == "女人等待"
    history = result.metadata["repair_history"]
    assert len(history) == 1
    assert history[0]["fixed_issues"] == 1
    assert history[0]["applied"][0]["issue_code"] == "prompt_empty"
    assert history[0]["applied"][0]["fragments"] == ["frag_001"]


def test_enhance_report_fills_issue_codes():
    """增强报告按来源阶段汇总去重后的确定性问题码"""
    agent = QualityAuditorAgent(None, None)
    violation = BasicViolation.create(
        "style_inconsistent",
        IssueType.STYLE,
        "片段风格不一致",
        severity=SeverityLevel.WARNING,
        fragment_id="frag_001",
        source_node=PipelineNode.CONVERT_PROMPT,
    )
    report = QualityAuditReport(violations=[violation])

    enhanced = agent._enhance_report(report, _instructions(), {})

    params = enhanced.repair_params[PipelineNode.CONVERT_PROMPT]
    assert params.issue_codes == ["style_inconsistent"]
    assert params.issue_types == ["style"]


def test_merge_reports_filters_empty_violations():
    """既无问题码又无描述的空违规不进入合并报告"""
    agent = QualityAuditorAgent(None, None)
    empty = BasicViolation(issue_type=IssueType.OTHER)
    report = QualityAuditReport(violations=[])

    merged = agent._merge_reports_with_dedup(
        report,
        None,
        _instructions(),
        {PipelineNode.CONVERT_PROMPT: [empty]},
    )

    assert merged.violations == []


def test_audit_node_marks_manual_required_when_no_auto_strategy():
    """阶段只报人工状态时，审计节点聚合为 manual_required 且不抬分"""
    instructions = _instructions()

    def _repair_result(inst, issues, fragments):
        inst.metadata.setdefault("repair_history", []).append(
            {"fixed_issues": 0, "actions": []}
        )
        inst.metadata["repair_status"] = REPAIR_STATUS_MANUAL
        return inst

    report = QualityAuditReport(
        status=AuditStatus.MINOR_ISSUES, score=81.0, violations=[]
    )
    report.detection_score = 81.0
    report.post_repair_score = 81.0
    report.repair_params = {
        PipelineNode.CONVERT_PROMPT: QualityRepairParams(
            fix_needed=True,
            issue_count=1,
            issue_codes=["character_outfit_missing"],
            issues=[
                BasicViolation.create(
                    "character_outfit_missing",
                    IssueType.CHARACTER,
                    "角色服装缺失",
                    fragment_id="frag_001",
                    source_node=PipelineNode.CONVERT_PROMPT,
                )
            ],
        )
    }

    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.workflow_memory = SimpleNamespace(
        get_memory_list=lambda *args, **kwargs: [],
        store_short_term_memory=lambda *args, **kwargs: None,
    )
    nodes.quality_auditor = SimpleNamespace(
        qa_process=lambda *args, **kwargs: report,
        recheck_rule_score=lambda *args, **kwargs: 95.0,
    )
    nodes.knowledge_manager = SimpleNamespace(
        count_active_templates=lambda script_id=None: 1,
        save_successful_prompt=lambda **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    nodes.prompt_converter = SimpleNamespace(repair_result=_repair_result)

    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_CODES"
    state.input.task_id = "TSK_CODES"
    state.domain.instructions = instructions

    nodes.quality_audit_node(state)

    assert report.metadata["repair_status"] == REPAIR_STATUS_MANUAL
    assert report.metadata["repair_action_count"] == 0
    assert report.post_repair_score == report.detection_score == 81.0
