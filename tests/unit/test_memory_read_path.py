"""三层记忆读取链路测试：按 key 存取、中期持久化与工作流键一致性。"""

from types import SimpleNamespace

import pytest

from penshot.neopen.agent.workflow.workflow_memory import WorkflowMemory
from penshot.neopen.knowledge.memory.base_memory_layer import BaseMemoryLayer
from penshot.neopen.knowledge.memory.long_term_memory import LongTermMemory
from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig, MemoryLevel
from penshot.neopen.knowledge.memory import script_memory as script_memory_module


class FakeLLM:
    """中期摘要只需要一个稳定的字符串返回"""

    def invoke(self, _prompt):
        return SimpleNamespace(content="阶段摘要")


class StubLongTermMemory(BaseMemoryLayer):
    """隔离向量库的长期记忆替身：复用基类 KV 契约，仅验证读写路由"""

    backend_type = "long_term"

    def __init__(self, config, script_id):
        super().__init__(config, script_id)

    def _clear_backend(self):
        return None

    def _extra_stats(self):
        return {"enabled": True, "document_count": 0}

    def add(self, text, metadata=None):
        return None

    def search(self, query, k=None, filter_dict=None):
        return []


@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(script_memory_module, "LongTermMemory", StubLongTermMemory)
    config = MemoryConfig(
        term_persist_path=str(tmp_path),
        short_term_redis_url=None,
        long_term_enabled=True,
        embeddings=object(),
    )
    return MemoryManager("SN_MEM", FakeLLM(), config)


def test_layers_share_base_contract(memory_manager):
    script = memory_manager.get_script("SN_MEM")
    assert isinstance(script.short_term, BaseMemoryLayer)
    assert isinstance(script.medium_term, BaseMemoryLayer)
    assert isinstance(script.long_term, BaseMemoryLayer)

    script.medium_term.set_value("contract_key", {"value": 1})
    stats = script.medium_term.get_stats()
    assert stats["type"] == "medium_term"
    assert stats["script_id"] == "SN_MEM"
    assert stats["key_value_count"] == 1
    assert "stages_count" in stats

    script.short_term.set_value("contract_key", "value")
    script.short_term.clear()
    assert not script.short_term.has_value("contract_key")


def test_short_term_get_is_keyed(memory_manager):
    memory_manager.add("alpha", {"value": 1}, MemoryLevel.SHORT_TERM)
    memory_manager.add("beta", {"value": 2}, MemoryLevel.SHORT_TERM)

    assert memory_manager.get("alpha", MemoryLevel.SHORT_TERM) == {"value": 1}
    assert memory_manager.get("beta", MemoryLevel.SHORT_TERM) == {"value": 2}
    assert memory_manager.get("missing", MemoryLevel.SHORT_TERM, default=None) is None


def test_medium_term_roundtrip_list_count_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(script_memory_module, "LongTermMemory", StubLongTermMemory)
    config = MemoryConfig(
        term_persist_path=str(tmp_path),
        short_term_redis_url=None,
        long_term_enabled=True,
        embeddings=object(),
    )
    manager = MemoryManager("SN_MEM", FakeLLM(), config)

    manager.add("stats_parse_script", {"attempts": 2}, MemoryLevel.MEDIUM_TERM)
    manager.add("issues_parse_script", [{"type": "x"}], MemoryLevel.MEDIUM_TERM)

    assert manager.get("stats_parse_script", MemoryLevel.MEDIUM_TERM) == {"attempts": 2}
    assert manager.get_list("issues_parse_script", MemoryLevel.MEDIUM_TERM) == [
        {"type": "x"}
    ]
    assert manager.count("issues_parse_script", MemoryLevel.MEDIUM_TERM) == 1
    assert manager.exists("stats_parse_script", MemoryLevel.MEDIUM_TERM)

    # 读写必须落在同一文件，重启后可恢复
    summary_file = tmp_path / "SN_MEM" / "medium_summary.json"
    assert summary_file.exists()
    assert not list((tmp_path / "SN_MEM").glob("medium_summary_*.json"))

    reloaded = MemoryManager("SN_MEM", FakeLLM(), config)
    assert reloaded.get("stats_parse_script", MemoryLevel.MEDIUM_TERM) == {
        "attempts": 2
    }


