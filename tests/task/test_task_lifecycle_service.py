"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: test_task_lifecycle_service.py
@Description: 任务生命周期服务单元测试
@Author: NeoPen
@Time: 2026/4/29
"""

import pytest
from unittest.mock import MagicMock, patch

from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_lifecycle_service import TaskLifecycleService
from penshot.neopen.task.task_models import TaskStatus, TaskStage
from penshot.neopen.task.task_repository import TaskRepository
from penshot.neopen.task.workflow_registry import WorkflowRegistry


class TestTaskLifecycleService:
    """任务生命周期服务测试"""

    @pytest.fixture
    def repository(self):
        return TaskRepository(task_ttl_seconds=3600)

    @pytest.fixture
    def workflow_registry(self):
        return WorkflowRegistry(max_cache_size=10)

    @pytest.fixture
    def lifecycle_service(self, repository, workflow_registry):
        return TaskLifecycleService(repository, workflow_registry)

    def test_create_task(self, lifecycle_service):
        """测试创建任务"""
        script = "测试剧本内容"
        script_id, task_id = lifecycle_service.create_task(script)

        assert script_id is not None
        assert task_id is not None
        assert task_id.startswith("TSK")

        task = lifecycle_service.get_task(task_id)
        assert task is not None
        assert task["task_id"] == task_id
        assert task["script"] == script
        assert task["status"] == TaskStatus.PENDING

    def test_update_progress(self, lifecycle_service):
        """测试更新任务进度"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        result = lifecycle_service.update_progress(
            task_id, TaskStage.PARSING_SCRIPT, progress=50.0
        )

        assert result is True

        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.PROCESSING
        assert task["progress"] == 15.0  # PARSE_SCRIPT weight is 10, 50% progress gives 15

    def test_complete_stage(self, lifecycle_service):
        """测试完成阶段"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        lifecycle_service.update_progress(task_id, TaskStage.PARSING_SCRIPT, 100.0)
        result = lifecycle_service.complete_stage(task_id, TaskStage.PARSING_SCRIPT)

        assert result is True

        task = lifecycle_service.get_task(task_id)
        assert task["progress_details"]["parsing_script"]["status"] == "completed"

    def test_complete_task_success(self, lifecycle_service):
        """测试成功完成任务"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        lifecycle_service.complete_task(task_id, {"success": True, "data": {"fragments": []}})

        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.SUCCESS
        assert task["result"]["success"] is True

    def test_complete_task_failure(self, lifecycle_service):
        """测试任务失败"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        lifecycle_service.complete_task(task_id, {"success": False, "error": "测试错误"})

        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.FAILED
        assert task["error"] == "测试错误"

    def test_fail_task(self, lifecycle_service):
        """测试标记任务失败"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        lifecycle_service.fail_task(task_id, "手动失败")

        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.FAILED
        assert task["error"] == "手动失败"

    def test_recover_task(self, lifecycle_service):
        """测试恢复任务"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")
        lifecycle_service.update_progress(task_id, TaskStage.PARSING_SCRIPT, 50.0)

        result = lifecycle_service.recover_task(task_id)

        assert result is True

        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.PENDING
        assert task["progress"] == 0

    def test_get_pending_tasks(self, lifecycle_service):
        """测试获取未完成任务"""
        lifecycle_service.create_task("剧本1")
        lifecycle_service.create_task("剧本2")

        pending = lifecycle_service.get_pending_tasks(max_age_hours=24)

        assert len(pending) == 2

    def test_get_metrics(self, lifecycle_service):
        """测试获取指标"""
        lifecycle_service.create_task("剧本1")
        script_id2, task_id2 = lifecycle_service.create_task("剧本2")
        lifecycle_service.complete_task(task_id2, {"success": True, "data": {}})

        metrics = lifecycle_service.get_metrics()

        assert metrics["created"] >= 2
        assert metrics["completed"] >= 1

    def test_set_callback(self, lifecycle_service):
        """测试设置回调"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        result = lifecycle_service.set_callback(task_id, "https://example.com/callback")

        assert result is True

        task = lifecycle_service.get_task(task_id)
        assert task["callback_url"] == "https://example.com/callback"

    def test_delete_task(self, lifecycle_service):
        """测试删除任务"""
        script_id, task_id = lifecycle_service.create_task("测试剧本")

        result = lifecycle_service.delete_task(task_id)

        assert result is True

        task = lifecycle_service.get_task(task_id)
        assert task is None


class TestTaskLifecycleServiceIntegration:
    """任务生命周期服务集成测试"""

    @pytest.fixture
    def lifecycle_service(self):
        repository = TaskRepository(task_ttl_seconds=3600)
        workflow_registry = WorkflowRegistry(max_cache_size=10)
        return TaskLifecycleService(repository, workflow_registry)

    def test_full_lifecycle(self, lifecycle_service):
        """测试完整任务生命周期"""
        # 1. 创建任务
        script_id, task_id = lifecycle_service.create_task("完整生命周期测试剧本")
        assert task_id is not None

        # 2. 更新进度 - 完成所有主要阶段
        lifecycle_service.update_progress(task_id, TaskStage.PARSING_SCRIPT, 100.0)
        lifecycle_service.complete_stage(task_id, TaskStage.PARSING_COMPLETE)

        lifecycle_service.update_progress(task_id, TaskStage.SEGMENTING, 100.0)
        lifecycle_service.complete_stage(task_id, TaskStage.SEGMENT_COMPLETE)

        lifecycle_service.update_progress(task_id, TaskStage.SPLITTING, 100.0)
        lifecycle_service.complete_stage(task_id, TaskStage.SPLIT_COMPLETE)

        # 3. 完成任务
        lifecycle_service.complete_task(task_id, {"success": True, "data": {"fragments": []}})

        # 4. 验证结果
        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.SUCCESS
        assert task["progress"] >= 50.0  # 至少完成到 SPLIT_COMPLETE 阶段

    def test_task_recovery_workflow(self, lifecycle_service):
        """测试任务恢复流程"""
        # 创建任务并开始处理
        script_id, task_id = lifecycle_service.create_task("恢复测试剧本")
        lifecycle_service.update_progress(task_id, TaskStage.PARSING_SCRIPT, 50.0)

        # 恢复任务
        lifecycle_service.recover_task(task_id)

        # 验证任务状态
        task = lifecycle_service.get_task(task_id)
        assert task["status"] == TaskStatus.PENDING
        assert task["progress"] == 0
        assert task["stage"] == "recovered"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])