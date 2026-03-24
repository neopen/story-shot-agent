"""
@FileName: rest_server.py
@Description: REST API 服务器 - 供非Python智能体通过HTTP调用
@Author: HiPeng
@Time: 2026/3/23 18:54
"""
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from penshot.logger import info, error, log_with_context
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.shot_context import task_id_ctx
from penshot.neopen.shot_language import set_language, Language
from penshot.neopen.task.task_factory import create_task_factory, TaskFactory
from penshot.neopen.task.task_models import (
    ProcessingStatus, TaskStatus, TaskResponse
)
from penshot.utils.log_utils import print_log_exception


def _generate_task_id() -> str:
    return "HL" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))


# ============================================================================
# 扩展的请求/响应模型
# ============================================================================

class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class CancelTaskResponse(BaseModel):
    """取消任务响应"""
    task_id: str
    status: str
    message: str
    cancelled_at: datetime


class SyncProcessRequest(BaseModel):
    """同步处理请求"""
    script: str
    task_id: Optional[str] = None
    language: Language = Language.ZH
    config: Optional[ShotConfig] = None
    timeout: float = 300


class ProcessRequest(BaseModel):
    """处理请求数据模型（用于 API 输入）

    Notes:
    - `config` 使用通用字典以保证可序列化并与内部 dataclass 互操作。
    - `task_id` 使用生成器作为默认值。
    """
    script: str = Field(..., min_length=1, description="原始剧本文本")
    config: Optional[ShotConfig] = Field(default_factory=ShotConfig, description="处理配置（序列化形式）")
    callback_url: Optional[str] = Field(default=None, description="回调URL，处理完成后通知（可选）")
    task_id: str = Field(default_factory=_generate_task_id, description="外部请求ID（可选）")
    language: Language = Field(default=Language.ZH, description='剧本语言，例如 "zh" 或 "en"')

    @field_validator("language")
    def validate_language(cls, v):
        if v not in {Language.ZH, Language.EN}:
            raise ValueError("language must be one of: 'zh', 'en'")
        return v


class ProcessResult(BaseModel):
    """处理结果响应模型（用于回调和最终响应）"""
    task_id: str
    status: TaskStatus = Field(..., description="success | failed")
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class BatchProcessResult(BaseModel):
    """批量处理结果模型（API 输出）"""
    batch_id: str
    total_tasks: int
    success_tasks: int
    failed_tasks: int
    pending_tasks: int
    results: List[ProcessingStatus] = Field(default_factory=list, )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchProcessRequest(BaseModel):
    """批量处理请求模型（API 输入）"""
    scripts: List[str] = Field(..., description="剧本列表")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    batch_id: Optional[str] = None
    language: Language = Field(default=Language.ZH, description='剧本语言，例如 "zh" 或 "en"')

    @field_validator("language")
    def validate_language(cls, v):
        if v not in {Language.ZH, Language.EN}:
            raise ValueError("language must be one of: 'zh', 'en'")
        return v

    @field_validator("scripts")
    def validate_scripts_length(cls, v):
        if not v or len(v) < 1:
            raise ValueError("scripts must contain at least 1 item")
        if len(v) > 50:
            raise ValueError("scripts contains too many items (max 50)")
        return v


# ============================================================================
# 初始化组件
# ============================================================================

router = APIRouter(prefix="/api/v1", tags=["Penshot"])

# 使用 TaskFactory 替代原始的 TaskManager + TaskProcessor
task_factory: TaskFactory = None


def init_task_factory(max_concurrent: int = 10, queue_size: int = 1000):
    """初始化任务工厂（在应用启动时调用）"""
    global task_factory
    task_factory = create_task_factory(
        max_concurrent=max_concurrent,
        queue_size=queue_size
    )


def get_task_factory() -> TaskFactory:
    """获取任务工厂实例"""
    if task_factory is None:
        init_task_factory()
    return task_factory


# ============================================================================
# 分镜生成接口
# ============================================================================

