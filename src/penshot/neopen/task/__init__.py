"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: __init__.py.py
@Description: 
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/3/6 22:34
"""
"""
Package exports for penshot.neopen.task
Expose API-friendly models and core classes for easier imports.
"""
from .task_models import (
    ProcessingStatus,
    CallbackPayload,
    APIResponse, BatchTaskResponse, TaskResponse, TaskStatus,
)

from .task_manager import TaskManager
from .task_lifecycle_service import TaskLifecycleService
from .task_processor import AsyncTaskProcessor
from .task_handler import CallbackHandler
from .task_repository import TaskRepository
from .workflow_registry import WorkflowRegistry

__all__ = [
    # models
    "ProcessingStatus",
    "TaskResponse",
    "BatchTaskResponse",
    "CallbackPayload",
    "APIResponse",
    "TaskStatus",
    # runtime classes
    "TaskManager",
    "TaskLifecycleService",
    "TaskRepository",
    "AsyncTaskProcessor",
    "CallbackHandler",
    "WorkflowRegistry",
]
