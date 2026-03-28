"""
@FileName: task_processor.py
@Description: 异步任务处理器（支持并发控制和任务队列）
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 16:40
"""
import asyncio
import threading
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable

from penshot.logger import info, warning, error, debug
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_handler import CallbackHandler
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.task.task_models import CallbackPayload, TaskPriority, TaskStatus
from penshot.utils.log_utils import print_log_exception
from penshot.utils.obj_utils import dict_to_obj


class QueuedTask:
    """队列中的任务"""

    def __init__(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            metadata: Optional[Dict] = None
    ):
        self.task_id = task_id
        self.priority = priority
        self.callback = callback
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.enqueued_at = None
        self.started_at = None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "priority": self.priority.value,
            "priority_name": self.priority.name,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "enqueued_at": self.enqueued_at.isoformat() if self.enqueued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None
        }


class AsyncTaskProcessor:
    """异步任务处理器（支持并发控制和任务队列）"""

    def __init__(
            self,
            task_manager: TaskManager,
            max_concurrent: int = 10,
            queue_size: int = 1000
    ):
        """
        初始化异步任务处理器
        """
        self.task_manager = task_manager
        self.callback_handler = CallbackHandler()

        # 并发控制
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_count = 0

        # 任务队列
        self._queue: deque = deque()
        self._queue_max_size = queue_size
        self._queue_waiting = 0
        self._total_processed = 0

        # 任务优先级映射
        self._priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3
        }

        # 控制标志
        self._is_running = True
        self._worker_task: Optional[asyncio.Task] = None

        # 后台事件循环相关
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None
        self._background_thread: Optional[threading.Thread] = None

        # 统计信息
        self._stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "peak_queue_size": 0,
            "avg_wait_time_ms": 0.0
        }

        # 启动后台事件循环
        self._start_background_loop()

    def _start_background_loop(self):
        """启动后台事件循环"""

        def run_loop():
            debug(f"[AsyncTaskProcessor] 后台线程启动，创建事件循环")
            # 创建新的事件循环
            self._background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._background_loop)

            info(f"[AsyncTaskProcessor] 事件循环创建成功，创建工作器任务")

            # 创建工作器任务
            self._worker_task = self._background_loop.create_task(self._worker_loop())

            try:
                self._background_loop.run_forever()
            except Exception as e:
                error(f"后台事件循环异常: {e}")
            finally:
                self._background_loop.close()
                info(f"[AsyncTaskProcessor] 后台事件循环已关闭")

        self._background_thread = threading.Thread(target=run_loop, daemon=True)
        self._background_thread.start()

        # 等待循环启动
        import time
        timeout = 5
        start = time.time()
        while self._background_loop is None and (time.time() - start) < timeout:
            time.sleep(0.01)

        if self._background_loop:
            info(f"[AsyncTaskProcessor] 后台事件循环启动成功")
        else:
            error(f"[AsyncTaskProcessor] 后台事件循环启动超时")

    def _run_async_in_background(self, coro):
        """在后台事件循环中运行协程"""
        if self._background_loop is None:
            raise RuntimeError("后台事件循环未启动")
        return asyncio.run_coroutine_threadsafe(coro, self._background_loop)

    async def _worker_loop(self):
        """后台工作器循环，持续处理队列中的任务"""
        info(f"[AsyncTaskProcessor] 工作器循环启动")

        while self._is_running:
            try:
                # 打印当前状态
                debug(f"[AsyncTaskProcessor] 状态 - 活跃: {self._active_count}/{self.max_concurrent}, 队列: {len(self._queue)}")

                # 等待有空闲槽位
                if self._active_count >= self.max_concurrent:
                    await asyncio.sleep(0.1)
                    continue

                # 从队列中获取任务
                queued_task = await self._dequeue_task()

                if queued_task:
                    info(f"[AsyncTaskProcessor] 从队列取出任务: {queued_task.task_id}")
                    # 启动任务
                    asyncio.create_task(self._execute_task(queued_task))
                else:
                    # 队列为空时短暂休眠
                    await asyncio.sleep(0.05)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error(f"工作器循环异常: {str(e)}")
                await asyncio.sleep(0.5)

    async def _enqueue_task(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            metadata: Optional[Dict] = None
    ) -> bool:
        """将任务加入队列"""
        # 检查队列是否已满
        if len(self._queue) >= self._queue_max_size:
            warning(f"任务队列已满，拒绝任务: {task_id}")
            return False

        queued_task = QueuedTask(task_id, priority, callback, metadata)
        queued_task.enqueued_at = datetime.now(timezone.utc)

        # 按优先级插入队列
        inserted = False
        for i, existing in enumerate(self._queue):
            if self._priority_order[queued_task.priority] < self._priority_order[existing.priority]:
                self._queue.insert(i, queued_task)
                inserted = True
                break

        if not inserted:
            self._queue.append(queued_task)

        self._queue_waiting += 1
        self._stats["total_submitted"] += 1
        self._stats["peak_queue_size"] = max(self._stats["peak_queue_size"], len(self._queue))

        debug(f"任务入队: {task_id}, 优先级: {priority.name}, 队列长度: {len(self._queue)}")
        return True

    async def _dequeue_task(self) -> Optional[QueuedTask]:
        """从队列中取出任务"""
        if not self._queue:
            return None

        await asyncio.sleep(0.01)

        if self._queue:
            task = self._queue.popleft()
            self._queue_waiting -= 1
            task.started_at = datetime.now(timezone.utc)

            # 计算等待时间
            wait_ms = (task.started_at - task.enqueued_at).total_seconds() * 1000
            self._update_avg_wait_time(wait_ms)

            debug(f"任务出队: {task.task_id}, 等待时间: {wait_ms:.0f}ms")
            return task

        return None

    def _update_avg_wait_time(self, wait_ms: float):
        """更新平均等待时间"""
        total = self._stats["total_completed"] + self._stats["total_failed"]
        if total > 0:
            current_avg = self._stats["avg_wait_time_ms"]
            new_avg = (current_avg * total + wait_ms) / (total + 1)
            self._stats["avg_wait_time_ms"] = new_avg

    async def _execute_task(self, queued_task: QueuedTask):
        """执行单个任务"""
        task_id = queued_task.task_id
        self._active_count += 1
        self._active_tasks[task_id] = asyncio.current_task()

        try:
            async with self._semaphore:
                debug(f"开始执行任务: {task_id}, 活跃任务数: {self._active_count}")

                # 执行实际的任务处理
                result = await self._process_script_task_internal(task_id)

                self._stats["total_completed"] += 1
                info(f"任务完成: {task_id}")

                # 触发回调
                if queued_task.callback:
                    try:
                        if asyncio.iscoroutinefunction(queued_task.callback):
                            await queued_task.callback(task_id, result)
                        else:
                            queued_task.callback(task_id, result)
                    except Exception as e:
                        error(f"任务回调执行失败: {task_id}, 错误: {str(e)}")
                        print_log_exception()

        except asyncio.CancelledError:
            self._stats["total_cancelled"] += 1
            warning(f"任务被取消: {task_id}")
            self.task_manager.fail_task(task_id, "任务被取消")

        except Exception as e:
            self._stats["total_failed"] += 1
            error(f"任务执行失败: {task_id}, 错误: {str(e)}")
            print_log_exception()
            self.task_manager.fail_task(task_id, str(e))

        finally:
            self._active_count -= 1
            self._active_tasks.pop(task_id, None)
            debug(f"任务结束: {task_id}, 剩余活跃: {self._active_count}")

    async def _process_script_task_internal(self, task_id: str) -> Dict:
        """内部任务处理逻辑"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        config = dict_to_obj(task["config"], ShotConfig) if task.get("config") else ShotConfig()

        try:
            # 更新状态为处理中
            self.task_manager.update_task_progress(task_id, "processing", 10)

            # 获取工作流实例
            workflow = self.task_manager.get_workflow(task_id, config)

            # 执行处理
            self.task_manager.update_task_progress(task_id, "parsing_script", 20)
            result = await workflow.run_process(task["script"], config)

            # 更新进度
            self.task_manager.update_task_progress(task_id, "finalizing", 90)

            # 完成任务
            self.task_manager.complete_task(task_id, result)

            # 处理回调
            if task.get("callback_url"):
                await self._handle_callback(task_id, result)

            return result

        except Exception as e:
            error(f"任务处理失败: {task_id}, 错误: {str(e)}")
            raise

    async def _handle_callback(self, task_id: str, result: Dict):
        """处理回调通知"""
        task = self.task_manager.get_task(task_id)
        if not task or not task.get("callback_url"):
            return

        try:
            payload = CallbackPayload(
                task_id=task_id,
                status=TaskStatus.SUCCESS if result.get("success") else TaskStatus.FAILED,
                data=result.get("data"),
                error_message=result.get("error"),
                completed_at=datetime.now(timezone.utc)
            )
            await self.callback_handler.notify_callback(
                task["callback_url"],
                payload.model_dump()
            )
        except Exception as e:
            error(f"回调发送失败 for task {task_id}: {e}")

    # ==================== 公共接口 ====================

    async def submit_task(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            metadata: Optional[Dict] = None
    ) -> bool:
        """
        提交任务到队列
        """
        # 检查任务是否存在
        task = self.task_manager.get_task(task_id)
        if not task:
            error(f"任务不存在，无法提交: {task_id}")
            return False

        info(f"[AsyncTaskProcessor] 提交任务到队列: {task_id}, 优先级: {priority.name}")

        # 加入队列
        success = await self._enqueue_task(task_id, priority, callback, metadata)

        if success:
            info(f"[AsyncTaskProcessor] 任务已入队: {task_id}")
        else:
            error(f"[AsyncTaskProcessor] 任务入队失败: {task_id}")

        return success

    async def process_script_task(self, task_id: str, priority: TaskPriority = TaskPriority.NORMAL):
        """
        处理单个剧本任务
        """
        # 确保任务已创建
        task = self.task_manager.get_task(task_id)
        if not task:
            error(f"任务不存在: {task_id}")
            return

        # 提交到队列
        success = await self.submit_task(task_id, priority)

        if not success:
            warning(f"任务提交失败（队列已满）: {task_id}")
            self.task_manager.fail_task(task_id, "任务队列已满，请稍后重试")

    async def process_batch(
            self,
            batch_id: str,
            scripts: List[str],
            config: Optional[ShotConfig] = None,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> Dict:
        """
        批量处理任务
        """
        task_ids = []

        for script in scripts:
            task_id = self.task_manager.create_task(script, config)
            task_ids.append(task_id)

        for task_id in task_ids:
            await self.submit_task(task_id, priority)

        info(f"批量任务已提交: {batch_id}, 任务数: {len(task_ids)}")

        return {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "total": len(task_ids),
            "status": "submitted"
        }

    async def wait_for_task(self, task_id: str, timeout: float = 300) -> Dict:
        """
        等待任务完成
        """
        start_time = datetime.now(timezone.utc)
        poll_interval = 0.5

        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
            task = self.task_manager.get_task(task_id)

            if not task:
                return {"success": False, "error": "任务不存在"}

            status = task.get("status")

            if status == TaskStatus.SUCCESS:
                return {
                    "success": True,
                    "result": task.get("result"),
                    "status": status
                }

            if status == TaskStatus.FAILED:
                return {
                    "success": False,
                    "error": task.get("error"),
                    "status": status
                }

            await asyncio.sleep(poll_interval)

        return {"success": False, "error": "等待超时", "status": TaskStatus.TIMEOUT}

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        """
        # 检查是否正在执行
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if not task.done():
                task.cancel()
                info(f"已取消正在执行的任务: {task_id}")
                return True

        # 检查是否在队列中
        for i, queued in enumerate(self._queue):
            if queued.task_id == task_id:
                del self._queue[i]
                self._queue_waiting -= 1
                info(f"已从队列中移除任务: {task_id}")
                return True

        return False

    #     ============================ 恢复任务 ================================
    def recover_pending_tasks(self, max_age_hours: int = 2):
        """
        恢复未完成的任务到队列（只恢复两小时内的任务）

        Args:
            max_age_hours: 最大任务年龄（小时）
        """
        pending_tasks = self.task_manager.get_pending_tasks(max_age_hours=max_age_hours)

        if not pending_tasks:
            info("没有需要恢复的未完成任务（两小时内）")
            return

        info(f"发现 {len(pending_tasks)} 个未完成的任务（两小时内），开始恢复...")

        # 显示即将恢复的任务信息
        for task in pending_tasks:
            created_at = task.get("created_at")
            info(f"  待恢复任务: {task.get('task_id')}, 状态: {task.get('status')}, 创建时间: {created_at}")

        # 将任务重新加入队列
        for task in pending_tasks:
            task_id = task.get("task_id")

            # 创建 QueuedTask 并加入队列
            queued_task = QueuedTask(
                task_id=task_id,
                priority=TaskPriority.NORMAL,
                callback=None
            )
            queued_task.enqueued_at = datetime.now(timezone.utc)

            # 直接加入队列
            self._queue.append(queued_task)
            self._queue_waiting += 1
            self._stats["total_submitted"] += 1

            info(f"任务已恢复并加入队列: {task_id}")

        info(f"任务恢复完成，队列长度: {len(self._queue)}")
    #     ============================ 恢复任务 ================================

    def get_queue_status(self) -> Dict:
        """获取队列状态"""
        return {
            "queue_length": len(self._queue),
            "queue_waiting": self._queue_waiting,
            "active_tasks": self._active_count,
            "max_concurrent": self.max_concurrent,
            "queue_max_size": self._queue_max_size,
            "queue_usage_percent": (len(self._queue) / self._queue_max_size * 100) if self._queue_max_size > 0 else 0
        }

    def get_stats(self) -> Dict:
        """获取处理器统计信息"""
        return {
            **self._stats,
            "queue_status": self.get_queue_status(),
            "active_tasks_detail": {
                task_id: {"status": TaskStatus.PROCESSING}
                for task_id in self._active_tasks.keys()
            }
        }

    async def shutdown(self, wait_for_completion: bool = True, timeout: float = 30):
        """关闭任务处理器"""
        self._is_running = False

        if wait_for_completion:
            start_time = datetime.now(timezone.utc)
            while self._queue or self._active_count > 0:
                if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout:
                    warning(f"关闭超时，强制终止，剩余任务: {len(self._queue)}, 活跃: {self._active_count}")
                    break
                await asyncio.sleep(0.5)

        # 停止后台事件循环
        if self._background_loop:
            self._background_loop.call_soon_threadsafe(self._background_loop.stop)

        if self._background_thread and self._background_thread.is_alive():
            self._background_thread.join(timeout=5)

        info(f"任务处理器已关闭，总处理: {self._stats['total_completed'] + self._stats['total_failed']}")

    def set_max_concurrent(self, max_concurrent: int):
        """动态调整最大并发数"""
        old = self.max_concurrent
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        info(f"最大并发数已调整: {old} -> {max_concurrent}")