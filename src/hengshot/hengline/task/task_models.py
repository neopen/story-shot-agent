"""
@FileName: task_models.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 16:41
"""
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from hengshot.hengline.hengline_config import HengLineConfig
from hengshot.hengline.language_manage import Language


class ProcessRequest(BaseModel):
    """处理请求数据模型"""
    script: str = Field(..., min_length=1, description="原始剧本文本")
    config: Optional[HengLineConfig] = Field(
        default=HengLineConfig(),
        description="处理配置，如模型选择、风格偏好等"
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="回调URL，处理完成后通知（可选）"
    )
    task_id: Optional[str] = Field(
        default="HL" + str(datetime.now().strftime("%Y%m%d%H%M%S")) + str(random.randint(1000, 9999)),
        description="外部请求ID（可选）"
    )
    # 剧本语言，可选值："zh"（中文）、"en"（英文）
    language: str = Language.ZH.value


class ProcessingStatus(BaseModel):
    """处理状态响应模型"""
    task_id: str
    status: str  # pending, processing, completed, failed
    stage: Optional[str] = None  # 当前处理阶段
    progress: Optional[float] = Field(default=None, ge=0, le=100)  # 进度百分比
    estimated_time_remaining: Optional[int] = None  # 预估剩余时间（秒）
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class ProcessResult(BaseModel):
    """处理结果响应模型"""
    task_id: str
    status: str  # success, failed
    success: bool
    data: Optional[Dict[str, Any]] = None  # 处理结果数据
    message: Optional[str] = None
    processing_time_ms: Optional[int] = None  # 处理耗时（毫秒）
    created_at: datetime
    completed_at: Optional[datetime] = None


class BatchProcessRequest(BaseModel):
    """批量处理请求模型"""
    scripts: List[str] = Field(..., min_length=1, max_length=10, description="剧本列表")
    config: HengLineConfig = HengLineConfig()
    batch_id: Optional[str] = None


class BatchProcessResult(BaseModel):
    """批量处理结果模型"""
    batch_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    results: List[Dict[str, Any]] = []  # 各任务结果摘要
    created_at: datetime
