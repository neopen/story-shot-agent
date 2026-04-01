"""
@FileName: web_app.py
@Description: 集成到Web应用（FastAPI示例）
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:44
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from penshot.api import PenshotFunction
from penshot.config import ShotConfig
from penshot import Language
from penshot.neopen.task.task_models import TaskStatus


# ============================================================================
# 请求/响应模型
# ============================================================================

class ScriptRequest(BaseModel):
    """剧本请求"""
    script_text: str = Field(..., description="剧本文本")
    task_id: Optional[str] = Field(None, description="任务ID（可选）")
    language: str = Field("zh", description="输出语言 (zh/en)")
    wait: bool = Field(False, description="是否等待完成")
    timeout: float = Field(300, description="等待超时时间（秒）")


class ScriptBatchRequest(BaseModel):
    """批量剧本请求"""
    scripts: List[str] = Field(..., description="剧本列表")
    batch_id: Optional[str] = Field(None, description="批量ID")
    language: str = Field("zh", description="输出语言")


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    status: str
    message: str
    created_at: datetime


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    stage: str
    progress: Optional[float] = None
    estimated_time_remaining: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class TaskResultResponse(BaseModel):
    """任务结果响应"""
    task_id: str
    success: bool
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BatchTaskResponse(BaseModel):
    """批量任务响应"""
    batch_id: str
    total_tasks: int
    pending_tasks: int
    processing_tasks: int
    completed_tasks: int
    failed_tasks: int
    created_at: datetime


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    timestamp: datetime
    task_count: int


# ============================================================================
# Web应用
# ============================================================================

def create_web_app(
        config: Optional[ShotConfig] = None,
        enable_cors: bool = True
) -> FastAPI:
    """
    创建 Web 应用

    Args:
        config: 全局配置
        enable_cors: 是否启用 CORS

    Returns:
        FastAPI 应用实例
    """

    app = FastAPI(
        title="Penshot 分镜生成 API",
        description="智能分镜视频生成服务",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 初始化服务
    config = config or ShotConfig()
    penshot = PenshotFunction(config=config)

    # 启用 CORS
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ========================================================================
    # 健康检查
    # ========================================================================

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health_check():
        """健康检查"""
        # 获取任务数量（简化实现）
        task_count = 0
        # 如果有 task_manager，可以获取实际数量
        if hasattr(penshot, 'task_manager'):
            # 这里需要根据实际实现获取任务数
            pass

        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.now(timezone.utc),
            task_count=task_count
        )

    @app.get("/", tags=["Health"])
    async def root():
        """根路径"""
        return {
            "service": "Penshot API",
            "version": "0.1.0",
            "docs": "/docs",
            "status": "running"
        }

    # ========================================================================
    # 分镜生成接口
    # ========================================================================

    @app.post("/api/generate", response_model=TaskResponse, tags=["Storyboard"])
    async def generate_storyboard(
            request: ScriptRequest,
            background_tasks: BackgroundTasks
    ):
        """
        生成视频分镜（异步）

        提交剧本进行分镜生成，立即返回 task_id
        """
        try:
            language = Language.ZH if request.language == "zh" else Language.EN

            # 确定任务ID
            task_id = request.task_id

            if request.wait:
                # 同步模式
                result = penshot.breakdown_script(
                    script_text=request.script_text,
                    task_id=task_id,
                    language=language,
                    wait_timeout=request.timeout
                )

                return TaskResponse(
                    task_id=result.task_id,
                    status=result.status,
                    message="同步处理完成" if result.success else f"处理失败: {result.error}",
                    created_at=datetime.now(timezone.utc)
                )
            else:
                # 异步模式
                task_id = penshot.breakdown_script_async(
                    script_text=request.script_text,
                    task_id=task_id,
                    language=language
                )

                return TaskResponse(
                    task_id=task_id,
                    status=TaskStatus.PENDING,
                    message="任务已提交，请使用 /api/status/{task_id} 查询状态",
                    created_at=datetime.now(timezone.utc)
                )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

    @app.post("/api/generate/sync", response_model=TaskResultResponse, tags=["Storyboard"])
    async def generate_storyboard_sync(request: ScriptRequest):
        """
        生成视频分镜（同步）

        等待任务完成后返回结果
        """
        try:
            language = Language.ZH if request.language == "zh" else Language.EN

            result = penshot.breakdown_script(
                script_text=request.script_text,
                task_id=request.task_id,
                language=language,
                wait_timeout=request.timeout
            )

            return TaskResultResponse(
                task_id=result.task_id,
                success=result.success,
                status=result.status,
                data=result.data,
                error=result.error,
                processing_time_ms=result.processing_time_ms
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

    # ========================================================================
    # 批量处理接口
    # ========================================================================

    @app.post("/api/generate/batch", response_model=BatchTaskResponse, tags=["Storyboard"])
    async def batch_generate(
            request: ScriptBatchRequest,
            background_tasks: BackgroundTasks
    ):
        """
        批量生成视频分镜

        提交多个剧本进行批量处理
        """
        try:
            import uuid
            batch_id = request.batch_id or str(uuid.uuid4())
            language = Language.ZH if request.language == "zh" else Language.EN

            # 批量提交
            task_ids = []
            for script in request.scripts:
                task_id = penshot.breakdown_script_async(
                    script_text=script,
                    language=language
                )
                task_ids.append(task_id)

            return BatchTaskResponse(
                batch_id=batch_id,
                total_tasks=len(request.scripts),
                pending_tasks=len(request.scripts),
                processing_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                created_at=datetime.now(timezone.utc)
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"批量处理失败: {str(e)}")

    # ========================================================================
    # 任务管理接口
    # ========================================================================

    @app.get("/api/status/{task_id}", response_model=TaskStatusResponse, tags=["Task"])
    async def get_task_status(task_id: str):
        """
        获取任务状态

        - **task_id**: 任务ID
        """
        status = penshot.get_task_status(task_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        # 解析时间
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        if status.get("created_at"):
            try:
                created_at = datetime.fromisoformat(status["created_at"])
            except:
                pass

        if status.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(status["updated_at"])
            except:
                pass

        return TaskStatusResponse(
            task_id=task_id,
            status=status.get("status", "unknown"),
            stage=status.get("stage", "unknown"),
            progress=status.get("progress"),
            estimated_time_remaining=status.get("estimated_time_remaining"),
            created_at=created_at,
            updated_at=updated_at,
            error_message=status.get("error")
        )

    @app.get("/api/result/{task_id}", response_model=TaskResultResponse, tags=["Task"])
    async def get_task_result(task_id: str):
        """
        获取任务结果

        - **task_id**: 任务ID
        """
        result = penshot.get_task_result(task_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"任务不存在或未完成: {task_id}")

        return TaskResultResponse(
            task_id=result.task_id,
            success=result.success,
            status=result.status,
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms
        )

    @app.delete("/api/task/{task_id}", tags=["Task"])
    async def cancel_task(task_id: str):
        """
        取消任务

        - **task_id**: 任务ID
        """
        success = penshot.cancel_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"任务不存在或无法取消: {task_id}")

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "任务已取消"
        }

    # ========================================================================
    # 配置接口
    # ========================================================================

    @app.get("/api/config", tags=["Config"])
    async def get_default_config():
        """获取默认配置"""
        return {
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "supported_languages": ["zh", "en"]
        }

    @app.get("/api/languages", tags=["Config"])
    async def get_supported_languages():
        """获取支持的语言"""
        return {
            "languages": [
                {"code": "zh", "name": "中文"},
                {"code": "en", "name": "English"}
            ],
            "default": "zh"
        }

    return app


# ============================================================================
# 启动函数
# ============================================================================

def run_web_app(
        host: str = "0.0.0.0",
        port: int = 8000,
        reload: bool = False,
        config: Optional[ShotConfig] = None
):
    """
    启动 Web 应用

    Args:
        host: 监听地址
        port: 监听端口
        reload: 是否启用热重载
        config: 配置参数
    """
    import uvicorn

    app = create_web_app(config=config)

    print(f"\n{'=' * 60}")
    print(f"Penshot Web API Server")
    print(f"{'=' * 60}")
    print(f"服务地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    print(f"交互式文档: http://{host}:{port}/redoc")
    print(f"{'=' * 60}\n")

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload
    )


# ============================================================================
# 命令行入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Penshot Web API Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="启用热重载")

    args = parser.parse_args()

    run_web_app(host=args.host, port=args.port, reload=args.reload)
