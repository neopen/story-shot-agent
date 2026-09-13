"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 01_langgraph_integration.py
@Description: 集成示例：把 Penshot SDK 封装成 LangGraph 工作流节点
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:50
"""
import asyncio
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from penshot import ShotLanguage
from penshot.api import PenshotFunction, PenshotResult
from penshot.neopen.task import TaskStatus

# 说明：
# - breakdown_script_async(script_text, script_id=..., ...) 立即返回真实 task_id；
#   script_id 只是调用方用来关联剧本的自定义 ID，不要把它当作轮询 ID。
# - get_task_status()["status"] 是 TaskStatus（str 枚举）实例；终态成功是 TaskStatus.SUCCESS，
#   没有 "completed" 字面量。示例统一用 TaskStatus 成员比较（str 枚举与同名字符串相等）。
# - 结果取数契约：result.data["instructions"]（含 project_info.total_fragments / fragments[]）。
# - wait_for_result_async 是协程，直接 await；breakdown_script_async 是普通函数，不要 await。


class WorkflowStage(str, Enum):
    """示例工作流自定义阶段（与项目内部的 PipelineNode 无关，可自行定义）。"""

    INIT = "init"
    PARSING = "parsing"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryboardState(BaseModel):
    """LangGraph 工作流状态。"""

    # 输入
    script_text: str = Field(..., description="输入剧本文本")
    script_id: Optional[str] = Field(default=None, description="调用方剧本关联 ID（非轮询 ID）")
    language: str = Field(default="zh", description="输出语言")

    # 中间状态
    stage: WorkflowStage = Field(default=WorkflowStage.INIT, description="当前阶段")
    task_id_assigned: Optional[str] = Field(default=None, description="提交后返回的真实任务 ID")
    poll_count: int = Field(default=0, description="轮询次数（避免无限轮询）")

    # 结果
    result: Optional[PenshotResult] = Field(default=None, description="分镜生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")

    # 元数据
    progress: float = Field(default=0.0, description="进度 0-100")


def llm_env_configured() -> bool:
    """检查是否已配置 LLM（环境变量或仓库根目录 .env）。"""
    if any(key.startswith("PENSHOT_LLM") for key in os.environ):
        return True
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.exists():
        for line in root_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("PENSHOT_LLM"):
                return True
    return False


def terminal_status(status) -> Optional[str]:
    """把任务状态归一为终态字符串：success / failed / cancelled；未结束返回 None。

    兼容 TaskStatus 枚举与纯字符串两种取值（str 枚举与同名字符串相等）。
    """
    if status in (TaskStatus.SUCCESS, "success"):
        return "success"
    if status in (TaskStatus.FAILED, "failed"):
        return "failed"
    if status in (TaskStatus.CANCELLED, "cancelled"):
        return "cancelled"
    return None


def print_instructions_summary(result: PenshotResult) -> None:
    """按 data.instructions 契约打印结果摘要。"""
    data = result.data or {}
    instructions = data.get("instructions", {})
    project_info = instructions.get("project_info", {})
    fragments = instructions.get("fragments", [])
    print(f"片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"总时长: {project_info.get('total_duration', 0.0):.1f} 秒")
    for i, frag in enumerate(fragments[:3], 1):
        print(f"  [{i}] {frag.get('fragment_id')}: {str(frag.get('prompt', ''))[:70]}...")


class StoryboardWorkflowNodes:
    """把 Penshot 调用封装为 LangGraph 节点函数。"""

    def __init__(self, config: Optional[Any] = None, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.agent = PenshotFunction(config=config, max_concurrent=max_concurrent)

    @staticmethod
    def _language(state: StoryboardState) -> ShotLanguage:
        return ShotLanguage.ZH if state.language == "zh" else ShotLanguage.EN

    def submit_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """提交任务节点：调用异步接口，返回真实 task_id 存入 task_id_assigned。"""
        print(f"[节点] 提交任务: {state.script_text[:40]}...")
        task_id = self.agent.breakdown_script_async(
            script_text=state.script_text,
            script_id=state.script_id,  # 关联 ID，不是轮询 ID
            language=self._language(state),
        )
        return {
            "task_id_assigned": task_id,
            "stage": WorkflowStage.PARSING,
            "progress": 10.0,
        }

    async def poll_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """轮询状态节点：按 TaskStatus 终态判断，最多轮询 max_polls 次。"""
        task_id = state.task_id_assigned
        if not task_id:
            return {"stage": WorkflowStage.FAILED, "error": "没有可轮询的任务 ID"}

        task = self.agent.get_task_status(task_id)
        if not task:
            return {"stage": WorkflowStage.FAILED, "error": f"任务不存在: {task_id}"}

        status = task.get("status")
        progress = task.get("progress", 0)
        print(f"[节点] 轮询 {task_id}: status={getattr(status, 'value', status)}, 进度={progress}%")

        terminal = terminal_status(status)
        if terminal == "success":
            result = self.agent.get_task_result(task_id)
            return {"stage": WorkflowStage.COMPLETED, "result": result, "progress": 100.0}
        if terminal == "failed":
            return {"stage": WorkflowStage.FAILED, "error": str(task.get("error", "未知错误"))}
        if terminal == "cancelled":
            return {"stage": WorkflowStage.FAILED, "error": "任务已取消"}

        # 仍在处理中：保护轮询上限，避免无 key 等场景死循环
        if state.poll_count >= 60:
            return {"stage": WorkflowStage.FAILED, "error": "轮询超过 60 次仍未结束"}
        await asyncio.sleep(1.0)
        return {"stage": WorkflowStage.GENERATING, "progress": progress}

    async def wait_for_result_node(self, state: StoryboardState) -> Dict[str, Any]:
        """等待结果节点：直接 await wait_for_result_async 阻塞到终态。"""
        task_id = state.task_id_assigned
        if not task_id:
            return {"stage": WorkflowStage.FAILED, "error": "没有任务 ID"}

        print(f"[节点] 等待结果: {task_id}")
        result = await self.agent.wait_for_result_async(task_id, timeout=900.0)
        if result.success:
            return {"stage": WorkflowStage.COMPLETED, "result": result, "progress": 100.0}
        return {"stage": WorkflowStage.FAILED, "error": result.error, "progress": 0}


# ==================== 路由函数 ====================


def route_after_submit(state: StoryboardState) -> str:
    """提交后路由：拿到 task_id 进入轮询/等待，否则进入错误节点。"""
    return "wait" if state.task_id_assigned else "error"


def route_after_poll(state: StoryboardState) -> str:
    """轮询后路由：completed 结束、failed 错误、其余继续轮询。"""
    if state.stage == WorkflowStage.COMPLETED:
        return "end"
    if state.stage == WorkflowStage.FAILED:
        return "error"
    return "poll"


def route_after_wait(state: StoryboardState) -> str:
    """等待后路由。"""
    return "end" if state.stage == WorkflowStage.COMPLETED else "error"


# ==================== 工作流构建器 ====================


class StoryboardWorkflowBuilder:
    """构建两种模式的分镜工作流（共用同一批节点实例，避免多份 agent/事件循环）。"""

    def __init__(self):
        self.nodes = StoryboardWorkflowNodes()

    def build_wait_workflow(self) -> CompiledStateGraph:
        """流程：提交任务 → 等待结果 → 完成/失败。"""
        workflow = StateGraph(StoryboardState)
        workflow.add_node("submit", self.nodes.submit_task_node)
        workflow.add_node("wait", self.nodes.wait_for_result_node)
        workflow.add_node("error", lambda s: {"stage": WorkflowStage.FAILED})
        workflow.set_entry_point("submit")
        workflow.add_conditional_edges(
            "submit", route_after_submit, {"wait": "wait", "error": "error"}
        )
        workflow.add_conditional_edges(
            "wait", route_after_wait, {"end": END, "error": "error"}
        )
        workflow.add_edge("error", END)
        return workflow.compile()

    def build_polling_workflow(self) -> CompiledStateGraph:
        """流程：提交任务 → 轮询状态 → 完成/失败。"""
        workflow = StateGraph(StoryboardState)
        workflow.add_node("submit", self.nodes.submit_task_node)
        workflow.add_node("poll", self.nodes.poll_task_node)
        workflow.add_node("error", lambda s: {"stage": WorkflowStage.FAILED})
        workflow.set_entry_point("submit")
        workflow.add_conditional_edges(
            "submit", route_after_submit, {"wait": "poll", "error": "error"}
        )
        workflow.add_conditional_edges(
            "poll", route_after_poll, {"poll": "poll", "end": END, "error": "error"}
        )
        workflow.add_edge("error", END)
        return workflow.compile()


async def _run(graph: CompiledStateGraph, script_text: str, script_id: str, label: str) -> StoryboardState:
    print(f"\n=== {label} ===")
    final = await graph.ainvoke(
        StoryboardState(script_text=script_text, script_id=script_id, language="zh")
    )
    print(f"最终阶段: {final.stage}")
    if final.result and final.result.success:
        print(f"成功，处理耗时: {final.result.processing_time_ms}ms")
        print_instructions_summary(final.result)
    elif final.error:
        print(f"失败: {final.error}")
    return final


async def main():
    """构建并运行两种 LangGraph 工作流。未配置 LLM key 时只做图构建演示。"""
    builder = StoryboardWorkflowBuilder()
    wait_graph = builder.build_wait_workflow()
    polling_graph = builder.build_polling_workflow()
    print("两个工作流图已成功编译（LangGraph 节点封装验证通过）。")

    if not llm_env_configured():
        print("未配置 LLM key：跳过真实执行。设置 PENSHOT_LLM__DEFAULT__API_KEY 后重跑可走完整流程。")
        builder.nodes.agent.shutdown()
        return

    try:
        await _run(
            wait_graph,
            "海边日落，一个男人牵着狗沿沙滩慢慢散步，浪花轻轻拍打脚踝。",
            "langgraph-wait-001",
            "等待模式工作流",
        )
        await _run(
            polling_graph,
            "午后办公室，程序员小李修改代码时突然接到电话，神情惊讶。",
            "langgraph-poll-001",
            "轮询模式工作流",
        )
    finally:
        builder.nodes.agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