@router.post("/storyboard", response_model=ProcessResult)
def generate_storyboard(
        request: ProcessRequest
) -> ProcessResult:
    """
    分镜生成接口（异步）

    提交剧本进行分镜生成，立即返回任务ID

    - **script**: 剧本文本内容
    - **task_id**: 可选，自定义任务ID
    - **language**: 输出语言 (zh/en)
    - **config**: 可选配置参数
    - **callback_url**: 回调URL（可选）
    """
    try:
        log_with_context(
            "INFO",
            "接收到分镜生成请求",
            {
                "task_id": request.task_id,
                "script_length": len(request.script),
                "language": request.language
            }
        )

        # 设置上下文
        if request.task_id:
            task_id_ctx.set(request.task_id)

        # 设置语言
        set_language(request.language)

        factory = get_task_factory()

        # 提交任务到工厂
        task_id = factory.submit(
            script=request.script,
            task_id=request.task_id,
            config=request.config,
            language=request.language,
            callback_url=request.callback_url
        )

        info(f"任务创建成功: {task_id}")

        return ProcessResult(
            success=True,
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="任务已提交，请使用任务ID查询状态",
            created_at=datetime.now(timezone.utc)
        )

    except ValueError as e:
        print_log_exception()
        error(f"参数错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print_log_exception()
        error(f"分镜生成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部服务器错误: {str(e)}"
        )


@router.post("/storyboard/sync", response_model=ProcessResult)
async def generate_storyboard_sync(
        request: SyncProcessRequest
):
    """
    同步分镜生成接口

    等待任务完成后返回结果

    - **script**: 剧本文本内容
    - **timeout**: 等待超时时间（秒）
    - **language**: 输出语言
    - **config**: 可选配置
    """
    try:
        log_with_context(
            "INFO",
            "接收到同步分镜生成请求",
            {"script_length": len(request.script)}
        )

        set_language(request.language)

        factory = get_task_factory()

        # 使用工厂的同步提交方法
        result: TaskResponse = factory.submit_and_wait(
            script=request.script,
            task_id=request.task_id,
            config=request.config,
            language=request.language,
            timeout=request.timeout
        )

        if result.success:
            return ProcessResult(
                task_id=result.task_id,
                success=True,
                status=TaskStatus.SUCCESS,
                data=result.data,
                processing_time_ms=result.processing_time_ms,
                created_at=result.created_at,
                completed_at=result.completed_at
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "任务处理失败"
            )

    except HTTPException:
        raise
    except Exception as e:
        print_log_exception()
        error(f"同步分镜生成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# 批量处理接口
# ============================================================================

@router.post("/storyboard/batch", response_model=BatchProcessResult)
def batch_process_scripts(
        request: BatchProcessRequest
) -> BatchProcessResult:
    """
    批量处理多个剧本（异步）

    - **scripts**: 剧本列表（最多50个）
    - **batch_id**: 可选，自定义批量ID
    - **config**: 统一配置（可选）
    - **language**: 输出语言
    """
    try:
        batch_id = request.batch_id or str(uuid.uuid4())

        log_with_context(
            "INFO",
            "接收到批量处理请求",
            {
                "batch_id": batch_id,
                "script_count": len(request.scripts)
            }
        )

        set_language(request.language)

        # 限制批量大小
        max_batch_size = 50
        if len(request.scripts) > max_batch_size:
            raise ValueError(f"批量处理最多支持 {max_batch_size} 个剧本")

        factory = get_task_factory()

        # 使用工厂的批量提交方法
        batch_response = factory.batch_submit(
            scripts=request.scripts,
            config=request.config,
            language=request.language
        )

        return BatchProcessResult(
            batch_id=batch_response.batch_id,
            total_tasks=batch_response.total_tasks,
            success_tasks=0,
            failed_tasks=0,
            pending_tasks=batch_response.total_tasks,
            created_at=batch_response.created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print_log_exception()
        error(f"批量处理创建失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量处理创建失败: {str(e)}"
        )


@router.post("/storyboard/batch/sync", response_model=List[ProcessResult])
async def batch_process_scripts_sync(
        request: BatchProcessRequest
):
    """
    批量处理多个剧本（同步，等待全部完成）

    - **scripts**: 剧本列表（最多20个）
    - **config**: 统一配置（可选）
    - **language**: 输出语言
    """
    try:
        log_with_context(
            "INFO",
            "接收到同步批量处理请求",
            {"script_count": len(request.scripts)}
        )

        set_language(request.language)

        # 限制批量大小（同步模式限制更小）
        max_batch_size = 20
        if len(request.scripts) > max_batch_size:
            raise ValueError(f"同步批量处理最多支持 {max_batch_size} 个剧本")

        factory = get_task_factory()

        # 使用工厂的批量同步方法
        results = factory.batch(
            scripts=request.scripts,
            config=request.config,
            language=request.language,
            timeout=600  # 10分钟超时
        )

        # 转换为 ProcessResult 列表
        return [
            ProcessResult(
                task_id=r.task_id,
                success=r.success,
                status=TaskStatus.SUCCESS if r.success else TaskStatus.FAILED,
                data=r.data,
                message=r.error if not r.success else None,
                error=r.error if not r.success else None,
                processing_time_ms=r.processing_time_ms,
                created_at=r.created_at,
                completed_at=r.completed_at
            )
            for r in results
        ]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print_log_exception()
        error(f"同步批量处理失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步批量处理失败: {str(e)}"
        )


@router.get("/batch/status/{batch_id}", response_model=BatchProcessResult)
def get_batch_status(batch_id):
    """
    获取批量任务状态

    - **batch_id**: 批量任务ID，逗号隔开
    """
    factory = get_task_factory()

    batch_status = factory.batch_get_status(batch_id)
    if not batch_status or batch_status == []:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {batch_id}"
        )

    return BatchProcessResult(
        batch_id=batch_id,
        total_tasks=len(batch_status),
        success_tasks=len([x for x in batch_status if x and x.status == TaskStatus.SUCCESS]),
        failed_tasks=len([x for x in batch_status if x and x.status == TaskStatus.FAILED]),
        pending_tasks=len([x for x in batch_status if x and x.status == TaskStatus.PENDING]),
        results=batch_status,
        created_at=datetime.now(timezone.utc)
    )


# ============================================================================
# 任务管理接口
# ============================================================================

@router.get("/status/{task_id}", response_model=ProcessingStatus)
def get_task_status(task_id: str):
    """
    获取任务状态

    - **task_id**: 任务ID
    """
    factory = get_task_factory()

    task_status = factory.get_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    return task_status


@router.get("/result/{task_id}", response_model=ProcessResult)
def get_task_result(task_id: str):
    """
    获取任务结果

    - **task_id**: 任务ID
    """
    factory = get_task_factory()

    result = factory.get_result(task_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    # 任务处理中
    if result.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"任务仍在处理中，当前状态: {result.status}"
        )

    return ProcessResult(
        task_id=result.task_id,
        success=result.success,
        status=TaskStatus.SUCCESS if result.success else TaskStatus.FAILED,
        data=result.data,
        message=result.error if not result.success else None,
        error=result.error if not result.success else None,
        processing_time_ms=result.processing_time_ms,
        created_at=result.created_at,
        completed_at=result.completed_at
    )


@router.delete("/task/{task_id}", response_model=CancelTaskResponse)
def cancel_task(task_id: str):
    """
    取消任务

    - **task_id**: 任务ID
    """
    factory = get_task_factory()

    # 先检查任务是否存在
    task_status = factory.get_status(task_id)
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    if task_status.status.is_completed():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务已结束，无法取消: {task_status.status}"
        )

    # 取消任务
    success = factory.cancel(task_id)

    return CancelTaskResponse(
        task_id=task_id,
        status=TaskStatus.CANCELLED if success else TaskStatus.FAILED,
        message="任务已取消" if success else "取消失败，无法取消",
        cancelled_at=datetime.now(timezone.utc)
    )


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
        limit: int = 20,
        offset: int = 0
):
    """
    列出任务列表

    - **status_filter**: 可选，按状态筛选 (pending/processing/completed/failed)
    - **limit**: 返回数量限制
    - **offset**: 偏移量
    """
    factory = get_task_factory()

    # 获取任务列表（需要扩展 factory 支持）
    # 简化实现
    tasks = []

    # 如果有统计信息，可以获取
    stats = factory.get_stats()

    return TaskListResponse(
        tasks=tasks,
        total=stats.get("total_submitted", 0),
        page=offset // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.get("/queue/status")
def get_queue_status():
    """
    获取队列状态

    返回当前任务队列的详细信息
    """
    factory = get_task_factory()
    return factory.get_queue_status()


@router.get("/stats")
def get_stats():
    """
    获取处理器统计信息

    返回任务处理的统计信息
    """
    factory = get_task_factory()
    return factory.get_stats()


# ============================================================================
# 配置接口
# ============================================================================

@router.get("/config", response_model=ShotConfig)
def get_default_config():
    """获取默认配置"""
    return ShotConfig()


@router.get("/languages")
def get_supported_languages():
    """获取支持的语言列表"""
    return {
        "languages": [
            {"code": "zh", "name": "中文"},
            {"code": "en", "name": "English"}
        ],
        "default": "zh"
    }


# ============================================================================
# 健康检查接口
# ============================================================================

@router.get("/health")
def health_check():
    """健康检查"""
    factory = get_task_factory()
    stats = factory.get_stats()
    queue_status = factory.get_queue_status()

    return {
        "status": "healthy",
        "service": "penshot",
        "stats": stats,
        "queue": queue_status
    }


# ============================================================================
# 应用启动/关闭钩子
# ============================================================================

async def startup_event():
    """应用启动时执行"""
    init_task_factory(max_concurrent=10, queue_size=1000)
    info("REST API 服务器启动完成")


async def shutdown_event():
    """应用关闭时执行"""
    factory = get_task_factory()
    await factory.shutdown(wait_for_completion=True, timeout=30)
    info("REST API 服务器已关闭")
