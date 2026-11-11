"""入库策略单元测试（0.4.4 T-507/T-508）。

覆盖：
- ``decide_ingestion`` 的整批判定：PASSED / 分数门槛 / 首次运行 cold_start_seed /
  major·critical 阻断 / 审计前拒绝（FR-045、AC-049、AC-043D）；
- ``add_template`` 写入 ``schema_version`` / ``audit_status``，且缓存与索引两侧一致（FR-045）；
- ``save_successful_prompt`` 不再自行标注 ``quality_audit_passed``（AC-049）；
- ``quality_audit_node`` 与 ``WorkflowMemory`` 两个入库点共用同一策略（pre-audit 不入库）。

全部用例使用 MockEmbedding 与临时目录，不触网、不读写真实 data/。
"""

import json
import os
from types import SimpleNamespace

import pytest
from llama_index.core.embeddings import MockEmbedding

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_enum import (
    AuditStatus,
    IssueType,
    SeverityLevel,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    BasicViolation,
    QualityAuditReport,
)
from penshot.neopen.agent.workflow.workflow_memory import WorkflowMemory
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.constants.schema import CONTRACT_SCHEMA_VERSION
from penshot.neopen.prompts.ingestion_policy import (
    AUDIT_STATUS_UNKNOWN,
    REASON_BELOW_THRESHOLD,
    REASON_COLD_START,
    REASON_PRE_AUDIT,
    REASON_SEVERE_VIOLATIONS,
    SOURCE_COLD_START_SEED,
    SOURCE_QUALITY_AUDIT_PASSED,
    SOURCE_QUALITY_AUDIT_SCORE,
    decide_ingestion,
)
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager


# ---------------------------------------------------------------------------
# 策略判定（FR-045 / AC-043D）
# ---------------------------------------------------------------------------


def test_passed_ingests_with_passed_source():
    """审计通过无需分数门槛，source 为 quality_audit_passed"""
    decision = decide_ingestion(
        audit_status=AuditStatus.PASSED,
        quality_score=70.0,
        active_template_count=3,
    )

    assert decision.allowed is True
    assert decision.source == SOURCE_QUALITY_AUDIT_PASSED
    assert decision.audit_status == "passed"


def test_minor_issues_high_score_uses_score_source():
    """非 PASSED 但分数 ≥ 90 时入库，source 为 quality_audit_score"""
    decision = decide_ingestion(
        audit_status="minor_issues",
        quality_score=92.0,
        active_template_count=3,
        severities=[SeverityLevel.WARNING],
    )

    assert decision.allowed is True
    assert decision.source == SOURCE_QUALITY_AUDIT_SCORE
    # AC-049：minor_issues 不得被标记为 quality_audit_passed
    assert decision.audit_status == "minor_issues"


def test_minor_issues_below_threshold_rejected():
    """非首次运行且分数不足 90 时拒绝入库"""
    decision = decide_ingestion(
        audit_status="minor_issues",
        quality_score=85.0,
        active_template_count=3,
        severities=[SeverityLevel.WARNING],
    )

    assert decision.allowed is False
    assert decision.source == ""
    assert decision.reason == REASON_BELOW_THRESHOLD


@pytest.mark.parametrize("score", [None, 0.0, 89.9])
def test_non_passed_without_score_evidence_rejected(score):
    """无分数证据或分数不达标时不得入库"""
    decision = decide_ingestion(
        audit_status="moderate_issues", quality_score=score, active_template_count=3
    )

    assert decision.allowed is False
    assert decision.reason == REASON_BELOW_THRESHOLD


def test_first_run_minor_issues_ingests_as_seed():
    """AC-043D：首次运行 minor_issues + 85 分 + 无严重缺陷 → cold_start_seed"""
    decision = decide_ingestion(
        audit_status="minor_issues",
        quality_score=85.0,
        active_template_count=0,
        severities=[SeverityLevel.WARNING],
    )

    assert decision.allowed is True
    assert decision.source == SOURCE_COLD_START_SEED
    assert decision.reason == REASON_COLD_START
    assert decision.audit_status == "minor_issues"


def test_second_run_same_result_rejected():
    """AC-043D：第二次运行（已有活跃模板）相同结果不得入库"""
    decision = decide_ingestion(
        audit_status="minor_issues",
        quality_score=85.0,
        active_template_count=1,
        severities=[SeverityLevel.WARNING],
    )

    assert decision.allowed is False
    assert decision.reason == REASON_BELOW_THRESHOLD


