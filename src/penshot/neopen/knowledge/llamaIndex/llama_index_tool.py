"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: llama_index_tool.py
@Description: LlamaIndex 工具函数模块
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/12/18
"""

import os
from typing import Optional, List, Any

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.storage import StorageContext
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.index_store import SimpleIndexStore
from llama_index.core.vector_stores import SimpleVectorStore

from penshot.config.config import settings
from penshot.logger import debug, info, error, warning


def create_vector_store(
        documents: Optional[List] = None,
        index_name: str = "default_index",
        storage_dir: Optional[str] = settings.get_data_paths().get("data_embedding"),
        embedding_model: Optional[BaseEmbedding] = None,
        rebuild: bool = False
) -> VectorStoreIndex:
    """
    创建或加载向量存储索引 - 修复版，处理损坏存储

    Args:
        documents: 要索引的文档列表，如果为None则尝试加载现有索引
        index_name: 索引名称
        storage_dir: 存储目录路径
        embedding_model: 嵌入模型实例
        rebuild: 是否重建索引，即使已存在也会删除旧索引

    Returns:
        VectorStoreIndex实例
    """
    import shutil

    try:
        # 如果提供了存储目录，配置存储上下文
        storage_context = None

        if storage_dir:
            # 确保目录存在
            os.makedirs(storage_dir, exist_ok=True)

            vector_store_path = os.path.join(storage_dir, "vector_store.json")
            vector_store = None

            # 检查现有存储是否有效
            if os.path.exists(vector_store_path) and not rebuild:
                try:
                    if os.path.getsize(vector_store_path) > 0:
                        vector_store = SimpleVectorStore.from_persist_path(vector_store_path)
                        debug(f"已加载向量存储: {vector_store_path}")
                    else:
                        warning(f"向量存储文件为空: {vector_store_path}")
                        vector_store = SimpleVectorStore()
                except Exception as e:
                    warning(f"加载向量存储失败: {e}")
                    # 备份并创建新存储
                    backup_path = f"{vector_store_path}_backup"
                    shutil.copy(vector_store_path, backup_path)
                    warning(f"已备份损坏文件到: {backup_path}")
                    vector_store = SimpleVectorStore()
            else:
                vector_store = SimpleVectorStore()

            doc_store = SimpleDocumentStore()
            index_store = SimpleIndexStore()

            storage_context = StorageContext.from_defaults(
                vector_store=vector_store,
                docstore=doc_store,
                index_store=index_store
            )

        # 如果需要重建或没有文档，从文档创建新索引
        if documents or rebuild or (not storage_dir):
            if documents:
                debug(f"从{len(documents)}个文档创建向量存储索引: {index_name}")

                try:
                    index = VectorStoreIndex.from_documents(
                        documents,
                        storage_context=storage_context,
                        embed_model=embedding_model,
                        show_progress=True
                    )
                except Exception as e:
                    error(f"创建索引失败: {str(e)}")
                    # 创建空索引作为后备
                    if storage_context:
                        index = VectorStoreIndex([], storage_context=storage_context, embed_model=embedding_model)
                    else:
                        index = VectorStoreIndex([], embed_model=embedding_model)

                # 保存索引到存储目录
                if storage_dir:
                    try:
                        index.storage_context.persist(persist_dir=storage_dir)
                        info(f"索引已保存到: {storage_dir}")
                    except Exception as e:
                        warning(f"保存索引失败: {e}")

                return index
            else:
                # 创建空索引
                debug("创建空索引")
                if storage_context:
                    return VectorStoreIndex([], storage_context=storage_context, embed_model=embedding_model)
                else:
                    return VectorStoreIndex([], embed_model=embedding_model)

        # 否则，从存储加载现有索引
        else:
            debug(f"从存储目录加载向量存储索引: {storage_dir}")
            try:
                index = VectorStoreIndex.from_vector_store(
                    storage_context.vector_store,
                    storage_context=storage_context,
                    embed_model=embedding_model
                )
                info(f"成功加载向量存储索引: {index_name}")
                return index
            except Exception as e:
                error(f"加载向量存储索引失败: {str(e)}")
                # 创建空索引作为后备
                return VectorStoreIndex([], embed_model=embedding_model)

    except Exception as e:
        error(f"创建向量存储索引失败: {str(e)}")
        # 最后的后备：返回空索引
        return VectorStoreIndex([], embed_model=embedding_model)


def create_index_from_directory(
        directory_path: str,
        index_name: str = "directory_index",
        storage_dir: Optional[str] = settings.get_data_paths().get("data_embedding"),
        embedding_model: Optional[BaseEmbedding] = None,
        recursive: bool = True,
        required_exts: Optional[List[str]] = None,
        rebuild: bool = False
) -> VectorStoreIndex:
    """
    从目录创建向量存储索引 - 修复版

    Args:
        directory_path: 包含文档的目录路径
        index_name: 索引名称
        storage_dir: 存储目录路径
        embedding_model: 嵌入模型实例
        recursive: 是否递归加载子目录
        required_exts: 必需的文件扩展名列表
        rebuild: 是否重建索引

    Returns:
        VectorStoreIndex实例
    """
    try:
        # 先检查是否可以直接加载现有索引
        if storage_dir and os.path.exists(storage_dir) and not rebuild:
            try:
                return create_vector_store(
                    index_name=index_name,
                    storage_dir=storage_dir,
                    embedding_model=embedding_model
                )
            except Exception as e:
                debug(f"加载现有索引失败，将创建新索引: {str(e)}")

        # 检查目录是否存在
        if not os.path.exists(directory_path):
            error(f"目录不存在: {directory_path}")
            return VectorStoreIndex([], embed_model=embedding_model)

        # 加载目录中的文档
        debug(f"从目录加载文档: {directory_path}")
        try:
            loader = SimpleDirectoryReader(
                input_dir=directory_path,
                recursive=recursive,
                required_exts=required_exts
            )
            documents = loader.load_data()
            info(f"从目录加载了{len(documents)}个文档")
        except Exception as e:
            error(f"加载目录文档失败: {str(e)}")
            return VectorStoreIndex([], embed_model=embedding_model)

        # 创建向量存储索引
        return create_vector_store(
            documents=documents,
            index_name=index_name,
            storage_dir=storage_dir,
            embedding_model=embedding_model,
            rebuild=rebuild
        )

    except Exception as e:
        error(f"从目录创建索引失败: {str(e)}")
        return VectorStoreIndex([], embed_model=embedding_model)


def get_retriever_from_index(
        index: VectorStoreIndex,
        similarity_top_k: int = 3,
        search_type: str = "similarity",
        **kwargs
) -> Any:
    """
    从索引获取检索器 - 修复版，处理空索引

    Args:
        index: 向量存储索引
        similarity_top_k: 返回的最相似文档数量
        search_type: 搜索类型，支持 "similarity", "mmr"
        **kwargs: 额外参数

    Returns:
        检索器实例
    """
    try:
        debug(f"获取检索器: search_type={search_type}, top_k={similarity_top_k}")

        # 检查索引是否有效
        if index is None:
            debug("索引为空，返回空检索器")
            class EmptyRetriever:
                def retrieve(self, query, **kwargs):
                    return []
            return EmptyRetriever()

        if search_type == "mmr":
            # 使用最大边际相关性搜索
            retriever = index.as_retriever(
                retriever_mode="mmr",
                similarity_top_k=similarity_top_k,
                **kwargs
            )
        else:
            # 默认使用相似度搜索
            retriever = index.as_retriever(
                retriever_mode="similarity",
                similarity_top_k=similarity_top_k,
                **kwargs
            )

        return retriever

    except Exception as e:
        error(f"获取检索器失败: {str(e)}")
        class EmptyRetriever:
            def retrieve(self, query, **kwargs):
                return []
        return EmptyRetriever()