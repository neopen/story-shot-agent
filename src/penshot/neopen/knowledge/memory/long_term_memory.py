"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: long_term_memory.py
@Description: 长期记忆 - 向量数据库 + 持久化
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 13:09
"""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List

from langchain_chroma import Chroma

from penshot.logger import error, debug, warning
from penshot.neopen.knowledge.memory.base_memory_layer import BaseMemoryLayer
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig


# 全局线程池，避免每个 LongTermMemory 实例创建线程
_VECTORSTORE_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="vectorstore-init"
)


def _relevance_from_distance(distance: float) -> float:
    """把向量库返回的距离换算成 [0, 1] 的相关度（越大越相关）

    Chroma 的 l2 距离是平方欧氏距离，对单位化向量有 ``距离 = 2 - 2 * 余弦相似度``，
    因此 ``1 - 距离 / 2`` 即余弦相似度；嵌入模型由 ``MemoryConfig.embeddings`` 提供（未指定时复用统一嵌入工厂）。
    """
    return max(0.0, min(1.0, 1.0 - distance / 2.0))


class LongTermMemory(BaseMemoryLayer):
    """长期记忆 - 基于向量检索的记忆"""

    backend_type = "long_term"

    def __init__(self, config: MemoryConfig, script_id: str):
        super().__init__(config, script_id)

        # 向量存储路径
        self.store_path = f"{config.term_persist_path}/{script_id}"

        # 按 key 精确存取的 KV 层：不依赖向量检索，保证按 key 读取稳定可用
        self._kv_path: Optional[Path] = None
        if config.term_persist_path:
            kv_dir = Path(config.term_persist_path) / script_id
            kv_dir.mkdir(parents=True, exist_ok=True)
            self._kv_path = kv_dir / "long_term_kv.json"
            self._key_values = self._load_json_dict(self._kv_path)

        # 延迟初始化
        self.vectorstore: Optional[Chroma] = None
        self.retriever: Any = None

        # 后台异步初始化
        self._vectorstore_future: Future = _VECTORSTORE_EXECUTOR.submit(
            self._init_vectorstore
        )

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
            vectorstore: Optional[Chroma] = self._vectorstore_future.result()

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

    def _persist(self) -> None:
        """持久化按 key 的长期记忆（JSON 侧车）"""
        self._save_json_dict(self._kv_path, self._key_values)

    def _delete_kv_file(self) -> None:
        self._delete_file(self._kv_path)

    def add(
        self,
        text: str,
        metadata: Optional[Dict] = None
    ) -> None:
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

        # 向量库只增不删会持续膨胀，写入后按上限清理最旧记录
        self.prune_old()

    def prune_old(self, max_documents: Optional[int] = None) -> int:
        """按时间戳清理最旧记录，保留不超过 max_documents 条

        Args:
            max_documents: 保留上限；未指定时取配置值，<=0 表示不清理

        Returns:
            实际删除的记录数
        """
        limit = (
            max_documents
            if max_documents is not None
            else getattr(self.config, "long_term_max_documents", 0)
        )
        if not limit or limit <= 0:
            return 0

        try:
            vectorstore = self._ensure_vectorstore()
            results = vectorstore.get(include=["metadatas"])
            ids = list(results.get("ids") or [])
            if len(ids) <= limit:
                return 0

            metadatas = results.get("metadatas") or [{} for _ in ids]
            paired = list(zip(ids, metadatas))
            paired.sort(key=lambda pair: (pair[1] or {}).get("timestamp", ""))
            remove_ids = [item_id for item_id, _ in paired[: len(paired) - limit]]
            if remove_ids:
                vectorstore.delete(remove_ids)
                debug(f"长期记忆清理旧记录: {len(remove_ids)} 条")
            return len(remove_ids)

        except Exception as e:
            warning(f"清理长期记忆失败: {e}")
            return 0

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
                    query, k=k, filter=filter_dict
                )
            else:
                results = vectorstore.similarity_search_with_score(query, k=k)

            memories = []
            for doc, distance in results:
                relevance = _relevance_from_distance(distance)
                if relevance < self.config.long_term_score_threshold:
                    continue
                memories.append(
                    {
                        "content": doc.page_content,
                        "score": relevance,
                        "metadata": doc.metadata,
                    }
                )

            return memories

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

    def _clear_backend(self) -> None:
        """清空并重建向量库（KV 与文件由基类统一处理）"""
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

            debug(
                f"长期记忆已清空: script={self.script_id}"
            )

        except Exception as e:
            error(f"清空长期记忆失败: {e}")

    def _extra_stats(self) -> Dict[str, Any]:
        try:
            vectorstore = self._ensure_vectorstore()

            count = vectorstore._collection.count()

            return {
                "enabled": True,
                "document_count": count,
                "k": self.config.long_term_k,
                "store_path": self.store_path
            }

        except Exception as e:
            error(f"获取长期记忆统计信息失败: {e}")

            return {
                "enabled": False,
                "document_count": 0,
                "k": self.config.long_term_k,
                "store_path": self.store_path
            }
