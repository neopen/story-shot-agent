"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: task_repository.py
@Description: Task record storage abstraction for local memory / Redis.
@Author: NeoPen
@Time: 2026/4/28 17:08
"""

from __future__ import annotations

import copy
import json
from threading import RLock
from typing import Any, Callable, Dict, Iterator, Optional

from penshot.logger import debug, error, warning
from penshot.utils.obj_utils import obj_to_dict
from penshot.utils.redis_utils import RedisClient


class TaskRepository:
    """负责任务记录的底层读写，不处理业务状态机。"""

    def __init__(self, task_ttl_seconds: int = 86400):
        self.task_ttl_seconds = task_ttl_seconds
        self._lock = RLock()
        self._local_tasks: Dict[str, Dict[str, Any]] = {}
        self._local_raw_configs: Dict[str, Any] = {}
        # 每个任务一把更新锁，保证“读-改-写”在进程内串行，避免并发进度更新互相覆盖
        self._update_locks: Dict[str, RLock] = {}

        self.use_redis = False
        self.redis_client = RedisClient()
        try:
            self.redis = self.redis_client.get_client()
            self.use_redis = True
            debug("Redis 客户端初始化成功")
        except Exception as e:
            warning(f"Redis 不可用，将使用内存存储: {e}")
            self.redis = None
            self.use_redis = False

    def redis_key(self, task_id: str) -> str:
        return f"penshot:tasks:data:{task_id}"

    def redis_tasks_set_key(self) -> str:
        return "penshot:tasks:ids"

    def create_task(self, task_id: str, record: Dict[str, Any], raw_config: Any = None) -> None:
        # raw_config 只保存在本进程内存中（不参与 Redis 序列化），
        # 供工作流缓存复用/清理使用；Redis 模式下也必须记录，
        # 否则 get_raw_config 恒为 None，缓存清理将永远失效。
        with self._lock:
            self._local_raw_configs[task_id] = raw_config

        if self.use_redis and self.redis is not None:
            key = self.redis_key(task_id)
            payload = json.dumps(obj_to_dict(record), ensure_ascii=False)
            if self.task_ttl_seconds < 1:
                self.redis.set(key, payload)
                self.redis.sadd(self.redis_tasks_set_key(), task_id)
            else:
                # 使用 set(key, payload, ex=ttl) 代替已弃用的 setex
                self.redis.set(key, payload, ex=self.task_ttl_seconds)
                self.redis.sadd(self.redis_tasks_set_key(), task_id)
                self.redis.expire(self.redis_tasks_set_key(), self.task_ttl_seconds * 2)
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    raise ValueError(f"task_id already exists: {task_id}")
                self._local_tasks[task_id] = record

    def read_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self.use_redis and self.redis:
            raw = self.redis.get(self.redis_key(task_id))
            if not raw:
                debug(f"Redis 中未找到任务: {task_id}")
                return self._read_local_task(task_id)
            try:
                return json.loads(raw)
            except Exception as e:
                warning(f"Redis 数据反序列化失败，尝试本地存储: task_id={task_id}, error={e}")
                return self._read_local_task(task_id)
        return self._read_local_task(task_id)

    def write_task(self, task_id: str, record: Dict[str, Any]) -> bool:
        if self.use_redis and self.redis:
            try:
                key = self.redis_key(task_id)
                payload = json.dumps(obj_to_dict(record), ensure_ascii=False)
                # 使用 set(key, payload, ex=ttl) 代替已弃用的 setex；
                # ttl 小于 1 表示不设置过期时间
                if self.task_ttl_seconds < 1:
                    self.redis.set(key, payload)
                else:
                    self.redis.set(key, payload, ex=self.task_ttl_seconds)
                return True
            except Exception as e:
                error(f"写入 Redis 任务失败: task_id={task_id}, error={e}")
                return False
        with self._lock:
            if task_id not in self._local_tasks:
                return False
            self._local_tasks[task_id] = record
            return True

    def _get_update_lock(self, task_id: str) -> RLock:
        """获取指定任务的更新锁（不存在时创建）"""
        with self._lock:
            lock = self._update_locks.get(task_id)
            if lock is None:
                lock = RLock()
                self._update_locks[task_id] = lock
            return lock

    def update_task(self, task_id: str, updater: Callable[[Dict[str, Any]], None]) -> bool:
        # 读-改-写整体加锁：Redis 与内存模式下都不会丢失并发更新
        with self._get_update_lock(task_id):
            record = self.read_task(task_id)
            if not record:
                return False
            updater(record)
            return self.write_task(task_id, record)

    def delete_task(self, task_id: str) -> bool:
        if self.use_redis and self.redis:
            try:
                self.redis.delete(self.redis_key(task_id))
                self.redis.srem(self.redis_tasks_set_key(), task_id)
            except Exception as e:
                error(f"从 Redis 删除任务失败: task_id={task_id}, error={e}")
                return False
            with self._lock:
                self._local_raw_configs.pop(task_id, None)
                self._update_locks.pop(task_id, None)
            return True
        with self._lock:
            if task_id not in self._local_tasks:
                return False
            self._local_tasks.pop(task_id, None)
            self._local_raw_configs.pop(task_id, None)
            self._update_locks.pop(task_id, None)
            return True

    def list_task_ids(self) -> list[str]:
        if self.use_redis and self.redis:
            try:
                return list(self.redis.smembers(self.redis_tasks_set_key()))
            except Exception as e:
                error(f"从 Redis 获取任务列表失败: {e}")
                return []
        with self._lock:
            return list(self._local_tasks.keys())

    def get_raw_config(self, task_id: str) -> Any:
        with self._lock:
            return self._local_raw_configs.get(task_id)

    def set_raw_config(self, task_id: str, raw_config: Any) -> None:
        with self._lock:
            self._local_raw_configs[task_id] = raw_config

    def pop_raw_config(self, task_id: str) -> Any:
        with self._lock:
            return self._local_raw_configs.pop(task_id, None)

    def iter_raw_configs(self) -> Iterator[tuple[str, Any]]:
        with self._lock:
            yield from list(self._local_raw_configs.items())

    def import_snapshot(self, snapshot: Dict[str, Any]) -> str:
        task_id = snapshot.get("task_id")
        if not task_id:
            raise ValueError("snapshot must contain task_id")
        self.create_task(task_id, snapshot, raw_config=None)
        return task_id

    def _read_local_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._local_tasks.get(task_id)
            return copy.deepcopy(rec) if rec is not None else None
