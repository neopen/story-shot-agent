from __future__ import annotations

from penshot.neopen.task.task_models import TaskStatus
from penshot.utils.log_utils import print_log_exception
from penshot.utils.obj_utils import obj_to_dict
from penshot.utils.redis_utils import RedisClient

"""
@FileName: task_manager.py
@Description: TaskManager with optional Redis backend.
    - If redis_url or redis_client is provided, tasks are persisted in Redis (JSON per task, and an ID set).
    - Otherwise tasks are stored in-process memory (protected by RLock).
    - Workflow cache and pipeline instances remain in-memory.
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 16:42
"""

import copy
import json
import uuid
from dataclasses import is_dataclass
from datetime import datetime, timezone, timedelta
from threading import RLock
from collections import OrderedDict
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from penshot.logger import info, error

if TYPE_CHECKING:
    from penshot.neopen.agent import MultiAgentPipeline
from penshot.neopen.shot_config import ShotConfig


class TaskManager:
    """任务状态管理器，支持内存或 Redis 后端（可选）。"""

    def __init__(self, max_workflow_cache_size: int = 64):
        # in-memory task store (used when Redis not configured)
        self._local_tasks: Dict[str, Dict[str, Any]] = {}
        # raw config objects for internal use when local
        self._local_raw_configs: Dict[str, Any] = {}

        # workflow cache (in-memory) and pipeline factory
        self.workflow_cache: "OrderedDict[str, Any]" = OrderedDict()
        self.max_workflow_cache_size = max_workflow_cache_size
        self.pipeline_factory = None

        # concurrency
        self._lock = RLock()

        # metrics (local if no redis; if redis configured, metrics stored in redis keys)
        self._metrics = {"created": 0, "completed": 0, "failed": 0}

        # redis client (lazy init) or None
        self.use_redis = False
        self.redis_client = RedisClient()
        try:
            self.redis = self.redis_client.get_client()
            self.use_redis = True
        except Exception:
            # redis not available
            self.redis = None
            self.use_redis = False

    # ---------------------- serialization helpers ----------------------
    def _safe_serialize(self, value: Any) -> Any:
        from enum import Enum

        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        if is_dataclass(value):
            try:
                return {k: self._safe_serialize(v) for k, v in vars(value).items()}
            except Exception:
                return str(value)
        if isinstance(value, dict):
            res = {}
            for k, v in value.items():
                try:
                    key = str(k)
                except Exception:
                    key = json.dumps(k, default=str)
                res[key] = self._safe_serialize(v)
            return res
        if isinstance(value, (list, tuple, set)):
            return [self._safe_serialize(v) for v in value]
        if isinstance(value, Enum):
            return getattr(value, "value", getattr(value, "name", str(value)))
        try:
            return json.loads(json.dumps(value))
        except Exception:
            return str(value)

    def _serialize_config(self, config: Any) -> Dict[str, Any]:
        try:
            if config is None:
                return {}
            return self._safe_serialize(config) or {}
        except Exception:
            return {"raw": str(config)}

    def _config_key(self, config: Any) -> str:
        """Generate a stable key for a config (sha256 of JSON)"""
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception:
            payload = str(config)
        try:
            import hashlib

            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
        except Exception:
            # fallback to uuid5-based key
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

    # ---------------------- redis helpers ----------------------
    def _redis_key(self, task_id: str) -> str:
        return f"penshot:task:{task_id}"

    def _redis_tasks_set_key(self) -> str:
        return "penshot:tasks:ids"

    def _redis_metrics_key(self, name: str) -> str:
        return f"penshot:tasks:metrics:{name}"

    # ---------------------- core operations ----------------------
    def create_task(self, script: str, config: Optional[ShotConfig] = None, task_id: str = None) -> str:
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a non-empty string")
        task_id = task_id or str(uuid.uuid4())

        record = {
            "task_id": task_id,
            "script": script,
            "config": config,
            "status": TaskStatus.PENDING,
            "stage": "initialized",
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
            "callbacks": [],
        }

        if self.use_redis and self.redis is not None:
            key = self._redis_key(task_id)
            # store JSON and add to set
            try:
                self.redis.set(key, json.dumps(obj_to_dict(record), ensure_ascii=False))
                self.redis.sadd(self._redis_tasks_set_key(), task_id)
                # increment metrics in redis
                try:
                    self.redis.incr(self._redis_metrics_key("created"))
                except Exception:
                    pass
            except Exception as e:
                print(f"Redis 添加任务失败: {e}")
                print_log_exception()
                # fallback to local
                with self._lock:
                    self._local_tasks[task_id] = record
                    self._local_raw_configs[task_id] = config
                    self._metrics["created"] += 1
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    raise ValueError(f"task_id already exists: {task_id}")
                self._local_tasks[task_id] = record
                self._local_raw_configs[task_id] = config
                self._metrics["created"] += 1

        info(f"创建任务: {task_id}")
        return task_id

    def _read_record_local(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._local_tasks.get(task_id)
            return copy.deepcopy(rec) if rec is not None else None

    def _read_record_redis(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not self.redis:
            return self._read_record_local(task_id)
        key = self._redis_key(task_id)
        raw = self.redis.get(key)
        if not raw:
            return self._read_record_local(task_id)
        try:
            return json.loads(raw)
        except Exception:
            return self._read_record_local(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self.use_redis and self.redis:
            return self._read_record_redis(task_id)
        return self._read_record_local(task_id)

    def update_task_progress(self, task_id: str, stage: str, progress: float = None):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            # simple read-modify-write
            raw = self.redis.get(key)
            if not raw:
                return
            try:
                rec = json.loads(raw)
            except Exception:
                return
            rec["stage"] = stage
            if progress is not None:
                try:
                    p = float(progress)
                    rec["progress"] = max(0.0, min(100.0, p))
                except Exception:
                    pass
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    return
                if stage is not None:
                    self._local_tasks[task_id]["stage"] = stage
                if progress is not None:
                    try:
                        p = float(progress)
                        self._local_tasks[task_id]["progress"] = max(0.0, min(100.0, p))
                    except Exception:
                        pass
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def update_task_result(self, task_id: str, partial_result: Dict[str, Any]) -> bool:
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            # optimistic retry using WATCH
            tries = 3
            for _ in range(tries):
                pipe = None
                try:
                    pipe = self.redis.pipeline()
                    pipe.watch(key)
                    raw = self.redis.get(key)
                    if not raw:
                        try:
                            if pipe is not None:
                                pipe.unwatch()
                        except Exception:
                            pass
                        return False
                    rec = json.loads(raw)
                    cur = rec.get("result") or {}
                    if not isinstance(cur, dict):
                        cur = {}
                    try:
                        cur.update(partial_result)
                    except Exception:
                        cur = partial_result
                    rec["result"] = cur
                    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                    pipe.multi()
                    pipe.set(key, json.dumps(rec, ensure_ascii=False))
                    pipe.execute()
                    return True
                except Exception:
                    try:
                        if pipe is not None:
                            pipe.reset()
                    except Exception:
                        pass
                    continue
            return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    return False
                cur = self._local_tasks[task_id].get("result") or {}
                try:
                    cur.update(partial_result)
                except Exception:
                    cur = partial_result
                self._local_tasks[task_id]["result"] = cur
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                return True

    def update_task_batch(self, task_id: str, batch_id: str) -> bool:
        """
        更新任务的批次ID

        Args:
            task_id: 任务ID
            batch_id: 批次ID

        Returns:
            bool: 是否成功
        """
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                return False
            try:
                rec = json.loads(raw)
                rec["batch_id"] = batch_id
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                return True
            except Exception:
                return False
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    self._local_tasks[task_id]["batch_id"] = batch_id
                    self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    return True
            return False

    def get_tasks_by_batch(self, batch_id: str) -> List[Dict[str, Any]]:
        """
        根据批次ID获取所有任务

        Args:
            batch_id: 批次ID

        Returns:
            List[Dict]: 任务列表
        """
        tasks = []

        if self.use_redis and self.redis:
            try:
                task_ids = self.list_tasks()
                for task_id in task_ids:
                    task = self.get_task(task_id)
                    if task and task.get("batch_id") == batch_id:
                        tasks.append(task)
            except Exception as e:
                error(f"从 Redis 获取批次任务失败: {e}")
        else:
            with self._lock:
                for task_id, task in self._local_tasks.items():
                    if task.get("batch_id") == batch_id:
                        tasks.append(copy.deepcopy(task))

        return tasks

    def complete_task(self, task_id: str, result: Dict[str, Any]):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                return
            try:
                rec = json.loads(raw)
            except Exception:
                return
            rec["status"] = TaskStatus.SUCCESS if result.get("success", False) else TaskStatus.FAILED
            rec["result"] = result
            rec["error"] = result.get("error")
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec["completed_at"] = datetime.now(timezone.utc).isoformat()
            self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
            try:
                if result.get("success", False):
                    self.redis.incr(self._redis_metrics_key("completed"))
                else:
                    self.redis.incr(self._redis_metrics_key("failed"))
            except Exception:
                pass
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    self._local_tasks[task_id]["status"] = TaskStatus.SUCCESS if result.get("success", False) else TaskStatus.FAILED
                    self._local_tasks[task_id]["result"] = result
                    self._local_tasks[task_id]["error"] = result.get("error")
                    self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._local_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
                    try:
                        if result.get("success", False):
                            self._metrics["completed"] += 1
                        else:
                            self._metrics["failed"] += 1
                    except Exception:
                        pass

    def fail_task(self, task_id: str, error_message: str):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                return
            try:
                rec = json.loads(raw)
            except Exception:
                return
            rec["status"] = TaskStatus.FAILED
            rec["error"] = error_message
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
            try:
                self.redis.incr(self._redis_metrics_key("failed"))
            except Exception:
                pass
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    self._local_tasks[task_id]["status"] = TaskStatus.FAILED
                    self._local_tasks[task_id]["error"] = error_message
                    self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    try:
                        self._metrics["failed"] += 1
                    except Exception:
                        pass

    def list_tasks(self) -> List[str]:
        if self.use_redis and self.redis:
            try:
                return list(self.redis.smembers(self._redis_tasks_set_key()))
            except Exception:
                return []
        with self._lock:
            return list(self._local_tasks.keys())

    def delete_task(self, task_id: str, cleanup_workflow: bool = True) -> bool:
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            try:
                self.redis.delete(key)
                self.redis.srem(self._redis_tasks_set_key(), task_id)
            except Exception:
                return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    return False
                self._local_tasks.pop(task_id, None)
                self._local_raw_configs.pop(task_id, None)

        if cleanup_workflow:
            # remove workflow cache if no other tasks use same config
            try:
                cfg = None
                if self.use_redis and self.redis:
                    # best-effort: try to read raw config is not stored in redis in raw form, skip
                    cfg = None
                else:
                    cfg = self._local_raw_configs.get(task_id)
                if cfg is not None:
                    key = self._config_key(cfg) if hasattr(self, "_config_key") else None
                    if key and key in self.workflow_cache:
                        # check if any other local task uses same config
                        still_used = False
                        for other_id, other_cfg in self._local_raw_configs.items():
                            if other_id == task_id:
                                continue
                            if hasattr(self, "_config_key") and self._config_key(other_cfg) == key:
                                still_used = True
                                break
                        if not still_used:
                            self.workflow_cache.pop(key, None)
            except Exception:
                pass

        return True

    # keep get_workflow behavior similar to previous (in-memory pipeline cache)
    def get_workflow(self, task_id: Optional[str] = None, config: Optional[Any] = None) -> "Any":
        # prefer local raw config when available
        if task_id is not None and (config is None or isinstance(config, dict)):
            with self._lock:
                raw = self._local_raw_configs.get(task_id)
            if raw is not None:
                config = raw

        # compute cache key (use serialized config JSON as key)
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception:
            payload = str(config)
        key = str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

        with self._lock:
            pipeline = self.workflow_cache.get(key)
            if pipeline is not None:
                try:
                    self.workflow_cache.move_to_end(key)
                except Exception:
                    pass
                return pipeline

        # create pipeline (use factory if provided)
        if getattr(self, "pipeline_factory", None) is not None:
            pipeline = self.pipeline_factory(task_id, config)
        else:
            from penshot.neopen.agent import MultiAgentPipeline  # type: ignore

            pipeline = MultiAgentPipeline(task_id, config)

        # insert into LRU cache
        with self._lock:
            if self.max_workflow_cache_size > 0 and len(self.workflow_cache) >= self.max_workflow_cache_size:
                try:
                    oldest_key, _ = self.workflow_cache.popitem(last=False)
                    info(f"Evicted oldest workflow cache key: {oldest_key}")
                except Exception:
                    pass
            self.workflow_cache[key] = pipeline

        return pipeline

    # ---------------------- utility methods ----------------------
    def clear_workflow_cache(self):
        with self._lock:
            self.workflow_cache.clear()

    def get_cached_workflow_keys(self) -> List[str]:
        with self._lock:
            return list(self.workflow_cache.keys())

    def get_metrics(self) -> Dict[str, int]:
        if self.use_redis and self.redis:
            try:
                return {
                    "created": int(self.redis.get(self._redis_metrics_key("created")) or 0),
                    "completed": int(self.redis.get(self._redis_metrics_key("completed")) or 0),
                    "failed": int(self.redis.get(self._redis_metrics_key("failed")) or 0),
                }
            except Exception:
                return dict(self._metrics)
        with self._lock:
            return dict(self._metrics)

    def set_max_workflow_cache_size(self, size: int):
        if not isinstance(size, int) or size < 0:
            raise ValueError("max_workflow_cache_size must be a non-negative integer")
        with self._lock:
            self.max_workflow_cache_size = size
            try:
                while self.max_workflow_cache_size > 0 and len(self.workflow_cache) > self.max_workflow_cache_size:
                    self.workflow_cache.popitem(last=False)
            except Exception:
                pass

    def export_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self.use_redis and self.redis:
            return self._read_record_redis(task_id)
        return self._read_record_local(task_id)

    def import_task_snapshot(self, snapshot: Dict[str, Any]) -> str:
        task_id = snapshot.get("task_id") or str(uuid.uuid4())
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            try:
                self.redis.set(key, json.dumps(snapshot, ensure_ascii=False))
                self.redis.sadd(self._redis_tasks_set_key(), task_id)
            except Exception:
                # fallback to local
                with self._lock:
                    self._local_tasks[task_id] = snapshot
                    self._local_raw_configs[task_id] = None
        else:
            with self._lock:
                self._local_tasks[task_id] = snapshot
                self._local_raw_configs[task_id] = None
        return task_id

    def shutdown(self, close_pipelines: bool = True):
        # attempt to call common cleanup methods on pipelines
        with self._lock:
            keys = list(self.workflow_cache.keys())
        for k in keys:
            with self._lock:
                pipeline = self.workflow_cache.get(k)
            if not pipeline:
                continue
            if close_pipelines:
                for method_name in ("close", "shutdown", "stop", "terminate"):
                    meth = getattr(pipeline, method_name, None)
                    if callable(meth):
                        try:
                            meth()
                        except Exception:
                            pass
                        break
        with self._lock:
            self.workflow_cache.clear()

    def set_task_callback(self, task_id: str, callback_url: str) -> bool:
        """Set or update the callback URL associated with a task.

        For Redis: perform a read-modify-write.
        For local: update the in-memory record.
        """
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                return False
            try:
                rec = json.loads(raw)
            except Exception:
                return False
            rec.setdefault("callbacks", [])
            # replace callbacks with single callback
            rec["callbacks"] = [callback_url]
            rec["callback_url"] = callback_url
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                return True
            except Exception:
                return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    return False
                self._local_tasks[task_id].setdefault("callbacks", [])
                self._local_tasks[task_id]["callbacks"] = [callback_url]
                self._local_tasks[task_id]["callback_url"] = callback_url
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                return True


#     ============================ 恢复任务 ================================
    def get_pending_tasks(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """
        获取所有未完成的任务（PENDING 或 PROCESSING 状态）

        Args:
            max_age_hours: 最大任务年龄（小时），只返回创建时间在此范围内的任务

        Returns:
            List[Dict]: 未完成的任务列表
        """
        pending_tasks = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        if self.use_redis and self.redis:
            try:
                # 从 Redis 获取所有任务ID
                task_ids = self.list_tasks()
                for task_id in task_ids:
                    task = self.get_task(task_id)
                    if task:
                        status = task.get("status")
                        # 只处理未完成的任务
                        if status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
                            # 检查任务创建时间
                            created_at = task.get("created_at")
                            if created_at:
                                try:
                                    if isinstance(created_at, str):
                                        created_at_dt = datetime.fromisoformat(created_at)
                                    else:
                                        created_at_dt = created_at

                                    # 只保留两小时内的任务
                                    if created_at_dt >= cutoff_time:
                                        pending_tasks.append(task)
                                except Exception as e:
                                    error(f"解析任务创建时间失败: {task_id}, 错误: {e}")
                                    # 时间解析失败的任务也加入，但记录警告
                                    pending_tasks.append(task)
            except Exception as e:
                error(f"从 Redis 获取未完成任务失败: {e}")
        else:
            with self._lock:
                for task_id, task in self._local_tasks.items():
                    status = task.get("status")
                    if status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
                        # 检查任务创建时间
                        created_at = task.get("created_at")
                        if created_at:
                            try:
                                if isinstance(created_at, str):
                                    created_at_dt = datetime.fromisoformat(created_at)
                                else:
                                    created_at_dt = created_at

                                # 只保留两小时内的任务
                                if created_at_dt >= cutoff_time:
                                    pending_tasks.append(copy.deepcopy(task))
                            except Exception as e:
                                error(f"解析任务创建时间失败: {task_id}, 错误: {e}")
                                pending_tasks.append(copy.deepcopy(task))
                        else:
                            # 没有创建时间的任务也加入
                            pending_tasks.append(copy.deepcopy(task))

        return pending_tasks

    def get_pending_tasks_with_filter(
            self,
            max_age_hours: int = 2,
            status_filter: Optional[List[TaskStatus]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取符合条件的未完成任务

        Args:
            max_age_hours: 最大任务年龄（小时）
            status_filter: 状态过滤器，默认 [PENDING, PROCESSING]

        Returns:
            List[Dict]: 符合条件的任务列表
        """
        if status_filter is None:
            status_filter = [TaskStatus.PENDING, TaskStatus.PROCESSING]

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        filtered_tasks = []

        if self.use_redis and self.redis:
            try:
                task_ids = self.list_tasks()
                for task_id in task_ids:
                    task = self.get_task(task_id)
                    if task:
                        status = task.get("status")
                        if status in status_filter:
                            created_at = task.get("created_at")
                            if self._is_task_within_age(created_at, cutoff_time):
                                filtered_tasks.append(task)
            except Exception as e:
                error(f"获取任务失败: {e}")
        else:
            with self._lock:
                for task_id, task in self._local_tasks.items():
                    status = task.get("status")
                    if status in status_filter:
                        created_at = task.get("created_at")
                        if self._is_task_within_age(created_at, cutoff_time):
                            filtered_tasks.append(copy.deepcopy(task))

        return filtered_tasks

    def _is_task_within_age(self, created_at: Any, cutoff_time: datetime) -> bool:
        """检查任务是否在有效时间内"""
        if not created_at:
            return True  # 没有时间信息的任务默认恢复

        try:
            if isinstance(created_at, str):
                created_at_dt = datetime.fromisoformat(created_at)
            else:
                created_at_dt = created_at

            return created_at_dt >= cutoff_time
        except Exception:
            return True  # 时间解析失败的任务默认恢复

    def recover_all_pending_tasks(self, max_age_hours: int = 2) -> List[str]:
        """
        恢复所有未完成的任务（只恢复两小时内的任务）

        Args:
            max_age_hours: 最大任务年龄（小时）

        Returns:
            List[str]: 恢复的任务ID列表
        """
        pending_tasks = self.get_pending_tasks(max_age_hours=max_age_hours)
        recovered_ids = []

        for task in pending_tasks:
            task_id = task.get("task_id")
            if self.recover_task(task_id):
                recovered_ids.append(task_id)
                info(f"恢复任务: {task_id}, 创建时间: {task.get('created_at')}")

        return recovered_ids

    def recover_task(self, task_id: str) -> bool:
        """恢复单个任务（将状态重置为 PENDING）"""
        task = self.get_task(task_id)
        if not task:
            return False

        # 只恢复未完成的任务
        if task.get("status") in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            if self.use_redis and self.redis:
                key = self._redis_key(task_id)
                raw = self.redis.get(key)
                if raw:
                    try:
                        rec = json.loads(raw)
                        rec["status"] = TaskStatus.PENDING
                        rec["stage"] = "recovered"
                        rec["progress"] = 0
                        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                        rec.pop("completed_at", None)
                        self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                        return True
                    except Exception:
                        pass
            else:
                with self._lock:
                    if task_id in self._local_tasks:
                        self._local_tasks[task_id]["status"] = TaskStatus.PENDING
                        self._local_tasks[task_id]["stage"] = "recovered"
                        self._local_tasks[task_id]["progress"] = 0
                        self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                        self._local_tasks[task_id].pop("completed_at", None)
                        return True

        return False
#     ============================ 恢复任务 ================================


# end of TaskManager
