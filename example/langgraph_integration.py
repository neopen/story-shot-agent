"""
@FileName: langgraph_integration.py
@Description: 集成到 LangGraph 工作流节点
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:43
"""
import asyncio
from typing import Dict, Any, Optional
from enum import Enum

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from penshot.api import PenshotFunction, PenshotResult
from penshot.config import ShotConfig
from penshot import Language


# ============================================================================
# 状态定义
# ============================================================================

class WorkflowStage(str, Enum):
    """工作流阶段"""
    INIT = "init"
    PARSING = "parsing"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryboardState(BaseModel):
    """LangGraph 工作流状态"""

    # 输入
    script_text: str = Field(..., description="输入剧本文本")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    language: str = Field(default="zh", description="输出语言")

    # 配置
    config: Optional[Dict[str, Any]] = Field(default=None, description="配置参数")

    # 中间状态
    stage: WorkflowStage = Field(default=WorkflowStage.INIT, description="当前阶段")
    task_id_assigned: Optional[str] = Field(default=None, description="分配的任务ID")

    # 结果
    result: Optional[PenshotResult] = Field(default=None, description="分镜生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")

    # 元数据
    progress: float = Field(default=0.0, description="进度 0-100")
    created_at: Optional[str] = Field(default=None, description="创建时间")


# ============================================================================
# 工作流节点
# ============================================================================

