"""
@FileName: a2a_integration.py
@Description: 集成到A2A系统（代理到代理）
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:45
"""
from dataclasses import dataclass
from typing import Dict, Any

from penshot.neopen import generate_storyboard


@dataclass
class A2ATask:
    """A2A任务数据类"""
    task_id: str
    script_content: str
    priority: int = 1
    metadata: Dict[str, Any] = None


class StoryboardA2AAgent:
    """分镜生成的A2A代理"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.task_queue = []

    async def process_task(self, task: A2ATask) -> Dict[str, Any]:
        """
        处理A2A任务
        """
        try:
            # 调用分镜生成智能体
            result = await generate_storyboard(
                script_text=task.script_content,
                task_id=task.task_id
            )

            return {
                "agent_id": self.agent_id,
                "task_id": task.task_id,
                "status": "completed",
                "result": result,
                "metadata": task.metadata or {}
            }
        except Exception as e:
            return {
                "agent_id": self.agent_id,
                "task_id": task.task_id,
                "status": "failed",
                "error": str(e)
            }


class A2AOrchestrator:
    """A2A系统编排器"""

    def __init__(self):
        self.agents = {}

    def register_agent(self, agent: StoryboardA2AAgent):
        self.agents[agent.agent_id] = agent

    async def dispatch_task(self, task: A2ATask, agent_id: str = None):
        """
        分发任务到指定代理或选择合适的代理
        """
        if agent_id and agent_id in self.agents:
            agent = self.agents[agent_id]
        else:
            # 简单的负载均衡：选择第一个可用代理
            agent = list(self.agents.values())[0]

        return await agent.process_task(task)


# 使用示例
async def a2a_demo():
    # 创建编排器
    orchestrator = A2AOrchestrator()

    # 注册分镜生成代理
    storyboard_agent = StoryboardA2AAgent(agent_id="storyboard_agent_001")
    orchestrator.register_agent(storyboard_agent)

    # 创建任务
    task = A2ATask(
        task_id="a2a_task_001",
        script_content="早晨，一个女孩在咖啡馆读书，阳光透过窗户...",
        priority=1,
        metadata={"user_id": "user123", "project": "短片制作"}
    )

    # 分发并处理任务
    result = await orchestrator.dispatch_task(task)

    print(f"任务处理结果: {result}")
    return result
