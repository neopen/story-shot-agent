"""
@FileName: task_models.py
@Description: API-friendly request/response models for task processing
@Author: HiPeng (adapted)
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/03/17
"""
from __future__ import annotations

from dataclasses import field, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """ task流程状态 """
    PENDING = "pending"
    PROCESSING = "processing"
    # COMPLETED = "completed"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"

    def is_completed(self) -> bool:
        return self in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED)


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class ProcessingStatus(BaseModel):
    """处理状态响应模型（用于轮询/状态接口）"""
    task_id: str
    status: TaskStatus = Field(..., description="任务状态: pending | processing | completed | failed")
    stage: Optional[str] = Field(default=None, description="当前处理阶段")
    progress: Optional[float] = Field(default=None, ge=0, le=100, description="进度百分比")
    estimated_time_remaining: Optional[int] = Field(default=None, description="预估剩余时间（秒）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


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


@dataclass
class TaskResponse:
    """任务响应数据类"""
    task_id: str
    success: bool
    status: TaskStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "status": self.status.value if hasattr(self.status, 'value') else self.status,
            "data": self.data,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


@dataclass
class BatchTaskResponse:
    """批量任务响应数据类"""
    batch_id: str
    total_tasks: int
    task_ids: List[str]
    status: TaskStatus
    results: List[TaskResponse] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_tasks": self.total_tasks,
            "task_ids": self.task_ids,
            "status": self.status.value if hasattr(self.status, 'value') else self.status,
            "results": [r.to_dict() for r in self.results],
            "created_at": self.created_at.isoformat()
        }


# 兼容导出名（保持原文件中常用符号）
__all__ = [
    "ProcessingStatus",
    "BatchTaskResponse",
    "TaskResponse",
    "CallbackPayload",
    "APIResponse",
]