class StoryboardWorkflowNodes:
    """分镜生成工作流节点"""

    def __init__(self, config: Optional[ShotConfig] = None, max_concurrent: int = 5):
        """
        初始化工作流节点

        Args:
            config: 全局配置
        """
        self.config = config or ShotConfig()
        self.max_concurrent = max_concurrent
        self.agent = PenshotFunction(config=self.config, max_concurrent=max_concurrent)

    async def submit_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        提交任务节点

        提交分镜生成任务，获取 task_id
        """
        print(f"[节点] 提交任务: {state.script_text[:50]}...")

        # 确定语言
        language = Language.ZH if state.language == "zh" else Language.EN

        # 创建临时智能体（或复用）
        task_id = self.agent.breakdown_script_async(
            script_text=state.script_text,
            task_id=state.task_id,
            language=language
        )

        return {
            "task_id_assigned": task_id,
            "stage": WorkflowStage.PARSING,
            "progress": 10.0
        }

    async def poll_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        轮询任务状态节点

        检查任务是否完成，更新进度
        """
        task_id = state.task_id_assigned or state.task_id

        if not task_id:
            return {
                "stage": WorkflowStage.FAILED,
                "error": "没有任务ID",
                "progress": 0
            }

        # 获取任务状态
        task = self.agent.get_task_status(task_id)

        if not task:
            return {
                "stage": WorkflowStage.FAILED,
                "error": f"任务不存在: {task_id}",
                "progress": 0
            }

        status = task.get("status")
        progress = task.get("progress", 0)

        print(f"[节点] 轮询任务: {task_id}, 状态={status}, 进度={progress}%")

        if status == "completed":
            # 获取结果
            result = self.agent.get_task_result(task_id)

            return {
                "stage": WorkflowStage.COMPLETED,
                "result": result,
                "progress": 100.0
            }

        elif status == "failed":
            return {
                "stage": WorkflowStage.FAILED,
                "error": task.get("error", "未知错误"),
                "progress": progress
            }

        else:
            # 仍在处理中
            return {
                "stage": WorkflowStage.GENERATING,
                "progress": progress
            }

    async def wait_for_result_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        等待结果节点

        阻塞等待任务完成
        """
        task_id = state.task_id_assigned or state.task_id

        if not task_id:
            return {
                "stage": WorkflowStage.FAILED,
                "error": "没有任务ID"
            }

        print(f"[节点] 等待结果: {task_id}")

        try:
            result = await self.agent.wait_for_result_async(task_id)

            if result.success:
                return {
                    "stage": WorkflowStage.COMPLETED,
                    "result": result,
                    "progress": 100.0
                }
            else:
                return {
                    "stage": WorkflowStage.FAILED,
                    "error": result.error,
                    "progress": 0
                }

        except Exception as e:
            return {
                "stage": WorkflowStage.FAILED,
                "error": str(e),
                "progress": 0
            }


# ============================================================================
# 路由函数
# ============================================================================

def route_after_submit(state: StoryboardState) -> str:
    """提交后路由"""
    if state.task_id_assigned:
        return "poll"
    return "error"


def route_after_poll(state: StoryboardState) -> str:
    """轮询后路由"""
    if state.stage == WorkflowStage.COMPLETED:
        return "end"
    elif state.stage == WorkflowStage.FAILED:
        return "error"
    else:
        return "poll"  # 继续轮询


def route_after_wait(state: StoryboardState) -> str:
    """等待后路由"""
    if state.stage == WorkflowStage.COMPLETED:
        return "end"
    return "error"


# ============================================================================
# 工作流构建器
# ============================================================================

class StoryboardWorkflowBuilder:
    """分镜工作流构建器"""

    def __init__(self, config: Optional[ShotConfig] = None):
        """
        初始化工作流构建器

        Args:
            config: 全局配置
        """
        self.config = config
        self.nodes = StoryboardWorkflowNodes(config)

    def build_polling_workflow(self) -> CompiledStateGraph:
        """
        构建轮询模式工作流

        流程: 提交任务 -> 轮询状态 -> 完成/失败
        """
        workflow = StateGraph(StoryboardState)

        # 添加节点
        workflow.add_node("submit", self.nodes.submit_task_node)
        workflow.add_node("poll", self.nodes.poll_task_node)
        workflow.add_node("error", lambda s: {"stage": WorkflowStage.FAILED})

        # 设置入口
        workflow.set_entry_point("submit")

        # 添加边
        workflow.add_conditional_edges(
            "submit",
            route_after_submit,
            {
                "poll": "poll",
                "error": "error"
            }
        )

        workflow.add_conditional_edges(
            "poll",
            route_after_poll,
            {
                "poll": "poll",
                "end": END,
                "error": "error"
            }
        )

        workflow.add_edge("error", END)

        return workflow.compile()

    def build_wait_workflow(self) -> CompiledStateGraph:
        """
        构建等待模式工作流

        流程: 提交任务 -> 等待结果 -> 完成/失败
        """
        workflow = StateGraph(StoryboardState)

        # 添加节点
        workflow.add_node("submit", self.nodes.submit_task_node)
        workflow.add_node("wait", self.nodes.wait_for_result_node)
        workflow.add_node("error", lambda s: {"stage": WorkflowStage.FAILED})

        # 设置入口
        workflow.set_entry_point("submit")

        # 添加边
        workflow.add_conditional_edges(
            "submit",
            route_after_submit,
            {
                "wait": "wait",
                "error": "error"
            }
        )

        workflow.add_conditional_edges(
            "wait",
            route_after_wait,
            {
                "end": END,
                "error": "error"
            }
        )

        workflow.add_edge("error", END)

        return workflow.compile()


# ============================================================================
# 使用示例
# ============================================================================

async def run_polling_workflow():
    """运行轮询模式工作流"""
    print("=== 轮询模式工作流示例 ===")

    builder = StoryboardWorkflowBuilder()
    workflow = builder.build_polling_workflow()

    # 初始化状态
    initial_state = StoryboardState(
        script_text="一个男孩在公园里放风筝，天空很蓝...",
        task_id="storyboard_task_001",
        language="zh"
    )

    # 运行工作流
    final_state = await workflow.ainvoke(initial_state)

    print(f"最终阶段: {final_state.stage}")

    if final_state.result and final_state.result.success:
        data = final_state.result.data or {}
        shots = data.get("shots", [])
        print(f"生成 {len(shots)} 个镜头")
    elif final_state.error:
        print(f"错误: {final_state.error}")

    return final_state


async def run_wait_workflow():
    """运行等待模式工作流"""
    print("\n=== 等待模式工作流示例 ===")

    builder = StoryboardWorkflowBuilder()
    workflow = builder.build_wait_workflow()

    # 初始化状态
    initial_state = StoryboardState(
        script_text="一个女孩在咖啡馆读书，阳光透过窗户...",
        task_id="storyboard_task_002",
        language="zh"
    )

    # 运行工作流
    final_state = await workflow.ainvoke(initial_state)

    print(f"最终阶段: {final_state.stage}")

    if final_state.result and final_state.result.success:
        data = final_state.result.data or {}
        stats = data.get("stats", {})
        print(f"镜头数: {stats.get('shot_count', 0)}")
        print(f"总时长: {stats.get('total_duration', 0):.1f}秒")
        print(f"处理时间: {final_state.result.processing_time_ms}ms")

    return final_state


async def run_advanced_workflow():
    """高级工作流示例（带条件分支）"""
    print("\n=== 高级工作流示例 ===")

    # 创建自定义工作流
    workflow = StateGraph(StoryboardState)

    nodes = StoryboardWorkflowNodes()

    # 添加节点
    workflow.add_node("submit", nodes.submit_task_node)
    workflow.add_node("wait", nodes.wait_for_result_node)
    workflow.add_node("process_success", lambda s: {"stage": WorkflowStage.COMPLETED})
    workflow.add_node("handle_failure", lambda s: {"stage": WorkflowStage.FAILED})

    workflow.set_entry_point("submit")

    # 条件路由
    def route_after_wait_advanced(state: StoryboardState) -> str:
        if state.result and state.result.success:
            return "success"
        return "failure"

    workflow.add_conditional_edges("submit", route_after_submit, {
        "wait": "wait",
        "error": "handle_failure"
    })

    workflow.add_conditional_edges("wait", route_after_wait_advanced, {
        "success": "process_success",
        "failure": "handle_failure"
    })

    workflow.add_edge("process_success", END)
    workflow.add_edge("handle_failure", END)

    app = workflow.compile()

    # 运行
    initial_state = StoryboardState(
        script_text="科幻场景：太空站内部，宇航员发现异常信号...",
        language="zh"
    )

    final_state = await app.ainvoke(initial_state)

    print(f"工作流完成: {final_state.stage}")

    return final_state


async def main():
    """主函数"""

    # 运行轮询模式
    await run_polling_workflow()

    # 运行等待模式
    await run_wait_workflow()

    # 运行高级工作流
    await run_advanced_workflow()


if __name__ == "__main__":
    asyncio.run(main())