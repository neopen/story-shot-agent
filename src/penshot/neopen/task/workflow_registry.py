"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: workflow_registry.py
@Description: In-memory workflow registry with LRU eviction.
@Author: NeoPen
@Time: 2026/4/28 17:02
"""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any, List, Optional

from penshot.logger import debug, error, info, warning


class WorkflowRegistry:
    """负责工作流实例缓存、复用和生命周期管理。"""

    def __init__(self, max_cache_size: int = 64):
        self.max_cache_size = max_cache_size
        self._cache: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            workflow = self._cache.get(key)
            if workflow is None:
                return None
            try:
                self._cache.move_to_end(key)
            except Exception as e:
                warning(f"更新工作流缓存顺序失败: {e}")
            return workflow

    def put(self, key: str, workflow: Any) -> None:
        with self._lock:
            if self.max_cache_size > 0 and len(self._cache) >= self.max_cache_size:
                try:
                    oldest_key, _ = self._cache.popitem(last=False)
                    info(f"清理最旧的工作流缓存: {oldest_key}")
                except Exception as e:
                    warning(f"清理工作流缓存失败: {e}")
            self._cache[key] = workflow

    def pop(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._cache.pop(key, None)

    def clear(self) -> int:
        with self._lock:
            cache_size = len(self._cache)
            self._cache.clear()
            return cache_size

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._cache.keys())

    def set_max_cache_size(self, size: int) -> None:
        if not isinstance(size, int) or size < 0:
            raise ValueError("max_cache_size must be a non-negative integer")
        with self._lock:
            old_size = self.max_cache_size
            self.max_cache_size = size
            while self.max_cache_size > 0 and len(self._cache) > self.max_cache_size:
                self._cache.popitem(last=False)
            info(f"更新最大缓存大小: {old_size} -> {size}")

    def shutdown(self, close_workflows: bool = True) -> int:
        keys = self.keys()
        for key in keys:
            workflow = self.get(key)
            if not workflow:
                continue
            if close_workflows:
                self._try_close_workflow(key, workflow)
        return self.clear()

    def _try_close_workflow(self, key: str, workflow: Any) -> None:
        for method_name in ("close", "shutdown", "stop", "terminate"):
            method = getattr(workflow, method_name, None)
            if callable(method):
                try:
                    method()
                    debug(f"关闭工作流: {key}")
                except Exception as e:
                    error(f"关闭工作流失败: {key}, error={e}")
                break