@pytest.mark.parametrize(
    "severity", [SeverityLevel.MAJOR, SeverityLevel.CRITICAL, "major", "critical"]
)
@pytest.mark.parametrize("active_count", [0, 5])
def test_severe_violations_block_ingestion(severity, active_count):
    """AC-043D：含 major/critical 时任何运行都不得入库（首次运行也不例外）"""
    decision = decide_ingestion(
        audit_status="passed",
        quality_score=99.0,
        active_template_count=active_count,
        severities=[SeverityLevel.WARNING, severity],
    )

    assert decision.allowed is False
    assert decision.source == ""
    assert decision.reason == REASON_SEVERE_VIOLATIONS


def test_pre_audit_rejected():
    """审计前阶段无真实状态，拒绝入库并给出 unknown"""
    for status in (None, ""):
        decision = decide_ingestion(
            audit_status=status, quality_score=95.0, active_template_count=0
        )

        assert decision.allowed is False
        assert decision.source == ""
        assert decision.audit_status == AUDIT_STATUS_UNKNOWN
        assert decision.reason == REASON_PRE_AUDIT


# ---------------------------------------------------------------------------
# add_template 审计字段（T-507）
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path):
    """隔离存储的模板管理器"""
    return PromptTemplateManager(
        embedding_model=MockEmbedding(embed_dim=8),
        script_id="script_a",
        storage_dir=str(tmp_path),
        min_similarity_score=0.0,
    )


def _cache_entries(manager, script_id):
    """读回落盘缓存条目"""
    with open(manager._get_cache_path(script_id), "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_add_template_writes_schema_version_and_audit_status(manager):
    """入库 metadata 在缓存与索引两侧都带 schema_version / audit_status"""
    assert manager.add_template(
        "雨夜咖啡店外的长镜头，人物缓慢回头。",
        {"fragment_id": "frag_001"},
        script_id="script_a",
    )

    entry = _cache_entries(manager, "script_a")[0]
    assert entry["metadata"]["schema_version"] == CONTRACT_SCHEMA_VERSION
    assert entry["metadata"]["audit_status"] == AUDIT_STATUS_UNKNOWN

    documents = list(manager._indices["script_a"].docstore.docs.values())
    assert len(documents) == 1
    assert documents[0].metadata["schema_version"] == CONTRACT_SCHEMA_VERSION
    assert documents[0].metadata["audit_status"] == AUDIT_STATUS_UNKNOWN


def test_add_template_keeps_explicit_legacy_marker(manager):
    """显式 schema_version=legacy 不被默认值覆盖（迁移标记可用）"""
    assert manager.add_template(
        "旧版模板：暖色调特写。",
        {"fragment_id": "frag_legacy", "schema_version": "legacy"},
        script_id="script_a",
    )

    entry = _cache_entries(manager, "script_a")[0]
    assert entry["metadata"]["schema_version"] == "legacy"
    assert manager.count_active_templates("script_a") == 0


def test_save_successful_prompt_does_not_fabricate_passed(manager):
    """AC-049：source 与 audit_status 取调用方传入的真实判定结果"""
    assert manager.save_successful_prompt(
        fragment_id="frag_001",
        prompt_text="雨夜咖啡店外的长镜头，人物缓慢回头。",
        quality_score=92.0,
        script_id="script_a",
        source=SOURCE_QUALITY_AUDIT_SCORE,
        audit_status="minor_issues",
    )

    metadata = _cache_entries(manager, "script_a")[0]["metadata"]
    assert metadata["source"] == SOURCE_QUALITY_AUDIT_SCORE
    assert metadata["audit_status"] == "minor_issues"
    assert metadata["source"] != SOURCE_QUALITY_AUDIT_PASSED


def test_count_active_templates_is_readonly(tmp_path):
    """统计活跃模板不索引、不创建剧本目录"""
    manager = PromptTemplateManager(
        embedding_model=MockEmbedding(embed_dim=8),
        script_id="script_a",
        storage_dir=str(tmp_path),
    )

    assert manager.count_active_templates("ghost_script") == 0
    assert not os.path.exists(
        os.path.join(str(tmp_path), "prompt_templates", "ghost_script")
    )


# ---------------------------------------------------------------------------
# quality_audit_node 接线（T-508）
# ---------------------------------------------------------------------------


class _RecordingKnowledgeManager:
    """记录入库调用的伪模板管理器"""

    def __init__(self, active_count):
        self.active_count = active_count
        self.saved = []

    def count_active_templates(self, script_id=None):
        return self.active_count

    def save_successful_prompt(self, **kwargs):
        self.saved.append(kwargs)
        return True


def _audit_report(status, score, severities=()):
    """构造最小审计报告"""
    violations = [
        BasicViolation(
            issue_type=IssueType.PROMPT,
            severity=severity,
            description=f"{severity} 级问题",
        )
        for severity in severities
    ]
    return QualityAuditReport(status=status, score=score, violations=violations)


def _audit_node(active_count, report):
    """构造只含入库判定所需依赖的审查节点"""
    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.workflow_memory = SimpleNamespace(
        get_memory_list=lambda *args, **kwargs: [],
        get_memory_dict=lambda *args, **kwargs: {},
        store_short_term_memory=lambda *args, **kwargs: None,
    )
    nodes.quality_auditor = SimpleNamespace(qa_process=lambda *args, **kwargs: report)
    nodes.knowledge_manager = _RecordingKnowledgeManager(active_count)
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    return nodes


def _audit_state(fragment_count=2):
    """构造带片段指令的审查状态"""
    state = WorkflowState.from_raw_script("剧本内容")
    state.input.script_id = "SN_TEST"
    state.input.task_id = "TSK_TEST"
    state.domain.instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id=f"frag_{index:03d}",
                prompt=f"片段 {index} 的中景提示词，人物缓慢回头。",
                duration=3.0,
            )
            for index in range(fragment_count)
        ]
    )
    return state


