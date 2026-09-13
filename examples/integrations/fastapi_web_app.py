"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: fastapi_web_app.py
@Description: Web 应用集成示例：把 Penshot SDK 封装为 FastAPI 服务
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 10:00
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from penshot import ShotConfig, ShotLanguage
from penshot.api import create_penshot_agent

# 说明：
# - breakdown_script*/batch_breakdown 用 script_id 关联调用方 ID；task_id 由返回值提供。
# - 状态比较/展示一律取 .value（TaskStatus 是 str 枚举，成功为 "success"，没有 "completed"）。
# - 结果取数走 result.data["instructions"]。
# - 本文件自带的响应模型加了 Web 前缀，避免与 penshot 命名空间中的 TaskResponse 等冲突。


# ==================== 请求模型 ====================


class WebScriptRequest(BaseModel):
    """单个剧本请求。"""

    script_text: str = Field(..., description="剧本文本")
    script_id: Optional[str] = Field(None, description="调用方剧本关联 ID（可选）")
    language: str = Field("zh", description="输出语言 (zh/en)")
    wait: bool = Field(False, description="是否同步等待完成")
    timeout: float = Field(300, description="同步等待超时（秒）")


class WebBatchRequest(BaseModel):
    """批量剧本请求。"""

    scripts: List[str] = Field(..., min_length=1, description="剧本列表")
    batch_id: Optional[str] = Field(None, description="调用方批量关联 ID")
    language: str = Field("zh", description="输出语言")
    wait: bool = Field(True, description="是否同步等待全部完成")


# ==================== 响应模型 ====================


class WebTaskCreated(BaseModel):
    """提交任务响应。"""

    task_id: str
    status: str
    message: str
    created_at: datetime


class WebTaskStatus(BaseModel):
    """任务状态响应。"""

    task_id: str
    status: str
    stage: str
    stage_name: Optional[str] = None
    progress: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error: Optional[str] = None


class WebTaskResult(BaseModel):
    """任务结果响应。"""

    task_id: str
    success: bool
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WebBatchResult(BaseModel):
    """批量处理结果。"""

    batch_id: str
    total_tasks: int
    success_count: int
    failed_count: int
    details: List[Dict[str, Any]]


class WebHealth(BaseModel):
    """健康检查响应。"""

    status: str
    service: str
    timestamp: datetime


# ==================== 辅助函数 ====================


def _status_str(value: Any) -> str:
    """TaskStatus 枚举/字符串 → 字符串。"""
    return str(getattr(value, "value", value))


