"""
@FileName: a2a_integration.py
@Description: 集成到A2A系统（代理到代理）
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/2/10 19:45
"""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List

from penshot.api import PenshotFunction, PenshotResult
from penshot import ShotConfig, ShotLanguage


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class A2ATask:
    """A2A任务数据类"""
    task_id: str
    script_content: str
    priority: TaskPriority = TaskPriority.NORMAL
    language: str = "zh"
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[PenshotResult] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


class StoryboardA2AAgent:
    """分镜生成的A2A代理"""

    def __init__(
            self,
            agent_id: str,
            config: Optional[ShotConfig] = None,
            max_concurrent: int = 5
    ):
        """
        初始化A2A代理

        Args:
            agent_id: 代理唯一标识
            config: 配置参数
            max_concurrent: 最大并发任务数
        """
        self.agent_id = agent_id
        self.config = config or ShotConfig()
        self.max_concurrent = max_concurrent

        # 创建 Penshot 智能体
        self.penshot = PenshotFunction(config=self.config, max_concurrent=max_concurrent)

        # 任务管理
        self.tasks: Dict[str, A2ATask] = {}
        self._processing_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process_task(self, task: A2ATask) -> A2ATask:
        """
        处理A2A任务

        Args:
            task: A2A任务

        Returns:
            更新后的任务对象
        """
        task.status = TaskStatus.PROCESSING
        self.tasks[task.task_id] = task

        try:
            # 使用信号量控制并发
            async with self._semaphore:
                language = ShotLanguage.ZH if task.language == "zh" else ShotLanguage.EN

                # 提交任务
                task_id = self.penshot.breakdown_script_async(
                    script_text=task.script_content,
                    task_id=task.task_id,
                    language=language
                )

                # 等待结果
                result = await self.penshot.wait_for_result_async(task_id)

                if result.success:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                else:
                    task.status = TaskStatus.FAILED
                    task.error = result.error

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

        return task

    async def process_task_async(self, task: A2ATask) -> A2ATask:
        """
        异步处理任务（非阻塞）

        Args:
            task: A2A任务

        Returns:
            立即返回任务对象（后台处理）
        """
        task.status = TaskStatus.PROCESSING
        self.tasks[task.task_id] = task

        # 创建后台任务
        async def _process():
            try:
                language = ShotLanguage.ZH if task.language == "zh" else ShotLanguage.EN

                task_id = self.penshot.breakdown_script_async(
                    script_text=task.script_content,
                    task_id=task.task_id,
                    language=language,
                    callback=lambda r: self._on_task_complete(task.task_id, r)
                )

                self._processing_tasks[task.task_id] = asyncio.current_task()

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self.tasks[task.task_id] = task

        asyncio.create_task(_process())
        return task

    def _on_task_complete(self, task_id: str, result: PenshotResult):
        """任务完成回调"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if result.success:
                task.status = TaskStatus.COMPLETED
                task.result = result
            else:
                task.status = TaskStatus.FAILED
                task.error = result.error
            self.tasks[task_id] = task

        if task_id in self._processing_tasks:
            del self._processing_tasks[task_id]

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "priority": task.priority.value,
            "error": task.error,
            "has_result": task.result is not None
        }

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self._processing_tasks:
            self._processing_tasks[task_id].cancel()
            del self._processing_tasks[task_id]

        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.CANCELLED
            return True

        return False

    def get_stats(self) -> Dict[str, int]:
        """获取代理统计信息"""
        stats = {
            "total": len(self.tasks),
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }

        for task in self.tasks.values():
            stats[task.status.value] += 1

        return stats


class A2AOrchestrator:
    """A2A系统编排器"""

    def __init__(self):
        self.agents: Dict[str, StoryboardA2AAgent] = {}
        self._task_queues: Dict[str, List[A2ATask]] = {}

    def register_agent(self, agent: StoryboardA2AAgent):
        """注册代理"""
        self.agents[agent.agent_id] = agent
        self._task_queues[agent.agent_id] = []

    def unregister_agent(self, agent_id: str):
        """注销代理"""
        if agent_id in self.agents:
            del self.agents[agent_id]
        if agent_id in self._task_queues:
            del self._task_queues[agent_id]

    async def dispatch_task(
            self,
            task: A2ATask,
            agent_id: Optional[str] = None,
            strategy: str = "round_robin"
    ) -> A2ATask:
        """
        分发任务到指定代理或选择合适的代理

        Args:
            task: A2A任务
            agent_id: 指定代理ID
            strategy: 负载均衡策略 (round_robin, least_loaded, priority)

        Returns:
            处理后的任务
        """
        # 选择代理
        if agent_id and agent_id in self.agents:
            agent = self.agents[agent_id]
        else:
            agent = self._select_agent(strategy)

        if not agent:
            raise ValueError("没有可用的代理")

        # 处理任务
        return await agent.process_task(task)

    async def dispatch_task_async(
            self,
            task: A2ATask,
            agent_id: Optional[str] = None,
            strategy: str = "round_robin"
    ) -> A2ATask:
        """
        异步分发任务（非阻塞）

        Returns:
            任务对象（后台处理）
        """
        if agent_id and agent_id in self.agents:
            agent = self.agents[agent_id]
        else:
            agent = self._select_agent(strategy)

        if not agent:
            raise ValueError("没有可用的代理")

        return await agent.process_task_async(task)

    def _select_agent(self, strategy: str) -> Optional[StoryboardA2AAgent]:
        """选择代理"""
        if not self.agents:
            return None

        if strategy == "round_robin":
            # 简单的轮询
            agent_ids = list(self.agents.keys())
            if not hasattr(self, '_round_robin_index'):
                self._round_robin_index = 0
            idx = self._round_robin_index % len(agent_ids)
            self._round_robin_index += 1
            return self.agents[agent_ids[idx]]

        elif strategy == "least_loaded":
            # 选择任务数最少的代理
            return min(
                self.agents.values(),
                key=lambda a: len([t for t in a.tasks.values() if t.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]])
            )

        else:
            # 默认返回第一个
            return list(self.agents.values())[0]

    def get_agent_stats(self) -> Dict[str, Dict]:
        """获取所有代理统计"""
        return {
            agent_id: agent.get_stats()
            for agent_id, agent in self.agents.items()
        }


# ============================================================================
# 使用示例
# ============================================================================

async def a2a_demo():
    """A2A系统演示"""
    print("=== A2A系统演示 ===")

    # 创建编排器
    orchestrator = A2AOrchestrator()

    # 注册多个分镜生成代理
    storyboard_agent1 = StoryboardA2AAgent(
        agent_id="storyboard_agent_001",
        max_concurrent=3
    )
    storyboard_agent2 = StoryboardA2AAgent(
        agent_id="storyboard_agent_002",
        max_concurrent=3
    )

    orchestrator.register_agent(storyboard_agent1)
    orchestrator.register_agent(storyboard_agent2)

    # 创建任务
    tasks = [
        A2ATask(
            task_id=f"a2a_task_{i:03d}",
            script_content=f"剧本内容 {i}",
            priority=TaskPriority.NORMAL if i % 2 == 0 else TaskPriority.HIGH,
            metadata={"user_id": "user123", "project": "短片制作"}
        )
        for i in range(5)
    ]

    # 分发并处理任务
    results = []
    for task in tasks:
        result = await orchestrator.dispatch_task(
            task,
            strategy="least_loaded"
        )
        results.append(result)

    # 显示结果
    for result in results:
        print(f"任务 {result.task_id}: 状态={result.status.value}")
        if result.result and result.result.success:
            data = result.result.data or {}
            stats = data.get("stats", {})
            print(f"  镜头数: {stats.get('shot_count', 0)}")
        elif result.error:
            print(f"  错误: {result.error}")

    # 显示统计
    stats = orchestrator.get_agent_stats()
    for agent_id, agent_stats in stats.items():
        print(f"\n代理 {agent_id}: {agent_stats}")

    return results


async def async_dispatch_demo():
    """异步分发演示"""
    print("\n=== 异步分发演示 ===")

    orchestrator = A2AOrchestrator()

    agent = StoryboardA2AAgent(agent_id="async_agent_001")
    orchestrator.register_agent(agent)

    # 创建任务
    task = A2ATask(
        task_id="async_task_001",
        script_content="异步测试剧本...",
        priority=TaskPriority.HIGH
    )

    # 异步分发（非阻塞）
    result_task = await orchestrator.dispatch_task_async(task)

    print(f"任务已提交: {result_task.task_id}")
    print(f"初始状态: {result_task.status.value}")

    # 等待任务完成
    while result_task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
        status = agent.get_task_status(result_task.task_id)
        print(f"  状态: {status['status']}")
        await asyncio.sleep(0.5)

    print(f"最终状态: {result_task.status.value}")

    return result_task


async def main():
    """主函数"""

    # 同步分发演示
    await a2a_demo()

    # 异步分发演示
    await async_dispatch_demo()


if __name__ == "__main__":
    asyncio.run(main())
