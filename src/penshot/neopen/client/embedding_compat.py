"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: embedding_compat.py
@Description: 嵌入模型参数兼容性辅助：处理服务端不支持 dimensions 参数的情况
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
"""
from typing import Any, Callable, List

from langchain_core.embeddings import Embeddings

from penshot.logger import warning


def supports_dimensions_field(embedding_class: Any) -> bool:
    """判断指定嵌入模型类是否提供 dimensions 参数（兼容不同版本的 langchain-openai）"""
    model_fields = getattr(embedding_class, "model_fields", None)
    if isinstance(model_fields, dict) and "dimensions" in model_fields:
        return True
    # pydantic v1 风格：__fields__
    legacy_fields = getattr(embedding_class, "__fields__", None)
    return isinstance(legacy_fields, dict) and "dimensions" in legacy_fields


def is_dimensions_error(error: BaseException) -> bool:
    """判断异常是否由服务端拒绝 dimensions 参数导致"""
    message = str(error).lower()
    if "dimension" not in message:
        return False
    # 常见报错：Unrecognized request argument supplied: dimensions / InvalidParameter: dimensions ...
    return any(
        keyword in message
        for keyword in ("unrecognized", "unknown", "unsupported", "not support", "invalid", "400", "422")
    )


class DimensionFallbackEmbeddings(Embeddings):
    """嵌入模型包装器：服务端不支持 dimensions 参数时自动降级为默认维度"""

    def __init__(
        self,
        primary: Embeddings,
        fallback_factory: Callable[[], Embeddings],
    ):
        """
        Args:
            primary: 带 dimensions 参数的嵌入模型
            fallback_factory: 不带 dimensions 参数的嵌入模型工厂（首次降级时才创建）
        """
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._fallback: Embeddings | None = None

    @property
    def primary(self) -> Embeddings:
        """返回首选（带 dimensions）的嵌入模型，便于外部检查配置"""
        return self._primary

    def _ensure_fallback(self) -> Embeddings:
        """首次降级时创建并缓存默认维度的嵌入模型"""
        if self._fallback is None:
            warning("嵌入服务端不支持 dimensions 参数，已自动降级为模型默认维度")
            self._fallback = self._fallback_factory()
        return self._fallback

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._fallback is None:
            try:
                return self._primary.embed_documents(texts)
            except Exception as error:
                if not is_dimensions_error(error):
                    raise
        return self._ensure_fallback().embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        if self._fallback is None:
            try:
                return self._primary.embed_query(text)
            except Exception as error:
                if not is_dimensions_error(error):
                    raise
        return self._ensure_fallback().embed_query(text)
