"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: embedding_adapter.py
@Description: 嵌入模型适配工具，统一 LangChain 与 llama_index 两种嵌入接口
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
"""
from typing import Any, List, Optional

from penshot.logger import debug, warning


def to_llama_index_embedding(embeddings: Any) -> Optional[Any]:
    """把嵌入模型统一适配为 llama_index 的 BaseEmbedding。

    项目默认通过 ``ShotConfig.get_embed_by_config()`` 拿到的是 LangChain
    ``Embeddings``（如 DashScopeEmbeddings），而 llama_index 的索引/检索只接受
    ``BaseEmbedding``，直接传入会触发 ``assert`` 失败。这里使用官方桥接层
    ``LangchainEmbedding`` 做一次包装；已经是 ``BaseEmbedding`` 时原样返回。

    Args:
        embeddings: 任意嵌入模型实例（LangChain Embeddings / llama_index BaseEmbedding / None）

    Returns:
        可安全用于 llama_index 的嵌入模型（适配失败时返回原始对象）
    """
    if embeddings is None:
        return None

    try:
        from llama_index.core.embeddings import BaseEmbedding
    except Exception as e:
        warning(f"无法导入 llama_index BaseEmbedding，跳过嵌入适配: {e}")
        return embeddings

    if isinstance(embeddings, BaseEmbedding):
        return embeddings

    try:
        from llama_index.embeddings.langchain import LangchainEmbedding

        adapted = LangchainEmbedding(langchain_embeddings=embeddings)
        debug(f"嵌入模型已适配为 llama_index BaseEmbedding: {type(embeddings).__name__}")
        return adapted
    except Exception as e:
        warning(f"嵌入模型适配失败，将沿用原始对象: {e}")
        return embeddings


def embed_query_vector(embeddings: Any, text: str) -> List[float]:
    """获取查询文本的向量，兼容 llama_index 与 LangChain 两套接口。

    Args:
        embeddings: 嵌入模型实例
        text: 待向量化的查询文本

    Returns:
        查询向量
    """
    if embeddings is None:
        raise ValueError("嵌入模型未初始化，无法计算查询向量")

    # llama_index 的 BaseEmbedding / LangchainEmbedding
    if hasattr(embeddings, "get_query_embedding"):
        return list(embeddings.get_query_embedding(text))

    # LangChain 的 Embeddings
    if hasattr(embeddings, "embed_query"):
        return list(embeddings.embed_query(text))

    raise TypeError(f"不支持的嵌入模型类型: {type(embeddings)!r}")
