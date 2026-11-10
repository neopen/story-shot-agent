"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_redis_chat_history.py
@Description: 短期记忆 Redis 会话历史测试（不再依赖 langchain_community）
@Author: neopen
"""
import json
from typing import List

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage

from penshot.neopen.knowledge.memory import redis_chat_history
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig
from penshot.neopen.knowledge.memory.redis_chat_history import RedisChatMessageHistory
from penshot.neopen.knowledge.memory.short_term_memory import ShortTermMemory


class _FakeRedisClient:
    """最小 Redis 列表实现，避免单测依赖真实 Redis 服务"""

    def __init__(self):
        self.data: dict = {}
        self.ttls: dict = {}

    def lpush(self, key: str, value: str) -> int:
        self.data.setdefault(key, []).insert(0, value)
        return len(self.data[key])

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        values = self.data.get(key, [])
        if end == -1:
            return values[start:]
        return values[start:end + 1]

    def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True

    def delete(self, key: str) -> int:
        self.data.pop(key, None)
        self.ttls.pop(key, None)
        return 1


class _StubEmbeddings(Embeddings):
    """占位嵌入模型，避免构造 MemoryConfig 时初始化真实客户端"""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return [0.0]


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedisClient()
    monkeypatch.setattr(redis_chat_history.redis, "from_url", lambda *args, **kwargs: client)
    return client


def test_messages_keep_chronological_order(fake_redis):
    """lpush 写入后读取应还原为时间顺序，并刷新过期时间"""
    history = RedisChatMessageHistory(session_id="penshot:memory:s1", url="redis://localhost:6379/0", ttl=60)
    history.add_user_message("第一句")
    history.add_ai_message("第一答")

    assert history.key == "message_store:penshot:memory:s1"
    assert fake_redis.ttls[history.key] == 60

    messages = history.messages
    assert [type(m) for m in messages] == [HumanMessage, AIMessage]
    assert [m.content for m in messages] == ["第一句", "第一答"]


def test_legacy_bytes_payload_is_readable(fake_redis, monkeypatch):
    """兼容 langchain_community 写入的 bytes JSON 历史数据"""
    history = RedisChatMessageHistory(session_id="penshot:memory:s2")

    def legacy_payload(message_type: str, content: str) -> bytes:
        return json.dumps(
            {
                "type": message_type,
                "data": {"content": content, "additional_kwargs": {}, "response_metadata": {}},
            },
            ensure_ascii=False,
        ).encode("utf-8")

    monkeypatch.setattr(
        fake_redis,
        "lrange",
        lambda key, start, end: [
            legacy_payload("ai", "旧回答"),
            legacy_payload("human", "旧提问"),
        ],
    )

    messages = history.messages
    assert [type(m) for m in messages] == [HumanMessage, AIMessage]
    assert [m.content for m in messages] == ["旧提问", "旧回答"]


def test_corrupted_entry_is_skipped(fake_redis):
    """单条损坏数据只跳过该条，不影响其余消息"""
    history = RedisChatMessageHistory(session_id="penshot:memory:s3")
    fake_redis.lpush(history.key, "not-json")
    history.add_user_message("正常消息")

    messages = history.messages
    assert len(messages) == 1
    assert messages[0].content == "正常消息"


def test_clear_removes_key(fake_redis):
    history = RedisChatMessageHistory(session_id="penshot:memory:s4", ttl=10)
    history.add_user_message("待清理")
    history.clear()

    assert history.key not in fake_redis.data
    assert history.key not in fake_redis.ttls
    assert history.messages == []


def test_short_term_memory_without_redis():
    """未配置 Redis 时短期记忆应使用内存存储且功能完整"""
    config = MemoryConfig(
        short_term_redis_url=None,
        term_persist_path=None,
        embeddings=_StubEmbeddings(),
    )
    memory = ShortTermMemory(config, "SN123456")

    memory.add("提问", "回答")

    recent = memory.get_recent()
    assert len(recent) == 1
    assert recent[0]["content"] == "提问"
    assert recent[0]["output"] == "回答"

    stats = memory.get_stats()
    assert stats["redis_enabled"] is False
    assert stats["message_count"] == 1

    memory.clear()
    assert memory.get_recent() == []
