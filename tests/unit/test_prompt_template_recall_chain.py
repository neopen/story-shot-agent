"""召回链路单元测试（0.4.4 T-501/T-502/T-503/T-505）。

覆盖 llama-index 当前持久化格式的索引加载（AC-046）、索引缺失/不一致时
从活跃缓存全量重建（FR-047/048、AC-047）、每任务只重建一次、
``add_template`` 不得以单文档索引覆盖既有模板库，以及结构化检索诊断
（FR-049、AC-048）与只读诊断字段（FR-040）。

全部用例使用 MockEmbedding 与临时目录，不触网、不读写真实 data/。
"""

import json
import os
from types import SimpleNamespace

import pytest
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding

from penshot.neopen.constants.rag import PROMPT_TEMPLATE_METADATA_TYPE
from penshot.neopen.prompts.prompt_template_manager import (
    PromptTemplateManager,
    is_legacy_template,
)


@pytest.fixture
def manager(tmp_path):
    """构造隔离存储的模板管理器（阈值置 0 便于断言召回命中）"""
    return PromptTemplateManager(
        embedding_model=MockEmbedding(embed_dim=8),
        script_id="script_a",
        storage_dir=str(tmp_path),
        min_similarity_score=0.0,
    )


def _write_cache(manager, script_id, count, legacy_count=0):
    """按真实缓存格式落盘 templates_cache.json"""
    entries = []
    for index in range(count):
        prompt = f"模板{index}：雨夜咖啡店外的长镜头，人物缓慢回头。"
        metadata = {"fragment_id": f"frag_{index:03d}", "scene": "咖啡店外"}
        if index < legacy_count:
            metadata["schema_version"] = "legacy"
        entries.append(
            {
                "prompt": prompt,
                "hash": manager._generate_template_hash(prompt),
                "metadata": metadata,
                "added_at": "2026-11-05T10:00:00",
            }
        )
    with open(manager._get_cache_path(script_id), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False)


def _persist_index(manager, script_id, texts):
    """直接持久化一个索引，模拟历史运行留下的 index_store"""
    documents = [
        Document(
            text=text,
            metadata={
                "type": PROMPT_TEMPLATE_METADATA_TYPE,
                "script_id": script_id,
            },
        )
        for text in texts
    ]
    index = VectorStoreIndex.from_documents(
        documents, embed_model=manager.embedding_model
    )
    index.storage_context.persist(persist_dir=manager._get_index_dir(script_id))


def test_ac046_loads_index_persisted_with_current_filenames(manager):
    """AC-046：缺少旧文件名 vector_store.json 不影响加载"""
    _persist_index(manager, "script_a", ["模板一", "模板二"])
    index_dir = manager._get_index_dir("script_a")
    assert os.path.exists(os.path.join(index_dir, "default__vector_store.json"))
    assert not os.path.exists(os.path.join(index_dir, "vector_store.json"))

    manager._load_index_for_script("script_a")

    assert manager._indices["script_a"] is not None
    state = manager._index_states["script_a"]
    assert state["has_index"] is True
    assert state["index_load_failed"] is False
    assert state["index_docs"] == 2


def test_missing_index_is_not_recorded_as_load_failure(manager):
    """FR-046：无索引与加载失败必须可区分"""
    manager._load_index_for_script("script_empty")

    assert manager._indices["script_empty"] is None
    state = manager._index_states["script_empty"]
    assert state["has_index"] is False
    assert state["index_load_failed"] is False


def test_corrupt_index_records_load_failure(manager):
    """FR-046：索引文件损坏时记录加载失败，供召回状态判定"""
    index_dir = manager._get_index_dir("script_a")
    os.makedirs(index_dir, exist_ok=True)
    with open(
        os.path.join(index_dir, "default__vector_store.json"), "w", encoding="utf-8"
    ) as fh:
        fh.write("{ not json")

    manager._load_index_for_script("script_a")

    assert manager._indices["script_a"] is None
    state = manager._index_states["script_a"]
    assert state["has_index"] is False
    assert state["index_load_failed"] is True


