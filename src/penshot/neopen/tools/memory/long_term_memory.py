"""
@FileName: long_term_memory.py
@Description: 长期记忆 - 向量数据库 + 持久化
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/30 13:09
"""
from datetime import datetime
from typing import Optional, Any, Dict, List

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_chroma import Chroma

from penshot.logger import error, debug
from penshot.neopen.tools.memory.memory_models import MemoryConfig


class LongTermMemory:
    """长期记忆 - 基于向量检索的记忆"""

    def __init__(self, config: MemoryConfig, script_id: str):
        self.config = config
        self.script_id = script_id

        # 向量存储路径
        self.store_path = f"{config.long_term_store_path}/{script_id}"

        # 初始化向量存储
        self.vectorstore = Chroma(
            collection_name=f"script_{script_id}_memory",
            embedding_function=config.embeddings,
            persist_directory=self.store_path
        )

        # 创建检索器
        self.retriever = self.vectorstore.as_retriever(
            search_kwargs={
                "k": config.long_term_k,
                "score_threshold": config.long_term_score_threshold
            }
        )

        # 会话历史存储
        self._session_histories: Dict[str, ChatMessageHistory] = {}

        # 创建带记忆的链
        self.memory = self._create_memory_chain()

        debug(f"初始化长期记忆: script={script_id}, k={config.long_term_k}, threshold={config.long_term_score_threshold}")

    def _get_session_history(self, session_id: str) -> ChatMessageHistory:
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
                    return "\n".join([m["content"] for m in memories])
            return ""

        # 创建检索链
        retrieval_chain = RunnableLambda(retrieve_memories)

        # 包装为带记忆的链
        return RunnableWithMessageHistory(
            retrieval_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history"
        )

    def add(self, text: str, metadata: Optional[Dict] = None):
        """添加记忆"""
        # 增强文本（加入元数据信息）
        enhanced_text = text
        if metadata:
            enhanced_text = f"{text}\n"
            if metadata.get("tags"):
                enhanced_text += f"标签: {', '.join(metadata['tags'])}\n"
            if metadata.get("category"):
                enhanced_text += f"类别: {metadata['category']}\n"

        # 添加到向量存储
        self.vectorstore.add_texts(
            texts=[enhanced_text],
            metadatas=[{
                "script_id": self.script_id,
                "timestamp": datetime.now().isoformat(),
                **(metadata or {})
            }]
        )

        # 自动持久化
        if hasattr(self.vectorstore, 'persist'):
            self.vectorstore.persist()

    def search(self, query: str, k: int = None, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """搜索相关记忆"""
        if k is None:
            k = self.config.long_term_k

        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(query, k=k)

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
        """根据ID获取记忆"""
        try:
            results = self.vectorstore.get(ids=[memory_id])
            if results and results.get("documents"):
                return {
                    "content": results["documents"][0],
                    "metadata": results["metadatas"][0] if results.get("metadatas") else {}
                }
        except Exception as e:
            error(f"获取记忆失败: {e}")
        return None

    def delete_by_filter(self, filter_dict: Dict) -> int:
        """按条件删除记忆"""
        try:
            # 获取所有匹配的ID
            results = self.vectorstore.get(where=filter_dict)
            ids = results.get("ids", [])
            if ids:
                self.vectorstore.delete(ids)
                if hasattr(self.vectorstore, 'persist'):
                    self.vectorstore.persist()
                return len(ids)
        except Exception as e:
            error(f"删除记忆失败: {e}")
        return 0

    def clear(self):
        """清空所有记忆"""
        try:
            # 删除集合
            self.vectorstore.delete_collection()
            # 重新创建
            self.vectorstore = Chroma(
                collection_name=f"script_{self.script_id}_memory",
                embedding_function=self.config.embeddings,
                persist_directory=self.store_path
            )
            self.retriever = self.vectorstore.as_retriever(
                search_kwargs={
                    "k": self.config.long_term_k,
                    "score_threshold": self.config.long_term_score_threshold
                }
            )
            # 清空会话历史
            self._session_histories.clear()
            self.memory = self._create_memory_chain()
        except Exception as e:
            error(f"清空长期记忆失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            count = self.vectorstore._collection.count() if self.vectorstore._collection else 0
            return {
                "type": "long_term",
                "document_count": count,
                "k": self.config.long_term_k,
                "store_path": self.store_path
            }
        except:
            return {"type": "long_term", "document_count": 0}