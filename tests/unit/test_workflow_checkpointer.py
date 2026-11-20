"""检查点管理器行为测试：稳定 thread_id、同步关闭、清理与释放。"""

import inspect
import os
import time
from pathlib import Path

from penshot.neopen.agent.workflow.workflow_checkpointer import (
    CheckpointMode,
    CheckpointerFactory,
    WorkflowCheckpointer,
    create_checkpointer,
)
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_lifecycle_service import TaskLifecycleService
from penshot.neopen.task.task_repository import TaskRepository
from penshot.neopen.task.workflow_registry import WorkflowRegistry


def _config(tmp_path: Path, mode: str = "sqlite") -> ShotConfig:
    return ShotConfig(checkpoint_mode=mode, checkpoint_dir=str(tmp_path))


def _make(tmp_path: Path, task_id: str, mode: str = "sqlite") -> WorkflowCheckpointer:
    return WorkflowCheckpointer("SN_TEST", task_id, _config(tmp_path, mode))


def test_thread_id_is_stable(tmp_path):
    cp = _make(tmp_path, "TSK1")
    try:
        assert cp.get_config()["configurable"]["thread_id"] == "SN_TEST_TSK1"
        assert cp.get_thread_id() == "SN_TEST_TSK1"
    finally:
        cp.close()


def test_close_is_synchronous_and_releases_connection(tmp_path):
    assert not inspect.iscoroutinefunction(WorkflowCheckpointer.close)

    cp = _make(tmp_path, "TSK2")
    cp.get_saver()
    assert cp._conn is not None

    cp.close()
    assert cp._conn is None
    assert cp._saver is None


def test_invalid_mode_falls_back_without_error(tmp_path):
    cp = _make(tmp_path, "TSK3", mode="postgres")
    try:
        assert cp.mode in (CheckpointMode.MEMORY, CheckpointMode.SQLITE)
    finally:
        cp.close()


def test_cleanup_keeps_active_db_and_removes_wal_sidecars(tmp_path):
    cp = _make(tmp_path, "TSK_KEEP")
    try:
        current = Path(cp.db_path)
        current.write_bytes(b"current")

        old = current.parent / "task_OLD.db"
        old.write_bytes(b"old")
        for suffix in ("-wal", "-shm"):
            Path(str(old) + suffix).write_bytes(b"x")

        past = time.time() - 3600
        os.utime(old, (past, past))
        for suffix in ("-wal", "-shm"):
            os.utime(str(old) + suffix, (past, past))

        cp.cleanup_old_checkpoints(keep_count=1)

        assert current.exists()
        assert not old.exists()
        assert not Path(str(old) + "-wal").exists()
        assert not Path(str(old) + "-shm").exists()
    finally:
        cp.close()


def test_workflow_key_isolated_by_task_id():
    service = TaskLifecycleService(
        TaskRepository(task_ttl_seconds=60), WorkflowRegistry()
    )
    config = ShotConfig()

    key_a = service._workflow_key(config, task_id="TSK_A")
    key_b = service._workflow_key(config, task_id="TSK_B")

    assert key_a != key_b
    assert key_a == service._workflow_key(ShotConfig(), task_id="TSK_A")


def test_factory_release_closes_connection(tmp_path):
    cp = create_checkpointer("SN_TEST", "TSK_REL", _config(tmp_path))
    try:
        assert (
            CheckpointerFactory.get_or_create("SN_TEST", "TSK_REL", _config(tmp_path))
            is cp
        )
        cp.get_saver()
        assert cp._conn is not None

        CheckpointerFactory.release("SN_TEST", "TSK_REL")

        assert cp._conn is None
    finally:
        CheckpointerFactory.release("SN_TEST", "TSK_REL")
