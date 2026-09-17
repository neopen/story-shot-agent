"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: llm_cache.py.py
@Description: 带质量控制的多级缓存
@Author: NeoPen
@Time: 2026/5/20 18:14
"""
import hashlib
from datetime import datetime
from typing import Dict, Optional


class LLMCache:
    """LLM 调用缓存，减少重复 API 调用"""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 100):
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self.ttl = ttl_seconds
        self.max_size = max_size

    def _make_key(self, prompt: str, system_prompt: str = "",
                  temperature: float = 0.1,
                  quality_threshold: float = 0.7) -> str:
        """缓存键包含质量要求"""
        content = f"{prompt}|{system_prompt}|{temperature}|{quality_threshold}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, key: str, min_quality_score: float = 0.7) -> Optional[tuple]:
        """获取缓存，同时检查质量分数"""
        if key in self._cache:
            value, timestamp, quality_score = self._cache[key]
            if quality_score >= min_quality_score:
                return value
            # 质量不达标，删除缓存
            del self._cache[key]
        return None

    def set(self, key: str, value: str, quality_score: float = 1.0):
        """存入缓存时记录质量分数"""
        self._cache[key] = (value, datetime.now(), quality_score)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