def test_long_term_key_roundtrip(memory_manager):
    memory_manager.add(
        "successful_convert_prompt_patterns",
        [{"pattern": "cinematic"}],
        MemoryLevel.LONG_TERM,
    )

    assert memory_manager.get(
        "successful_convert_prompt_patterns", MemoryLevel.LONG_TERM
    ) == [{"pattern": "cinematic"}]
    assert (
        memory_manager.count(
            "successful_convert_prompt_patterns", MemoryLevel.LONG_TERM
        )
        == 1
    )


def test_workflow_memory_writes_keys_read_by_nodes(memory_manager):
    workflow_memory = WorkflowMemory("SN_MEM", memory_manager, knowledge_manager=None)
    result = SimpleNamespace(stats={"completeness_score": 0.9, "total_elements": 5})
    issue = SimpleNamespace(
        model_dump=lambda: {"type": "missing_scene", "description": "缺少场景"}
    )

    workflow_memory.after_stage_completion(
        stage="parse_script",
        result=result,
        metadata={"issues": [issue], "issue_count": 1},
    )

    assert workflow_memory.get_memory_list(
        "issues_parse_script", MemoryLevel.SHORT_TERM
    ) == [{"type": "missing_scene", "description": "缺少场景"}]
    common = workflow_memory.get_memory_list(
        "common_parse_script_patterns", MemoryLevel.LONG_TERM
    )
    assert common and common[0]["issue_type"] == "missing_scene"

    restored = workflow_memory.restore_context_for_stage("parse_script")
    assert restored["recent_issues"]
    assert restored["has_memory"]


def test_audit_keys_are_readable(memory_manager):
    workflow_memory = WorkflowMemory("SN_MEM", memory_manager, knowledge_manager=None)
    workflow_memory.store_short_term_value("latest_audit_result", {"score": 90})
    workflow_memory.append_memory_value(
        "audit_results_history",
        {"score": 90, "status": "passed"},
        MemoryLevel.MEDIUM_TERM,
    )

    assert workflow_memory.get_memory_dict(
        "latest_audit_result", MemoryLevel.SHORT_TERM
    ) == {"score": 90}
    assert workflow_memory.get_memory_list(
        "audit_results_history", MemoryLevel.MEDIUM_TERM
    ) == [{"score": 90, "status": "passed"}]


class FakeVectorStore:
    """只实现 prune 所需的 get/add_texts/delete 接口"""

    def __init__(self):
        self.entries = {}
        self.deleted = []
        self._counter = 0

    def add_texts(self, texts, metadatas):
        for text, metadata in zip(texts, metadatas):
            self._counter += 1
            memory_id = f"doc_{self._counter}"
            self.entries[memory_id] = {"text": text, "timestamp": str(self._counter)}
        return [f"doc_{self._counter}"]

    def get(self, include=None):
        ids = list(self.entries)
        return {
            "ids": ids,
            "metadatas": [
                {
                    **(self.entries[memory_id]),
                    "timestamp": self.entries[memory_id]["timestamp"],
                }
                for memory_id in ids
            ],
        }

    def delete(self, ids):
        for memory_id in ids:
            self.entries.pop(memory_id, None)
            self.deleted.append(memory_id)


def test_long_term_prunes_oldest_documents():
    config = MemoryConfig(
        term_persist_path=None,
        embeddings=object(),
        long_term_max_documents=2,
    )
    memory = object.__new__(LongTermMemory)
    memory.config = config
    memory.script_id = "SN_PRUNE"
    memory.store_path = ""
    memory._key_values = {}
    memory._kv_path = None
    memory.vectorstore = FakeVectorStore()
    memory.retriever = None

    for index in range(4):
        memory.add(f"text_{index}")

    assert len(memory.vectorstore.entries) == 2
    assert set(memory.vectorstore.entries) == {"doc_3", "doc_4"}
