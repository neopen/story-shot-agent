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

from __future__ import annotations

import copy
import json
import random
import uuid
from collections import OrderedDict
from dataclasses import is_dataclass
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Optional, Dict, Any, List

from penshot.logger import info, error, warning, debug
from penshot.neopen.agent.base_models import VideoStyle
# if TYPE_CHECKING:
from penshot.neopen.agent.workflow.workflow_pipeline import MultiAgentPipeline
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_models import TaskStatus, TaskStage
from penshot.utils.hash_utils import text_to_id
from penshot.utils.log_utils import print_log_exception
from penshot.utils.obj_utils import obj_to_dict
from penshot.utils.redis_utils import RedisClient


class TaskManager:
    """任务状态管理器，支持内存或 Redis 后端（可选）。"""

    def __init__(self, max_cache_size: int = 64, task_ttl_seconds: int = 86400):
        """
            Args:
                max_cache_size: 工作流缓存最大数量
                task_ttl_seconds: 任务数据在 Redis 中的过期时间（秒），默认24小时
            """

        # in-memory task store (used when Redis not configured)
        self._local_tasks: Dict[str, Dict[str, Any]] = {}
        # raw config objects for internal use when local
        self._local_raw_configs: Dict[str, Any] = {}

        # workflow cache (in-memory) and pipeline factory
        self.workflow_cache: "OrderedDict[str, Any]" = OrderedDict()
        self.max_cache_size = max_cache_size
        self.task_ttl_seconds = task_ttl_seconds

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
            debug("Redis 客户端初始化成功")
        except Exception as e:
            # redis not available - 这是预期的降级行为，使用 warning 级别
            warning(f"Redis 不可用，将使用内存存储: {e}")
            self.redis = None
            self.use_redis = False


    # ==================== 辅助方法 ====================
    def _generate_script_code(self, script: str) -> str:
        return text_to_id(script)

    def _generate_script_id(self, script_code: str) -> str:
        return "HL" + datetime.now(timezone.utc).strftime("%y%m%d") + script_code

    def _generate_task_id(self, script_code: str) -> str:
        """生成任务ID"""
        # return "TSK" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(10, 99)) + str(hash(script_id))
        return "TSK" + script_code + str(random.randint(1000, 9999))


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
            except Exception as e:
                warning(f"日期序列化失败，使用字符串转换: {e}")
                return str(value)
        if is_dataclass(value):
            try:
                return {k: self._safe_serialize(v) for k, v in vars(value).items()}
            except Exception as e:
                error(f"数据类序列化失败: {e}")
                return str(value)
        if isinstance(value, dict):
            res = {}
            for k, v in value.items():
                try:
                    key = str(k)
                except Exception as e:
                    warning(f"字典键序列化失败: {e}")
                    key = json.dumps(k, default=str)
                res[key] = self._safe_serialize(v)
            return res
        if isinstance(value, (list, tuple, set)):
            return [self._safe_serialize(v) for v in value]
        if isinstance(value, Enum):
            return getattr(value, "value", getattr(value, "name", str(value)))
        try:
            return json.loads(json.dumps(value))
        except Exception as e:
            debug(f"JSON 序列化失败，转为字符串: {e}")
            return str(value)

    def _serialize_config(self, config: Any) -> Dict[str, Any]:
        try:
            if config is None:
                return {}
            return self._safe_serialize(config) or {}
        except Exception as e:
            error(f"配置序列化失败: {e}")
            return {"raw": str(config)}

    def _config_key(self, config: Any) -> str:
        """Generate a stable key for a config (sha256 of JSON)"""
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            warning(f"生成配置键失败，使用字符串转换: {e}")
            payload = str(config)
        try:
            import hashlib
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
        except Exception as e:
            # fallback to uuid5-based key
            error(f"SHA256 计算失败，使用 UUID5 降级: {e}")
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

    # ---------------------- redis helpers ----------------------
    def _redis_key(self, task_id: str) -> str:
        return f"penshot:tasks:data:{task_id}"

    def _redis_tasks_set_key(self) -> str:
        return "penshot:tasks:ids"

    def _redis_metrics_key(self, name: str) -> str:
        return f"penshot:tasks:metrics:{name}"

    # ---------------------- core operations ----------------------
    def create_task(self, script: str, script_id: Optional[str] = None,
                    style: Optional[VideoStyle] = None, config: Optional[ShotConfig] = None) -> (str, str):
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a non-empty string")
        script_code = self._generate_script_code(script)
        script_id = script_id or self._generate_script_id(script_code)
        task_id = self._generate_task_id(script_code)
        shot_config = config or ShotConfig()
        if style:
            shot_config.default_style = style.value

        record = {
            "task_id": task_id,
            "script_id": script_id,
            "script": script,
            "config": shot_config,
            "status": TaskStatus.PENDING,
            "stage": TaskStage.INIT.code,
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
                if self.task_ttl_seconds < 1:
                    self.redis.set(key, json.dumps(obj_to_dict(record), ensure_ascii=False))
                    self.redis.sadd(self._redis_tasks_set_key(), task_id)
                else:
                    self.redis.setex(
                        key,
                        self.task_ttl_seconds,
                        json.dumps(obj_to_dict(record), ensure_ascii=False)
                    )
                    self.redis.sadd(self._redis_tasks_set_key(), task_id)
                    # 为任务ID集合也设置过期时间（可选，使用较长时间）
                    self.redis.expire(self._redis_tasks_set_key(), self.task_ttl_seconds * 2)

                # increment metrics in redis
                try:
                    self.redis.incr(self._redis_metrics_key("created"))
                except Exception as e:
                    # 指标更新失败不影响主流程，使用 warning 级别
                    warning(f"Redis 指标更新失败: {e}")
            except Exception as e:
                # Redis 操作失败，降级到本地存储 - 这是严重的降级，使用 error 级别
                error(f"Redis 添加任务失败，降级到本地存储: {e}")
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
        return script_id, task_id

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
            debug(f"Redis 中未找到任务: {task_id}")
            return self._read_record_local(task_id)
        try:
            return json.loads(raw)
        except Exception as e:
            warning(f"Redis 数据反序列化失败，尝试本地存储: task_id={task_id}, error={e}")
            return self._read_record_local(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self.use_redis and self.redis:
            return self._read_record_redis(task_id)
        return self._read_record_local(task_id)

    def update_task_progress(self, task_id: str, stage: str, progress: float = None):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                debug(f"更新进度时未找到任务: {task_id}")
                return
            try:
                rec = json.loads(raw)
            except Exception as e:
                warning(f"Redis 数据反序列化失败，跳过进度更新: task_id={task_id}, error={e}")
                return
            rec["stage"] = stage
            if progress is not None:
                try:
                    p = float(progress)
                    rec["progress"] = max(0.0, min(100.0, p))
                except Exception as e:
                    warning(f"进度值无效: task_id={task_id}, progress={progress}, error={e}")
                    pass
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            # 更新时刷新过期时间
            self.redis.setex(key, self.task_ttl_seconds, json.dumps(obj_to_dict(rec), ensure_ascii=False))
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    debug(f"本地未找到任务: {task_id}")
                    return
                if stage is not None:
                    self._local_tasks[task_id]["stage"] = stage
                if progress is not None:
                    try:
                        p = float(progress)
                        self._local_tasks[task_id]["progress"] = max(0.0, min(100.0, p))
                    except Exception as e:
                        warning(f"进度值无效: task_id={task_id}, progress={progress}, error={e}")
                        pass
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def update_task_progress_detail(
            self,
            task_id: str,
            stage: TaskStage,
            progress: float = None,
            details: Dict[str, Any] = None
    ) -> bool:
        """
        更新任务详细进度

        Args:
            task_id: 任务ID
            stage: 当前阶段
            progress: 该阶段进度百分比
            details: 阶段详细信息
        """
        # 获取阶段代码（作为字典键）
        stage_code = stage.code

        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"更新进度详情时未找到任务: {task_id}")
                return False
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return False

            # 确保状态为 PROCESSING（如果不是终态）
            current_status = rec.get("status")
            if current_status not in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                rec["status"] = TaskStatus.PROCESSING.value

            # 更新当前阶段
            rec["current_stage"] = stage_code
            rec["stage"] = stage_code
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

            # 初始化进度详情
            if "progress_details" not in rec:
                rec["progress_details"] = {}

            # 更新阶段进度
            if stage_code not in rec["progress_details"]:
                rec["progress_details"][stage_code] = {
                    "name": stage.name,
                    "progress": 0,
                    "status": "processing",
                    "started_at": datetime.now(timezone.utc).isoformat()
                }

            stage_detail = rec["progress_details"][stage_code]
            if progress is not None:
                stage_detail["progress"] = progress
            if details:
                stage_detail["details"] = details

            # 计算整体进度
            try:
                rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
            except Exception as e:
                error(f"计算整体进度失败: task_id={task_id}, error={e}")
                rec["progress"] = 0

            # 更新到 Redis
            self.redis.setex(key, self.task_ttl_seconds, json.dumps(rec, ensure_ascii=False))
            return True
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"本地未找到任务: {task_id}")
                    return False

                rec = self._local_tasks[task_id]

                # 确保状态为 PROCESSING
                current_status = rec.get("status")
                if current_status not in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                    rec["status"] = TaskStatus.PROCESSING.value

                rec["current_stage"] = stage_code
                rec["stage"] = stage_code
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()

                if "progress_details" not in rec:
                    rec["progress_details"] = {}

                if stage_code not in rec["progress_details"]:
                    rec["progress_details"][stage_code] = {
                        "name": stage.name,
                        "progress": 0,
                        "status": "processing",
                        "started_at": datetime.now(timezone.utc).isoformat()
                    }

                stage_detail = rec["progress_details"][stage_code]
                if progress is not None:
                    stage_detail["progress"] = progress
                if details:
                    stage_detail["details"] = details

                try:
                    rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
                except Exception as e:
                    error(f"计算整体进度失败: task_id={task_id}, error={e}")
                    rec["progress"] = 0

                return True

    def complete_stage(
            self,
            task_id: str,
            stage: TaskStage,
            result: Dict[str, Any] = None
    ) -> bool:
        """
        完成一个阶段

        Args:
            task_id: 任务ID
            stage: 完成的阶段
            result: 阶段结果
        """
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"完成阶段时未找到任务: {task_id}")
                return False
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return False

            if "progress_details" not in rec:
                rec["progress_details"] = {}

            if stage.code in rec["progress_details"]:
                rec["progress_details"][stage.code]["progress"] = 100
                rec["progress_details"][stage.code]["status"] = "completed"
                rec["progress_details"][stage.code]["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                debug(f"阶段 {stage.code} 不在进度详情中，跳过完成标记")

            if result:
                if "stage_results" not in rec:
                    rec["stage_results"] = {}
                rec["stage_results"][stage.code] = result

            try:
                rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
            except Exception as e:
                error(f"计算整体进度失败: task_id={task_id}, error={e}")
                rec["progress"] = rec.get("progress", 0)

            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

            self.redis.setex(key, self.task_ttl_seconds, json.dumps(rec, ensure_ascii=False))
            return True
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"本地未找到任务: {task_id}")
                    return False

                rec = self._local_tasks[task_id]

                if "progress_details" not in rec:
                    rec["progress_details"] = {}

                if stage.code in rec["progress_details"]:
                    rec["progress_details"][stage.code]["progress"] = 100
                    rec["progress_details"][stage.code]["status"] = "completed"
                    rec["progress_details"][stage.code]["completed_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    debug(f"阶段 {stage.code} 不在进度详情中，跳过完成标记")

                if result:
                    if "stage_results" not in rec:
                        rec["stage_results"] = {}
                    rec["stage_results"][stage.code] = result

                try:
                    rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
                except Exception as e:
                    error(f"计算整体进度失败: task_id={task_id}, error={e}")
                    rec["progress"] = rec.get("progress", 0)

                rec["updated_at"] = datetime.now(timezone.utc).isoformat()

                return True

    def _get_stage_name(self, stage: TaskStage) -> str:
        """获取阶段名称"""
        return stage.name

    def _calculate_overall_progress(self, progress_details: Dict) -> float:
        """计算整体进度"""
        max_progress = 0
        for stage_code, detail in progress_details.items():
            # 根据代码获取阶段枚举
            stage = TaskStage.from_code(stage_code)
            if stage:
                weight = stage.weight
                if detail.get("status") == "completed":
                    if weight > max_progress:
                        max_progress = weight
                elif detail.get("status") == "processing":
                    stage_progress = weight + (detail.get("progress", 0) / 100) * 10
                    if stage_progress > max_progress:
                        max_progress = stage_progress

        return min(100, max_progress)

    def update_task_result(self, task_id: str, partial_result: Dict[str, Any]) -> bool:
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            tries = 3
            for attempt in range(tries):
                pipe = None
                try:
                    pipe = self.redis.pipeline()
                    pipe.watch(key)
                    raw = self.redis.get(key)
                    if not raw:
                        try:
                            if pipe is not None:
                                pipe.unwatch()
                        except Exception as e:
                            debug(f"Redis 事务回滚失败: {e}")
                        warning(f"更新结果时未找到任务: {task_id}")
                        return False
                    rec = json.loads(raw)
                    cur = rec.get("result") or {}
                    if not isinstance(cur, dict):
                        cur = {}
                    try:
                        cur.update(partial_result)
                    except Exception as e:
                        error(f"结果合并失败: task_id={task_id}, error={e}")
                        cur = partial_result
                    rec["result"] = cur
                    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                    pipe.multi()
                    # 更新时刷新过期时间
                    pipe.setex(key, self.task_ttl_seconds, json.dumps(rec, ensure_ascii=False))
                    pipe.execute()
                    debug(f"任务结果更新成功: {task_id}")
                    return True
                except Exception as e:
                    error(f"更新任务结果失败 (尝试 {attempt + 1}/{tries}): task_id={task_id}, error={e}")
                    try:
                        if pipe is not None:
                            pipe.reset()
                    except Exception as reset_err:
                        debug(f"重置 Redis 连接失败: {reset_err}")
                    continue
            error(f"更新任务结果最终失败: {task_id}")
            return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"本地未找到任务: {task_id}")
                    return False
                cur = self._local_tasks[task_id].get("result") or {}
                try:
                    cur.update(partial_result)
                except Exception as e:
                    error(f"本地结果合并失败: task_id={task_id}, error={e}")
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
                warning(f"更新批次ID时未找到任务: {task_id}")
                return False
            try:
                rec = json.loads(raw)
                rec["batch_id"] = batch_id
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                return True
            except Exception as e:
                error(f"更新批次ID失败: task_id={task_id}, batch_id={batch_id}, error={e}")
                return False
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    self._local_tasks[task_id]["batch_id"] = batch_id
                    self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    return True
            warning(f"本地未找到任务: {task_id}")
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
                debug(f"从 Redis 获取到 {len(tasks)} 个批次任务: batch_id={batch_id}")
            except Exception as e:
                error(f"从 Redis 获取批次任务失败: batch_id={batch_id}, error={e}")
        else:
            with self._lock:
                for task_id, task in self._local_tasks.items():
                    if task.get("batch_id") == batch_id:
                        tasks.append(copy.deepcopy(task))
                debug(f"从本地获取到 {len(tasks)} 个批次任务: batch_id={batch_id}")

        return tasks

    def complete_task(self, task_id: str, result: Dict[str, Any]):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"完成任务时未找到任务: {task_id}")
                return
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return
            rec["status"] = TaskStatus.SUCCESS if result.get("success", False) else TaskStatus.FAILED
            rec["result"] = result
            rec["error"] = result.get("error")
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec["completed_at"] = datetime.now(timezone.utc).isoformat()
            # 完成后保留一段时间再过期
            self.redis.setex(key, self.task_ttl_seconds, json.dumps(obj_to_dict(rec), ensure_ascii=False))
            try:
                if result.get("success", False):
                    self.redis.incr(self._redis_metrics_key("completed"))
                    info(f"任务完成: {task_id}")
                else:
                    self.redis.incr(self._redis_metrics_key("failed"))
                    warning(f"任务失败: {task_id}, error={result.get('error')}")
            except Exception as e:
                warning(f"Redis 指标更新失败: {e}")
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
                            info(f"任务完成: {task_id}")
                        else:
                            self._metrics["failed"] += 1
                            warning(f"任务失败: {task_id}, error={result.get('error')}")
                    except Exception as e:
                        error(f"更新本地指标失败: {e}")

    def fail_task(self, task_id: str, error_message: str):
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"失败任务时未找到任务: {task_id}")
                return
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return
            rec["status"] = TaskStatus.FAILED
            rec["error"] = error_message
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            # 失败后保留一段时间再过期
            self.redis.setex(key, self.task_ttl_seconds, json.dumps(obj_to_dict(rec), ensure_ascii=False))
            try:
                self.redis.incr(self._redis_metrics_key("failed"))
                warning(f"任务失败: {task_id}, error={error_message}")
            except Exception as e:
                warning(f"Redis 指标更新失败: {e}")
        else:
            with self._lock:
                if task_id in self._local_tasks:
                    self._local_tasks[task_id]["status"] = TaskStatus.FAILED
                    self._local_tasks[task_id]["error"] = error_message
                    self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    try:
                        self._metrics["failed"] += 1
                        warning(f"任务失败: {task_id}, error={error_message}")
                    except Exception as e:
                        error(f"更新本地指标失败: {e}")

    def list_tasks(self) -> List[str]:
        if self.use_redis and self.redis:
            try:
                tasks = list(self.redis.smembers(self._redis_tasks_set_key()))
                debug(f"从 Redis 获取到 {len(tasks)} 个任务")
                return tasks
            except Exception as e:
                error(f"从 Redis 获取任务列表失败: {e}")
                return []
        with self._lock:
            tasks = list(self._local_tasks.keys())
            debug(f"从本地获取到 {len(tasks)} 个任务")
            return tasks

    def delete_task(self, task_id: str, cleanup_workflow: bool = True) -> bool:
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            try:
                self.redis.delete(key)
                self.redis.srem(self._redis_tasks_set_key(), task_id)
                debug(f"从 Redis 删除任务: {task_id}")
            except Exception as e:
                error(f"从 Redis 删除任务失败: task_id={task_id}, error={e}")
                return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"删除本地任务时未找到任务: {task_id}")
                    return False
                self._local_tasks.pop(task_id, None)
                self._local_raw_configs.pop(task_id, None)
                debug(f"从本地删除任务: {task_id}")

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
                            debug(f"清理工作流缓存: {key}")
            except Exception as e:
                error(f"清理工作流缓存失败: task_id={task_id}, error={e}")

        return True

    # keep get_workflow behavior similar to previous (in-memory pipeline cache)
    def get_workflow(self, task_manager, script_id, task_id: str, config: Optional[Any] = None) -> "Any":
        # prefer local raw config when available
        if task_id is not None and (config is None or isinstance(config, dict)):
            with self._lock:
                raw = self._local_raw_configs.get(task_id)
            if raw is not None:
                config = raw

        # compute cache key (use serialized config JSON as key)
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            warning(f"生成工作流键失败，使用字符串转换: {e}")
            payload = str(config)
        key = str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

        with self._lock:
            pipeline = self.workflow_cache.get(key)
            if pipeline is not None:
                try:
                    self.workflow_cache.move_to_end(key)
                    debug(f"从缓存获取工作流: {key}")
                except Exception as e:
                    warning(f"更新工作流缓存顺序失败: {e}")
                return pipeline

        # create pipeline (use factory if provided)
        try:
            if getattr(self, "pipeline_factory", None) is not None:
                pipeline = self.pipeline_factory(task_id, config)
            else:
                pipeline = MultiAgentPipeline(script_id, task_id, config, task_manager)
            info(f"创建新工作流: {key}")
        except Exception as e:
            error(f"创建工作流失败: {e}")
            raise

        # insert into LRU cache
        with self._lock:
            if self.max_cache_size > 0 and len(self.workflow_cache) >= self.max_cache_size:
                try:
                    oldest_key, _ = self.workflow_cache.popitem(last=False)
                    info(f"清理最旧的工作流缓存: {oldest_key}")
                except Exception as e:
                    warning(f"清理工作流缓存失败: {e}")
            self.workflow_cache[key] = pipeline

        return pipeline

    # ---------------------- utility methods ----------------------
    def clear_workflow_cache(self):
        with self._lock:
            cache_size = len(self.workflow_cache)
            self.workflow_cache.clear()
            info(f"清理工作流缓存，共清理 {cache_size} 项")

    def get_cached_workflow_keys(self) -> List[str]:
        with self._lock:
            return list(self.workflow_cache.keys())

    def get_metrics(self) -> Dict[str, int]:
        if self.use_redis and self.redis:
            try:
                metrics = {
                    "created": int(self.redis.get(self._redis_metrics_key("created")) or 0),
                    "completed": int(self.redis.get(self._redis_metrics_key("completed")) or 0),
                    "failed": int(self.redis.get(self._redis_metrics_key("failed")) or 0),
                }
                debug(f"从 Redis 获取指标: {metrics}")
                return metrics
            except Exception as e:
                warning(f"从 Redis 获取指标失败，使用本地指标: {e}")
                with self._lock:
                    return dict(self._metrics)
        with self._lock:
            return dict(self._metrics)

    def set_max_cache_size(self, size: int):
        if not isinstance(size, int) or size < 0:
            raise ValueError("max_cache_size must be a non-negative integer")
        with self._lock:
            old_size = self.max_cache_size
            self.max_cache_size = size
            try:
                while self.max_cache_size > 0 and len(self.workflow_cache) > self.max_cache_size:
                    self.workflow_cache.popitem(last=False)
                info(f"更新最大缓存大小: {old_size} -> {size}")
            except Exception as e:
                error(f"清理缓存失败: {e}")

    def export_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self.use_redis and self.redis:
            snapshot = self._read_record_redis(task_id)
            if snapshot:
                debug(f"导出任务快照: {task_id}")
            return snapshot
        snapshot = self._read_record_local(task_id)
        if snapshot:
            debug(f"导出任务快照: {task_id}")
        return snapshot

    def import_task_snapshot(self, snapshot: Dict[str, Any]) -> str:
        task_id = snapshot.get("task_id") or str(uuid.uuid4())
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            try:
                self.redis.set(key, json.dumps(snapshot, ensure_ascii=False))
                self.redis.sadd(self._redis_tasks_set_key(), task_id)
                info(f"导入任务快照到 Redis: {task_id}")
            except Exception as e:
                error(f"导入任务快照到 Redis 失败，降级到本地: {e}")
                # fallback to local
                with self._lock:
                    self._local_tasks[task_id] = snapshot
                    self._local_raw_configs[task_id] = None
        else:
            with self._lock:
                self._local_tasks[task_id] = snapshot
                self._local_raw_configs[task_id] = None
                info(f"导入任务快照到本地: {task_id}")
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
                            debug(f"关闭工作流: {k}")
                        except Exception as e:
                            error(f"关闭工作流失败: {k}, error={e}")
                        break
        with self._lock:
            cache_size = len(self.workflow_cache)
            self.workflow_cache.clear()
            info(f"关闭 TaskManager，清理 {cache_size} 个工作流缓存")

    def set_task_callback(self, task_id: str, callback_url: str) -> bool:
        """Set or update the callback URL associated with a task.

        For Redis: perform a read-modify-write.
        For local: update the in-memory record.
        """
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"设置回调时未找到任务: {task_id}")
                return False
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return False
            rec.setdefault("callbacks", [])
            # replace callbacks with single callback
            rec["callbacks"] = [callback_url]
            rec["callback_url"] = callback_url
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self.redis.set(key, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                info(f"设置任务回调: {task_id} -> {callback_url}")
                return True
            except Exception as e:
                error(f"保存回调配置失败: task_id={task_id}, error={e}")
                return False
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"设置回调时本地未找到任务: {task_id}")
                    return False
                self._local_tasks[task_id].setdefault("callbacks", [])
                self._local_tasks[task_id]["callbacks"] = [callback_url]
                self._local_tasks[task_id]["callback_url"] = callback_url
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                info(f"设置本地任务回调: {task_id} -> {callback_url}")
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
                debug(f"检查 {len(task_ids)} 个任务是否有未完成状态")
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
                                        debug(f"找到未完成任务: {task_id}, 创建时间: {created_at}")
                                    else:
                                        debug(f"跳过过期任务: {task_id}, 创建时间: {created_at}")
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

        info(f"获取到 {len(pending_tasks)} 个未完成任务")
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
                debug(f"过滤后得到 {len(filtered_tasks)} 个任务")
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
        except Exception as e:
            warning(f"时间解析失败，默认恢复: {e}")
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

        info(f"成功恢复 {len(recovered_ids)}/{len(pending_tasks)} 个任务")
        return recovered_ids

    def recover_task(self, task_id: str) -> bool:
        """恢复单个任务（将状态重置为 PENDING）"""
        task = self.get_task(task_id)
        if not task:
            warning(f"恢复任务失败: 任务不存在 {task_id}")
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
                        # 恢复时刷新过期时间
                        self.redis.setex(key, self.task_ttl_seconds, json.dumps(obj_to_dict(rec), ensure_ascii=False))
                        debug(f"Redis 任务恢复成功: {task_id}")
                        return True
                    except Exception as e:
                        error(f"Redis 任务恢复失败: {task_id}, error={e}")
                        return False
            else:
                with self._lock:
                    if task_id in self._local_tasks:
                        self._local_tasks[task_id]["status"] = TaskStatus.PENDING
                        self._local_tasks[task_id]["stage"] = "recovered"
                        self._local_tasks[task_id]["progress"] = 0
                        self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                        self._local_tasks[task_id].pop("completed_at", None)
                        debug(f"本地任务恢复成功: {task_id}")
                        return True

        return False

    #     ============================ 恢复任务 ================================

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
        """
        if self.use_redis and self.redis:
            key = self._redis_key(task_id)
            raw = self.redis.get(key)
            if not raw:
                warning(f"更新状态时未找到任务: {task_id}")
                return False
            try:
                rec = json.loads(raw)
            except Exception as e:
                error(f"Redis 数据反序列化失败: task_id={task_id}, error={e}")
                return False

            rec["status"] = status.value if hasattr(status, 'value') else status
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

            self.redis.setex(key, self.task_ttl_seconds, json.dumps(rec, ensure_ascii=False))
            debug(f"任务状态更新: {task_id} -> {status}")
            return True
        else:
            with self._lock:
                if task_id not in self._local_tasks:
                    warning(f"本地未找到任务: {task_id}")
                    return False

                self._local_tasks[task_id]["status"] = status.value if hasattr(status, 'value') else status
                self._local_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                debug(f"本地任务状态更新: {task_id} -> {status}")
                return True

# end of TaskManager