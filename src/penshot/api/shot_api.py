"""
@FileName: a2a_api.py
@Description:  分镜生成API，通过A2A协议调用分镜生成功能
@Author: Haeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10/23 11:19
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi import HTTPException

from penshot.logger import error, log_with_context
from penshot.neopen.context_var import task_id_ctx
from penshot.neopen.language_manage import set_language
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.task.task_models import ProcessRequest, ProcessResult, ProcessingStatus, BatchProcessResult, BatchProcessRequest
from penshot.neopen.task.task_processor import AsyncTaskProcessor
from penshot.utils.log_utils import print_log_exception

app = APIRouter()
task_manager = TaskManager()
task_processor = AsyncTaskProcessor(task_manager)


@app.post("/storyboard", response_model=ProcessResult)
def generate_storyboard_api(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    通过A2A协议调用分镜生成功能

    Args:
        request: 分镜生成请求参数

    Returns:
        StoryboardResponse: 分镜生成结果
    """
    try:
        log_with_context(
            "INFO",
            "接收到分镜生成请求",
            {
                "task_id": request.task_id,
                "duration": request.config.max_fragment_duration
            }
        )

        if request.task_id:
            task_id_ctx.set(request.task_id)

        set_language(request.language)

        # 创建任务
        task_id = task_manager.create_task(
            script=request.script,
            config=request.config,
            task_id=request.task_id
        )

        # 在后台异步处理
        background_tasks.add_task(
            task_processor.process_script_task,
            task_id
        )

        # 立即返回任务ID
        return ProcessResult(
            success=True,
            task_id=task_id,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )

    except ValueError as e:
        print_log_exception()
        error(f"参数错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print_log_exception()
        error(f"分镜生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@app.post("/storyboard/batch", response_model=BatchProcessResult)
async def batch_process_scripts(
        request: BatchProcessRequest,
        background_tasks: BackgroundTasks
):
    """
    批量处理多个剧本

    - **scripts**: 剧本列表（最多10个）
    - **config**: 统一配置（可选）
    - **batch_id**: 批量ID（可选）
    """
    try:
        batch_id = request.batch_id or str(uuid.uuid4())
        set_language(request.language)

        # 在后台异步处理批量任务
        background_tasks.add_task(
            task_processor.process_batch,
            batch_id,
            request.scripts,
            request.config
        )

        return BatchProcessResult(
            batch_id=batch_id,
            total_tasks=len(request.scripts),
            completed_tasks=0,
            failed_tasks=0,
            pending_tasks=len(request.scripts),
            created_at=datetime.now(timezone.utc)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"批量处理创建失败: {str(e)}"
        )


@app.get("/status/{task_id}", response_model=ProcessingStatus)
def get_task_status(task_id: str):
    """
    获取任务状态

    - **task_id**: 任务ID
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"任务不存在: {task_id}"
        )

    # 计算预估剩余时间（基于进度），并把存储的 ISO 字符串解析为 datetime
    try:
        created_at_dt = datetime.fromisoformat(task["created_at"]) if isinstance(task["created_at"], str) else task["created_at"]
    except Exception:
        created_at_dt = datetime.now(timezone.utc)

    try:
        updated_at_dt = datetime.fromisoformat(task["updated_at"]) if isinstance(task["updated_at"], str) else task["updated_at"]
    except Exception:
        updated_at_dt = datetime.now(timezone.utc)

    estimated_time = None
    if task["status"] == "processing" and task.get("progress") and task["progress"] > 0:
        try:
            elapsed = (datetime.now(timezone.utc) - created_at_dt).total_seconds()
            estimated_time = int((elapsed / task["progress"]) * (100 - task["progress"]))
        except Exception:
            estimated_time = None

    return ProcessingStatus(
        task_id=task_id,
        status=task["status"],
        stage=task["stage"],
        progress=task.get("progress"),
        estimated_time_remaining=estimated_time,
        created_at=created_at_dt,
        updated_at=updated_at_dt,
        error_message=task.get("error")
    )


@app.get("/result/{task_id}", response_model=ProcessResult)
async def get_task_result(task_id: str):
    """
    获取任务结果

    - **task_id**: 任务ID
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"任务不存在: {task_id}"
        )

    if task["status"] == "pending":
        raise HTTPException(
            status_code=202,  # Accepted
            detail="任务仍在处理中"
        )

    if task["status"] == "processing":
        raise HTTPException(
            status_code=202,
            detail="任务正在处理中"
        )

    # 解析时间字符串并计算处理时间（毫秒）
    processing_time = None
    try:
        if task.get("completed_at"):
            completed_at_dt = datetime.fromisoformat(task["completed_at"]) if isinstance(task["completed_at"], str) else task["completed_at"]
            created_at_dt = datetime.fromisoformat(task["created_at"]) if isinstance(task["created_at"], str) else task["created_at"]
            processing_time = int((completed_at_dt - created_at_dt).total_seconds() * 1000)
        else:
            completed_at_dt = None
            created_at_dt = datetime.fromisoformat(task["created_at"]) if isinstance(task["created_at"], str) else task["created_at"]
    except Exception:
        completed_at_dt = task.get("completed_at")
        created_at_dt = task.get("created_at")

    return ProcessResult(
        task_id=task_id,
        success=task["status"] == "completed",
        status="success" if task["status"] == "completed" else "failed",
        data=task.get("result", {}).get("data"),
        message=task.get("error"),
        processing_time_ms=processing_time,
        created_at=created_at_dt,
        completed_at=completed_at_dt
    )


@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """
    取消任务（标记为取消状态）

    - **task_id**: 任务ID
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"任务不存在: {task_id}"
        )

    if task["status"] in ["completed", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"任务已结束，无法取消: {task['status']}"
        )

    # 标记为取消（实际实现可能需要中断正在执行的任务）
    task_manager.fail_task(task_id, "任务被用户取消")

    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "任务已标记为取消"
    }
