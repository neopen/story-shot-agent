"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: workflow_error_handler.py
@Description: 统一错误处理服务 - 集中管理工作流中的错误处理逻辑
@Author: NeoPen
@Time: 2026/4/29
"""

import asyncio
import time
from enum import Enum
from typing import Dict, Any, Optional, Callable

from penshot.logger import warning, info, debug, error
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_state_types import ErrorState, ExecutionState


class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    CONFIG = "config"
    BUSINESS = "business"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorAction(Enum):
    """错误处理动作枚举"""
    RETRY = "retry"
    DELAY_RETRY = "delay_retry"
    REPAIR = "repair"
    HUMAN = "human"
    ABORT = "abort"
    IGNORE = "ignore"


class WorkflowError(Exception):
    """工作流错误基类"""

    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN,
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, source: Optional[PipelineNode] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.source = source
        self.timestamp = time.time()


class NetworkError(WorkflowError):
    """网络错误"""

    def __init__(self, message: str, source: Optional[PipelineNode] = None):
        super().__init__(message, ErrorType.NETWORK, ErrorSeverity.HIGH, source)


class ValidationError(WorkflowError):
    """验证错误"""

    def __init__(self, message: str, source: Optional[PipelineNode] = None):
        super().__init__(message, ErrorType.VALIDATION, ErrorSeverity.MEDIUM, source)


class ConfigError(WorkflowError):
    """配置错误"""

    def __init__(self, message: str, source: Optional[PipelineNode] = None):
        super().__init__(message, ErrorType.CONFIG, ErrorSeverity.CRITICAL, source)


class BusinessError(WorkflowError):
    """业务逻辑错误"""

    def __init__(self, message: str, source: Optional[PipelineNode] = None):
        super().__init__(message, ErrorType.BUSINESS, ErrorSeverity.MEDIUM, source)


class WorkflowErrorHandler:
    """统一错误处理服务"""

    def __init__(self, max_retries: int = 3, max_delay: int = 60):
        """
        初始化错误处理器
        
        Args:
            max_retries: 最大重试次数
            max_delay: 最大延迟时间（秒）
        """
        self.max_retries = max_retries
        self.max_delay = max_delay
        self._error_handlers: Dict[ErrorType, Callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """注册默认错误处理器"""
        self._error_handlers[ErrorType.NETWORK] = self._handle_network_error
        self._error_handlers[ErrorType.TIMEOUT] = self._handle_timeout_error
        self._error_handlers[ErrorType.RATE_LIMIT] = self._handle_rate_limit_error
        self._error_handlers[ErrorType.VALIDATION] = self._handle_validation_error
        self._error_handlers[ErrorType.CONFIG] = self._handle_config_error
        self._error_handlers[ErrorType.BUSINESS] = self._handle_business_error
        self._error_handlers[ErrorType.UNKNOWN] = self._handle_unknown_error

    def register_handler(self, error_type: ErrorType, handler: Callable):
        """
        注册自定义错误处理器
        
        Args:
            error_type: 错误类型
            handler: 处理函数
        """
        self._error_handlers[error_type] = handler
        info(f"注册自定义错误处理器: {error_type.value}")

    def classify_error(self, exception: Exception, source: Optional[PipelineNode] = None) -> WorkflowError:
        """
        分类错误
        
        Args:
            exception: 异常对象
            source: 错误来源节点
        
        Returns:
            分类后的工作流错误
        """
        message = str(exception)
        message_lower = message.lower()

        # 网络错误
        if any(keyword in message_lower for keyword in ['timeout', 'connection', 'network', 'socket', 'http', 'request failed']):
            return NetworkError(message, source)

        # 限流错误
        if any(keyword in message_lower for keyword in ['rate limit', 'too many requests', '429', 'quota']):
            return WorkflowError(message, ErrorType.RATE_LIMIT, ErrorSeverity.HIGH, source)

        # 验证错误
        if any(keyword in message_lower for keyword in ['invalid', 'validation', 'not valid', 'wrong format']):
            return ValidationError(message, source)

        # 配置错误
        if any(keyword in message_lower for keyword in ['config', 'configuration', 'setting']):
            return ConfigError(message, source)

        # 超时错误
        if 'timeout' in message_lower:
            return WorkflowError(message, ErrorType.TIMEOUT, ErrorSeverity.HIGH, source)

        # 默认：业务错误
        return BusinessError(message, source)

    def determine_action(self, error: WorkflowError, execution_state: ExecutionState) -> ErrorAction:
        """
        根据错误类型和执行状态决定处理动作

        Args:
            error: 工作流错误
            execution_state: 执行状态

        Returns:
            错误处理动作
        """
        source = error.source

        # 检查是否可以重试
        if not execution_state.can_retry_stage(source):
            warning(f"无法重试，阶段 {source} 已达最大重试次数")
            return ErrorAction.HUMAN

        # 根据错误类型决定动作
        action_map = {
            ErrorType.NETWORK: ErrorAction.DELAY_RETRY,
            ErrorType.TIMEOUT: ErrorAction.DELAY_RETRY,
            ErrorType.RATE_LIMIT: ErrorAction.DELAY_RETRY,
            ErrorType.VALIDATION: ErrorAction.REPAIR,
            ErrorType.CONFIG: ErrorAction.HUMAN,
            ErrorType.BUSINESS: ErrorAction.RETRY,
            ErrorType.UNKNOWN: ErrorAction.RETRY,
        }

        return action_map.get(error.error_type, ErrorAction.RETRY)

    def handle_error(self, exception: Exception, source: Optional[PipelineNode],
                     error_state: ErrorState, execution_state: ExecutionState) -> ErrorAction:
        """
        处理错误的主入口

        Args:
            exception: 异常对象
            source: 错误来源节点
            error_state: 错误状态
            execution_state: 执行状态

        Returns:
            错误处理动作
        """
        # 分类错误
        workflow_error = self.classify_error(exception, source)

        # 记录错误
        error_state.add_error(workflow_error.message, source)

        # 记录日志
        self._log_error(workflow_error)

        # 确定处理动作
        action = self.determine_action(workflow_error, execution_state)

        # 执行处理
        self._execute_action(action, workflow_error, execution_state)

        return action

    def _log_error(self, error: WorkflowError):
        """记录错误日志"""
        log_func = {
            ErrorSeverity.LOW: debug,
            ErrorSeverity.MEDIUM: warning,
            ErrorSeverity.HIGH: error,
            ErrorSeverity.CRITICAL: error,
        }.get(error.severity, warning)

        source_info = f", 来源: {error.source.value}" if error.source else ""
        log_func(f"工作流错误 [{error.error_type.value}] [{error.severity.value}]: {error.message}{source_info}")

    def _execute_action(self, action: ErrorAction, error: WorkflowError, execution_state: ExecutionState):
        """执行错误处理动作"""
        if action == ErrorAction.DELAY_RETRY:
            delay = self._calculate_delay(execution_state)
            info(f"执行延迟重试，延迟 {delay} 秒")
            self._execute_delay(delay)
            execution_state.increment_stage_retry(error.source)

        elif action == ErrorAction.RETRY:
            info(f"执行重试")
            execution_state.increment_stage_retry(error.source)

        elif action == ErrorAction.REPAIR:
            info(f"标记需要修复")
            execution_state.recovery_flags['need_repair'] = True
            execution_state.recovery_flags['repair_type'] = "validation"

        elif action == ErrorAction.HUMAN:
            info(f"标记需要人工干预")
            execution_state.needs_human_review = True

        elif action == ErrorAction.ABORT:
            info(f"中止流程")
            execution_state.should_abort = True

    def _calculate_delay(self, execution_state: ExecutionState) -> float:
        """计算延迟时间（指数退避）"""
        if execution_state.source:
            retry_count = execution_state.stage_current_retries.get(execution_state.source, 0)
        else:
            retry_count = execution_state.total_retries

        base_delay = 2 ** retry_count  # 指数退避
        return min(base_delay, self.max_delay)

    def _execute_delay(self, delay_seconds: float):
        """执行延迟"""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                info("事件循环已关闭，跳过延迟")
                return
            # 使用同步延迟（在工作流上下文中更安全）
            time.sleep(delay_seconds)
        except RuntimeError:
            # 不在事件循环中，使用同步延迟
            time.sleep(delay_seconds)

    def _handle_network_error(self, error: WorkflowError):
        """处理网络错误"""
        warning(f"网络错误，将尝试重试: {error.message}")

    def _handle_timeout_error(self, error: WorkflowError):
        """处理超时错误"""
        warning(f"超时错误，将延迟后重试: {error.message}")

    def _handle_rate_limit_error(self, error: WorkflowError):
        """处理限流错误"""
        warning(f"限流错误，需要等待: {error.message}")

    def _handle_validation_error(self, error: WorkflowError):
        """处理验证错误"""
        warning(f"验证错误，需要修复: {error.message}")

    def _handle_config_error(self, workflow_error: WorkflowError):
        """处理配置错误"""
        error(f"配置错误，需要人工干预: {workflow_error.message}")

    def _handle_business_error(self, error: WorkflowError):
        """处理业务错误"""
        warning(f"业务错误: {error.message}")

    def _handle_unknown_error(self, error: WorkflowError):
        """处理未知错误"""
        warning(f"未知错误: {error.message}")

    def get_retry_node(self, source: Optional[PipelineNode]) -> PipelineNode:
        """
        根据错误来源获取重试节点
        
        Args:
            source: 错误来源节点
        
        Returns:
            应该重试的节点
        """
        retry_mapping = {
            PipelineNode.PARSE_SCRIPT: PipelineNode.PARSE_SCRIPT,
            PipelineNode.SEGMENT_SHOT: PipelineNode.SEGMENT_SHOT,
            PipelineNode.SPLIT_VIDEO: PipelineNode.SPLIT_VIDEO,
            PipelineNode.CONVERT_PROMPT: PipelineNode.CONVERT_PROMPT,
            PipelineNode.AUDIT_QUALITY: PipelineNode.CONVERT_PROMPT,
            PipelineNode.CONTINUITY_CHECK: PipelineNode.CONVERT_PROMPT,
            PipelineNode.LOOP_CHECK: PipelineNode.PARSE_SCRIPT,
        }

        return retry_mapping.get(source, PipelineNode.PARSE_SCRIPT)

    def format_error_report(self, error_state: ErrorState) -> Dict[str, Any]:
        """
        格式化错误报告
        
        Args:
            error_state: 错误状态
        
        Returns:
            格式化的错误报告
        """
        return {
            "error_count": len(error_state.error_messages),
            "errors": error_state.error_messages,
            "last_error": error_state.error,
            "error_source": error_state.error_source.value if error_state.error_source else None,
            "last_error_timestamp": error_state.last_error_timestamp,
            "handling_history": error_state.error_handling_history,
        }


class ErrorHandlerMiddleware:
    """错误处理中间件 - 用于工作流节点的错误处理"""

    def __init__(self, error_handler: WorkflowErrorHandler):
        self.error_handler = error_handler

    def wrap_node(self, node_func: Callable) -> Callable:
        """
        包装工作流节点函数，添加错误处理
        
        Args:
            node_func: 节点函数
            
        Returns:
            包装后的节点函数
        """

        def wrapper(state):
            try:
                return node_func(state)
            except Exception as e:
                # 处理错误
                error_state = state.errors if hasattr(state, 'errors') else None
                execution_state = state.execution if hasattr(state, 'execution') else None

                if error_state and execution_state:
                    action = self.error_handler.handle_error(
                        e,
                        state.current_node if hasattr(state, 'current_node') else None,
                        error_state,
                        execution_state
                    )

                    # 根据处理动作设置状态
                    if action == ErrorAction.HUMAN:
                        state.execution.needs_human_review = True
                    elif action == ErrorAction.ABORT:
                        state.execution.should_abort = True

                # 重新抛出异常让工作流处理
                raise

        return wrapper

    async def wrap_node_async(self, node_func: Callable) -> Callable:
        """
        异步包装工作流节点函数
        
        Args:
            node_func: 异步节点函数
            
        Returns:
            包装后的异步节点函数
        """

        async def wrapper(state):
            try:
                return await node_func(state)
            except Exception as e:
                error_state = state.errors if hasattr(state, 'errors') else None
                execution_state = state.execution if hasattr(state, 'execution') else None

                if error_state and execution_state:
                    self.error_handler.handle_error(
                        e,
                        state.current_node if hasattr(state, 'current_node') else None,
                        error_state,
                        execution_state
                    )

                raise

        return wrapper
