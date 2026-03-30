"""
@FileName: mcp_http_server.py
@Description: HTTP MCP Server - 用于本地联调
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/30
"""

from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from penshot.api.function_calls import create_penshot_agent
from penshot.neopen.shot_language import Language

app = FastAPI(title="Penshot MCP Server", version="1.0.0")

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建智能体实例
agent = create_penshot_agent()


# ==================== 请求模型 ====================

class BreakdownRequest(BaseModel):
    script: str
    language: str = "zh"
    wait: bool = False
    timeout: int = 300


class TaskRequest(BaseModel):
    task_id: str


class StatusFilterRequest(BaseModel):
    status_filter: Optional[str] = None
    limit: int = 20


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Penshot MCP Server",
        "version": "1.0.0",
        "endpoints": [
            "GET /tools - 获取工具列表",
            "POST /tools/breakdown_script - 拆分剧本",
            "POST /tools/get_task_status - 获取任务状态",
            "POST /tools/get_task_result - 获取任务结果",
            "POST /tools/cancel_task - 取消任务",
            "POST /tools/list_tasks - 列出任务",
            "GET /tools/queue_status - 队列状态",
            "GET /tools/stats - 统计信息"
        ]
    }


@app.get("/tools")
async def list_tools():
    """获取工具列表"""
    return {
        "tools": [
            {
                "name": "breakdown_script",
                "description": "将剧本拆分为分镜序列。提交剧本后返回任务ID，可后续查询状态和结果。",
                "parameters": {
                    "script": {"type": "string", "description": "剧本文本内容"},
                    "language": {"type": "string", "enum": ["zh", "en"], "default": "zh", "description": "输出语言"},
                    "wait": {"type": "boolean", "default": False, "description": "是否等待完成"},
                    "timeout": {"type": "integer", "default": 300, "description": "超时时间（秒）"}
                }
            },
            {
                "name": "get_task_status",
                "description": "获取任务状态，包括进度、阶段等信息",
                "parameters": {
                    "task_id": {"type": "string", "description": "任务ID"}
                }
            },
            {
                "name": "get_task_result",
                "description": "获取任务结果",
                "parameters": {
                    "task_id": {"type": "string", "description": "任务ID"}
                }
            },
            {
                "name": "cancel_task",
                "description": "取消正在执行的任务",
                "parameters": {
                    "task_id": {"type": "string", "description": "任务ID"}
                }
            },
            {
                "name": "list_tasks",
                "description": "列出所有任务",
                "parameters": {
                    "status_filter": {"type": "string", "enum": ["pending", "processing", "completed", "failed"], "description": "按状态筛选"},
                    "limit": {"type": "integer", "default": 20, "description": "返回数量限制"}
                }
            },
            {
                "name": "get_queue_status",
                "description": "获取任务队列状态",
                "parameters": {}
            },
            {
                "name": "get_stats",
                "description": "获取服务器统计信息",
                "parameters": {}
            }
        ]
    }


@app.post("/tools/breakdown_script")
async def breakdown_script(request: BreakdownRequest):
    """拆分剧本"""
    try:
        if request.wait:
            # 同步模式
            result = agent.breakdown_script(
                script_text=request.script,
                language=Language(request.language),
                wait_timeout=request.timeout
            )
            return {
                "success": True,
                "task_id": result.task_id,
                "status": result.status,
                "data": result.data,
                "error": result.error,
                "processing_time_ms": result.processing_time_ms
            }
        else:
            # 异步模式
            task_id = agent.breakdown_script_async(
                script_text=request.script,
                language=Language(request.language),
            )
            return {
                "success": True,
                "task_id": task_id,
                "status": "pending",
                "message": "任务已提交，请使用 /tools/get_task_status 查询进度"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/get_task_status")
async def get_task_status(request: TaskRequest):
    """获取任务状态"""
    status = agent.get_task_status(request.task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {request.task_id}")
    return status


@app.post("/tools/get_task_result")
async def get_task_result(request: TaskRequest):
    """获取任务结果"""
    result = agent.get_task_result(request.task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"任务不存在: {request.task_id}")

    return {
        "task_id": result.task_id,
        "success": result.success,
        "status": result.status,
        "data": result.data,
        "error": result.error,
        "processing_time_ms": result.processing_time_ms
    }


@app.post("/tools/cancel_task")
async def cancel_task(request: TaskRequest):
    """取消任务"""
    success = agent.cancel_task(request.task_id)
    return {
        "task_id": request.task_id,
        "cancelled": success,
        "message": "任务已取消" if success else "取消失败"
    }


@app.post("/tools/list_tasks")
async def list_tasks(request: StatusFilterRequest):
    """列出任务列表"""
    # 获取所有任务ID
    task_ids = agent.task_manager.list_tasks() if hasattr(agent.task_manager, 'list_tasks') else []

    tasks = []
    for task_id in task_ids[:request.limit]:
        status = agent.get_task_status(task_id)
        if status:
            if request.status_filter and status.get("status") != request.status_filter:
                continue
            tasks.append({
                "task_id": task_id,
                "status": status.get("status"),
                "stage": status.get("stage"),
                "progress": status.get("progress"),
                "created_at": status.get("created_at")
            })

    return {
        "total": len(tasks),
        "limit": request.limit,
        "tasks": tasks
    }


@app.get("/tools/queue_status")
async def get_queue_status():
    """获取队列状态"""
    return agent.get_queue_status()


@app.get("/tools/stats")
async def get_stats():
    """获取统计信息"""
    return agent.get_stats()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )
