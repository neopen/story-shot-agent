"""
@FileName: task_factory.py
@Description: 任务工厂 - 封装任务提交和执行
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/24 11:56
"""

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import Future, TimeoutError

from penshot.logger import info, error, debug
from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.shot_language import ShotLanguage
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.task.task_models import ProcessingStatus, TaskStatus, TaskResponse, BatchTaskResponse, TaskStage
from penshot.neopen.task.task_processor import AsyncTaskProcessor, TaskPriority
from penshot.utils.log_utils import print_log_exception


class TaskFactory:
    """任务工厂 - 封装任务提交和执行"""

    def __init__(
            self,
            task_manager: Optional[TaskManager] = None,
            max_concurrent: int = 10,
            queue_size: int = 1000,
            default_config: Optional[ShotConfig] = None,
            default_language: ShotLanguage = ShotLanguage.ZH,
            max_cache_size: int = 64,
            task_ttl_seconds: int = 86400  # 新增参数，默认24小时
    ):
        self.task_manager = task_manager or TaskManager(max_cache_size=max_cache_size, task_ttl_seconds=task_ttl_seconds)
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

        self._batch_tasks: Dict[str, List[str]] = {}  # batch_id -> list of task_ids

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
            script_id: Optional[str] = None,
            style: Optional[VideoStyle] = None,
            config: Optional[ShotConfig] = None,
            language: ShotLanguage = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            callback_url: Optional[str] = None
    ) -> tuple[str, str]:
        """提交任务（异步，立即返回task_id）"""
        config = config or self.default_config
        language = language or self.default_language

        script_id, task_id = self.task_manager.create_task(
            script_id=script_id,
            script=script,
            style=style,
            config=config,
        )

        debug(f"[TaskFactory] 任务已创建: {task_id}")

        if callback_url:
            self.task_manager.set_task_callback(task_id, callback_url)

        if callback:
            self._callbacks[task_id] = callback

        # 创建 Future 用于同步等待
        future = Future()
        self._task_futures[task_id] = future

        def on_task_complete(task_id: str, result: TaskResponse):
            debug(f"[TaskFactory] 任务完成回调: {task_id}")

            # 直接存储 TaskResponse
            self._task_results[task_id] = result
            future = self._task_futures.pop(task_id, None)
            if future and not future.done():
                future.set_result(result)  # 直接传递 TaskResponse

            if task_id in self._callbacks:
                try:
                    self._callbacks[task_id](result)
                except Exception as e:
                    error(f"回调执行失败: {task_id}, 错误: {e}")
                    print_log_exception()
                finally:
                    del self._callbacks[task_id]

        async def submit_task():
            success = await self.processor.submit_task(task_id, priority, on_task_complete)
            if not success:
                error(f"[TaskFactory] 任务提交失败: {task_id}")
                future = self._task_futures.pop(task_id, None)
                if future and not future.done():
                    future.set_exception(RuntimeError(f"任务提交失败: {task_id}"))

        self._run_async_in_background(submit_task())

        info(f"任务已提交: {task_id}, 优先级: {priority.name}")
        return script_id, task_id

    def submit_and_wait(
            self,
            script: str,
            script_id: Optional[str] = None,
            config: Optional[ShotConfig] = None,
            language: ShotLanguage = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 300,
            callback_url: Optional[str] = None
    ) -> TaskResponse:
        """提交任务并等待完成（同步）"""
        script_id2, task_id = self.submit(
            script=script,
            script_id=script_id,
            config=config,
            language=language,
            priority=priority,
            callback_url=callback_url
        )
        return self.wait_for_result(task_id, timeout)

    async def submit_and_wait_async(
            self,
            script: str,
            script_id: Optional[str] = None,
            config: Optional[ShotConfig] = None,
            language: ShotLanguage = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 300,
            callback_url: Optional[str] = None
    ) -> TaskResponse:
        """
        提交任务并等待完成（异步）

        Args:
            script: 剧本文本
            script_id: 剧本ID（可选）
            config: 配置
            language: 语言
            priority: 优先级
            timeout: 超时时间
            callback_url: 回调URL

        Returns:
            TaskResponse: 任务结果
        """
        # 提交任务
        script_id2, task_id = self.submit(
            script=script,
            script_id=script_id,
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

        # 获取状态
        status = task.get("status", TaskStatus.PENDING)
        if isinstance(status, str):
            try:
                status = TaskStatus(status)
            except ValueError:
                status = TaskStatus.UNKNOWN

        # 获取当前阶段
        current_stage = task.get("current_stage")
        progress = task.get("progress", 0)

        # 获取阶段进度详情
        progress_details = task.get("progress_details", {})
        stages_progress = {}
        for stage_code, detail in progress_details.items():
            stage = TaskStage.from_code(stage_code)
            if stage:
                stages_progress[stage.name] = detail
            else:
                stages_progress[stage_code] = detail

        return ProcessingStatus(
            task_id=task_id,
            status=status,
            stage=current_stage or task.get("stage"),
            stage_name=TaskStage.from_code(current_stage).name if current_stage else None,
            progress=progress,
            created_at=created_at,
            updated_at=updated_at,
            error_message=task.get("error"),
            current_stage=current_stage,
            stages_progress=stages_progress
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
            # 使用 Future.result() 等待
            result_data = future.result(timeout=timeout)

            # 如果 result_data 已经是 TaskResponse，直接返回
            if isinstance(result_data, TaskResponse):
                return result_data

            # 否则创建 TaskResponse
            return TaskResponse(
                task_id=task_id,
                success=True,
                status=TaskStatus.SUCCESS,
                data=result_data,
            )

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
            language: ShotLanguage = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            timeout: float = 600,
            callback_url: Optional[str] = None
    ) -> List[TaskResponse]:
        """批量处理（同步，等待全部完成）"""
        task_ids = []
        for script in scripts:
            script_id, task_id = self.submit(
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
            language: ShotLanguage = None,
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
            language: ShotLanguage = None,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback_url: Optional[str] = None
    ) -> BatchTaskResponse:
        """
        批量提交（不等待完成）
        """
        batch_id = self._generate_batch_id()
        task_ids = []

        for script in scripts:
            script_id, task_id = self.submit(
                script=script,
                config=config,
                language=language,
                priority=priority,
                callback_url=callback_url
            )
            task_ids.append(task_id)

            # 保存批次信息到任务中
            task = self.task_manager.get_task(task_id)
            if task:
                # 更新任务的批次信息
                task["batch_id"] = batch_id
                self.task_manager.update_task_result(task_id, {"batch_id": batch_id})

        # 保存批次映射
        self._batch_tasks[batch_id] = task_ids

        return BatchTaskResponse(
            batch_id=batch_id,
            total_tasks=len(task_ids),
            task_ids=task_ids,
            status=TaskStatus.PENDING
        )

    def batch_get_status(self, batch_id: str) -> List[ProcessingStatus]:
        """
        获取批量任务状态

        Args:
            batch_id: 批量任务ID

        Returns:
            List[ProcessingStatus]: 批次中所有任务的状态列表
        """
        # 获取批次下所有任务ID
        # 注意：这里需要从 TaskManager 获取批次信息
        # 由于当前 TaskManager 没有直接存储批次信息，我们需要通过其他方式获取

        # 方式1：通过 task_manager 的元数据获取（如果存储了批次信息）
        task_ids = self._get_task_ids_by_batch(batch_id)

        if not task_ids:
            # 方式2：如果没有存储批次信息，尝试从所有任务中查找
            all_task_ids = self.task_manager.list_tasks()
            task_ids = []
            for tid in all_task_ids:
                task = self.task_manager.get_task(tid)
                if task and task.get("batch_id") == batch_id:
                    task_ids.append(tid)

        # 获取每个任务的状态
        statuses = []
        for task_id in task_ids:
            status = self.get_status(task_id)
            if status:
                statuses.append(status)

        return statuses

    def batch_get_results(self, batch_id: str) -> List[TaskResponse]:
        """
        获取批量任务结果

        Args:
            batch_id: 批量任务ID

        Returns:
            List[TaskResponse]: 批次中所有任务的结果列表
        """
        task_ids = self._get_task_ids_by_batch(batch_id)

        results = []
        for task_id in task_ids:
            result = self.get_result(task_id)
            if result:
                results.append(result)

        return results

    def _get_task_ids_by_batch(self, batch_id: str) -> List[str]:
        """
        根据批次ID获取任务ID列表
        """
        task_ids = []

        # 方式1：从 batch_submit 时保存的映射中获取
        if hasattr(self, '_batch_tasks'):
            return self._batch_tasks.get(batch_id, [])

        # 方式2：遍历所有任务查找
        all_task_ids = self.task_manager.list_tasks()
        for tid in all_task_ids:
            task = self.task_manager.get_task(tid)
            if task and task.get("batch_id") == batch_id:
                task_ids.append(tid)

        return task_ids

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

    #     ============================ 恢复任务 ================================
    def recover_pending_tasks(self, max_age_hours: int = 2):
        """
        恢复所有未完成的任务（只恢复两小时内的任务）

        Args:
            max_age_hours: 最大任务年龄（小时），默认2小时

        Returns:
            int: 恢复的任务数量
        """
        info(f"开始恢复未完成的任务（{max_age_hours}小时内）...")

        # 先恢复任务状态
        recovered_ids = self.task_manager.recover_all_pending_tasks(max_age_hours=max_age_hours)

        if recovered_ids:
            # 将恢复的任务加入处理器队列
            async def recover_in_background():
                self.processor.recover_pending_tasks(max_age_hours=max_age_hours)

            self._run_async_in_background(recover_in_background())

            info(f"已恢复 {len(recovered_ids)} 个任务（{max_age_hours}小时内）")
        else:
            info(f"没有需要恢复的任务（{max_age_hours}小时内）")


    def get_pending_tasks(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """
        获取所有未完成的任务（只返回两小时内的任务）

        Args:
            max_age_hours: 最大任务年龄（小时）

        Returns:
            List[Dict]: 未完成的任务列表
        """
        return self.task_manager.get_pending_tasks(max_age_hours=max_age_hours)


    def _generate_batch_id(self) -> str:
        """生成批次ID"""
        import random
        return "BCH" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))


def create_task_factory(
        max_concurrent: int = 10,
        queue_size: int = 1000,
        default_config: Optional[ShotConfig] = None,
        default_language: ShotLanguage = ShotLanguage.ZH,
        task_ttl_seconds: int = 7 * 86400
) -> TaskFactory:
    """创建任务工厂实例"""
    return TaskFactory(
        max_concurrent=max_concurrent,
        queue_size=queue_size,
        default_config=default_config,
        default_language=default_language,
        task_ttl_seconds=task_ttl_seconds
    )