def _coerce_dt(value: Any) -> Optional[datetime]:
    """把 datetime / ISO 字符串 / None 统一为 datetime 或 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _public_config(config) -> Dict[str, Any]:
    """返回不包含密钥的安全配置子集。"""
    scalar = ["video_model", "audio_model", "max_fragment_duration", "min_fragment_duration",
              "duration_split_threshold", "max_total_loops", "enable_llm"]
    return {key: getattr(config, key, None) for key in scalar}


def create_web_app(config: Optional[ShotConfig] = None, enable_cors: bool = True) -> FastAPI:
    """创建封装 Penshot 的 FastAPI 应用。"""
    app = FastAPI(title="Penshot 分镜生成 API", version="0.1.0")
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    penshot = create_penshot_agent(config=config)

    @app.get("/", tags=["Health"])
    async def root():
        return {"service": "Penshot API", "version": "0.1.0", "docs": "/docs", "status": "running"}

    @app.get("/health", response_model=WebHealth, tags=["Health"])
    async def health_check():
        return WebHealth(status="healthy", service="penshot", timestamp=datetime.now(timezone.utc))

    @app.post("/api/generate", response_model=WebTaskCreated, tags=["Storyboard"])
    async def generate_storyboard(request: WebScriptRequest):
        """提交单个剧本；wait=False 立即返回，wait=True 同步等待完成后返回。"""
        language = ShotLanguage.ZH if request.language == "zh" else ShotLanguage.EN
        now = datetime.now(timezone.utc)
        try:
            if request.wait:
                result = penshot.breakdown_script(
                    script_text=request.script_text,
                    script_id=request.script_id,
                    language=language,
                    wait_timeout=request.timeout,
                )
                return WebTaskCreated(
                    task_id=result.task_id,
                    status=_status_str(result.status),
                    message="同步处理完成" if result.success else f"处理失败: {result.error}",
                    created_at=now,
                )
            task_id = penshot.breakdown_script_async(
                script_text=request.script_text,
                script_id=request.script_id,
                language=language,
            )
            return WebTaskCreated(
                task_id=task_id,
                status="pending",
                message="任务已提交，请使用 /api/status/{task_id} 查询状态",
                created_at=now,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"生成失败: {exc}") from exc

    @app.post("/api/generate/sync", response_model=WebTaskResult, tags=["Storyboard"])
    async def generate_storyboard_sync(request: WebScriptRequest):
        """同步分镜：等待任务完成后直接返回完整结果。"""
        language = ShotLanguage.ZH if request.language == "zh" else ShotLanguage.EN
        try:
            result = penshot.breakdown_script(
                script_text=request.script_text,
                script_id=request.script_id,
                language=language,
                wait_timeout=request.timeout,
            )
            return WebTaskResult(
                task_id=result.task_id,
                success=result.success,
                status=_status_str(result.status),
                data=result.data,
                error=result.error,
                processing_time_ms=result.processing_time_ms,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"生成失败: {exc}") from exc

    @app.post("/api/generate/batch", response_model=WebBatchResult, tags=["Storyboard"])
    async def batch_generate(request: WebBatchRequest):
        """批量分镜：wait=True 用 batch_breakdown 同步等待并统计结果。"""
        batch_id = request.batch_id or f"batch-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        language = ShotLanguage.ZH if request.language == "zh" else ShotLanguage.EN
        try:
            results = penshot.batch_breakdown(request.scripts, language=language, wait_timeout=600.0)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"批量处理失败: {exc}") from exc

        details = [
            {
                "task_id": r.task_id,
                "success": r.success,
                "status": _status_str(r.status),
                "error": r.error,
            }
            for r in results
        ]
        return WebBatchResult(
            batch_id=batch_id,
            total_tasks=len(results),
            success_count=sum(1 for r in results if r.success),
            failed_count=sum(1 for r in results if not r.success),
            details=details,
        )

    @app.get("/api/status/{task_id}", response_model=WebTaskStatus, tags=["Task"])
    async def get_task_status(task_id: str):
        """查询任务状态。"""
        status = penshot.get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return WebTaskStatus(
            task_id=task_id,
            status=_status_str(status.get("status")),
            stage=str(status.get("stage") or ""),
            stage_name=status.get("stage_name"),
            progress=status.get("progress"),
            created_at=_coerce_dt(status.get("created_at")),
            updated_at=_coerce_dt(status.get("updated_at")),
            error=status.get("error"),
        )

    @app.get("/api/result/{task_id}", response_model=WebTaskResult, tags=["Task"])
    async def get_task_result(task_id: str):
        """拉取任务结果。"""
        result = penshot.get_task_result(task_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"任务不存在或未完成: {task_id}")
        return WebTaskResult(
            task_id=result.task_id,
            success=result.success,
            status=_status_str(result.status),
            data=result.data,
            error=result.error,
            processing_time_ms=result.processing_time_ms,
            created_at=getattr(result, "created_at", None),
            completed_at=getattr(result, "completed_at", None),
        )

    @app.delete("/api/task/{task_id}", tags=["Task"])
    async def cancel_task(task_id: str):
        """取消任务。"""
        success = penshot.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"任务不存在或无法取消: {task_id}")
        return {"task_id": task_id, "status": "cancelled", "message": "任务已取消"}

    @app.get("/api/config", tags=["Config"])
    async def get_config():
        """返回脱敏的运行配置（不含任何密钥）。"""
        cfg = _public_config(penshot.config)
        cfg["language"] = str(getattr(penshot.language, "value", penshot.language))
        return cfg

    @app.get("/api/languages", tags=["Config"])
    async def get_languages():
        return {"languages": [{"code": "zh", "name": "中文"}, {"code": "en", "name": "English"}], "default": "zh"}

    return app


def run_web_app(host: str = "0.0.0.0", port: int = 8000, reload: bool = False,
                config: Optional[ShotConfig] = None) -> None:
    """启动 FastAPI 服务。"""
    import uvicorn

    uvicorn.run(create_web_app(config=config), host=host, port=port, reload=reload)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Penshot FastAPI 集成示例")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    run_web_app(host=args.host, port=args.port, reload=args.reload)
