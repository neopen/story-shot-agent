"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: task_processor.py
@Description: 异步任务处理器（支持并发控制和任务队列）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 16:40
"""
import asyncio
import threading
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable

from penshot.logger import info, warning, error, debug
from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.task.task_models import TaskPriority, TaskStatus, TaskResponse, TaskStage, QueuedTask
from penshot.utils.log_utils import print_log_exception
from penshot.utils.obj_utils import dict_to_obj


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

        # 并发控制
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_count = 0

        # 任务队列
        self._queue: deque = deque()
        self._queue_max_size = queue_size
        self._queue_waiting = 0

        # 队列唤醒事件：有新任务时唤醒工作器，避免空队列空转轮询
        self._queue_event = asyncio.Event()
        # 队列跨线程访问锁：cancel/recover 可能从非事件循环线程调用
        self._queue_lock = threading.Lock()

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
        started = threading.Event()

        def run_loop():
            debug(f"[AsyncTaskProcessor] 后台线程启动，创建事件循环")
            # 创建新的事件循环
            self._background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._background_loop)

            info(f"[AsyncTaskProcessor] 事件循环创建成功，创建工作器任务")

            # 创建工作器任务
            self._worker_task = self._background_loop.create_task(self._worker_loop())
            started.set()

            try:
                self._background_loop.run_forever()
            except Exception as e:
                error(f"后台事件循环异常: {e}")
            finally:
                self._background_loop.close()
                info(f"[AsyncTaskProcessor] 后台事件循环已关闭")

        self._background_thread = threading.Thread(target=run_loop, daemon=True)
        self._background_thread.start()

        # 等待循环启动（用事件等待替代 time.sleep 轮询）
        if started.wait(timeout=5):
            info(f"[AsyncTaskProcessor] 后台事件循环启动成功")
        else:
            error(f"[AsyncTaskProcessor] 后台事件循环启动超时")

    def _notify_queue_not_empty(self) -> None:
        """唤醒等待队列的工作器（支持从任意线程调用）"""
        loop = self._background_loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._queue_event.set)
        else:
            self._queue_event.set()

    def _stop_background_loop(self) -> None:
        """停止后台事件循环：先取消工作器并等待其退出，再停止循环"""
        loop = self._background_loop
        if loop is None:
            return

        async def _stop():
            worker = self._worker_task
            if worker and not worker.done():
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
            loop.stop()

        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(_stop()))
        except RuntimeError:
            # 事件循环已关闭，无需再停止
            debug("[AsyncTaskProcessor] 后台事件循环已关闭，跳过停止操作")

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
                    # 队列为空：先清空唤醒标记再复核一次，避免漏掉刚入队的任务
                    self._queue_event.clear()
                    if not self._queue:
                        await self._queue_event.wait()

            except asyncio.CancelledError:
                break
            except Exception as e:
                error(f"工作器循环异常: {str(e)}")
                await asyncio.sleep(0.5)

    def _insert_queued_task(self, queued_task: QueuedTask) -> bool:
        """按优先级插入队列（线程安全），队列已满时返回 False"""
        with self._queue_lock:
            if len(self._queue) >= self._queue_max_size:
                return False

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

        return True

    async def _enqueue_task(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            metadata: Optional[Dict] = None
    ) -> bool:
        """将任务加入队列"""
        queued_task = QueuedTask(task_id, priority, callback, metadata)
        queued_task.enqueued_at = datetime.now(timezone.utc)

        if not self._insert_queued_task(queued_task):
            warning(f"任务队列已满，拒绝任务: {task_id}")
            return False

        # 唤醒等待队列的工作器
        self._notify_queue_not_empty()

        debug(f"任务入队: {task_id}, 优先级: {priority.name}, 队列长度: {len(self._queue)}")
        return True

    async def _dequeue_task(self) -> Optional[QueuedTask]:
        """从队列中取出任务"""
        with self._queue_lock:
            if not self._queue:
                return None
            task = self._queue.popleft()
            self._queue_waiting -= 1

        task.started_at = datetime.now(timezone.utc)

        # 计算等待时间
        wait_ms = (task.started_at - task.enqueued_at).total_seconds() * 1000
        self._update_avg_wait_time(wait_ms)

        debug(f"任务出队: {task.task_id}, 等待时间: {wait_ms:.0f}ms")
        return task

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

                # 更新任务状态为 PROCESSING
                self.task_manager.update_task_status(task_id, TaskStatus.PROCESSING)
                self.task_manager.update_task_progress_detail(task_id, TaskStage.INIT, 0)

                # 执行实际的任务处理
                result = await self._process_script_task_internal(task_id)

                # 依据执行结果区分完成/失败，避免失败任务停留在 PROCESSING
                if getattr(result, "success", False):
                    self._stats["total_completed"] += 1
                else:
                    self._stats["total_failed"] += 1
                    current = self.task_manager.get_task(task_id) or {}
                    current_status = getattr(current.get("status"), "value", current.get("status"))
                    # 内部已把任务标记为终态（如 complete_task 判定失败）时不再重复失败，
                    # 否则会重复计数并重复触发回调
                    if current_status == TaskStatus.PROCESSING.value:
                        self.task_manager.fail_task(
                            task_id, getattr(result, "error", None) or "任务执行失败"
                        )

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
            self.task_manager.update_task_status(task_id, TaskStatus.CANCELLED)

        except Exception as e:
            self._stats["total_failed"] += 1
            error(f"任务执行失败: {task_id}, 错误: {str(e)}")
            print_log_exception()
            self.task_manager.fail_task(task_id, str(e))
            self.task_manager.update_task_status(task_id, TaskStatus.FAILED)

        finally:
            self._active_count -= 1
            self._active_tasks.pop(task_id, None)
            debug(f"任务结束: {task_id}, 剩余活跃: {self._active_count}")


    async def _process_script_task_internal(self, task_id: str) -> TaskResponse:
        """内部任务处理逻辑"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return TaskResponse(
                task_id=task_id,
                success=False,
                status=TaskStatus.FAILED,
                error=f"任务不存在: {task_id}"
            )

        config = dict_to_obj(task["config"], ShotConfig) if task.get("config") else ShotConfig()

        try:
            # 更新状态为处理中
            self.task_manager.update_task_progress_detail(task_id, TaskStage.INIT, 0)

            # 获取工作流实例
            workflow = self.task_manager.get_workflow(self.task_manager, task["script_id"], task_id, config)
            self.task_manager.update_task_progress_detail(task_id, TaskStage.PROCESSING, 10)

            # 执行处理 - 工作流内部会更新详细进度
            self.task_manager.update_task_progress_detail(task_id, TaskStage.PARSING_START, 0)
            result_dict = await workflow.run_process(
                task["script"], config, asset_manifest=task.get("asset_manifest")
            )

            # 更新最终进度
            self.task_manager.update_task_progress_detail(task_id, TaskStage.COMPLETE, 100)

            # 获取时间信息
            created_at = task.get("created_at")
            completed_at = datetime.now(timezone.utc)

            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except (ValueError, TypeError):
                    created_at = None

            processing_time_ms = None
            if created_at and completed_at:
                processing_time_ms = int((completed_at - created_at).total_seconds() * 1000)

            result = TaskResponse(
                task_id=task_id,
                success=result_dict.get("success", False),
                status=TaskStatus.SUCCESS if result_dict.get("success") else TaskStatus.FAILED,
                data=result_dict.get("data"),
                error=result_dict.get("error"),
                processing_time_ms=processing_time_ms,
                created_at=created_at,
                completed_at=completed_at
            )

            # 回调统一由 TaskLifecycleService 在任务进入终态时触发，
            # 此处不再重复发送 HTTP 回调，避免同一任务收到两次通知
            self.task_manager.complete_task(task_id, result_dict)

            return result

        except Exception as e:
            error(f"任务处理失败: {task_id}, 错误: {str(e)}")
            print_log_exception()
            self.task_manager.update_task_progress_detail(task_id, TaskStage.ERROR_HANDLING, 0, {"error": str(e)})

            return TaskResponse(
                task_id=task_id,
                success=False,
                status=TaskStatus.FAILED,
                error=str(e)
            )


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
            style: Optional[VideoStyle] = None,
            config: Optional[ShotConfig] = None,
            priority: TaskPriority = TaskPriority.NORMAL
    ) -> Dict:
        """
        批量处理任务
        """
        task_ids = []

        for script in scripts:
            script_id, task_id = self.task_manager.create_task(script=script, style=style, config=config)
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
        with self._queue_lock:
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

        # 将任务重新加入队列（复用统一入队逻辑，保持优先级、容量与统计一致）
        restored = 0
        for task in pending_tasks:
            task_id = task.get("task_id")
            if not task_id:
                warning("跳过缺少 task_id 的待恢复任务")
                continue

            queued_task = QueuedTask(
                task_id=task_id,
                priority=TaskPriority.NORMAL,
                callback=None
            )
            queued_task.enqueued_at = datetime.now(timezone.utc)

            if not self._insert_queued_task(queued_task):
                warning(f"队列已满，跳过恢复任务: {task_id}")
                continue

            restored += 1
            info(f"任务已恢复并加入队列: {task_id}")

        if restored:
            self._notify_queue_not_empty()

        info(f"任务恢复完成: 恢复 {restored}/{len(pending_tasks)} 个，队列长度: {len(self._queue)}")
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
                task_id: {"status": TaskStatus.PROCESSING.value}
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

        # 停止后台事件循环（先取消工作器，避免关闭时残留 pending 任务）
        self._stop_background_loop()

        if self._background_thread and self._background_thread.is_alive():
            # 同步 join 会阻塞调用方事件循环，放到线程池中等待
            await asyncio.to_thread(self._background_thread.join, 5)

        info(f"任务处理器已关闭，总处理: {self._stats['total_completed'] + self._stats['total_failed']}")

    def set_max_concurrent(self, max_concurrent: int):
        """动态调整最大并发数"""
        old = self.max_concurrent
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        info(f"最大并发数已调整: {old} -> {max_concurrent}")