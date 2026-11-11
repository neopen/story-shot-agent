"""
@FileName: test_recall_threshold_gate.py
@Description: 0.4.4 M0 召回阈值门禁单测（常量锁定 + AC-041/042/048 确定性断言）
@Author: HiPeng
@Time: 2026/11/9
"""

from penshot.config.config_models import PromptTemplatesConfig
from penshot.neopen.constants.rag import (
    PROMPT_TEMPLATE_MIN_SIMILARITY,
    PROMPT_TEMPLATE_RECALL_MAX_INJECTED,
    PROMPT_TEMPLATE_RECALL_TOP_K,
)
from penshot.neopen.prompts.recall_status import (
    RecallFacts,
    aggregate_status,
    build_anchor_recall,
    count_hits,
    derive_status,
    summarize_scores,
)


def _ready_facts(**overrides) -> RecallFacts:
    """构造“模板与索引均就绪”的默认事实，便于按用例覆盖单字段"""
    values = {
        "template_count": 3,
        "active_template_count": 3,
        "has_index": True,
        "index_docs": 3,
    }
    values.update(overrides)
    return RecallFacts(**values)


def test_default_recall_threshold_matches_constant():
    """常量与配置默认值必须一致，且锁定实测校准值 0.80"""
    config = PromptTemplatesConfig()
    assert PROMPT_TEMPLATE_MIN_SIMILARITY == 0.80
    assert config.min_similarity_score == PROMPT_TEMPLATE_MIN_SIMILARITY
    assert config.top_k == PROMPT_TEMPLATE_RECALL_TOP_K == 2
    assert config.max_injected_patterns == PROMPT_TEMPLATE_RECALL_MAX_INJECTED == 6
    assert config.include_global is True


def test_ac041_hit_when_top_score_above_threshold():
    """AC-041：有命中时状态为 hit"""
    status = derive_status(
        _ready_facts(), scores=[1.0], local_hits=1, global_hits=0, include_global=True
    )
    assert status == "hit"


def test_ac042_all_below_threshold():
    """AC-042：全部低于阈值时状态与分数摘要字段"""
    scores = [0.10, 0.12]
    status = derive_status(
        _ready_facts(), scores=scores, local_hits=0, global_hits=0, include_global=True
    )
    assert status == "all_below_threshold"

    diagnostics = summarize_scores(scores, top_k=PROMPT_TEMPLATE_RECALL_TOP_K)
    assert diagnostics["min_score"] == 0.10
    assert diagnostics["max_score"] == 0.12
    assert diagnostics["top_k"] == 2


def test_threshold_boundary_equal_counts_as_hit():
    """阈值边界：等于阈值算命中，低 0.01 不算"""
    threshold = PROMPT_TEMPLATE_MIN_SIMILARITY
    assert count_hits([threshold], threshold) == 1
    assert count_hits([threshold - 0.01], threshold) == 0


def test_ac048_status_mapping():
    """AC-048：五类失败原因映射到不同状态且互不覆盖"""
    cases = [
        ("empty_templates", _ready_facts(active_template_count=0, has_index=False)),
        (
            "index_load_failed",
            _ready_facts(has_index=False, index_load_failed=True),
        ),
        ("index_unavailable", _ready_facts(has_index=False)),
        ("cache_index_mismatch", _ready_facts(cache_index_mismatch=True)),
        ("retrieval_error", _ready_facts(retrieval_error="boom")),
        ("embeddings_unavailable", _ready_facts(embeddings_available=False)),
    ]
    for expected, facts in cases:
        assert (
            derive_status(
                facts, scores=[0.1], local_hits=0, global_hits=0, include_global=True
            )
            == expected
        )


def test_first_run_status_respects_global_hits():
    """首次运行：跨剧本命中为 first_run_global_hit，否则 first_run_no_history"""
    empty_facts = RecallFacts(template_count=0, active_template_count=0)
    assert (
        derive_status(empty_facts, [], 0, 2, include_global=True)
        == "first_run_global_hit"
    )
    assert (
        derive_status(empty_facts, [], 0, 0, include_global=True)
        == "first_run_no_history"
    )
    # 关闭跨剧本时即使有全局命中也不能报 first_run_global_hit
    assert (
        derive_status(empty_facts, [], 0, 2, include_global=False)
        == "first_run_no_history"
    )


# ==================== T-506：多查询聚合与 anchor_recall ====================


def _diagnostic(status, **overrides):
    """构造一次检索的诊断快照"""
    values = {
        "status": status,
        "attempted": 1,
        "retrieved": 2,
        "hits": 1,
        "min_score": 0.6,
        "max_score": 0.9,
        "error": "",
        "kb": {"template_count": 3, "index_docs": 3, "has_index": True},
    }
    values.update(overrides)
    return values


