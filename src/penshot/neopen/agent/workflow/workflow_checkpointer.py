"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: workflow_checkpointer.py
@Description: 工作流检查点管理器 - 简化版（仅同步）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/5/14 20:55
"""
import glob
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    # langgraph-checkpoint-sqlite 未安装时优雅降级：SQLite 模式自动回退为内存模式
    SqliteSaver = None

from penshot.logger import debug, info, warning
from penshot.neopen.shot_config import ShotConfig


class CheckpointMode(str, Enum):
    """检查点存储模式"""
    MEMORY = "memory"   # 内存模式（开发测试）
    SQLITE = "sqlite"   # SQLite 模式（本地生产）


@dataclass
class CheckpointStats:
    """检查点统计信息"""
    script_id: str
    task_id: str
    mode: str
    db_path: Optional[str] = None
    file_size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)


class WorkflowCheckpointer:
    """
    工作流检查点管理器 - 简化版

    功能：
    - 自动选择存储模式（内存/SQLite）
    - 管理 SQLite 数据库生命周期
    - 清理旧检查点文件
    - 提供 LangGraph 所需的 BaseCheckpointSaver 实例

    使用示例：
        # 创建管理器
        cp = WorkflowCheckpointer("script_001", "task_001", config)

        # 获取 LangGraph saver
        saver = cp.get_saver()

        # 编译工作流
        graph = builder.compile(checkpointer=saver)

        # 执行
        config = cp.get_config()
        result = graph.invoke(initial_state, config=config)

        # 清理和关闭
        cp.cleanup_old_checkpoints(keep_count=5)
        cp.close()
    """

    def __init__(self, script_id: str, task_id: str, config: ShotConfig):
        """
        初始化检查点管理器

        Args:
            script_id: 剧本ID
            task_id: 任务ID
            config: 配置对象
        """
        self.script_id = script_id
        self.task_id = task_id
        self.config = config

        # 确定存储模式
        self.mode = self._determine_mode()
        self.db_path: Optional[str] = None
        self._saver = None
        self._conn = None

        # 设置存储路径
        self._setup_storage()

        # 统计信息
        self.stats = CheckpointStats(
            script_id=script_id,
            task_id=task_id,
            mode=self.mode.value,
            db_path=self.db_path
        )

        info(f"检查点管理器初始化: {script_id}/{task_id}, mode={self.mode.value}")

    def _determine_mode(self) -> CheckpointMode:
        """确定存储模式"""
        mode = getattr(self.config, 'checkpoint_mode', 'auto')

        if mode == 'memory':
            return CheckpointMode.MEMORY

        elif mode == 'sqlite':
            return CheckpointMode.SQLITE

        else:  # auto 或其他
            # 尝试使用 SQLite，失败则降级到内存
            try:
                checkpoint_dir = getattr(self.config, 'checkpoint_dir', 'data/checkpoints')
                os.makedirs(checkpoint_dir, exist_ok=True)
                test_path = os.path.join(checkpoint_dir, '.write_test')
                with open(test_path, 'w') as f:
                    f.write('test')
                os.remove(test_path)
                return CheckpointMode.SQLITE
            except Exception:
                warning("SQLite 不可用，降级到内存模式")
                return CheckpointMode.MEMORY

    def _setup_storage(self):
        """设置存储路径"""
        if self.mode == CheckpointMode.SQLITE:
            checkpoint_dir = getattr(self.config, 'checkpoint_dir', 'data/checkpoints')
            script_dir = os.path.join(checkpoint_dir, self.script_id)
            os.makedirs(script_dir, exist_ok=True)
            self.db_path = os.path.join(script_dir, f"task_{self.task_id}.db")

    def get_saver(self):
        """
        获取 BaseCheckpointSaver 实例（供 LangGraph 使用）

        Returns:
            MemorySaver 或 SqliteSaver 实例
        """
        if self._saver is not None:
            return self._saver

        if self.mode == CheckpointMode.MEMORY:
            # 使用 MemorySaver（仅内存）
            from langgraph.checkpoint.memory import MemorySaver
            self._saver = MemorySaver()
            info("使用 MemorySaver（内存模式）")

        elif self.mode == CheckpointMode.SQLITE:
            if SqliteSaver is None:
                # langgraph-checkpoint-sqlite 未安装：回退为内存模式
                warning("langgraph-checkpoint-sqlite 未安装，SQLite 检查点不可用，回退为内存模式（服务重启后状态丢失）")
                from langgraph.checkpoint.memory import MemorySaver
                self._saver = MemorySaver()
            else:
                # 创建数据库连接
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")

                self._saver = SqliteSaver(self._conn)
                info(f"使用 SqliteSaver: {self.db_path}")

        return self._saver

    def get_config(self) -> Dict[str, Any]:
        """
        获取 LangGraph 运行配置

        Returns:
            包含 thread_id 的配置字典
        """
        return {
            "configurable": {
                "thread_id": f"{self.script_id}_{self.task_id}"
            }
        }

    def get_thread_id(self) -> str:
        """获取线程ID"""
        return f"{self.script_id}_{self.task_id}"

    def cleanup_old_checkpoints(self, keep_count: int = 10):
        """
        清理旧的检查点文件

        Args:
            keep_count: 保留最近的文件数量
        """
        if self.mode != CheckpointMode.SQLITE:
            return

        if not self.db_path:
            return

        script_dir = os.path.dirname(self.db_path)
        pattern = os.path.join(script_dir, "task_*.db")
        files = glob.glob(pattern)

        if len(files) <= keep_count:
            return

        # 按修改时间排序
        files.sort(key=os.path.getmtime, reverse=True)

        # 删除多余文件（保留当前使用的）
        removed = 0
        for old_file in files[keep_count:]:
            if old_file != self.db_path:  # 不删除当前正在使用的
                try:
                    os.remove(old_file)
                    removed += 1
                    debug(f"已清理旧检查点: {old_file}")
                except Exception as e:
                    warning(f"清理检查点失败: {old_file}, {e}")

        if removed > 0:
            info(f"已清理 {removed} 个旧检查点文件")

    def get_stats(self) -> CheckpointStats:
        """获取统计信息"""
        self.stats.last_accessed = datetime.now()

        if self.mode == CheckpointMode.SQLITE and self.db_path and os.path.exists(self.db_path):
            try:
                self.stats.file_size_bytes = os.path.getsize(self.db_path)
            except Exception:
                pass

        return self.stats

    async def close(self):
        """关闭检查点，释放资源"""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        self._saver = None
        info(f"检查点已关闭: {self.script_id}/{self.task_id}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# ============================================================================
# 工厂类
# ============================================================================

class CheckpointerFactory:
    """
    检查点工厂类
    管理多个检查点实例，避免重复创建
    """

    _instances: Dict[str, WorkflowCheckpointer] = {}
    _lock = threading.RLock()

    @classmethod
    def get_or_create(cls, script_id: str, task_id: str, config: ShotConfig) -> WorkflowCheckpointer:
        """获取或创建检查点实例"""
        key = f"{script_id}_{task_id}"

        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = WorkflowCheckpointer(script_id, task_id, config)
            return cls._instances[key]

    @classmethod
    def close_all(cls):
        """关闭所有检查点"""
        with cls._lock:
            for key, cp in cls._instances.items():
                try:
                    cp.close()
                except Exception as e:
                    warning(f"关闭检查点失败: {key}, {e}")
            cls._instances.clear()

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取所有检查点统计"""
        with cls._lock:
            return {
                "total_instances": len(cls._instances),
                "instances": {
                    key: cp.get_stats().__dict__
                    for key, cp in cls._instances.items()
                }
            }


# ============================================================================
# 便捷函数
# ============================================================================

def create_checkpointer(script_id: str, task_id: str, config: ShotConfig) -> WorkflowCheckpointer:
    """创建检查点实例（便捷函数）"""
    return CheckpointerFactory.get_or_create(script_id, task_id, config)


def close_all_checkpointers():
    """关闭所有检查点"""
    CheckpointerFactory.close_all()