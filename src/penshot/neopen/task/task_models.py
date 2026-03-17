"""
@FileName: task_models.py
@Description: API-friendly request/response models for task processing
@Author: Haeng (adapted)
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/03/17
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator

from penshot.neopen.language_manage import Language
from penshot.neopen.shot_config import ShotConfig


def _generate_task_id() -> str:
    return "HL" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))


class ProcessRequest(BaseModel):
    """处理请求数据模型（用于 API 输入）

    Notes:
    - `config` 使用通用字典以保证可序列化并与内部 dataclass 互操作。
    - `task_id` 使用生成器作为默认值。
    """
    script: str = Field(..., min_length=1, description="原始剧本文本")
    config: Optional[ShotConfig] = Field(default_factory=dict, description="处理配置（序列化形式）")
    callback_url: Optional[str] = Field(default=None, description="回调URL，处理完成后通知（可选）")
    task_id: str = Field(default_factory=_generate_task_id, description="外部请求ID（可选）")
    language: str = Field(default=Language.ZH.value, description='剧本语言，例如 "zh" 或 "en"')

    @field_validator("language")
    def validate_language(cls, v):
        if v not in {Language.ZH.value, Language.EN.value}:
            raise ValueError("language must be one of: 'zh', 'en'")
        return v


class ProcessingStatus(BaseModel):
    """处理状态响应模型（用于轮询/状态接口）"""
    task_id: str
    status: str = Field(..., description="任务状态: pending | processing | completed | failed")
    stage: Optional[str] = Field(default=None, description="当前处理阶段")
    progress: Optional[float] = Field(default=None, ge=0, le=100, description="进度百分比")
    estimated_time_remaining: Optional[int] = Field(default=None, description="预估剩余时间（秒）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


class ProcessResult(BaseModel):
    """处理结果响应模型（用于回调和最终响应）"""
    task_id: str
    status: str = Field(..., description="success | failed")
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class BatchProcessRequest(BaseModel):
    """批量处理请求模型（API 输入）"""
    scripts: List[str] = Field(..., description="剧本列表")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    batch_id: Optional[str] = None

    @field_validator("scripts")
    def validate_scripts_length(cls, v):
        if not v or len(v) < 1:
            raise ValueError("scripts must contain at least 1 item")
        if len(v) > 50:
            raise ValueError("scripts contains too many items (max 50)")
        return v


class BatchProcessResult(BaseModel):
    """批量处理结果模型（API 输出）"""
    batch_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    results: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CallbackPayload(BaseModel):
    """回调通知的标准负载"""
    task_id: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class APIResponse(BaseModel):
    """统一的 API 响应包装"""
    success: bool
    code: int = 200
    message: Optional[str] = None
    data: Optional[Any] = None


# 兼容导出名（保持原文件中常用符号）
__all__ = [
    "ProcessRequest",
    "ProcessingStatus",
    "ProcessResult",
    "BatchProcessRequest",
    "BatchProcessResult",
    "CallbackPayload",
    "APIResponse",
]
