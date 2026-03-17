"""
@FileName: langgraph_integration.py
@Description: 集成到 LangGraph 工作流节点
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:43
"""
from typing import Dict, Any

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from penshot.neopen import generate_storyboard


# 定义状态结构
class StoryboardState(BaseModel):
    script_text: str = Field(description="输入剧本文本")
    task_id: str = Field(default=None, description="任务ID")
    storyboard_result: Dict[str, Any] = Field(default=None, description="分镜生成结果")
    next_step: str = Field(default="", description="下一步操作指示")


# 创建分镜生成节点
async def storyboard_generator_node(state: StoryboardState) -> Dict[str, Any]:
    """
    LangGraph 工作流中的分镜生成节点
    """
    try:
        result = await generate_storyboard(
            script_text=state.script_text,
            task_id=state.task_id
        )

        return {
            "storyboard_result": result,
            "next_step": "storyboard_generated"
        }
    except Exception as e:
        return {
            "storyboard_result": {"error": str(e)},
            "next_step": "error"
        }


# 构建工作流示例
def create_storyboard_workflow():
    workflow = StateGraph(StoryboardState)

    # 添加节点
    workflow.add_node("generate_storyboard", storyboard_generator_node)

    # 设置入口点
    workflow.set_entry_point("generate_storyboard")
    workflow.add_edge("generate_storyboard", END)

    return workflow.compile()


# 使用示例
async def run_langgraph_example():
    app = create_storyboard_workflow()

    # 初始化状态
    initial_state = StoryboardState(
        script_text="一个男孩在公园里放风筝，天空很蓝...",
        task_id="storyboard_task_001"
    )

    # 运行工作流
    final_state = await app.ainvoke(initial_state)

    return final_state
