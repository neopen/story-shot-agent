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
