"""
@FileName: memory_manager.py
@Description: 统一记忆管理器 - 支持多层级记忆和自动降级
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/30 13:10
"""
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict, List

from penshot.logger import error
from penshot.neopen.tools.memory.long_term_memory import LongTermMemory
from penshot.neopen.tools.memory.medium_term_memory import MediumTermMemory
from penshot.neopen.tools.memory.short_term_memory import ShortTermMemory


class MemoryType(str, Enum):
    """记忆类型枚举"""
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    AUTO = "auto"  # 自动选择


@dataclass
class MemoryEntry:
    """记忆条目"""
    key: str
    value: Any
    memory_type: MemoryType
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    last_access: float = field(default_factory=time.time)


class MemoryManager:
    """统一记忆管理器 - 支持多层级记忆和自动降级"""

    def __init__(
            self,
            llm,
            embeddings,
            enable_long_term: bool = False,
            short_term_size: int = 20,
            short_term_ttl: int = 3600,
            medium_term_max: int = 50,
            long_term_collection: str = "penshot_memory"
    ):
        """
        初始化记忆管理器

        Args:
            llm: 语言模型实例
            enable_long_term: 是否启用长期记忆
            short_term_size: 短期记忆容量
            short_term_ttl: 短期记忆TTL（秒）
            medium_term_max: 中期记忆最大阶段数
            long_term_collection: 长期记忆集合名
        """
        self.llm = llm
        self.embeddings = embeddings

        # 初始化各层级记忆
        self.short_term = ShortTermMemory(
            max_size=short_term_size,
            ttl_seconds=short_term_ttl
        )
        self.medium_term = MediumTermMemory(
            llm=llm,
            max_stages=medium_term_max
        )
        self.long_term = LongTermMemory(
            embeddings=self.embeddings,
            collection_name=long_term_collection
        ) if enable_long_term else None

        # 记忆访问统计
        self._access_stats: Dict[str, MemoryEntry] = {}
        self._enable_long_term = enable_long_term

    def remember(
            self,
            key: str,
            value: Any,
            memory_type: MemoryType = MemoryType.SHORT,
            metadata: Optional[Dict] = None,
            tags: Optional[List[str]] = None
    ) -> None:
        """
        存储记忆

        Args:
            key: 记忆键
            value: 记忆值
            memory_type: 记忆类型
            metadata: 元数据
            tags: 标签
        """
        metadata = metadata or {}
        if tags:
            metadata["tags"] = tags

        entry = MemoryEntry(
            key=key,
            value=value,
            memory_type=memory_type,
            metadata=metadata
        )
        self._access_stats[key] = entry

        if memory_type == MemoryType.MEDIUM:
            # 中期记忆存储摘要
            self.medium_term.summarize_stage(key, str(value), metadata)
        elif memory_type == MemoryType.LONG and self.long_term:
            # 长期记忆存储向量
            self.long_term.store(str(value), {"key": key, **metadata})
        else:
            # 短期记忆
            self.short_term.add(key, value, metadata)

    def recall(
            self,
            key: str,
            memory_type: Optional[MemoryType] = None,
            default: Any = None
    ) -> Optional[Any]:
        """
        回忆记忆

        Args:
            key: 记忆键
            memory_type: 指定记忆类型，None时自动降级查找
            default: 默认返回值
        """
        # 更新访问统计
        if key in self._access_stats:
            self._access_stats[key].access_count += 1
            self._access_stats[key].last_access = time.time()

        try:
            # 指定类型查找
            if memory_type:
                if memory_type == MemoryType.MEDIUM:
                    return self.medium_term.get_stage_summary(key) or default
                elif memory_type == MemoryType.LONG and self.long_term:
                    results = self.long_term.retrieve(key, k=1)
                    if results:
                        return results[0]["content"]
                    return default
                else:
                    return self.short_term.get(key) or default

            # 自动降级查找
            # 1. 短期记忆
            value = self.short_term.get(key)
            if value is not None:
                return value

            # 2. 中期记忆
            value = self.medium_term.get_stage_summary(key)
            if value is not None:
                return value

            # 3. 长期记忆
            if self.long_term:
                results = self.long_term.retrieve(key, k=1)
                if results:
                    return results[0]["content"]

        except Exception as e:
            error(f"记忆检索异常: {e}")

        return default

    def recall_with_metadata(self, key: str) -> Optional[Dict]:
        """获取记忆及元数据"""
        # 短期记忆
        result = self.short_term.get_with_metadata(key)
        if result:
            return {"value": result["value"], "metadata": result["metadata"], "source": "short"}

        # 中期记忆
        value = self.medium_term.get_stage_summary(key)
        if value:
            return {"value": value, "metadata": self.medium_term.get_stage_metadata(key), "source": "medium"}

        # 长期记忆
        if self.long_term:
            results = self.long_term.retrieve(key, k=1)
            if results:
                return {"value": results[0]["content"], "metadata": results[0]["metadata"], "source": "long"}

        return None

    def recall_by_tags(self, tags: List[str], k: int = 5) -> List[Dict]:
        """根据标签检索记忆"""
        results = []

        # 短期记忆按标签筛选
        short_results = self.short_term.get_recent(k)
        for r in short_results:
            if any(tag in r.get("metadata", {}).get("tags", []) for tag in tags):
                results.append(r)

        # 长期记忆按标签检索
        if self.long_term:
            for tag in tags:
                long_results = self.long_term.retrieve_by_filter(
                    tag, {"tags": tag}, k
                )
                for doc in long_results:
                    results.append({
                        "key": doc.metadata.get("key"),
                        "value": doc.page_content,
                        "metadata": doc.metadata,
                        "source": "long"
                    })

        return results[:k]

    def get_context(self, query: str, max_tokens: int = 2000) -> str:
        """获取融合上下文"""
        contexts = []
        current_tokens = 0

        # 短期上下文（最高优先级）
        recent = self.short_term.get_recent(5)
        for item in recent:
            ctx = f"[当前] {item['key']}: {str(item['value'])[:200]}"
            contexts.append(ctx)
            current_tokens += len(ctx) // 2  # 粗略估算

        # 中期上下文
        stages = self.medium_term.get_recent_stages(3)
        for stage in stages:
            ctx = f"[阶段] {stage['stage_name']}: {stage['summary'][:200]}"
            if current_tokens + len(ctx) // 2 <= max_tokens:
                contexts.append(ctx)
                current_tokens += len(ctx) // 2

        # 长期上下文（相关性检索）
        if self.long_term and current_tokens < max_tokens:
            long_results = self.long_term.retrieve(query, k=2)
            for r in long_results:
                ctx = f"[历史] {r['content'][:200]}"
                if current_tokens + len(ctx) // 2 <= max_tokens:
                    contexts.append(ctx)
                    current_tokens += len(ctx) // 2

        return "\n".join(contexts)

    def promote_to_medium(self, key: str) -> bool:
        """将短期记忆提升为中期记忆"""
        value = self.short_term.get(key)
        if value is not None:
            self.medium_term.summarize_stage(key, str(value))
            return True
        return False

    def promote_to_long(self, key: str) -> bool:
        """将中期记忆提升为长期记忆"""
        if not self.long_term:
            return False

        value = self.medium_term.get_stage_full(key)
        if value is not None:
            metadata = self.medium_term.get_stage_metadata(key) or {}
            self.long_term.store(value, {"key": key, **metadata})
            return True
        return False

    def delete(self, key: str) -> bool:
        """删除记忆"""
        # 从各层删除
        deleted = False
        if self.short_term.delete(key):
            deleted = True
        if self.medium_term.clear_stage(key):
            deleted = True
        if self.long_term:
            self.long_term.delete_by_filter({"key": key})
        if key in self._access_stats:
            del self._access_stats[key]
        return deleted

    def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        """清空指定类型记忆"""
        if memory_type is None or memory_type == MemoryType.SHORT:
            self.short_term.clear()
        if memory_type is None or memory_type == MemoryType.MEDIUM:
            self.medium_term.clear_all()
        if memory_type is None or memory_type == MemoryType.LONG and self.long_term:
            self.long_term.clear_all()

        if memory_type is None:
            self._access_stats.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "short_term": self.short_term.get_stats(),
            "medium_term": self.medium_term.get_stats(),
            "long_term": self.long_term.get_stats() if self.long_term else {"enabled": False},
            "access_stats": {
                "total_keys": len(self._access_stats),
                "most_accessed": sorted(
                    self._access_stats.values(),
                    key=lambda x: x.access_count,
                    reverse=True
                )[:5]
            }
        }

    def get_most_accessed(self, n: int = 5) -> List[Dict]:
        """获取最常访问的记忆"""
        sorted_entries = sorted(
            self._access_stats.values(),
            key=lambda x: x.access_count,
            reverse=True
        )[:n]
        return [
            {
                "key": e.key,
                "access_count": e.access_count,
                "last_access": e.last_access,
                "memory_type": e.memory_type
            }
            for e in sorted_entries
        ]
