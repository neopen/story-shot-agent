"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_task_manager_smoke.py
@Description: TaskManager 冒烟测试（适配 TaskManager 重构后的协调层新 API）
    覆盖：创建/读取/进度/回调/结果/完成/失败/指标/快照/删除
@Author: neopen
"""

import pytest

from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_manager import TaskManager


def _status_value(value):
    """兼容内存模式（TaskStatus 枚举）与 Redis 模式（字符串）的状态取值。"""
    return getattr(value, "value", value)


@pytest.fixture(scope="module")
def manager():
    """模块级 TaskManager；Redis 可用时走 Redis，否则自动回退内存存储。"""
    return TaskManager()


@pytest.fixture()
def make_task(manager):
    """创建任务并跟踪其 ID，用例结束后统一清理，避免污染共享 Redis。"""
    created = []

    def _make(script="冒烟测试剧本内容", **kwargs):
        script_id, task_id = manager.create_task(script, **kwargs)
        created.append(task_id)
        return script_id, task_id

    yield _make

    for task_id in created:
        try:
            manager.delete_task(task_id)
        except Exception:
            pass


def test_create_task(manager, make_task):
    """创建任务：返回 (script_id, task_id)，初始状态为 pending/init/0。"""
    script_id, task_id = make_task()

    assert isinstance(script_id, str) and script_id.startswith("SN")
    assert isinstance(task_id, str) and task_id.startswith("TSK")

    task = manager.get_task(task_id)
    assert task is not None
    assert task["task_id"] == task_id
    assert _status_value(task["status"]) == "pending"
    assert task["stage"] == "init"
    assert task["progress"] == 0
    assert task_id in manager.list_tasks()


def test_create_task_with_config(manager, make_task):
    """创建任务时传入 ShotConfig，任务应正常建立且可读取。"""
    _, task_id = make_task("带配置的剧本内容", config=ShotConfig())

    assert task_id in manager.list_tasks()
    assert manager.get_task(task_id) is not None


def test_update_progress(manager, make_task):
    """更新进度：状态转为 processing，阶段与整体进度随之变化。"""
    _, task_id = make_task()

    manager.update_task_progress(task_id, "segmenting", 30)

    task = manager.get_task(task_id)
    assert _status_value(task["status"]) == "processing"
    assert task["stage"] == "segmenting"
    assert task["progress"] > 0


def test_set_callback(manager, make_task):
    """设置回调：callback_url 应被持久化到任务记录。"""
    _, task_id = make_task()

    assert manager.set_task_callback(task_id, "https://example.com/cb") is True
    assert manager.get_task(task_id)["callback_url"] == "https://example.com/cb"


def test_update_result(manager, make_task):
    """更新部分结果：result 应合并写入。"""
    _, task_id = make_task()

    assert manager.update_task_result(task_id, {"partial": 1}) is True
    assert manager.get_task(task_id)["result"] == {"partial": 1}


def test_complete_task(manager, make_task):
    """完成任务（success）：状态为 success，且记录完成时间。"""
    _, task_id = make_task()

    manager.complete_task(task_id, {"success": True, "data": {"shots": []}})

    task = manager.get_task(task_id)
    assert _status_value(task["status"]) == "success"
    assert task.get("completed_at")


def test_fail_task(manager, make_task):
    """标记失败：状态为 failed，error 为传入信息。"""
    _, task_id = make_task()

    manager.fail_task(task_id, "some error")

    task = manager.get_task(task_id)
    assert _status_value(task["status"]) == "failed"
    assert task["error"] == "some error"


def test_metrics(manager, make_task):
    """指标：创建 +1、完成后 completed +1（用增量断言，避免跨用例累计干扰）。"""
    before = manager.get_metrics()

    _, task_id = make_task()
    manager.complete_task(task_id, {"success": True, "data": {}})

    after = manager.get_metrics()
    assert after["created"] - before["created"] == 1
    assert after["completed"] - before["completed"] == 1


def test_export_import_snapshot(manager, make_task):
    """快照导出/导入：删除原任务后可据快照重建，task_id 保持不变。"""
    _, task_id = make_task()

    snapshot = manager.export_task_snapshot(task_id)
    assert snapshot is not None
    assert snapshot["task_id"] == task_id

    assert manager.delete_task(task_id) is True
    assert manager.get_task(task_id) is None

    restored_id = manager.import_task_snapshot(snapshot)
    assert restored_id == task_id
    assert manager.get_task(restored_id) is not None


def test_delete_task(manager, make_task):
    """删除任务：删除后不再出现在任务列表中。"""
    _, task_id = make_task("待删除的剧本")

    assert task_id in manager.list_tasks()
    assert manager.delete_task(task_id) is True
    assert task_id not in manager.list_tasks()
