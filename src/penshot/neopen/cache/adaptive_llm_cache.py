"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: adaptive_llm_cache.py
@Description: 短期缓存 + 人工反馈清除
@Author: NeoPen
@Time: 2026/5/20 18:52
"""
from datetime import datetime, timedelta
from typing import Optional


class AdaptiveLLMCache:
    """自适应 LLM 缓存 - 支持人工反馈"""

    def __init__(self):
        self._cache = {}
        self._rejected_keys = set()  # 被用户拒绝的缓存
        self._accepted_keys = set()  # 被用户接受的缓存

    def get(self, key: str) -> Optional[str]:
        # 被拒绝的缓存不再使用
        if key in self._rejected_keys:
            return None

        if key in self._cache:
            value, timestamp = self._cache[key]
            # 24小时后自动过期
            if datetime.now() - timestamp < timedelta(hours=24):
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: str):
        self._cache[key] = (value, datetime.now())

    def accept(self, key: str):
        """用户接受此结果，提升缓存优先级"""
        self._accepted_keys.add(key)
        self._rejected_keys.discard(key)

    def reject(self, key: str):
        """用户拒绝此结果，清除并加入黑名单"""
        self._rejected_keys.add(key)
        if key in self._cache:
            del self._cache[key]

    def get_stats(self) -> dict:
        return {
            "cached_items": len(self._cache),
            "accepted": len(self._accepted_keys),
            "rejected": len(self._rejected_keys),
        }
