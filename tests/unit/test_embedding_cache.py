"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_embedding_cache.py
@Description: 嵌入模型工厂缓存单元测试（确保同一配置只初始化一次）
@Author: NeoPen
"""
import pytest

from penshot.config.config_models import EmbeddingBaseConfig
from penshot.neopen.client import client_factory
from penshot.neopen.client.client_config import AIConfig


@pytest.fixture(autouse=True)
def _clear_embedding_cache():
    """每个用例前后清空缓存，避免用例间互相影响"""
    client_factory.clear_embedding_cache()
    yield
    client_factory.clear_embedding_cache()


def test_get_default_embedding_reuses_instance(monkeypatch):
    """相同配置重复获取时应复用同一实例，且只初始化一次"""
    calls = []

    def fake_embedding_client(ai_config, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(client_factory, "_get_default_embedding_client", fake_embedding_client)

    first = client_factory.get_default_embedding()
    second = client_factory.get_default_embedding()

    assert first is second
    assert len(calls) == 1


def test_get_default_embedding_caches_by_overrides(monkeypatch):
    """覆盖参数不同（如模型名）时应视为不同配置，分别缓存"""
    calls = []

    def fake_embedding_client(ai_config, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(client_factory, "_get_default_embedding_client", fake_embedding_client)

    first = client_factory.get_default_embedding(embed_model_name="model-a")
    second = client_factory.get_default_embedding(embed_model_name="model-b")

    assert first is not second
    assert len(calls) == 2


def test_get_embedding_client_reuses_instance(monkeypatch):
    """通过 AIConfig 获取嵌入模型时同样应命中缓存"""
    calls = []

    class FakeClient:
        def llm_embed(self):
            calls.append(1)
            return object()

    monkeypatch.setattr(client_factory, "get_client", lambda provider, config: FakeClient())

    config = AIConfig(embed=EmbeddingBaseConfig(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_name="qwen-embed",
        api_key="test-key",
    ))

    first = client_factory.get_embedding_client(config)
    second = client_factory.get_embedding_client(config)

    assert first is second
    assert len(calls) == 1


def test_failed_initialization_is_not_cached(monkeypatch):
    """初始化失败不应写入缓存，下次调用仍会重新尝试"""
    attempts = []

    def failing_embedding_client(ai_config, **kwargs):
        attempts.append(1)
        raise RuntimeError("embedding init failed")

    monkeypatch.setattr(client_factory, "_get_default_embedding_client", failing_embedding_client)

    assert client_factory.get_default_embedding() is None
    first_attempts = len(attempts)

    assert client_factory.get_default_embedding() is None
    assert len(attempts) > first_attempts
    assert not client_factory._EMBEDDING_CACHE
