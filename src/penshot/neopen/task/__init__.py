"""
@FileName: __init__.py.py
@Description: 
@Author: Haeng
@Time: 2026/3/6 22:34
"""
"""
Package exports for penshot.neopen.task
Expose API-friendly models and core classes for easier imports.
"""
from .task_models import (
    ProcessRequest,
    ProcessingStatus,
    ProcessResult,
    BatchProcessRequest,
    BatchProcessResult,
    CallbackPayload,
    APIResponse,
)

from .task_manager import TaskManager
from .task_processor import AsyncTaskProcessor
from .task_handler import CallbackHandler

__all__ = [
    # models
    "ProcessRequest",
    "ProcessingStatus",
    "ProcessResult",
    "BatchProcessRequest",
    "BatchProcessResult",
    "CallbackPayload",
    "APIResponse",
    # runtime classes
    "TaskManager",
    "AsyncTaskProcessor",
    "CallbackHandler",
]
