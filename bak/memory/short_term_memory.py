"""
@FileName: short_term_memory.py
@Description: 短期记忆 - 滑动窗口 + TTL过期
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 13:06
"""
import time
from collections import deque, OrderedDict
from datetime import datetime
from typing import Dict, Any, Optional, List


class ShortTermMemory:
    """短期记忆 - 基于滑动窗口，支持TTL过期"""

    def __init__(self, max_size: int = 10, ttl_seconds: int = 3600):
        """
        初始化短期记忆

        Args:
            max_size: 最大记忆条数
            ttl_seconds: 记忆存活时间（秒），默认1小时
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.buffer = deque(maxlen=max_size)
        self.current_context: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: Dict[str, float] = {}

    def add(self, key: str, value: Any, metadata: Optional[Dict] = None) -> None:
        """添加记忆"""
        # 清理过期记忆
        self._clean_expired()

        # 更新当前上下文
        self.current_context[key] = value
        self._timestamps[key] = time.time()

        # 移动到末尾（LRU）
        self.current_context.move_to_end(key)

        # 添加到缓冲区
        self.buffer.append({
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "timestamp_epoch": time.time()
        })

        # 限制缓冲区大小
        if len(self.buffer) > self.max_size:
            removed = self.buffer.popleft()
            # 从上下文移除最旧的
            if removed["key"] in self.current_context:
                del self.current_context[removed["key"]]
                del self._timestamps[removed["key"]]

    def get(self, key: str) -> Optional[Any]:
        """获取记忆，同时更新访问时间（LRU）"""
        self._clean_expired()

        if key in self.current_context:
            # 更新访问时间
            self.current_context.move_to_end(key)
            self._timestamps[key] = time.time()
            return self.current_context[key]
        return None

    def get_with_metadata(self, key: str) -> Optional[Dict]:
        """获取记忆及元数据"""
        value = self.get(key)
        if value is None:
            return None

        # 从缓冲区查找元数据
        for item in self.buffer:
            if item["key"] == key:
                return {
                    "value": value,
                    "metadata": item["metadata"],
                    "timestamp": item["timestamp"]
                }

        return {"value": value, "metadata": {}, "timestamp": None}

    def get_recent(self, n: int = 3) -> List[Dict]:
        """获取最近N条记忆"""
        self._clean_expired()
        recent = list(self.buffer)[-n:]
        return [
            {
                "key": item["key"],
                "value": item["value"],
                "metadata": item["metadata"],
                "timestamp": item["timestamp"]
            }
            for item in recent
        ]

    def get_all(self) -> Dict[str, Any]:
        """获取所有当前记忆"""
        self._clean_expired()
        return dict(self.current_context)

    def delete(self, key: str) -> bool:
        """删除指定记忆"""
        if key in self.current_context:
            del self.current_context[key]
            del self._timestamps[key]

            # 从缓冲区移除
            self.buffer = deque(
                [item for item in self.buffer if item["key"] != key],
                maxlen=self.max_size
            )
            return True
        return False

    def clear(self) -> None:
        """清空所有记忆"""
        self.buffer.clear()
        self.current_context.clear()
        self._timestamps.clear()

    def _clean_expired(self) -> None:
        """清理过期的记忆"""
        now = time.time()
        expired_keys = [
            key for key, ts in self._timestamps.items()
            if now - ts > self.ttl_seconds
        ]

        for key in expired_keys:
            if key in self.current_context:
                del self.current_context[key]
            del self._timestamps[key]

            # 从缓冲区移除
            self.buffer = deque(
                [item for item in self.buffer if item["key"] != key],
                maxlen=self.max_size
            )

    def size(self) -> int:
        """获取当前记忆数量"""
        self._clean_expired()
        return len(self.current_context)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        self._clean_expired()
        return {
            "current_size": len(self.current_context),
            "buffer_size": len(self.buffer),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "keys": list(self.current_context.keys())
        }
