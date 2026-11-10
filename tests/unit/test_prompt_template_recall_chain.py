"""召回链路单元测试（0.4.4 T-501/T-502）。

覆盖 llama-index 当前持久化格式的索引加载（AC-046）、索引缺失/不一致时
从活跃缓存全量重建（FR-047/048、AC-047）、每任务只重建一次，以及
``add_template`` 不得以单文档索引覆盖既有模板库。

全部用例使用 MockEmbedding 与临时目录，不触网、不读写真实 data/。
"""

import json
import os

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
