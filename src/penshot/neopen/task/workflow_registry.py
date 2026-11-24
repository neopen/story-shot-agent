"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: workflow_registry.py
@Description: In-memory workflow registry with LRU eviction.
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
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
        evicted: Optional[tuple] = None
        with self._lock:
            if self.max_cache_size > 0 and len(self._cache) >= self.max_cache_size:
                try:
                    evicted = self._cache.popitem(last=False)
                    info(f"清理最旧的工作流缓存: {evicted[0]}")
                except Exception as e:
                    warning(f"清理工作流缓存失败: {e}")
            self._cache[key] = workflow

        # 淘汰项需关闭，否则其检查点连接会一直占用
        if evicted is not None:
            self._try_close_workflow(evicted[0], evicted[1])

    def pop(self, key: str) -> Optional[Any]:
        with self._lock:
            workflow = self._cache.pop(key, None)
        if workflow is not None:
            self._try_close_workflow(key, workflow)
        return workflow

    def clear(self, close_workflows: bool = False) -> int:
        with self._lock:
            items = list(self._cache.items())
            self._cache.clear()

        if close_workflows:
            for key, workflow in items:
                self._try_close_workflow(key, workflow)
        return len(items)

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._cache.keys())

    def set_max_cache_size(self, size: int) -> None:
        if not isinstance(size, int) or size < 0:
            raise ValueError("max_cache_size must be a non-negative integer")
        evicted: List[tuple] = []
        with self._lock:
            old_size = self.max_cache_size
            self.max_cache_size = size
            while self.max_cache_size > 0 and len(self._cache) > self.max_cache_size:
                evicted.append(self._cache.popitem(last=False))
            info(f"更新最大缓存大小: {old_size} -> {size}")

        for key, workflow in evicted:
            self._try_close_workflow(key, workflow)

    def shutdown(self, close_workflows: bool = True) -> int:
        return self.clear(close_workflows=close_workflows)

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
