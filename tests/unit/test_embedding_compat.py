"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_embedding_compat.py
@Description: 嵌入模型 dimensions 参数降级逻辑测试
@Author: neopen
"""
import pytest
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from penshot.neopen.client.embedding_compat import (
    DimensionFallbackEmbeddings,
    is_dimensions_error,
    supports_dimensions_field,
)


class _StubEmbeddings(Embeddings):
    """可控的嵌入模型桩：按需抛出异常或返回固定向量"""

    def __init__(self, dimension: int, error: Exception | None = None):
        self.dimension = dimension
        self.error = error
        self.calls = 0

    def _maybe_raise(self):
        self.calls += 1
        if self.error is not None:
            raise self.error

    def embed_documents(self, texts):
        self._maybe_raise()
        return [[float(self.dimension)] * self.dimension for _ in texts]

    def embed_query(self, text):
        self._maybe_raise()
        return [float(self.dimension)] * self.dimension


def test_supports_dimensions_field_detects_openai_embeddings():
    """当前 langchain-openai 提供 dimensions 字段"""
    assert supports_dimensions_field(OpenAIEmbeddings) is True


def test_supports_dimensions_field_handles_unknown_class():
    """没有 dimensions 字段的类应返回 False"""

    class Plain:
        pass

    assert supports_dimensions_field(Plain) is False


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 400 - Unrecognized request argument supplied: dimensions",
        "InvalidParameter: dimensions is not supported by this model",
        "422 Unprocessable Entity: unknown field dimensions",
    ],
)
def test_dimensions_error_detection_positive(message):
    assert is_dimensions_error(Exception(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 401 - Invalid API-key provided",
        "Value error, text input should not be empty",
        "Request timeout after 30 seconds",
    ],
)
def test_dimensions_error_detection_negative(message):
    assert is_dimensions_error(Exception(message)) is False


def test_fallback_retries_without_dimensions_and_caches():
    """服务端拒绝 dimensions 时自动降级，且后续调用直接走降级模型"""
    primary = _StubEmbeddings(
        dimension=1536,
        error=Exception("Error code: 400 - Unrecognized request argument supplied: dimensions"),
    )
    created = []

    def _fallback_factory():
        embedding = _StubEmbeddings(dimension=1024)
        created.append(embedding)
        return embedding

    embeddings = DimensionFallbackEmbeddings(primary, _fallback_factory)

    assert len(embeddings.embed_documents(["你好"])) == 1
    assert len(created) == 1
    assert len(embeddings.embed_query("你好")) == 1024

    # 降级后不再重复请求首选模型，工厂也只创建一次
    embeddings.embed_query("再见")
    assert primary.calls == 1
    assert len(created) == 1


def test_non_dimensions_error_is_raised():
    """非 dimensions 相关错误不应被吞掉"""
    primary = _StubEmbeddings(dimension=1536, error=Exception("Error code: 401 - Invalid API-key"))
    embeddings = DimensionFallbackEmbeddings(primary, lambda: _StubEmbeddings(1024))

    with pytest.raises(Exception, match="Invalid API-key"):
        embeddings.embed_query("你好")
