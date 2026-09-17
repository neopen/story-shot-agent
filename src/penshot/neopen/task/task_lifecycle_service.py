"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: task_lifecycle_service.py
@Description: 任务生命周期服务 - 负责任务状态机管理和生命周期控制
@Author: NeoPen
@Time: 2026/4/29
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import is_dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import RLock
from typing import Optional, Dict, Any, List, Tuple

from penshot.logger import info, error, warning, debug
from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.agent.workflow.workflow_pipeline import MultiAgentPipeline
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_models import TaskStatus, TaskStage
from penshot.utils.hash_utils import text_to_id
from .task_repository import TaskRepository
from .workflow_registry import WorkflowRegistry


class TaskLifecycleService:
    """负责任务状态机管理和生命周期控制。"""

    def __init__(self, repository: TaskRepository,
                 workflow_registry: WorkflowRegistry,
                 task_ttl_seconds: int = 86400):
        self.repository = repository
        self.workflow_registry = workflow_registry
        self.task_ttl_seconds = task_ttl_seconds
        self._metrics = {"created": 0, "completed": 0, "failed": 0}
        self._lock = RLock()
        self.pipeline_factory = None

    # ==================== ID生成方法 ====================
    def _generate_script_code(self, script: str) -> str:
        return text_to_id(script, 3)

    def _generate_script_id(self, script_code: str) -> str:
        # return "NP" + datetime.now().strftime("%y%m") + script_code
        return "SN" + script_code

    def _generate_task_id(self, script_code: str) -> str:
        """生成任务ID"""
        return "TSK" + script_code[:6] + datetime.now().strftime("%y%m%d%H%M") + str(random.randint(1000, 9999))

    # ==================== 序列化方法 ====================
    def _safe_serialize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            try:
                return value.isoformat()
            except Exception as e:
                warning(f"日期序列化失败: {e}")
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
            debug(f"JSON序列化失败: {e}")
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
        """Generate a stable key for a config"""
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            warning(f"生成配置键失败: {e}")
            payload = str(config)
        try:
            import hashlib
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
        except Exception as e:
            error(f"SHA256计算失败: {e}")
            import uuid
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

    # ==================== 核心业务方法 ====================
    def create_task(self, script: str, script_id: Optional[str] = None,
                    style: Optional[VideoStyle] = None,
                    config: Optional[ShotConfig] = None) -> Tuple[str, str]:
        """
        创建任务

        Args:
            script: 剧本内容
            script_id: 剧本ID（可选）
            style: 视频风格（可选）
            config: 配置（可选）

        Returns:
            (script_id, task_id)
        """
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

        self.repository.create_task(task_id, record, raw_config=config)

        with self._lock:
            self._metrics["created"] += 1

        info(f"创建任务: {task_id}")
        return script_id, task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        return self.repository.read_task(task_id)

    def update_progress(self, task_id: str, stage: TaskStage,
                        progress: Optional[float] = None,
                        details: Optional[Dict[str, Any]] = None) -> bool:
        """
        更新任务详细进度

        Args:
            task_id: 任务ID
            stage: 当前阶段
            progress: 该阶段进度百分比
            details: 阶段详细信息

        Returns:
            是否成功
        """
        stage_code = stage.code

        def updater(rec: Dict[str, Any]) -> None:
            current_status = rec.get("status")
            if current_status not in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                rec["status"] = TaskStatus.PROCESSING.value

            rec["current_stage"] = stage_code
            rec["stage"] = stage_code
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec.setdefault("progress_details", {})

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
                error(f"计算整体进度失败: {e}")
                rec["progress"] = 0

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"更新进度详情时未找到任务: {task_id}")
        return updated

    def complete_stage(self, task_id: str, stage: TaskStage,
                       result: Optional[Dict[str, Any]] = None) -> bool:
        """
        完成一个阶段

        Args:
            task_id: 任务ID
            stage: 完成的阶段
            result: 阶段结果

        Returns:
            是否成功
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.setdefault("progress_details", {})

            if stage.code in rec["progress_details"]:
                rec["progress_details"][stage.code]["progress"] = 100
                rec["progress_details"][stage.code]["status"] = "completed"
                rec["progress_details"][stage.code]["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                debug(f"阶段 {stage.code} 不在进度详情中")

            if result:
                rec.setdefault("stage_results", {})
                rec["stage_results"][stage.code] = result

            try:
                rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
            except Exception as e:
                error(f"计算整体进度失败: {e}")
                rec["progress"] = rec.get("progress", 0)

            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"完成阶段时未找到任务: {task_id}")
        return updated

    def _calculate_overall_progress(self, progress_details: Dict) -> float:
        """计算整体进度"""
        max_progress = 0
        for stage_code, detail in progress_details.items():
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
        """更新任务部分结果"""

        def updater(rec: Dict[str, Any]) -> None:
            cur = rec.get("result") or {}
            if not isinstance(cur, dict):
                cur = {}
            try:
                cur.update(partial_result)
            except Exception as e:
                error(f"结果合并失败: {e}")
                cur = partial_result
            rec["result"] = cur
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        return self.repository.update_task(task_id, updater)

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """
        完成任务

        Args:
            task_id: 任务ID
            result: 任务结果
        """
        success = result.get("success", False)

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": TaskStatus.SUCCESS if success else TaskStatus.FAILED,
                "result": result,
                "error": result.get("error"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"完成任务时未找到任务: {task_id}")
            return

        with self._lock:
            if success:
                self._metrics["completed"] += 1
                info(f"任务完成: {task_id}")
            else:
                self._metrics["failed"] += 1
                warning(f"任务失败: {task_id}, error={result.get('error')}")

        self._try_trigger_callback(task_id, result)
        self._cleanup_workflow_cache(task_id)

    def fail_task(self, task_id: str, error_message: str) -> None:
        """
        标记任务失败

        Args:
            task_id: 任务ID
            error_message: 错误信息
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": TaskStatus.FAILED,
                "error": error_message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"失败任务时未找到任务: {task_id}")
            return

        with self._lock:
            self._metrics["failed"] += 1
            warning(f"任务失败: {task_id}, error={error_message}")

        self._try_trigger_callback(task_id, {"success": False, "error": error_message})

    def _try_trigger_callback(self, task_id: str, result: Dict[str, Any]) -> None:
        """尝试触发回调"""
        task = self.repository.read_task(task_id)
        if not task:
            return

        callback_url = task.get("callback_url")
        if not callback_url:
            return

        asyncio.create_task(self._trigger_callback_async(task_id, callback_url, result))

    async def _trigger_callback_async(self, task_id: str, callback_url: str, result: Dict[str, Any]) -> None:
        """异步触发HTTP回调"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={"task_id": task_id, **result},
                    timeout=30
                )
                debug(f"回调触发成功: {task_id} -> {callback_url}")
        except Exception as e:
            error(f"回调触发失败: {task_id}, error={e}")

    def _cleanup_workflow_cache(self, task_id: str) -> None:
        """清理任务相关的工作流缓存"""
        try:
            cfg = self.repository.get_raw_config(task_id)
            if cfg is not None:
                key = self._config_key(cfg)
                if key and self.workflow_registry.get(key):
                    still_used = False
                    for other_id, other_cfg in self.repository.iter_raw_configs():
                        if other_id == task_id:
                            continue
                        if self._config_key(other_cfg) == key:
                            still_used = True
                            break
                    if not still_used:
                        self.workflow_registry.pop(key)
                        debug(f"清理工作流缓存: {key}")
        except Exception as e:
            error(f"清理工作流缓存失败: {e}")

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态

        Returns:
            是否成功
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": status.value if hasattr(status, 'value') else status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"更新状态时未找到任务: {task_id}")
        return updated

    # ==================== 任务恢复方法 ====================
    def get_pending_tasks(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """获取所有未完成的任务"""
        pending_tasks = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        task_ids = self.repository.list_task_ids()
        for task_id in task_ids:
            task = self.repository.read_task(task_id)
            if task:
                status = task.get("status")
                if status in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]:
                    created_at = task.get("created_at")
                    if created_at:
                        try:
                            if isinstance(created_at, str):
                                created_at_dt = datetime.fromisoformat(created_at)
                            else:
                                created_at_dt = created_at
                            if created_at_dt >= cutoff_time:
                                pending_tasks.append(task)
                        except Exception as e:
                            error(f"解析任务创建时间失败: {e}")
                            pending_tasks.append(task)

        info(f"获取到 {len(pending_tasks)} 个未完成任务")
        return pending_tasks

    def recover_task(self, task_id: str) -> bool:
        """恢复单个任务（将状态重置为 PENDING）"""
        task = self.repository.read_task(task_id)
        if not task:
            warning(f"恢复任务失败: 任务不存在 {task_id}")
            return False

        current_status = task.get("status")
        if current_status not in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]:
            return False

        def updater(rec: Dict[str, Any]) -> None:
            rec["status"] = TaskStatus.PENDING.value
            rec["stage"] = "recovered"
            rec["progress"] = 0
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec.pop("completed_at", None)

        updated = self.repository.update_task(task_id, updater)
        if updated:
            debug(f"任务恢复成功: {task_id}")
        return updated

    def recover_all_pending_tasks(self, max_age_hours: int = 2) -> List[str]:
        """恢复所有未完成的任务"""
        pending_tasks = self.get_pending_tasks(max_age_hours=max_age_hours)
        recovered_ids = []

        for task in pending_tasks:
            task_id = task.get("task_id")
            if self.recover_task(task_id):
                recovered_ids.append(task_id)
                info(f"恢复任务: {task_id}")

        info(f"成功恢复 {len(recovered_ids)}/{len(pending_tasks)} 个任务")
        return recovered_ids

    # ==================== 工作流管理 ====================
    def get_workflow(self, script_id: str, task_id: str, config: Optional[Any] = None) -> Any:
        """获取或创建工作流"""
        if task_id is not None and (config is None or isinstance(config, dict)):
            raw = self.repository.get_raw_config(task_id)
            if raw is not None:
                config = raw

        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            warning(f"生成工作流键失败: {e}")
            payload = str(config)

        import uuid
        key = str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

        pipeline = self.workflow_registry.get(key)
        if pipeline is not None:
            debug(f"从缓存获取工作流: {key}")
            return pipeline

        try:
            if self.pipeline_factory is not None:
                pipeline = self.pipeline_factory(task_id, config)
            else:
                pipeline = MultiAgentPipeline(script_id, task_id, config, self)
            info(f"创建新工作流: {key}")
        except Exception as e:
            error(f"创建工作流失败: {e}")
            raise

        self.workflow_registry.put(key, pipeline)
        return pipeline

    # ==================== 工具方法 ====================
    def list_tasks(self) -> List[str]:
        """获取所有任务ID"""
        return self.repository.list_task_ids()

    def delete_task(self, task_id: str, cleanup_workflow: bool = True) -> bool:
        """删除任务"""
        if not self.repository.delete_task(task_id):
            return False

        if cleanup_workflow:
            self._cleanup_workflow_cache(task_id)

        return True

    def get_metrics(self) -> Dict[str, int]:
        """获取任务统计指标"""
        with self._lock:
            return dict(self._metrics)

    def set_callback(self, task_id: str, callback_url: str) -> bool:
        """设置任务回调URL"""

        def updater(rec: Dict[str, Any]) -> None:
            rec.setdefault("callbacks", [])
            rec["callbacks"] = [callback_url]
            rec["callback_url"] = callback_url
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.repository.update_task(task_id, updater)
        if updated:
            info(f"设置任务回调: {task_id} -> {callback_url}")
        return updated

    def export_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        """导出任务快照"""
        return self.repository.read_task(task_id)

    def import_task_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """导入任务快照"""
        return self.repository.import_snapshot(snapshot)

    def shutdown(self, close_pipelines: bool = True) -> None:
        """关闭服务"""
        cache_size = self.workflow_registry.shutdown(close_workflows=close_pipelines)
        info(f"关闭 TaskLifecycleService，清理 {cache_size} 个工作流缓存")
