"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: task_manager.py
@Description: TaskManager - 任务管理协调层，对外统一入口
    协调 TaskLifecycleService、TaskRepository 和 WorkflowRegistry
    保持向后兼容性
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/4/29
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List

from penshot.logger import info, warning, debug
from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_models import TaskStatus, TaskStage
from .task_lifecycle_service import TaskLifecycleService
from .task_repository import TaskRepository
from .workflow_registry import WorkflowRegistry


class TaskManager:
    """任务管理协调层，对外统一入口，保持向后兼容性。"""

    def __init__(self, max_cache_size: int = 64, task_ttl_seconds: int = 86400):
        """
        Args:
            max_cache_size: 工作流缓存最大数量
            task_ttl_seconds: 任务数据过期时间（秒），默认24小时
        """
        self.repository = TaskRepository(task_ttl_seconds=task_ttl_seconds)
        self.workflow_registry = WorkflowRegistry(max_cache_size=max_cache_size)
        self.lifecycle_service = TaskLifecycleService(
            repository=self.repository,
            workflow_registry=self.workflow_registry,
            task_ttl_seconds=task_ttl_seconds
        )

        self.use_redis = self.repository.use_redis
        self.redis = self.repository.redis
        self.max_cache_size = max_cache_size
        self.task_ttl_seconds = task_ttl_seconds

    # ==================== 任务创建 ====================
    def create_task(self, script: str, script_id: Optional[str] = None,
                    style: Optional[VideoStyle] = None, config: Optional[ShotConfig] = None) -> (str, str):
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
        return self.lifecycle_service.create_task(script, script_id, style, config)

    # ==================== 任务读取 ====================
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        return self.lifecycle_service.get_task(task_id)

    # ==================== 任务进度更新 ====================
    def update_task_progress(self, task_id: str, stage: str, progress: float = None):
        """更新任务进度（兼容旧接口）"""
        task_stage = TaskStage.from_code(stage)
        if task_stage:
            self.lifecycle_service.update_progress(task_id, task_stage, progress)
        else:
            warning(f"未知阶段: {stage}")

    def update_task_progress_detail(self, task_id: str, stage: TaskStage,
                                    progress: float = None, details: Dict[str, Any] = None) -> bool:
        """更新任务详细进度"""
        return self.lifecycle_service.update_progress(task_id, stage, progress, details)

    # ==================== 阶段完成 ====================
    def complete_stage(self, task_id: str, stage: TaskStage, result: Dict[str, Any] = None) -> bool:
        """完成一个阶段"""
        return self.lifecycle_service.complete_stage(task_id, stage, result)

    # ==================== 任务完成 ====================
    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """完成任务"""
        self.lifecycle_service.complete_task(task_id, result)

    # ==================== 任务失败 ====================
    def fail_task(self, task_id: str, error_message: str):
        """标记任务失败"""
        self.lifecycle_service.fail_task(task_id, error_message)

    # ==================== 任务列表 ====================
    def list_tasks(self) -> List[str]:
        """获取所有任务ID"""
        return self.lifecycle_service.list_tasks()

    # ==================== 任务删除 ====================
    def delete_task(self, task_id: str, cleanup_workflow: bool = True) -> bool:
        """删除任务"""
        return self.lifecycle_service.delete_task(task_id, cleanup_workflow)

    # ==================== 任务结果更新 ====================
    def update_task_result(self, task_id: str, partial_result: Dict[str, Any]) -> bool:
        """更新任务部分结果"""
        return self.lifecycle_service.update_task_result(task_id, partial_result)

    # ==================== 工作流管理 ====================
    def get_workflow(self, task_manager, script_id: str, task_id: str, config: Optional[Any] = None) -> Any:
        """获取或创建工作流"""
        return self.lifecycle_service.get_workflow(script_id, task_id, config)

    def clear_workflow_cache(self):
        """清理工作流缓存"""
        cache_size = self.workflow_registry.clear()
        info(f"清理工作流缓存，共清理 {cache_size} 项")

    def get_cached_workflow_keys(self) -> List[str]:
        """获取缓存的工作流键"""
        return self.workflow_registry.keys()

    # ==================== 指标获取 ====================
    def get_metrics(self) -> Dict[str, int]:
        """获取任务统计指标"""
        return self.lifecycle_service.get_metrics()

    # ==================== 任务恢复 ====================
    def get_pending_tasks(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """获取所有未完成的任务"""
        return self.lifecycle_service.get_pending_tasks(max_age_hours)

    def get_pending_tasks_with_filter(self, max_age_hours: int = 2,
                                      status_filter: Optional[List[TaskStatus]] = None) -> List[Dict[str, Any]]:
        """获取符合条件的未完成任务"""
        if status_filter is None:
            return self.lifecycle_service.get_pending_tasks(max_age_hours)

        pending = self.lifecycle_service.get_pending_tasks(max_age_hours)
        status_values = [s.value for s in status_filter]
        return [task for task in pending if task.get("status") in status_values]

    def recover_task(self, task_id: str) -> bool:
        """恢复单个任务"""
        return self.lifecycle_service.recover_task(task_id)

    def recover_all_pending_tasks(self, max_age_hours: int = 2) -> List[str]:
        """恢复所有未完成的任务"""
        return self.lifecycle_service.recover_all_pending_tasks(max_age_hours)

    # ==================== 状态更新 ====================
    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """更新任务状态"""
        return self.lifecycle_service.update_task_status(task_id, status)

    # ==================== 回调管理 ====================
    def set_task_callback(self, task_id: str, callback_url: str) -> bool:
        """设置任务回调URL"""
        return self.lifecycle_service.set_callback(task_id, callback_url)

    # ==================== 快照管理 ====================
    def export_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        """导出任务快照"""
        return self.lifecycle_service.export_task_snapshot(task_id)

    def import_task_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """导入任务快照"""
        return self.lifecycle_service.import_task_snapshot(snapshot)

    # ==================== 服务关闭 ====================
    def shutdown(self, close_pipelines: bool = True):
        """关闭服务"""
        self.lifecycle_service.shutdown(close_pipelines)

    # ==================== 缓存配置 ====================
    def set_max_cache_size(self, size: int):
        """设置最大缓存大小"""
        self.max_cache_size = size
        self.workflow_registry.set_max_cache_size(size)

    # ==================== 批次操作 ====================
    def update_task_batch(self, task_id: str, batch_id: str) -> bool:
        """更新任务的批次ID"""

        def updater(rec: Dict[str, Any]) -> None:
            rec["batch_id"] = batch_id
            rec["updated_at"] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"更新批次ID时未找到任务: {task_id}")
        return updated

    def get_tasks_by_batch(self, batch_id: str) -> List[Dict[str, Any]]:
        """根据批次ID获取所有任务"""
        tasks = []
        for task_id in self.list_tasks():
            task = self.get_task(task_id)
            if task and task.get("batch_id") == batch_id:
                tasks.append(task)
        debug(f"获取到 {len(tasks)} 个批次任务: batch_id={batch_id}")
        return tasks

    # ==================== 辅助方法（保持向后兼容） ====================
    @property
    def _lock(self):
        return self.repository._lock

    @property
    def _local_tasks(self):
        return self.repository._local_tasks

    @property
    def _local_raw_configs(self):
        return self.repository._local_raw_configs
