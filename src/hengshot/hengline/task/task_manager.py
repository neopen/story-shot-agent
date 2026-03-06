"""
@FileName: task_manager.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 16:42
"""
import uuid
from datetime import datetime
from typing import Optional, Dict

from hengshot.hengline.agent import MultiAgentPipeline
from hengshot.hengline.hengline_config import HengLineConfig
from hengshot.logger import info


class TaskManager:
    """任务状态管理器"""

    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self.workflow_cache: Dict[str, MultiAgentPipeline] = {}

    def create_task(self, script: str, config: Optional[HengLineConfig] = None, task_id: str = None) -> str:
        """创建新任务"""
        task_id = task_id or str(uuid.uuid4())

        self.tasks[task_id] = {
            "task_id": task_id,
            "script": script,
            "config": config or {},
            "status": "pending",
            "stage": "initialized",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
            "callbacks": []
        }

        info(f"创建任务: {task_id}")
        return task_id

    def update_task_progress(self, task_id: str, stage: str, progress: float = None):
        """更新任务进度"""
        if task_id in self.tasks:
            self.tasks[task_id]["stage"] = stage
            if progress is not None:
                self.tasks[task_id]["progress"] = progress
            self.tasks[task_id]["updated_at"] = datetime.now().isoformat()

    def complete_task(self, task_id: str, result: Dict):
        """完成任务"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "completed" if result.get("success", False) else "failed"
            self.tasks[task_id]["result"] = result
            self.tasks[task_id]["error"] = result.get("error")
            self.tasks[task_id]["updated_at"] = datetime.now().isoformat()
            self.tasks[task_id]["completed_at"] = datetime.now().isoformat()

    def fail_task(self, task_id: str, error_message: str):
        """标记任务失败"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["error"] = error_message
            self.tasks[task_id]["updated_at"] = datetime.now().isoformat()

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        return self.tasks.get(task_id)

    def get_workflow(self, task_id, config: Optional[HengLineConfig] = None) -> MultiAgentPipeline:
        """获取或创建工作流实例"""
        # config_key = str(config) if config else "default"
        config_key = task_id if task_id else "default"

        if config_key not in self.workflow_cache:
            self.workflow_cache[config_key] = MultiAgentPipeline(task_id, config)

        return self.workflow_cache[config_key]
