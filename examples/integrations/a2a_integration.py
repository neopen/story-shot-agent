"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: a2a_integration.py
@Description: A2A（代理到代理）集成示例：把 Penshot 封装为可编排的分镜生成 Agent
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 10:00
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Dict, List, Optional

from penshot import ShotLanguage
from penshot.api import PenshotFunction, PenshotResult

# A2A 层的任务 ID 由调用方指定，仅用于跨代理编排；调用 Penshot 时通过 script_id 关联，
# 真正用于轮询/等待的 task_id 由 breakdown_script_async 返回并存入 backend_task_id。


def llm_env_configured() -> bool:
    """检查是否已配置 LLM（环境变量）。"""
    import os
    return any(key.startswith("PENSHOT_LLM") for key in os.environ)


class A2ATaskPriority(IntEnum):
    """A2A 任务优先级（A2A 层语义，与 Penshot 的 TaskPriority 相互独立）。"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class A2ATaskStatus(str, Enum):
    """A2A 任务状态。终态成功用 success（与 Penshot 语义对齐），不引入 "completed" 字面量。"""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in (A2ATaskStatus.SUCCESS, A2ATaskStatus.FAILED, A2ATaskStatus.CANCELLED)


@dataclass
class A2ATask:
    """A2A 任务数据类。"""

    a2a_id: str
    script_content: str
    priority: A2ATaskPriority = A2ATaskPriority.NORMAL
    language: str = "zh"
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: A2ATaskStatus = A2ATaskStatus.PENDING
    result: Optional[PenshotResult] = None
    error: Optional[str] = None
    backend_task_id: Optional[str] = None
    created_at: Optional[str] = None


def print_instructions_summary(result: PenshotResult) -> None:
    """按 data.instructions 契约打印结果摘要。"""
    data = result.data or {}
    instructions = data.get("instructions", {})
    project_info = instructions.get("project_info", {})
    fragments = instructions.get("fragments", [])
    print(f"  片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"  总时长: {project_info.get('total_duration', 0.0):.1f} 秒")


class StoryboardA2AAgent:
    """分镜生成的 A2A 代理：内部持有一个 PenshotFunction 实例。"""

    def __init__(self, agent_id: str, max_concurrent: int = 3):
        self.agent_id = agent_id
        self.max_concurrent = max_concurrent
        self.penshot = PenshotFunction(max_concurrent=max_concurrent)
        self.tasks: Dict[str, A2ATask] = {}
        self._processing: Dict[str, asyncio.Task] = {}

    async def _execute(self, task: A2ATask) -> None:
        """提交并等待真实后端任务完成，然后更新 A2A 任务状态。"""
        try:
            language = ShotLanguage.ZH if task.language == "zh" else ShotLanguage.EN
            backend_id = self.penshot.breakdown_script_async(
                script_text=task.script_content,
                script_id=task.a2a_id,  # A2A ID 作为关联 ID
                language=language,
            )
            task.backend_task_id = backend_id
            result = await self.penshot.wait_for_result_async(backend_id, timeout=900.0)
            if result.success:
                task.status = A2ATaskStatus.SUCCESS
                task.result = result
            else:
                task.status = A2ATaskStatus.FAILED
                task.error = result.error
        except Exception as exc:  # noqa: BLE001 - A2A 层统一收口到任务错误
            task.status = A2ATaskStatus.FAILED
            task.error = str(exc)
        finally:
            self._processing.pop(task.a2a_id, None)

    async def process_task(self, task: A2ATask) -> A2ATask:
        """阻塞式处理：等待任务完成后返回。"""
        task.status = A2ATaskStatus.PROCESSING
        self.tasks[task.a2a_id] = task
        await self._execute(task)
        return task

    async def process_task_async(self, task: A2ATask) -> A2ATask:
        """非阻塞式处理：后台执行，立即返回（调用方可轮询 get_status）。"""
        task.status = A2ATaskStatus.PROCESSING
        self.tasks[task.a2a_id] = task
        runner = asyncio.create_task(self._execute(task))
        self._processing[task.a2a_id] = runner
        return task

    def get_status(self, a2a_id: str) -> Optional[Dict[str, Any]]:
        """查询任务状态（A2A 层聚合结果）。"""
        task = self.tasks.get(a2a_id)
        if not task:
            return None
        return {
            "a2a_id": task.a2a_id,
            "status": task.status.value,
            "backend_task_id": task.backend_task_id,
            "error": task.error,
            "has_result": task.result is not None,
        }

    def cancel_task(self, a2a_id: str) -> bool:
        """取消任务：先取消后端任务，再取消本地后台协程。"""
        task = self.tasks.get(a2a_id)
        if not task or task.status in (A2ATaskStatus.SUCCESS, A2ATaskStatus.FAILED):
            return False
        if task.backend_task_id:
            self.penshot.cancel_task(task.backend_task_id)
        runner = self._processing.pop(a2a_id, None)
        if runner and not runner.done():
            runner.cancel()
        task.status = A2ATaskStatus.CANCELLED
        return True

    def get_stats(self) -> Dict[str, int]:
        """获取代理统计信息。"""
        stats = {s.value: 0 for s in A2ATaskStatus}
        for task in self.tasks.values():
            stats[task.status.value] += 1
        return stats

    def shutdown(self) -> None:
        """关闭底层的 PenshotFunction（停止后台事件循环）。"""
        self.penshot.shutdown()


class A2AOrchestrator:
    """A2A 系统编排器：注册代理并按策略分发任务。"""

    def __init__(self):
        self.agents: Dict[str, StoryboardA2AAgent] = {}
        self._round_robin_index = 0

    def register_agent(self, agent: StoryboardA2AAgent) -> None:
        self.agents[agent.agent_id] = agent

    def _select_agent(self, strategy: str) -> Optional[StoryboardA2AAgent]:
        if not self.agents:
            return None
        if strategy == "least_loaded":
            return min(
                self.agents.values(),
                key=lambda a: len([t for t in a.tasks.values() if not t.status.is_terminal()]),
            )
        # round_robin
        agent_ids = list(self.agents.keys())
        idx = self._round_robin_index % len(agent_ids)
        self._round_robin_index += 1
        return self.agents[agent_ids[idx]]

    async def dispatch(self, task: A2ATask, agent_id: Optional[str] = None, strategy: str = "round_robin") -> A2ATask:
        """分发并阻塞等待完成。"""
        agent = self.agents.get(agent_id) if agent_id else self._select_agent(strategy)
        if not agent:
            raise ValueError("没有可用的代理")
        return await agent.process_task(task)

    async def dispatch_async(self, task: A2ATask, agent_id: Optional[str] = None, strategy: str = "round_robin") -> A2ATask:
        """非阻塞分发。"""
        agent = self.agents.get(agent_id) if agent_id else self._select_agent(strategy)
        if not agent:
            raise ValueError("没有可用的代理")
        return await agent.process_task_async(task)

    def agent_stats(self) -> Dict[str, Dict[str, int]]:
        return {aid: agent.get_stats() for aid, agent in self.agents.items()}


def _make_tasks(count: int) -> List[A2ATask]:
    scripts = [
        "海边日落，一个男人牵着狗沿着沙滩慢慢散步。",
        "午后办公室，程序员小李修改代码时接到电话，神情惊讶。",
        "两个孩子放学后在操场追逐，笑声不断。",
        "老人在公园石桌旁下棋，夕阳把影子拉得很长。",
        "雨夜街角，撑伞的老人停下脚步望向亮灯的便利店。",
    ]
    return [
        A2ATask(
            a2a_id=f"a2a_task_{i:03d}",
            script_content=scripts[i % len(scripts)],
            priority=A2ATaskPriority.HIGH if i % 2 else A2ATaskPriority.NORMAL,
            metadata={"project": "短片制作", "user": "demo"},
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        for i in range(count)
    ]


async def demo_orchestrated():
    """编排器演示：多代理 least_loaded 分发并打印结果。"""
    print("=== A2A 编排演示（least_loaded） ===")
    orchestrator = A2AOrchestrator()
    agent_a = StoryboardA2AAgent(agent_id="storyboard_a")
    agent_b = StoryboardA2AAgent(agent_id="storyboard_b")
    orchestrator.register_agent(agent_a)
    orchestrator.register_agent(agent_b)

    try:
        tasks = _make_tasks(4)
        results = [await orchestrator.dispatch(t, strategy="least_loaded") for t in tasks]
        for result in results:
            print(f"任务 {result.a2a_id}: 状态={result.status.value}")
            if result.result and result.result.success:
                print_instructions_summary(result.result)
            elif result.error:
                print(f"  错误: {result.error}")
        print("代理统计:", orchestrator.agent_stats())
    finally:
        agent_a.shutdown()
        agent_b.shutdown()


async def demo_async_dispatch():
    """非阻塞分发 + 轮询演示。"""
    print("\n=== A2A 非阻塞分发 + 轮询演示 ===")
    orchestrator = A2AOrchestrator()
    agent = StoryboardA2AAgent(agent_id="async_agent")
    orchestrator.register_agent(agent)
    try:
        task = _make_tasks(1)[0]
        submitted = await orchestrator.dispatch_async(task, agent_id="async_agent")
        print(f"已非阻塞提交: {submitted.a2a_id}，初始状态={submitted.status.value}")

        while not submitted.status.is_terminal():
            status = agent.get_status(submitted.a2a_id)
            if status:
                print(f"  状态: {status['status']}")
            await asyncio.sleep(1.0)
        print(f"最终状态: {submitted.status.value}")

        # 演示取消一个未完成/不存在任务
        print("取消不存在任务:", agent.cancel_task("a2a_task_missing"))
    finally:
        agent.shutdown()


async def main():
    if not llm_env_configured():
        print("未配置 LLM key：A2A 封装演示需要真实后端任务才能跑通。")
        print("设置 PENSHOT_LLM__DEFAULT__API_KEY 后重跑。")
        return
    await demo_orchestrated()
    await demo_async_dispatch()


if __name__ == "__main__":
    asyncio.run(main())
