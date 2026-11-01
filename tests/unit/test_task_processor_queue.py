"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_task_processor_queue.py
@Description: 异步任务处理器队列行为测试（优先级、容量、取消、恢复）
@Author: NeoPen
"""
from datetime import datetime, timezone

import pytest

from penshot.neopen.task.task_models import QueuedTask, TaskPriority
from penshot.neopen.task.task_processor import AsyncTaskProcessor


class _StubTaskManager:
    """只提供队列恢复与任务执行所需方法的桩，避免触发真实任务处理"""

    def __init__(self, pending=None):
        self._pending = pending or []

    def get_pending_tasks(self, max_age_hours: int = 2):
        return self._pending

    def get_task(self, task_id):
        return None

    def update_task_status(self, *args, **kwargs):
        return True

    def update_task_progress_detail(self, *args, **kwargs):
        return True

    def fail_task(self, *args, **kwargs):
        return True

    def complete_task(self, *args, **kwargs):
        return True


@pytest.fixture()
async def processor():
    """启动处理器后台循环；用例结束后关闭"""
    proc = AsyncTaskProcessor(task_manager=_StubTaskManager(), max_concurrent=1, queue_size=3)
    yield proc
    await proc.shutdown(wait_for_completion=False)


def _make_queued(task_id: str, priority: TaskPriority = TaskPriority.NORMAL) -> QueuedTask:
    task = QueuedTask(task_id=task_id, priority=priority, callback=None)
    task.enqueued_at = datetime.now(timezone.utc)
    return task


def test_priority_insertion_order(processor):
    """入队后队列应按优先级从高到低排列"""
    for task_id, priority in (
        ("T1", TaskPriority.NORMAL),
        ("T2", TaskPriority.LOW),
        ("T3", TaskPriority.CRITICAL),
    ):
        assert processor._insert_queued_task(_make_queued(task_id, priority))

    assert [t.task_id for t in processor._queue] == ["T3", "T1", "T2"]
    status = processor.get_queue_status()
    assert status["queue_waiting"] == 3
    assert processor.get_stats()["total_submitted"] == 3


def test_queue_full_rejects_new_task(processor):
    """队列达到上限后应拒绝新任务且不污染统计"""
    for i in range(3):
        assert processor._insert_queued_task(_make_queued(f"T{i}"))

    assert not processor._insert_queued_task(_make_queued("T3"))
    status = processor.get_queue_status()
    assert status["queue_length"] == 3
    assert status["queue_waiting"] == 3
    assert processor.get_stats()["total_submitted"] == 3


async def test_cancel_queued_task(processor):
    """取消队列中的任务应原子地移除并同步等待计数"""
    assert processor._insert_queued_task(_make_queued("T1"))

    assert processor.cancel_task("T1") is True
    assert processor.get_queue_status()["queue_length"] == 0
    assert processor.get_queue_status()["queue_waiting"] == 0
    assert processor.cancel_task("T1") is False


async def test_recover_pending_tasks_respects_capacity(monkeypatch):
    """恢复未完成任务时应复用统一入队逻辑，不超过队列容量"""
    pending = [{"task_id": f"R{i}"} for i in range(5)]
    proc = AsyncTaskProcessor(
        task_manager=_StubTaskManager(pending=pending),
        max_concurrent=1,
        queue_size=2,
    )
    # 关闭唤醒，避免后台工作器在断言前就把任务取出，保证队列内容可断言
    monkeypatch.setattr(proc, "_notify_queue_not_empty", lambda: None)
    try:
        proc.recover_pending_tasks()

        assert len(proc._queue) == 2
        assert proc.get_queue_status()["queue_waiting"] == 2
        assert proc.get_stats()["total_submitted"] == 2
        assert [t.task_id for t in proc._queue] == ["R0", "R1"]
    finally:
        await proc.shutdown(wait_for_completion=False)