def test_ac047_search_rebuilds_index_from_cache(manager):
    """AC-047：索引缺失但缓存有 5 条时，检索前自动重建并落盘"""
    _write_cache(manager, "script_a", 5)

    results = manager.search_similar("雨夜咖啡店", script_id="script_a")

    assert results
    assert manager._count_index_docs(manager._indices["script_a"]) == 5
    repair = manager._index_states["script_a"]["last_repair"]
    assert repair["reason"] == "index_missing"
    assert repair["before"]["index_docs"] == 0
    assert repair["after"]["index_docs"] == 5
    assert os.path.exists(
        os.path.join(manager._get_index_dir("script_a"), "default__vector_store.json")
    )


def test_fr048_mismatch_rebuilds_only_once_per_task(manager, monkeypatch):
    """FR-048：文档数与活跃模板数不一致时重建一次，并记录前后数量"""
    _write_cache(manager, "script_a", 5)
    _persist_index(manager, "script_a", ["旧模板一", "旧模板二"])
    calls = []
    original = manager._rebuild_index_for_script

    def spy(script_id, persist=True):
        calls.append(script_id)
        return original(script_id, persist=persist)

    monkeypatch.setattr(manager, "_rebuild_index_for_script", spy)

    manager.search_similar("雨夜", script_id="script_a")
    manager.search_similar("雨夜", script_id="script_a")

    assert calls == ["script_a"]
    assert manager._count_index_docs(manager._indices["script_a"]) == 5
    repair = manager._index_states["script_a"]["last_repair"]
    assert repair["reason"] == "cache_index_mismatch"
    assert repair["before"]["index_docs"] == 2
    assert repair["after"]["index_docs"] == 5


def test_ac047_add_template_rebuilds_before_insert(manager):
    """AC-047：入库先重建再插入，既有模板数不得从 N 降为 1"""
    _write_cache(manager, "script_a", 5)

    added = manager.add_template(
        "新模板：雨后街道的反打镜头",
        {"fragment_id": "frag_006"},
        "script_a",
        save_to_memory=False,
    )

    assert added is True
    assert manager._count_index_docs(manager._indices["script_a"]) == 6
    assert len(manager._caches["script_a"]) == 6


def test_add_template_refuses_overwrite_when_rebuild_fails(manager, monkeypatch):
    """FR-047：重建失败时拒绝以单文档索引覆盖既有模板库"""
    _write_cache(manager, "script_a", 5)
    monkeypatch.setattr(
        manager, "_rebuild_index_for_script", lambda *args, **kwargs: False
    )

    added = manager.add_template("新模板", {}, "script_a", save_to_memory=False)

    assert added is False
    assert len(manager._caches["script_a"]) == 5


def test_first_template_creates_single_doc_index(manager):
    """首次入库（缓存为空）仍允许创建单文档索引"""
    added = manager.add_template(
        "首个模板", {"fragment_id": "frag_001"}, "script_new", save_to_memory=False
    )

    assert added is True
    assert manager._count_index_docs(manager._indices["script_new"]) == 1


def test_legacy_templates_are_excluded_from_rebuild(manager):
    """FR-045/048：legacy 模板不参与索引重建"""
    _write_cache(manager, "script_a", 5, legacy_count=2)

    manager.search_similar("雨夜", script_id="script_a")

    assert manager._count_index_docs(manager._indices["script_a"]) == 3


@pytest.mark.parametrize(
    "entry",
    [
        {"legacy": True},
        {"metadata": {"legacy": True}},
        {"metadata": {"schema_version": "legacy"}},
    ],
)
def test_is_legacy_template_accepts_both_marker_styles(entry):
    """legacy 判定兼容顶层与 metadata 两种写法（与校准脚本口径一致）"""
    assert is_legacy_template(entry) is True


