"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: __init__.py.py
@Description: Workflow package exports
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/9 20:53
"""

from .workflow_models import AgentStage, PipelineNode, PipelineState
from .workflow_state_types import (
    WorkflowState,
    InputState,
    DomainState,
    ExecutionState,
    ErrorState,
    ConfigState,
    OutputState,
)
from .workflow_nodes import WorkflowNodes
from .workflow_decision import PipelineDecision
from .workflow_orchestrator import WorkflowOrchestrator
from .workflow_pipeline import MultiAgentPipeline
from .workflow_error_handler import (
    WorkflowErrorHandler,
    ErrorHandlerMiddleware,
    WorkflowError,
    NetworkError,
    ValidationError,
    ConfigError,
    BusinessError,
    ErrorType,
    ErrorSeverity,
    ErrorAction,
)

__all__ = [
    # Models
    "AgentStage",
    "PipelineNode",
    "PipelineState",
    # State types
    "WorkflowState",
    "InputState",
    "DomainState",
    "ExecutionState",
    "ErrorState",
    "ConfigState",
    "OutputState",
    # Error handling
    "WorkflowErrorHandler",
    "ErrorHandlerMiddleware",
    "WorkflowError",
    "NetworkError",
    "ValidationError",
    "ConfigError",
    "BusinessError",
    "ErrorType",
    "ErrorSeverity",
    "ErrorAction",
    # Runtime classes
    "WorkflowNodes",
    "PipelineDecision",
    "WorkflowOrchestrator",
    "MultiAgentPipeline",
]