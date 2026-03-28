"""
@FileName: function_calls.py
@Description: Function Call接口 - 供其他Python智能体调用
@Author: HiPeng
@Time: 2026/3/23 18:39
"""

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List, Any, Callable

from penshot.logger import log_with_context, info, error
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.shot_language import Language, set_language
from penshot.neopen.task.task_factory import create_task_factory, TaskFactory, TaskResponse, TaskPriority
from penshot.neopen.task.task_models import TaskStatus
from penshot.utils.log_utils import print_log_exception


@dataclass
class PenshotResult:
    """Penshot 执行结果"""
    task_id: str
    success: bool
    status: TaskStatus  # pending, processing, completed, failed, timeout, not_found
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms
        }


class PenshotFunction:
    """
    Penshot 智能体功能调用接口

    使用 TaskFactory 统一管理任务队列、并发控制和任务生命周期
    """

    def __init__(
            self,
            config: Optional[ShotConfig] = None,
            language: Language = Language.ZH,
            max_concurrent: int = 10,
            queue_size: int = 1000
    ):
        """
        初始化 Penshot 功能接口

        Args:
            config: 系统配置
            language: 输出语言
            max_concurrent: 最大并发数（默认10）
            queue_size: 队列大小（默认1000）
        """
        self.config = config or ShotConfig()
        self.language = language

        # 使用 TaskFactory 替代原始的 TaskManager + TaskProcessor
        self.task_factory: TaskFactory = create_task_factory(
            max_concurrent=max_concurrent,
            queue_size=queue_size,
            default_config=config,
            default_language=language
        )

        # 保持兼容性
        self.task_manager = self.task_factory.task_manager

        # 回调存储
        self._callbacks: Dict[str, Callable] = {}

        # 后台任务事件循环
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None
        self._background_thread: Optional[threading.Thread] = None
        self._start_background_loop()

        info(f"PenshotFunction 初始化完成，最大并发: {max_concurrent}")

    def _start_background_loop(self):
        """启动后台事件循环"""

        def run_loop():
            self._background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._background_loop)
            self._background_loop.run_forever()

        self._background_thread = threading.Thread(target=run_loop, daemon=True)
        self._background_thread.start()

        # 等待循环启动
        while self._background_loop is None:
            pass

    def _run_async_in_background(self, coro):
        """在后台事件循环中运行协程"""
        if self._background_loop is None:
            raise RuntimeError("后台事件循环未启动")
        return asyncio.run_coroutine_threadsafe(coro, self._background_loop)

    # ==================== 核心方法 ====================
    def breakdown_script(
            self,
            script_text: str,
            task_id: Optional[str] = None,
            language: Optional[Language] = None,
            wait_timeout: float = 300.0,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> PenshotResult:
        """
        同步执行剧本分镜拆分（等待完成）

        Args:
            script_text: 剧本文本
            task_id: 任务ID（可选）
            language: 输出语言
            wait_timeout: 等待超时时间（秒）
            priority: 任务优先级

        Returns:
            PenshotResult: 执行结果
        """
        task_id = self.breakdown_script_async(
            script_text=script_text,
            task_id=task_id,
            language=language,
            priority=priority
        )
        return self.wait_for_result(task_id, timeout=wait_timeout)

    def breakdown_script_async(
            self,
            script_text: str,
            task_id: Optional[str] = None,
            language: Optional[Language] = None,
            callback: Optional[Callable] = None,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """
        异步执行剧本分镜拆分（立即返回 task_id）

        Args:
            script_text: 剧本文本
            task_id: 任务ID（可选）
            language: 输出语言
            callback: 任务完成回调函数
            priority: 任务优先级

        Returns:
            str: 任务ID
        """
        # 生成任务ID
        task_id = task_id or self._generate_task_id()
        lang = language or self.language

        # 保存回调
        if callback:
            self._callbacks[task_id] = callback

        # 设置语言
        set_language(lang)

        # 使用 TaskFactory 提交任务
        self.task_factory.submit(
            script=script_text,
            task_id=task_id,
            config=self.config,
            language=lang,
            priority=priority,
            callback=lambda r: self._on_task_complete(task_id, r)
        )

        log_with_context("INFO", f"任务已提交: {task_id}", {"priority": priority.name})
        return task_id

    def _on_task_complete(self, task_id: str, task_response: TaskResponse):
        """任务完成回调"""
        # 转换为 PenshotResult
        result = PenshotResult(
            task_id=task_response.task_id,
            success=task_response.success,
            status=task_response.status,
            data=task_response.data,
            error=task_response.error,
            processing_time_ms=task_response.processing_time_ms
        )

        # 触发用户回调
        if task_id in self._callbacks:
            callback = self._callbacks[task_id]
            try:
                callback(result)
            except Exception as e:
                error(f"回调失败: {task_id}, 错误: {str(e)}")
                print_log_exception()
            finally:
                del self._callbacks[task_id]

    # ==================== 状态查询方法 ====================

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            Dict: 任务状态信息
        """
        status = self.task_factory.get_status(task_id)
        if status:
            return {
                "task_id": status.task_id,
                "status": status.status,
                "stage": status.stage,
                "progress": status.progress,
                "created_at": status.created_at,
                "updated_at": status.updated_at,
                "error": status.error_message
            }
        return None

    def get_task_result(self, task_id: str) -> Optional[PenshotResult]:
        """
        获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            PenshotResult: 任务结果
        """
        result = self.task_factory.get_result(task_id)
        if not result:
            return None

        return PenshotResult(
            task_id=result.task_id,
            success=result.success,
            status=result.status,
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms
        )

    def wait_for_result(
            self,
            task_id: str,
            timeout: float = 300.0
    ) -> Optional[PenshotResult]:
        """
        同步等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）

        Returns:
            PenshotResult: 任务结果
        """
        result = self.task_factory.wait_for_result(
            task_id=task_id,
            timeout=timeout,
        )

        if not result:
            return None

        return PenshotResult(
            task_id=result.task_id,
            success=result.success,
            status=result.status,
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms
        )

    async def wait_for_result_async(
            self,
            task_id: str,
            timeout: float = 300.0,
            poll_interval: float = 0.5
    ) -> PenshotResult:
        """
        异步等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）

        Returns:
            PenshotResult: 任务结果
        """
        result = await self.task_factory.wait_for_result_async(
            task_id=task_id,
            timeout=timeout,
            poll_interval=poll_interval
        )

        return PenshotResult(
            task_id=result.task_id,
            success=result.success,
            status=result.status,
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms
        )

    # ==================== 任务管理方法 ====================

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        return self.task_factory.cancel(task_id)

    def batch_breakdown(
            self,
            scripts: List[str],
            language: Optional[Language] = None,
            wait_timeout: float = 600.0,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> List[PenshotResult]:
        """
        批量处理多个剧本（同步，等待全部完成）

        Args:
            scripts: 剧本列表
            language: 输出语言
            wait_timeout: 单个任务超时时间
            priority: 任务优先级

        Returns:
            List[PenshotResult]: 结果列表
        """
        # 使用 TaskFactory 的批量处理方法
        results = self.task_factory.batch(
            scripts=scripts,
            config=self.config,
            language=language.value if language else self.language.value,
            priority=priority,
            timeout=wait_timeout
        )

        # 转换为 PenshotResult
        return [
            PenshotResult(
                task_id=r.task_id,
                success=r.success,
                status=r.status,
                data=r.data,
                error=r.error,
                processing_time_ms=r.processing_time_ms
            )
            for r in results
        ]

    async def batch_breakdown_async(
            self,
            scripts: List[str],
            language: Optional[Language] = None,
            max_concurrent: int = 3,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> List[PenshotResult]:
        """
        批量处理多个剧本（异步，支持并发控制）

        Args:
            scripts: 剧本列表
            language: 输出语言
            max_concurrent: 最大并发数
            priority: 任务优先级

        Returns:
            List[PenshotResult]: 结果列表
        """
        results = await self.task_factory.batch_async(
            scripts=scripts,
            config=self.config,
            language=language.value if language else self.language.value,
            priority=priority,
            max_concurrent=max_concurrent
        )

        return [
            PenshotResult(
                task_id=r.task_id,
                success=r.success,
                status=r.status,
                data=r.data,
                error=r.error,
                processing_time_ms=r.processing_time_ms
            )
            for r in results
        ]

    # ==================== 队列监控方法 ====================

    def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态

        Returns:
            Dict: 队列状态信息
        """
        return self.task_factory.get_queue_status()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return self.task_factory.get_stats()

    def set_max_concurrent(self, max_concurrent: int):
        """
        动态设置最大并发数

        Args:
            max_concurrent: 最大并发数
        """
        self.task_factory.set_max_concurrent(max_concurrent)
        info(f"最大并发数已调整为: {max_concurrent}")

    # ==================== 生命周期管理 ====================

    def shutdown(self):
        """
        关闭 Penshot 功能接口

        等待所有任务完成后关闭
        """
        info("正在关闭 PenshotFunction...")
        # 使用异步方式关闭
        future = self._run_async_in_background(
            self.task_factory.shutdown(wait_for_completion=True, timeout=30)
        )
        try:
            future.result(timeout=35)
        except Exception as e:
            error(f"关闭时发生错误: {str(e)}")

        # 停止后台事件循环
        if self._background_loop:
            self._background_loop.call_soon_threadsafe(self._background_loop.stop)
        if self._background_thread:
            self._background_thread.join(timeout=5)

        info("PenshotFunction 已关闭")

    # ==================== 辅助方法 ====================

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        import random
        return "TSK" + datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))


# ==================== 便捷函数 ====================

def create_penshot_agent(
        config: Optional[ShotConfig] = None,
        language: Language = Language.ZH,
        max_concurrent: int = 10,
        queue_size: int = 1000
) -> PenshotFunction:
    """
    创建 Penshot 智能体实例

    Args:
        config: 系统配置
        language: 输出语言
        max_concurrent: 最大并发数
        queue_size: 队列大小

    Returns:
        PenshotFunction: 智能体实例
    """
    return PenshotFunction(
        config=config,
        language=language,
        max_concurrent=max_concurrent,
        queue_size=queue_size
    )