def test_is_legacy_template_false_for_active_entry():
    assert is_legacy_template({"metadata": {"schema_version": "0.4.4"}}) is False
    assert is_legacy_template({}) is False


def test_rebuild_without_persist_keeps_disk_untouched(manager):
    """persist=False 时只在内存重建，不写索引文件"""
    _write_cache(manager, "script_a", 3)
    manager._load_cache_for_script("script_a")

    assert manager._rebuild_index_for_script("script_a", persist=False) is True
    assert manager._count_index_docs(manager._indices["script_a"]) == 3
    assert not os.path.exists(
        os.path.join(manager._get_index_dir("script_a"), "default__vector_store.json")
    )


# ==================== T-503/T-505：结构化诊断 ====================


def _read_cache(manager, script_id):
    """读回测试写入的缓存条目（用于构造带哈希的历史索引）"""
    with open(manager._get_cache_path(script_id), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _persist_index_with_hashes(manager, script_id, entries):
    """持久化一个带 hash 元数据的索引，模拟 legacy 标记之前留下的 index_store"""
    documents = [
        Document(
            text=entry["prompt"],
            metadata={
                "type": PROMPT_TEMPLATE_METADATA_TYPE,
                "script_id": script_id,
                "hash": entry["hash"],
                **entry.get("metadata", {}),
            },
        )
        for entry in entries
    ]
    index = VectorStoreIndex.from_documents(
        documents, embed_model=manager.embedding_model
    )
    index.storage_context.persist(persist_dir=manager._get_index_dir(script_id))


class _BrokenIndex:
    """构造检索器即抛异常的伪索引（文档数与缓存一致，避免触发重建）"""

    def __init__(self, doc_count):
        self.docstore = SimpleNamespace(docs={str(i): None for i in range(doc_count)})

    def as_retriever(self, **kwargs):
        raise RuntimeError("检索器不可用")


def test_ac048_no_history_maps_to_first_run_no_history(manager):
    """AC-048：无模板、无索引 → first_run_no_history，且不抛异常"""
    results, diagnostics = manager.search_similar_detailed(
        "雨夜", script_id="script_new"
    )

    assert results == []
    assert diagnostics["status"] == "first_run_no_history"
    assert diagnostics["attempted"] == 0
    assert diagnostics["retrieved"] == 0
    assert diagnostics["error"] == ""
    assert diagnostics["kb"]["template_count"] == 0
    assert diagnostics["kb"]["has_index"] is False


def test_ac048_all_legacy_maps_to_empty_templates(manager):
    """AC-048：有历史但全为 legacy → empty_templates，并给出排除数量"""
    _write_cache(manager, "script_a", 3, legacy_count=3)

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results == []
    assert diagnostics["status"] == "empty_templates"
    assert diagnostics["attempted"] == 0
    assert diagnostics["kb"]["template_count"] == 3
    assert diagnostics["kb"]["active_template_count"] == 0
    assert diagnostics["kb"]["legacy_templates"] == 3


def test_ac048_missing_index_maps_to_index_unavailable(manager, monkeypatch):
    """AC-048：索引缺失且重建失败 → index_unavailable（区别于加载失败）"""
    _write_cache(manager, "script_a", 3)
    monkeypatch.setattr(
        manager, "_rebuild_index_for_script", lambda *args, **kwargs: False
    )

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results == []
    assert diagnostics["status"] == "index_unavailable"
    assert diagnostics["attempted"] == 0
    assert diagnostics["kb"]["has_index"] is False
    assert diagnostics["last_repair"]["rebuilt"] is False


def test_ac048_load_failure_maps_to_index_load_failed(manager, monkeypatch):
    """AC-048：索引损坏且重建失败 → index_load_failed"""
    _write_cache(manager, "script_a", 3)
    index_dir = manager._get_index_dir("script_a")
    os.makedirs(index_dir, exist_ok=True)
    with open(
        os.path.join(index_dir, "default__vector_store.json"), "w", encoding="utf-8"
    ) as fh:
        fh.write("{ not json")
    monkeypatch.setattr(
        manager, "_rebuild_index_for_script", lambda *args, **kwargs: False
    )

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results == []
    assert diagnostics["status"] == "index_load_failed"
    assert diagnostics["kb"]["index_docs"] == 0


def test_ac048_scores_below_threshold_map_to_all_below_threshold(manager):
    """AC-048：检索有结果但全部低于阈值 → all_below_threshold，并保留分数摘要"""
    _write_cache(manager, "script_a", 3)

    results, diagnostics = manager.search_similar_detailed(
        "雨夜", script_id="script_a", min_score=1.1
    )

    assert results == []
    assert diagnostics["status"] == "all_below_threshold"
    assert diagnostics["attempted"] == 1
    assert diagnostics["retrieved"] > 0
    assert diagnostics["hits"] == 0
    assert diagnostics["threshold"] == 1.1
    assert diagnostics["max_score"] < 1.1
    assert diagnostics["min_score"] <= diagnostics["max_score"]
    assert diagnostics["error"] == ""


def test_ac048_retrieval_exception_maps_to_retrieval_error(manager):
    """AC-048：检索异常 → retrieval_error，异常信息随诊断返回而非向上抛出"""
    _write_cache(manager, "script_a", 3)
    manager._load_cache_for_script("script_a")
    manager._indices["script_a"] = _BrokenIndex(3)

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results == []
    assert diagnostics["status"] == "retrieval_error"
    assert diagnostics["attempted"] == 1
    assert "检索器不可用" in diagnostics["error"]


def test_hit_diagnostics_carry_scores_kb_and_source_scope(manager):
    """命中时诊断给出分数摘要、知识库快照与来源标注（FR-040/044/049）"""
    _write_cache(manager, "script_a", 3)

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results
    assert diagnostics["status"] == "hit"
    assert diagnostics["hits"] == len(results)
    assert diagnostics["attempted"] == 1
    assert diagnostics["retrieved"] >= diagnostics["hits"]
    assert diagnostics["max_score"] >= diagnostics["min_score"] > 0
    assert diagnostics["top_k"] == manager.top_k
    assert diagnostics["kb"]["template_count"] == 3
    assert diagnostics["kb"]["active_template_count"] == 3
    assert diagnostics["kb"]["index_docs"] == 3
    assert diagnostics["kb"]["legacy_templates"] == 0
    assert diagnostics["kb"]["has_index"] is True
    assert diagnostics["last_repair"]["reason"] == "index_missing"
    assert diagnostics["last_repair"]["after"]["index_docs"] == 3
    for result in results:
        assert result["source_scope"] == "script"
        assert result["source_script_id"] == "script_a"
        assert result["script_id"] == "script_a"


def test_search_similar_wrapper_keeps_list_contract(manager):
    """兼容包装只返回结果列表，与 detailed 的结果一致（D8）"""
    _write_cache(manager, "script_a", 3)

    detailed, _ = manager.search_similar_detailed("雨夜", script_id="script_a")
    wrapped = manager.search_similar("雨夜", script_id="script_a")

    assert isinstance(wrapped, list)
    assert [item["prompt"] for item in wrapped] == [item["prompt"] for item in detailed]
    assert manager.get_best_match("雨夜", script_id="script_a") is not None


def test_wrapper_returns_empty_list_on_failure_without_raising(manager):
    """失败场景下包装仍返回空列表，诊断由 detailed 承担"""
    assert manager.search_similar("雨夜", script_id="script_new") == []


def test_explicit_zero_min_score_overrides_strict_default(manager, tmp_path):
    """显式 min_score=0.0 不得被 `or` 吞掉回退到严格默认阈值"""
    _write_cache(manager, "script_a", 3)
    strict = PromptTemplateManager(
        embedding_model=MockEmbedding(embed_dim=8),
        script_id="script_a",
        storage_dir=str(tmp_path),
        min_similarity_score=2.0,
    )

    results, diagnostics = strict.search_similar_detailed(
        "雨夜", script_id="script_a", min_score=0.0
    )

    assert results
    assert diagnostics["threshold"] == 0.0
    assert diagnostics["status"] == "hit"

    _, default_diagnostics = strict.search_similar_detailed(
        "雨夜", script_id="script_a"
    )
    assert default_diagnostics["threshold"] == 2.0
    assert default_diagnostics["status"] == "all_below_threshold"


def test_stale_index_legacy_hash_is_excluded_at_retrieval(manager):
    """FR-045：索引文档数与活跃数一致但含 legacy 哈希时，检索层仍需排除"""
    _write_cache(manager, "script_a", 3, legacy_count=1)
    entries = _read_cache(manager, "script_a")
    # 去掉 metadata 标记，只留哈希，确保排除动作来自缓存哈希比对
    legacy_entry = {**entries[0], "metadata": {"fragment_id": "frag_000"}}
    active_entry = entries[2]
    _persist_index_with_hashes(manager, "script_a", [active_entry, legacy_entry])

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert diagnostics["kb"]["index_docs"] == 2
    assert diagnostics["kb"]["legacy_templates"] == 1
    assert diagnostics["last_repair"] is None
    assert results
    assert all(item["prompt"] != legacy_entry["prompt"] for item in results)
    assert any(item["prompt"] == active_entry["prompt"] for item in results)


def test_stale_index_legacy_metadata_is_excluded_at_retrieval(manager):
    """FR-045：索引节点自带 legacy 标记时同样排除，且不触发重建"""
    _write_cache(manager, "script_a", 2, legacy_count=1)
    entries = _read_cache(manager, "script_a")
    # 用活跃条目的哈希 + legacy 标记，确保排除动作来自节点 metadata
    legacy_entry = {**entries[1], "metadata": {"schema_version": "legacy"}}
    _persist_index_with_hashes(manager, "script_a", [legacy_entry])

    results, diagnostics = manager.search_similar_detailed("雨夜", script_id="script_a")

    assert results == []
    assert diagnostics["retrieved"] == 1
    assert diagnostics["hits"] == 0
    assert diagnostics["last_repair"] is None


def test_t505_get_recall_diagnostics_full_field_set(manager):
    """T-505：诊断字段齐全，legacy 数量与索引文档数如实反映"""
    _write_cache(manager, "script_a", 5, legacy_count=2)

    diagnostics = manager.get_recall_diagnostics("script_a")

    assert set(diagnostics) == {
        "template_count",
        "active_template_count",
        "index_docs",
        "legacy_templates",
        "global_template_count",
        "global_scripts",
        "has_index",
        "storage_dir",
    }
    assert diagnostics["template_count"] == 5
    assert diagnostics["active_template_count"] == 3
    assert diagnostics["legacy_templates"] == 2
    assert diagnostics["index_docs"] == 0
    assert diagnostics["has_index"] is False
    assert diagnostics["storage_dir"] == os.path.join(
        manager.base_storage_dir, "prompt_templates", "script_a"
    )

    manager.search_similar("雨夜", script_id="script_a")
    after = manager.get_recall_diagnostics("script_a")
    assert after["has_index"] is True
    assert after["index_docs"] == 3


def test_t505_get_recall_diagnostics_never_rebuilds(manager, monkeypatch):
    """T-505：诊断接口只读，不得触发重建或写入索引文件"""
    _write_cache(manager, "script_a", 3)
    calls = []
    monkeypatch.setattr(
        manager,
        "_rebuild_index_for_script",
        lambda *args, **kwargs: calls.append(args) or False,
    )

    diagnostics = manager.get_recall_diagnostics("script_a")

    assert calls == []
    assert diagnostics["index_docs"] == 0
    assert not os.path.exists(
        os.path.join(manager._get_index_dir("script_a"), "default__vector_store.json")
    )