def test_aggregate_status_prefers_usable_hits():
    """有命中时优先反映命中，个别来源异常不掩盖可用召回"""
    assert aggregate_status(["retrieval_error", "hit", "all_below_threshold"]) == "hit"
    assert (
        aggregate_status(["first_run_no_history", "first_run_global_hit"])
        == "first_run_global_hit"
    )
    assert aggregate_status(["hit_global", "index_unavailable"]) == "hit_global"


def test_aggregate_status_without_hits_takes_worst_reason():
    """无命中时按失败严重度取最严重原因"""
    assert (
        aggregate_status(["all_below_threshold", "index_load_failed"])
        == "index_load_failed"
    )
    assert (
        aggregate_status(["first_run_no_history", "all_below_threshold"])
        == "all_below_threshold"
    )
    assert aggregate_status([], has_history=True) == "all_below_threshold"
    # 无任何观测且无知识库信息时不得伪造首次运行结论
    assert aggregate_status([], has_history=False) == ""


def test_build_anchor_recall_full_field_set_and_extremes():
    """FR-040：字段齐全，分数取各次查询实测极值，计数来自调用方"""
    anchor_recall = build_anchor_recall(
        fragments=4,
        queries=3,
        queries_skipped=1,
        hits=2,
        injected=2,
        diagnostics=[
            _diagnostic("hit", min_score=0.81, max_score=0.93),
            _diagnostic(
                "all_below_threshold", retrieved=2, min_score=0.2, max_score=0.4
            ),
        ],
        top_k=2,
    )

    assert set(anchor_recall) >= {
        "fragments",
        "queries",
        "queries_skipped",
        "attempted",
        "hits",
        "injected",
        "status",
        "kb",
        "min_score",
        "max_score",
        "top_k",
    }
    assert anchor_recall["fragments"] == 4
    assert anchor_recall["queries"] == 3
    assert anchor_recall["queries_skipped"] == 1
    assert anchor_recall["attempted"] == 2
    assert anchor_recall["hits"] == 2
    assert anchor_recall["injected"] == 2
    assert anchor_recall["status"] == "hit"
    assert anchor_recall["min_score"] == 0.2
    assert anchor_recall["max_score"] == 0.93
    assert anchor_recall["top_k"] == 2
    assert anchor_recall["kb"]["index_docs"] == 3
    assert "rebuilt" not in anchor_recall


def test_build_anchor_recall_records_repair_and_error():
    """FR-048：重建前后文档数与首个异常如实进入 anchor_recall"""
    anchor_recall = build_anchor_recall(
        fragments=1,
        queries=1,
        queries_skipped=0,
        hits=1,
        injected=1,
        diagnostics=[
            _diagnostic(
                "hit",
                error="script_b: 检索器不可用",
                last_repair={
                    "reason": "cache_index_mismatch",
                    "before": {"index_docs": 11},
                    "after": {"index_docs": 127},
                },
            )
        ],
        top_k=2,
    )

    assert anchor_recall["rebuilt"] == {"before": 11, "after": 127}
    assert anchor_recall["error"] == "script_b: 检索器不可用"
    assert anchor_recall["status"] == "hit"


def test_build_anchor_recall_without_retrieval_keeps_status_empty():
    """一次检索都没执行时不产出召回结论，但保留真实 kb 快照"""
    anchor_recall = build_anchor_recall(
        fragments=2,
        queries=0,
        queries_skipped=2,
        hits=0,
        injected=0,
        diagnostics=[],
        top_k=2,
        kb={"template_count": 0, "has_index": False, "index_docs": 0},
    )

    assert anchor_recall["status"] == ""
    assert anchor_recall["attempted"] == 0
    assert anchor_recall["queries_skipped"] == 2
    assert anchor_recall["kb"]["template_count"] == 0
    assert anchor_recall["max_score"] == 0.0


def test_build_anchor_recall_empty_kb_reports_first_run():
    """AC-040：空知识库下逐查询状态聚合为 first_run_no_history"""
    anchor_recall = build_anchor_recall(
        fragments=1,
        queries=1,
        queries_skipped=0,
        hits=0,
        injected=0,
        diagnostics=[
            _diagnostic(
                "first_run_no_history",
                attempted=0,
                retrieved=0,
                hits=0,
                min_score=0.0,
                max_score=0.0,
                kb={"template_count": 0, "index_docs": 0, "has_index": False},
            )
        ],
        top_k=2,
    )

    assert anchor_recall["status"] == "first_run_no_history"
    assert anchor_recall["attempted"] == 0
    assert anchor_recall["kb"]["has_index"] is False
