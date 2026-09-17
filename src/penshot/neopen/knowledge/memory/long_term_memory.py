"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: long_term_memory.py
@Description: 长期记忆 - 向量数据库 + 持久化
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 13:09
"""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Any, Dict, List

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_chroma import Chroma

from penshot.logger import error, debug
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig


# 全局线程池，避免每个 LongTermMemory 实例创建线程
_VECTORSTORE_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="vectorstore-init"
)


class LongTermMemory:
    """长期记忆 - 基于向量检索的记忆"""

    def __init__(self, config: MemoryConfig, script_id: str):
        self.config = config
        self.script_id = script_id

        # 向量存储路径
        self.store_path = f"{config.term_persist_path}/{script_id}"

        # 延迟初始化
        self.vectorstore: Optional[Chroma] = None
        self.retriever = None

        # 后台异步初始化
        self._vectorstore_future: Future = _VECTORSTORE_EXECUTOR.submit(
            self._init_vectorstore
        )

        # 会话历史存储
        self._session_histories: Dict[str, ChatMessageHistory] = {}

        # 创建带记忆的链
        self.memory = self._create_memory_chain()

        debug(
            f"初始化长期记忆: "
            f"script={script_id}, "
            f"k={config.long_term_k}, "
            f"threshold={config.long_term_score_threshold}"
        )

    def _init_vectorstore(self) -> Optional[Chroma]:
        """后台初始化向量数据库"""
        try:
            vectorstore = Chroma(
                collection_name=f"script_{self.script_id}_memory",
                embedding_function=self.config.embeddings,
                persist_directory=self.store_path
            )

            self.vectorstore = vectorstore

            self.retriever = vectorstore.as_retriever(
                search_kwargs={
                    "k": self.config.long_term_k,
                    "score_threshold": self.config.long_term_score_threshold
                }
            )

            debug(
                f"长期记忆向量数据库初始化完成: "
                f"script={self.script_id}"
            )

            return vectorstore

        except Exception as e:
            error(
                f"长期记忆向量数据库初始化失败: "
                f"script={self.script_id}, error={e}"
            )
            raise

    def _ensure_vectorstore(self) -> Chroma:
        """
        确保向量数据库已经初始化。

        正常情况下后台初始化已经完成；
        如果业务请求先于初始化完成，则在这里等待。
        """
        if self.vectorstore is not None:
            return self.vectorstore

        try:
            vectorstore = self._vectorstore_future.result()

            if vectorstore is None:
                raise RuntimeError(
                    f"VectorStore 初始化失败: script={self.script_id}"
                )

            return vectorstore

        except Exception as e:
            error(
                f"获取长期记忆向量数据库失败: "
                f"script={self.script_id}, error={e}"
            )
            raise

    def is_ready(self) -> bool:
        """判断向量数据库是否初始化完成"""
        return self.vectorstore is not None

    def _get_session_history(
        self,
        session_id: str
    ) -> ChatMessageHistory:
        """获取或创建会话历史"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = ChatMessageHistory()

        return self._session_histories[session_id]

    def _create_memory_chain(self):
        """创建带记忆的链"""
        from langchain_core.runnables import RunnableLambda

        def retrieve_memories(input_dict):
            """检索相关记忆"""
            query = input_dict.get("input", "")

            if query:
                memories = self.search(query)

                if memories:
                    return "\n".join(
                        m["content"] for m in memories
                    )

            return ""

        retrieval_chain = RunnableLambda(retrieve_memories)

        return RunnableWithMessageHistory(
            retrieval_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history"
        )

    def add(
        self,
        text: str,
        metadata: Optional[Dict] = None
    ):
        """添加记忆"""

        vectorstore = self._ensure_vectorstore()

        # 增强文本
        enhanced_text = text

        if metadata:
            enhanced_text = f"{text}\n"

            if metadata.get("tags"):
                enhanced_text += (
                    f"标签: {', '.join(metadata['tags'])}\n"
                )

            if metadata.get("category"):
                enhanced_text += (
                    f"类别: {metadata['category']}\n"
                )

        vectorstore.add_texts(
            texts=[enhanced_text],
            metadatas=[{
                "script_id": self.script_id,
                "timestamp": datetime.now().isoformat(),
                **(metadata or {})
            }]
        )

    def search(
        self,
        query: str,
        k: Optional[int] = None,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict]:
        """搜索相关记忆"""

        vectorstore = self._ensure_vectorstore()

        if k is None:
            k = self.config.long_term_k

        try:
            if filter_dict:
                results = vectorstore.similarity_search_with_score(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = vectorstore.similarity_search_with_score(
                    query,
                    k=k
                )

            return [
                {
                    "content": doc.page_content,
                    "score": score,
                    "metadata": doc.metadata
                }
                for doc, score in results
                if score >= self.config.long_term_score_threshold
            ]

        except Exception as e:
            error(f"长期记忆搜索失败: {e}")
            return []

    def get_by_id(self, memory_id: str) -> Optional[Dict]:
        """根据 ID 获取记忆"""

        vectorstore = self._ensure_vectorstore()

        try:
            results = vectorstore.get(ids=[memory_id])

            if results and results.get("documents"):
                return {
                    "content": results["documents"][0],
                    "metadata": (
                        results["metadatas"][0]
                        if results.get("metadatas")
                        else {}
                    )
                }

        except Exception as e:
            error(f"获取记忆失败: {e}")

        return None

    def delete_by_filter(self, filter_dict: Dict) -> int:
        """按条件删除记忆"""

        vectorstore = self._ensure_vectorstore()

        try:
            results = vectorstore.get(where=filter_dict)
            ids = results.get("ids", [])

            if ids:
                vectorstore.delete(ids)

                return len(ids)

        except Exception as e:
            error(f"删除记忆失败: {e}")

        return 0

    def clear(self):
        """清空所有记忆"""

        try:
            vectorstore = self._ensure_vectorstore()

            # 删除当前 collection
            vectorstore.delete_collection()

            # 重新创建
            new_vectorstore = Chroma(
                collection_name=f"script_{self.script_id}_memory",
                embedding_function=self.config.embeddings,
                persist_directory=self.store_path
            )

            self.vectorstore = new_vectorstore

            self.retriever = new_vectorstore.as_retriever(
                search_kwargs={
                    "k": self.config.long_term_k,
                    "score_threshold": self.config.long_term_score_threshold
                }
            )

            # 清空会话历史
            self._session_histories.clear()

            # 重新创建 memory chain
            self.memory = self._create_memory_chain()

            debug(
                f"长期记忆已清空: script={self.script_id}"
            )

        except Exception as e:
            error(f"清空长期记忆失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""

        try:
            vectorstore = self._ensure_vectorstore()

            count = vectorstore._collection.count()

            return {
                "type": "long_term",
                "document_count": count,
                "k": self.config.long_term_k,
                "store_path": self.store_path
            }

        except Exception as e:
            error(f"获取长期记忆统计信息失败: {e}")

            return {
                "type": "long_term",
                "document_count": 0,
                "k": self.config.long_term_k,
                "store_path": self.store_path
            }
