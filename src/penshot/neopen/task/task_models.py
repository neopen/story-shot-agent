"""
@FileName: task_models.py
@Description: API-friendly request/response models for task processing
@Author: HiPeng (adapted)
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/03/17
"""
from __future__ import annotations

from dataclasses import field, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Callable

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务流程状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"

    def is_completed(self) -> bool:
        return self in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED)


@dataclass
class StageInfo:
    """阶段信息"""
    code: str
    name: str
    weight: int = 0  # 权重（用于计算进度）


class TaskStage(Enum):
    """任务处理阶段 - 详细阶段状态"""

    # 初始化
    INIT = StageInfo("init", "初始化", 0)

    # 剧本解析阶段
    PARSING_START = StageInfo("parsing_start", "开始解析剧本", 0)
    PARSING_SCRIPT = StageInfo("parsing_script", "解析剧本中", 10)
    PARSING_COMPLETE = StageInfo("parsing_complete", "剧本解析完成", 15)

    # 镜头拆分阶段
    SEGMENT_START = StageInfo("segment_start", "开始拆分镜头", 15)
    SEGMENTING = StageInfo("segmenting", "拆分镜头中", 25)
    SEGMENT_COMPLETE = StageInfo("segment_complete", "镜头拆分完成", 30)

    # 视频分割阶段
    SPLIT_START = StageInfo("split_start", "开始视频分段", 30)
    SPLITTING = StageInfo("splitting", "视频分段中", 45)
    SPLIT_COMPLETE = StageInfo("split_complete", "视频分段完成", 50)

    # 提示词转换阶段
    CONVERT_START = StageInfo("convert_start", "开始转换提示词", 50)
    CONVERTING = StageInfo("converting", "转换提示词中", 65)
    CONVERT_COMPLETE = StageInfo("convert_complete", "提示词转换完成", 70)

    # 质量审查阶段
    AUDIT_START = StageInfo("audit_start", "开始质量审查", 70)
    AUDITING = StageInfo("auditing", "质量审查中", 80)
    AUDIT_COMPLETE = StageInfo("audit_complete", "质量审查完成", 85)

    # 连续性检查阶段
    CONTINUITY_START = StageInfo("continuity_start", "开始连续性检查", 85)
    CONTINUITY_CHECKING = StageInfo("continuity_checking", "连续性检查中", 92)
    CONTINUITY_COMPLETE = StageInfo("continuity_complete", "连续性检查完成", 95)

    # 输出阶段
    OUTPUT_START = StageInfo("output_start", "开始生成输出", 95)
    OUTPUT_GENERATING = StageInfo("output_generating", "生成输出中", 98)
    COMPLETE = StageInfo("complete", "处理完成", 100)

    # 错误处理
    ERROR_HANDLING = StageInfo("error_handling", "错误处理中", 0)

    @property
    def code(self) -> str:
        """获取阶段代码"""
        return self.value.code

    @property
    def name(self) -> str:
        """获取阶段中文名称"""
        return self.value.name

    @property
    def weight(self) -> int:
        """获取阶段权重"""
        return self.value.weight

    @classmethod
    def from_code(cls, code: str) -> Optional['TaskStage']:
        """根据代码获取阶段"""
        for stage in cls:
            if stage.code == code:
                return stage
        return None

    def __str__(self) -> str:
        return self.name


class StageProgress(BaseModel):
    """阶段进度信息"""
    stage: TaskStage = Field(..., description="当前阶段")
    name: str = Field(..., description="阶段名称")
    progress: float = Field(default=0.0, ge=0, le=100, description="该阶段进度百分比")
    status: str = Field(default="pending", description="阶段状态: pending/processing/completed/failed")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = Field(default=None, description="阶段详细信息")


class TaskProgress(BaseModel):
    """任务进度详情"""
    task_id: str
    status: TaskStatus
    current_stage: TaskStage
    stage_name: str
    overall_progress: float = Field(default=0.0, description="整体进度百分比")
    stages: Dict[str, StageProgress] = Field(default_factory=dict, description="各阶段进度")
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4



class QueuedTask:
    """队列中的任务"""

    def __init__(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            callback: Optional[Callable] = None,
            metadata: Optional[Dict] = None
    ):
        self.task_id = task_id
        self.priority = priority
        self.callback = callback
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.enqueued_at = None
        self.started_at = None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "priority": self.priority.value,
            "priority_name": self.priority.name,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "enqueued_at": self.enqueued_at.isoformat() if self.enqueued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None
        }


class ProcessingStatus(BaseModel):
    """处理状态响应模型（用于轮询/状态接口）"""
    task_id: str
    status: TaskStatus = Field(..., description="任务状态")
    stage: Optional[str] = Field(default=None, description="当前处理阶段（兼容旧版）")
    stage_name: Optional[str] = Field(default=None, description="阶段名称")
    progress: Optional[float] = Field(default=None, ge=0, le=100, description="进度百分比")
    estimated_time_remaining: Optional[int] = Field(default=None, description="预估剩余时间（秒）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None

    # 新增详细进度字段
    current_stage: Optional[str] = None
    stages_progress: Optional[Dict[str, Any]] = Field(default=None, description="各阶段进度详情")


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


# 兼容导出名
__all__ = [
    "ProcessingStatus",
    "BatchTaskResponse",
    "TaskResponse",
    "CallbackPayload",
    "APIResponse",
    "TaskStatus",
    "TaskStage",
    "StageProgress",
    "TaskProgress",
]