"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_embedding_adapter.py
@Description: 嵌入模型适配层单元测试（离线，不依赖真实嵌入服务）
@Author: NeoPen
"""
from langchain_core.embeddings import Embeddings
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding

from penshot.neopen.knowledge.embedding_adapter import embed_query_vector, to_llama_index_embedding
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.knowledge.template.prompt_template_knowledge import PromptTemplateKB


class FakeLangchainEmbeddings(Embeddings):
    """模拟 LangChain 嵌入模型，避免测试依赖网络与 API Key"""

    def embed_documents(self, texts):
        return [[0.1 * (i + 1), 0.2, 0.3] for i, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def test_langchain_embeddings_are_adapted():
    """LangChain Embeddings 应被适配为 llama_index BaseEmbedding"""
    adapted = to_llama_index_embedding(FakeLangchainEmbeddings())
    assert isinstance(adapted, BaseEmbedding)
    assert len(adapted.get_query_embedding("林然")) == 3


def test_adapter_is_idempotent():
    """已是 BaseEmbedding 时应原样返回，避免重复包装"""
    adapted = to_llama_index_embedding(FakeLangchainEmbeddings())
    assert to_llama_index_embedding(adapted) is adapted


def test_none_embeddings_return_none():
    """未配置嵌入模型时应安全返回 None"""
    assert to_llama_index_embedding(None) is None


def test_script_knowledge_base_adapts_embeddings(tmp_path):
    """剧本知识库应自动适配传入的 LangChain 嵌入模型"""
    kb = ScriptKnowledgeBase(FakeLangchainEmbeddings(), script_id="TEST", storage_dir=str(tmp_path))
    assert isinstance(kb.embeddings, BaseEmbedding)

    # 回归点：适配前用 LangChain 对象建索引会触发 llama_index 断言失败
    index = VectorStoreIndex([Document(text="林然站在雨中望着灯塔")], embed_model=kb.embeddings)
    assert index is not None


def test_prompt_template_kb_adapts_embeddings(tmp_path):
    """提示词模板知识库应自动适配传入的 LangChain 嵌入模型"""
    kb = PromptTemplateKB(FakeLangchainEmbeddings(), script_id="TEST", storage_dir=str(tmp_path))
    assert isinstance(kb.embeddings, BaseEmbedding)


def test_embed_query_vector_supports_langchain_interface():
    """查询向量获取应兼容 LangChain 的 embed_query 接口"""
    assert embed_query_vector(FakeLangchainEmbeddings(), "林然") == [0.1, 0.2, 0.3]


def test_embed_query_vector_supports_llama_interface():
    """查询向量获取应兼容 llama_index 的 get_query_embedding 接口"""
    adapted = to_llama_index_embedding(FakeLangchainEmbeddings())
    assert embed_query_vector(adapted, "林然") == [0.1, 0.2, 0.3]
