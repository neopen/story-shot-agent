"""
@FileName: task_processor.py
@Description: 
@Author: Haeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 16:40
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Dict

from penshot.neopen.shot_config import ShotConfig
from penshot.logger import error, info
from penshot.neopen.task.task_handler import CallbackHandler
from penshot.neopen.task.task_manager import TaskManager
from penshot.utils.log_utils import print_log_exception
from penshot.neopen.task.task_models import CallbackPayload


class AsyncTaskProcessor:
    """异步任务处理器"""

    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.callback_handler = CallbackHandler()

    async def process_script_task(self, task_id: str):
        """处理单个剧本任务"""
        task = self.task_manager.get_task(task_id)
        if not task:
            error(f"任务不存在: {task_id}")
            return

        try:
            # 更新状态为处理中
            self.task_manager.update_task_progress(task_id, "processing", 10)

            # 获取工作流实例
            workflow = self.task_manager.get_workflow(task_id, task["config"])

            # 执行处理
            self.task_manager.update_task_progress(task_id, "parsing_script", 20)
            # workflow.run_process should return a dict-like result with keys: success, data, error
            result = await workflow.run_process(task["script"], task["config"])  # type: ignore

            # 更新进度
            self.task_manager.update_task_progress(task_id, "finalizing", 90)

            # 完成任务
            self.task_manager.complete_task(task_id, result)

            info(f"任务完成: {task_id}")

            # 处理回调
            if task.get("callback_url"):
                await self._handle_callback(task_id, result)

        except Exception as e:
            error(f"任务处理失败: {task_id}, 错误: {str(e)}")
            print_log_exception()
            self.task_manager.fail_task(task_id, str(e))

    async def _handle_callback(self, task_id: str, result: Dict):
        """处理回调通知"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        # standardize callback payload using CallbackPayload model
        try:
            payload = CallbackPayload(
                task_id=task_id,
                status="success" if result.get("success") else "failed",
                data=result.get("data"),
                error_message=result.get("error"),
                completed_at=datetime.now(timezone.utc)
            )
            # use pydantic model_dump to get a dict representation (compatible with pydantic v2)
            await self.callback_handler.notify_callback(task["callback_url"], payload.model_dump())
        except Exception as e:
            error(f"回调构建/发送失败 for task {task_id}: {e}")
            # don't change task state here; just log the callback failure
            return

    async def process_batch(self, batch_id: str, scripts: List[str], config: ShotConfig = None):
        """批量处理任务"""
        tasks = []
        for script in scripts:
            task_id = self.task_manager.create_task(script, config)
            tasks.append(task_id)

        # 并行处理所有任务
        batch_tasks = [self.process_script_task(task_id) for task_id in tasks]
        await asyncio.gather(*batch_tasks, return_exceptions=True)

        return {
            "batch_id": batch_id,
            "task_ids": tasks,
            "total": len(tasks),
            "completed": len([t for t in tasks if self.task_manager.get_task(t)["status"] == "completed"])
        }
