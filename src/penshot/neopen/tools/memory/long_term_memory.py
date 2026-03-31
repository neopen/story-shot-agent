"""
@FileName: long_term_memory.py
@Description: 长期记忆 - 向量数据库 + 持久化
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/30 13:09
"""
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from penshot.logger import info, error, warning, debug


class LongTermMemory:
    """长期记忆 - 基于向量数据库，支持持久化和元数据过滤"""

    def __init__(self, embeddings: Embeddings, collection_name: str = "penshot_memory",
                 persist_directory: Optional[str] = "data/output/memory"):
        """
        初始化长期记忆

        Args:
            embeddings: 嵌入模型
            collection_name: 集合名称
            persist_directory: 持久化目录
        """
        # 确保日志目录存在
        self.embeddings = embeddings or OpenAIEmbeddings()
        self.collection_name = collection_name
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        debug(f"初始化长期记忆: collection={collection_name}, persist={persist_directory}")

        try:
            self.vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=persist_directory
            )
            debug("Chroma 向量存储初始化成功")
        except Exception as e:
            error(f"Chroma 向量存储初始化失败: {e}")
            raise

        # 记忆统计
        self._stats = {
            "total_stored": 0,
            "last_cleanup": None
        }

    def store(self, text: str, metadata: Dict[str, Any]) -> str:
        """存储长期记忆，返回记忆ID"""
        # 生成唯一ID
        memory_id = hashlib.md5(
            f"{text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # 添加时间戳
        metadata.update({
            "memory_id": memory_id,
            "stored_at": datetime.now().isoformat(),
            "text_length": len(text)
        })

        debug(f"存储记忆: id={memory_id}, text_length={len(text)}, metadata={metadata}")

        try:
            self.vectorstore.add_texts(
                texts=[text],
                metadatas=[metadata],
                ids=[memory_id]
            )
            self._stats["total_stored"] += 1
            debug(f"记忆存储成功: {memory_id}, 总数={self._stats['total_stored']}")
        except Exception as e:
            error(f"记忆存储失败: {memory_id}, 错误: {e}")
            raise

        return memory_id

    def store_batch(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> List[str]:
        """批量存储记忆"""
        debug(f"批量存储记忆: count={len(texts)}")
        memory_ids = []
        for i, (text, metadata) in enumerate(zip(texts, metadatas)):
            try:
                memory_id = self.store(text, metadata)
                memory_ids.append(memory_id)
            except Exception as e:
                error(f"批量存储第{i}条记忆失败: {e}")
        debug(f"批量存储完成: 成功={len(memory_ids)}/{len(texts)}")
        return memory_ids

    def retrieve(self, query: str, k: int = 3, score_threshold: float = 0.0) -> List[Dict]:
        """
        检索相关记忆

        Args:
            query: 查询字符串
            k: 返回结果数量
            score_threshold: 相似度阈值（分数越低越相似）

        Returns:
            记忆列表
        """
        debug(f"检索记忆: query='{query[:50]}...', k={k}, threshold={score_threshold}")

        try:
            # 方法1：直接调用 similarity_search_with_score
            results = self.vectorstore.similarity_search_with_score(
                query, k=k
            )
            debug(f"检索到 {len(results)} 条结果")

            # 记录每条结果的分数
            for doc, score in results:
                debug(f"  结果: score={score:.4f}, content={doc.page_content[:50]}...")

            filtered_results = [
                {
                    "content": doc.page_content,
                    "score": score,
                    "metadata": doc.metadata,
                    "memory_id": doc.metadata.get("memory_id")
                }
                for doc, score in results
                if score <= score_threshold  # 注意：分数越小越相似
            ]

            if score_threshold > 0:
                debug(f"过滤后剩余 {len(filtered_results)} 条结果 (阈值={score_threshold})")

            return filtered_results

        except TypeError as e:
            # 如果版本不支持 k 参数
            if "unexpected keyword argument" in str(e) and "k" in str(e):
                warning(f"Chroma 版本可能不支持 k 参数，尝试不带 k 调用: {e}")
                try:
                    results = self.vectorstore.similarity_search_with_score(query)
                    # 手动限制 k
                    results = results[:k]
                    debug(f"手动截取前 {k} 条结果")
                    return [
                        {
                            "content": doc.page_content,
                            "score": score,
                            "metadata": doc.metadata,
                            "memory_id": doc.metadata.get("memory_id")
                        }
                        for doc, score in results
                        if score <= score_threshold
                    ]
                except Exception as e2:
                    error(f"备用检索方法失败: {e2}")
                    return []
            else:
                error(f"检索记忆时发生 TypeError: {e}")
                return []

        except Exception as e:
            error(f"检索记忆失败: {e}")
            return []

    def retrieve_by_filter(self, query: str, filter_dict: Dict[str, Any], k: int = 3) -> List[Document]:
        """按条件过滤检索"""
        debug(f"按条件检索: query='{query[:50]}...', filter={filter_dict}, k={k}")
        try:
            results = self.vectorstore.similarity_search(
                query, k=k, filter=filter_dict
            )
            debug(f"检索到 {len(results)} 条结果")
            return results
        except Exception as e:
            error(f"按条件检索失败: {e}")
            return []

    def retrieve_by_type(self, memory_type: str, query: str, k: int = 3) -> List[Document]:
        """按类型检索记忆"""
        debug(f"按类型检索: type={memory_type}, query='{query[:50]}...'")
        return self.retrieve_by_filter(query, {"type": memory_type}, k)

    def get_by_id(self, memory_id: str) -> Optional[Document]:
        """根据ID获取记忆"""
        debug(f"根据ID获取记忆: {memory_id}")
        try:
            # 尝试通过 metadata 过滤
            results = self.vectorstore.get(where={"memory_id": memory_id})
            ids = results.get("ids", [])
            if ids:
                debug(f"找到记忆: {ids}")
                # 获取文档内容
                docs = self.vectorstore.get_by_ids(ids)
                if docs:
                    return docs[0]
            else:
                debug(f"未找到记忆: {memory_id}")
        except Exception as e:
            error(f"根据ID获取记忆失败: {memory_id}, 错误: {e}")
        return None

    def delete_by_filter(self, filter_dict: Dict[str, Any]) -> int:
        """按条件删除记忆"""
        debug(f"按条件删除记忆: filter={filter_dict}")
        try:
            # 获取所有匹配的文档
            results = self.vectorstore.get(where=filter_dict)
            ids = results.get("ids", [])
            if ids:
                self.vectorstore.delete(ids)
                self._stats["total_stored"] -= len(ids)
                debug(f"删除记忆成功: {len(ids)} 条")
                return len(ids)
            else:
                debug("没有匹配的记忆需要删除")
        except Exception as e:
            error(f"按条件删除记忆失败: {e}")
        return 0

    def delete_old_memories(self, days: int = 30) -> int:
        """删除超过指定天数的记忆"""
        debug(f"删除超过 {days} 天的旧记忆")
        # 简化实现：需要根据 metadata 中的时间过滤
        warning("delete_old_memories 功能尚未完整实现")
        return 0

    def clear_all(self) -> None:
        """清空所有记忆"""
        info(f"清空所有记忆: collection={self.collection_name}")
        try:
            self.vectorstore.delete_collection()
            self.vectorstore = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory.name
            )
            self._stats["total_stored"] = 0
            info("记忆清空成功")
        except Exception as e:
            error(f"清空记忆失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_stored": self._stats["total_stored"],
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory
        }
        debug(f"记忆统计: {stats}")
        return stats

    def similarity_search(self, query: str, k: int = 3) -> List[Dict]:
        """简化的相似度搜索（兼容旧接口）"""
        debug(f"相似度搜索（兼容接口）: query='{query[:50]}...', k={k}")
        return self.retrieve(query, k=k)