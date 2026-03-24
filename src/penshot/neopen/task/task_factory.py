"""
@FileName: task_factory.py
@Description: 任务工厂 - 封装任务提交和执行
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/24 11:56
"""

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import Future, TimeoutError

from penshot.logger import info, error, debug
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.shot_language import Language
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.task.task_models import ProcessingStatus, TaskStatus, TaskResponse, BatchTaskResponse
from penshot.neopen.task.task_processor import AsyncTaskProcessor, TaskPriority

class TaskFactory:
    """任务工厂 - 封装任务提交和执行"""

    def __init__(
            self,
            task_manager: Optional[TaskManager] = None,
            max_concurrent: int = 10,
            queue_size: int = 1000,
            default_config: Optional[ShotConfig] = None,
            default_language: Language = Language.ZH
    ):
        self.task_manager = task_manager or TaskManager()
        self.processor = AsyncTaskProcessor(
            task_manager=self.task_manager,
            max_concurrent=max_concurrent,
            queue_size=queue_size
        )
        self.default_config = default_config or ShotConfig()
        self.default_language = default_language

        # 存储任务回调
        self._callbacks: Dict[str, Callable] = {}

        # 使用 Future 替代 threading.Event
        self._task_futures: Dict[str, Future] = {}
        self._task_results: Dict[str, TaskResponse] = {}

        # 启动后台任务处理线程
        self._background_thread: Optional[threading.Thread] = None
        self._start_background_processor()

        info(f"任务工厂初始化完成，最大并发: {max_concurrent}")

    def _start_background_processor(self):
        """启动后台任务处理器"""
        def run_processor():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.processor._background_loop = loop
            try:
                loop.run_forever()
            except Exception as e:
                error(f"后台处理器循环异常: {e}")
            finally:
                loop.close()

        self._background_thread = threading.Thread(target=run_processor, daemon=True)
        self._background_thread.start()

        timeout = 5
        start = time.time()
        while not hasattr(self.processor, '_background_loop') or self.processor._background_loop is None:
            if time.time() - start > timeout:
                error("后台处理器启动超时")
                break
            time.sleep(0.01)

        info("后台任务处理器已启动")

    def _run_async_in_background(self, coro):
        """在后台事件循环中运行协程"""
        if not hasattr(self.processor, '_background_loop') or self.processor._background_loop is None:
            raise RuntimeError("后台事件循环未启动")
        return asyncio.run_coroutine_threadsafe(coro, self.processor._background_loop)

    # ==================== 核心提交方法 ====================

    def submit(
            self,
            script: str,
            task_id: Optional[str] = None,
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            callback_url: Optional[str] = None
    ) -> str:
        """提交任务（异步，立即返回task_id）"""
        task_id = task_id or self._generate_task_id()
        config = config or self.default_config
        language = language or self.default_language

        created_task_id = self.task_manager.create_task(
            script=script,
            config=config,
            task_id=task_id
        )

        debug(f"[TaskFactory] 任务已创建: {created_task_id}")

        if callback_url:
            self.task_manager.set_task_callback(created_task_id, callback_url)

        if callback:
            self._callbacks[created_task_id] = callback

        # 创建 Future 用于同步等待
        future = Future()
        self._task_futures[created_task_id] = future

        def on_task_complete(task_id: str, result: TaskResponse):
            debug(f"[TaskFactory] 任务完成回调: {task_id}")
            self._task_results[task_id] = result
            future = self._task_futures.pop(task_id, None)
            if future and not future.done():
                future.set_result(result)
            if task_id in self._callbacks:
                try:
                    self._callbacks[task_id](result)
                except Exception as e:
                    error(f"回调执行失败: {task_id}, 错误: {e}")
                finally:
                    del self._callbacks[task_id]

        async def submit_task():
            success = await self.processor.submit_task(created_task_id, priority, on_task_complete)
            if not success:
                error(f"[TaskFactory] 任务提交失败: {created_task_id}")
                future = self._task_futures.pop(created_task_id, None)
                if future and not future.done():
                    future.set_exception(RuntimeError(f"任务提交失败: {created_task_id}"))

        self._run_async_in_background(submit_task())

        info(f"任务已提交: {created_task_id}, 优先级: {priority.name}")
        return created_task_id

    def submit_and_wait(
            self,
            script: str,
            task_id: Optional[str] = None,
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 300,
            callback_url: Optional[str] = None
    ) -> TaskResponse:
        """提交任务并等待完成（同步）"""
        task_id = self.submit(
            script=script,
            task_id=task_id,
            config=config,
            language=language,
            priority=priority,
            callback_url=callback_url
        )
        return self.wait_for_result(task_id, timeout)

    async def submit_and_wait_async(
            self,
            script: str,
            task_id: Optional[str] = None,
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 300,
            callback_url: Optional[str] = None
    ) -> TaskResponse:
        """
        提交任务并等待完成（异步）

        Args:
            script: 剧本文本
            task_id: 任务ID（可选）
            config: 配置
            language: 语言
            priority: 优先级
            timeout: 超时时间
            callback_url: 回调URL

        Returns:
            TaskResponse: 任务结果
        """
        # 提交任务
        task_id = self.submit(
            script=script,
            task_id=task_id,
            config=config,
            language=language,
            priority=priority,
            callback_url=callback_url
        )

        # 异步等待结果
        return await self.wait_for_result_async(task_id, timeout)

    # ==================== 结果获取方法 ====================

    def get_status(self, task_id: str) -> Optional[ProcessingStatus]:
        """获取任务状态"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return None

        created_at = task.get("created_at")
        updated_at = task.get("updated_at")

        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = None

        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = None

        return ProcessingStatus(
            task_id=task_id,
            status=task.get("status", TaskStatus.PENDING),
            stage=task.get("stage"),
            progress=task.get("progress"),
            created_at=created_at,
            updated_at=updated_at,
            error_message=task.get("error")
        )

    def get_result(self, task_id: str) -> Optional[TaskResponse]:
        """获取任务结果"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return None

        status = task.get("status")
        is_success = status == TaskStatus.SUCCESS

        created_at = task.get("created_at")
        completed_at = task.get("completed_at")

        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = None

        if isinstance(completed_at, str):
            try:
                completed_at = datetime.fromisoformat(completed_at)
            except Exception:
                completed_at = None

        processing_time = None
        if completed_at and created_at:
            try:
                processing_time = int((completed_at - created_at).total_seconds() * 1000)
            except Exception:
                pass

        data = None
        if task.get("result") and isinstance(task["result"], dict):
            data = task["result"].get("data")

        return TaskResponse(
            task_id=task_id,
            success=is_success,
            status=status,
            data=data,
            error=task.get("error"),
            processing_time_ms=processing_time,
            created_at=created_at,
            completed_at=completed_at
        )

    def wait_for_result(
            self,
            task_id: str,
            timeout: float = 300
    ) -> Optional[TaskResponse]:
        """
        同步等待任务完成（使用 Future，不阻塞后台事件循环）
        """
        # 先检查是否已经完成
        result = self.get_result(task_id)
        if result and result.status in [TaskStatus.SUCCESS, TaskStatus.FAILED]:
            return result

        # 检查任务是否存在
        task = self.task_manager.get_task(task_id)
        if not task:
            return TaskResponse(
                task_id=task_id,
                success=False,
                status=TaskStatus.NOT_FOUND,
                error=f"任务不存在: {task_id}"
            )

        # 获取 Future
        future = self._task_futures.get(task_id)
        if future is None:
            debug(f"[TaskFactory] Future不存在，使用轮询: {task_id}")
            return self._wait_by_polling(task_id, timeout)

        try:
            # 使用 Future.result() 等待，这会释放 GIL，允许其他线程运行
            result = future.result(timeout=timeout)
            return result
        except TimeoutError:
            return TaskResponse(
                task_id=task_id,
                success=False,
                status=TaskStatus.TIMEOUT,
                error=f"等待超时 ({timeout}秒)"
            )
        except Exception as e:
            error(f"等待任务异常: {task_id}, 错误: {e}")
            return TaskResponse(
                task_id=task_id,
                success=False,
                status=TaskStatus.FAILED,
                error=str(e)
            )
        finally:
            self._cleanup_task(task_id)

    def _wait_by_polling(
            self,
            task_id: str,
            timeout: float
    ) -> TaskResponse:
        """通过轮询等待任务完成（备用方案）"""
        start_time = time.time()
        poll_interval = 0.5

        while time.time() - start_time < timeout:
            result = self.get_result(task_id)
            if result and result.status in [TaskStatus.SUCCESS, TaskStatus.FAILED]:
                return result
            time.sleep(poll_interval)

        return TaskResponse(
            task_id=task_id,
            success=False,
            status=TaskStatus.TIMEOUT,
            error=f"等待超时 ({timeout}秒)"
        )

    def _cleanup_task(self, task_id: str):
        """清理任务相关资源"""
        self._task_futures.pop(task_id, None)
        self._task_results.pop(task_id, None)

    async def wait_for_result_async(
            self,
            task_id: str,
            timeout: float = 300,
            poll_interval: float = 0.5
    ) -> TaskResponse:
        """
        异步等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）

        Returns:
            TaskResponse: 任务结果
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # 检查任务是否已完成
            result = self.get_result(task_id)
            if result and result.status in [TaskStatus.SUCCESS, TaskStatus.FAILED]:
                return result

            # 检查超时
            if asyncio.get_event_loop().time() - start_time > timeout:
                return TaskResponse(
                    task_id=task_id,
                    success=False,
                    status=TaskStatus.TIMEOUT,
                    error=f"等待超时 ({timeout}秒)"
                )

            # 等待后继续轮询
            await asyncio.sleep(poll_interval)

    # ==================== 批量处理方法 ====================

    def batch(
            self,
            scripts: List[str],
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 600,
            callback_url: Optional[str] = None
    ) -> List[TaskResponse]:
        """批量处理（同步，等待全部完成）"""
        task_ids = []
        for script in scripts:
            task_id = self.submit(
                script=script,
                config=config,
                language=language,
                priority=priority,
                callback_url=callback_url
            )
            task_ids.append(task_id)

        results = []
        for task_id in task_ids:
            result = self.wait_for_result(task_id, timeout)
            results.append(result)

        return results

    async def batch_async(
            self,
            scripts: List[str],
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 600,
            callback_url: Optional[str] = None,
            max_concurrent: int = 5
    ) -> List[TaskResponse]:
        """批量处理（异步，支持并发控制）"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_one(script: str) -> TaskResponse:
            async with semaphore:
                return await self.submit_and_wait_async(
                    script=script,
                    config=config,
                    language=language,
                    priority=priority,
                    timeout=timeout,
                    callback_url=callback_url
                )

        tasks = [process_one(script) for script in scripts]
        return await asyncio.gather(*tasks)

    def batch_submit(
            self,
            scripts: List[str],
            config: Optional[ShotConfig] = None,
            language: Language = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback_url: Optional[str] = None
    ) -> BatchTaskResponse:
        """批量提交（不等待完成）"""
        batch_id = self._generate_batch_id()
        task_ids = []

        for script in scripts:
            task_id = self.submit(
                script=script,
                config=config,
                language=language,
                priority=priority,
                callback_url=callback_url
            )
            task_ids.append(task_id)

        return BatchTaskResponse(
            batch_id=batch_id,
            total_tasks=len(task_ids),
            task_ids=task_ids,
            status=TaskStatus.PENDING
        )

    def batch_get_results(
            self,
            task_ids: List[str]
    ) -> List[TaskResponse]:
        """批量获取任务结果"""
        results = []
        for task_id in task_ids:
            result = self.get_result(task_id)
            if result is not None:
                results.append(result)
        return results

    # ==================== 任务管理方法 ====================

    def cancel(self, task_id: str) -> bool:
        """取消任务"""
        future = self._task_futures.pop(task_id, None)
        if future and not future.done():
            future.set_exception(RuntimeError(f"任务被取消: {task_id}"))
        self._cleanup_task(task_id)
        return self.processor.cancel_task(task_id)

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return self.processor.get_queue_status()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.processor.get_stats()

    def set_max_concurrent(self, max_concurrent: int):
        """设置最大并发数"""
        self.processor.set_max_concurrent(max_concurrent)
        info(f"最大并发数已调整为: {max_concurrent}")

    async def shutdown(self, wait_for_completion: bool = True, timeout: float = 30):
        """关闭工厂"""
        info("正在关闭任务工厂...")

        # 取消所有等待中的 Future
        for task_id, future in self._task_futures.items():
            if not future.done():
                future.set_exception(RuntimeError("任务工厂正在关闭"))

        await self.processor.shutdown(wait_for_completion, timeout)

        self._task_futures.clear()
        self._task_results.clear()

        info("任务工厂已关闭")

    # ==================== 辅助方法 ====================

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        import random
        return "TSK" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))

    def _generate_batch_id(self) -> str:
        """生成批次ID"""
        import random
        return "BCH" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))


def create_task_factory(
        max_concurrent: int = 10,
        queue_size: int = 1000,
        default_config: Optional[ShotConfig] = None,
        default_language: Language = Language.ZH
) -> TaskFactory:
    """创建任务工厂实例"""
    return TaskFactory(
        max_concurrent=max_concurrent,
        queue_size=queue_size,
        default_config=default_config,
        default_language=default_language
    )