def test_audit_node_ingests_cold_start_batch_as_seed():
    """AC-043D：首次运行 minor_issues 整批入库，全部标 cold_start_seed"""
    nodes = _audit_node(
        active_count=0,
        report=_audit_report(AuditStatus.MINOR_ISSUES, 85.0, [SeverityLevel.WARNING]),
    )

    nodes.quality_audit_node(_audit_state())

    saved = nodes.knowledge_manager.saved
    assert len(saved) == 2
    assert {item["source"] for item in saved} == {SOURCE_COLD_START_SEED}
    assert {item["audit_status"] for item in saved} == {"minor_issues"}


def test_audit_node_skips_below_threshold_on_second_run():
    """AC-043D：已有活跃模板时，相同结果不再入库"""
    nodes = _audit_node(
        active_count=3,
        report=_audit_report(AuditStatus.MINOR_ISSUES, 85.0, [SeverityLevel.WARNING]),
    )

    nodes.quality_audit_node(_audit_state())

    assert nodes.knowledge_manager.saved == []


def test_audit_node_blocks_major_violation():
    """含 major 缺陷时即使分数高也不入库"""
    nodes = _audit_node(
        active_count=0,
        report=_audit_report(AuditStatus.MAJOR_ISSUES, 95.0, [SeverityLevel.MAJOR]),
    )

    nodes.quality_audit_node(_audit_state())

    assert nodes.knowledge_manager.saved == []


def test_audit_node_passed_uses_passed_source():
    """审计通过时 source 为 quality_audit_passed"""
    nodes = _audit_node(active_count=3, report=_audit_report(AuditStatus.PASSED, 98.0))

    nodes.quality_audit_node(_audit_state())

    saved = nodes.knowledge_manager.saved
    assert len(saved) == 2
    assert {item["source"] for item in saved} == {SOURCE_QUALITY_AUDIT_PASSED}
    assert {item["audit_status"] for item in saved} == {"passed"}


# ---------------------------------------------------------------------------
# WorkflowMemory 接线（T-508）
# ---------------------------------------------------------------------------


def _memory(knowledge_manager):
    """构造只含入库依赖的记忆管理器"""
    memory = object.__new__(WorkflowMemory)
    memory.script_id = "SN_TEST"
    memory.knowledge_manager = knowledge_manager
    return memory


def _conversion_result(fragment_count=2):
    return SimpleNamespace(
        fragments=[
            SimpleNamespace(
                fragment_id=f"frag_{index:03d}",
                prompt=f"片段 {index} 的中景提示词，人物在雨夜缓慢回头。",
                style="cinematic",
                duration=3.0,
            )
            for index in range(fragment_count)
        ]
    )


def test_workflow_memory_does_not_ingest_pre_audit():
    """convert_prompt 阶段无审计结果：走同一策略并被 pre_audit 拒绝"""
    knowledge_manager = _RecordingKnowledgeManager(active_count=0)
    memory = _memory(knowledge_manager)

    memory._update_knowledge_manager_with_success(
        _conversion_result(), {"completeness_score": 95.0}
    )

    assert knowledge_manager.saved == []


def test_workflow_memory_uses_same_policy_when_audit_facts_present():
    """stats 携带审计事实时，与节点使用同一策略与来源标注"""
    knowledge_manager = _RecordingKnowledgeManager(active_count=3)
    memory = _memory(knowledge_manager)

    memory._update_knowledge_manager_with_success(
        _conversion_result(),
        {"completeness_score": 95.0, "audit_status": "minor_issues"},
    )

    saved = knowledge_manager.saved
    assert len(saved) == 2
    assert {item["source"] for item in saved} == {SOURCE_QUALITY_AUDIT_SCORE}
    assert {item["audit_status"] for item in saved} == {"minor_issues"}
