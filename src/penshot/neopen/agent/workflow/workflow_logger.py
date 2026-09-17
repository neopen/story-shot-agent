"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: workflow_logger.py
@Description: 统一日志格式工具 - 定义工作流的结构化日志规范
@Author: NeoPen
@Time: 2026/4/29
"""

import json
import time
from typing import Dict, Any, Optional, Union
from enum import Enum

from penshot.logger import logger as base_logger, warning, info, error


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogType(Enum):
    """日志类型枚举"""
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    NODE_ENTER = "node_enter"
    NODE_EXIT = "node_exit"
    DECISION = "decision"
    ERROR = "error"
    RETRY = "retry"
    HUMAN_INTERVENTION = "human_intervention"
    PERFORMANCE = "performance"
    METRIC = "metric"


class WorkflowLogger:
    """统一工作流日志记录器"""

    def __init__(self, task_id: Optional[str] = None, script_id: Optional[str] = None):
        """
        初始化日志记录器
        
        Args:
            task_id: 任务ID
            script_id: 剧本ID
        """
        self.task_id = task_id
        self.script_id = script_id
        self._start_time = time.time()
        self._node_start_times = {}

    def _create_log_entry(self, log_type: LogType, level: LogLevel,
                          message: str, **kwargs) -> Dict[str, Any]:
        """
        创建结构化日志条目
        
        Args:
            log_type: 日志类型
            level: 日志级别
            message: 日志消息
            **kwargs: 额外的日志字段
        
        Returns:
            结构化日志字典
        """
        entry = {
            "timestamp": time.time(),
            "timestamp_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "log_type": log_type.value,
            "level": level.value,
            "message": message,
            "task_id": self.task_id,
            "script_id": self.script_id,
        }

        # 添加额外字段
        entry.update(kwargs)

        return entry

    def _log(self, level: LogLevel, entry: Dict[str, Any]):
        """输出日志"""
        log_message = json.dumps(entry, ensure_ascii=False)

        if level == LogLevel.DEBUG:
            base_logger.debug(log_message)
        elif level == LogLevel.INFO:
            base_logger.info(log_message)
        elif level == LogLevel.WARNING:
            base_logger.warning(log_message)
        elif level == LogLevel.ERROR:
            base_logger.error(log_message)
        elif level == LogLevel.CRITICAL:
            base_logger.critical(log_message)

    def log_workflow_start(self, initial_state: Dict = None):
        """记录工作流开始"""
        entry = self._create_log_entry(
            LogType.WORKFLOW_START,
            LogLevel.INFO,
            "工作流开始执行",
            initial_state=initial_state,
            start_time=self._start_time
        )
        self._log(LogLevel.INFO, entry)

    def log_workflow_end(self, success: bool, duration: float, result: Dict = None):
        """记录工作流结束"""
        entry = self._create_log_entry(
            LogType.WORKFLOW_END,
            LogLevel.INFO,
            "工作流执行完成" if success else "工作流执行失败",
            success=success,
            duration=duration,
            result=result
        )
        self._log(LogLevel.INFO, entry)

    def log_node_enter(self, node_name: str, state: Dict = None):
        """记录进入节点"""
        self._node_start_times[node_name] = time.time()

        entry = self._create_log_entry(
            LogType.NODE_ENTER,
            LogLevel.DEBUG,
            f"进入节点: {node_name}",
            node_name=node_name,
            state=state
        )
        self._log(LogLevel.DEBUG, entry)

    def log_node_exit(self, node_name: str, success: bool = True, result: Dict = None, error: str = None):
        """记录离开节点"""
        duration = time.time() - self._node_start_times.get(node_name, time.time())

        entry = self._create_log_entry(
            LogType.NODE_EXIT,
            LogLevel.DEBUG if success else LogLevel.WARNING,
            f"离开节点: {node_name}",
            node_name=node_name,
            success=success,
            duration=duration,
            result=result,
            error=error
        )
        self._log(LogLevel.DEBUG if success else LogLevel.WARNING, entry)

    def log_decision(self, node_name: str, decision: str, reason: str = None):
        """记录决策"""
        entry = self._create_log_entry(
            LogType.DECISION,
            LogLevel.INFO,
            f"决策: {decision}",
            node_name=node_name,
            decision=decision,
            reason=reason
        )
        self._log(LogLevel.INFO, entry)

    def log_error(self, node_name: str, error: Union[str, Exception],
                  error_type: str = "unknown", severity: str = "medium"):
        """记录错误"""
        error_message = str(error)
        if isinstance(error, Exception):
            error_message = f"{type(error).__name__}: {str(error)}"

        entry = self._create_log_entry(
            LogType.ERROR,
            LogLevel.ERROR,
            f"错误: {error_message}",
            node_name=node_name,
            error_type=error_type,
            severity=severity,
            error_message=error_message
        )
        self._log(LogLevel.ERROR, entry)

    def log_retry(self, node_name: str, retry_count: int, max_retries: int, reason: str = None):
        """记录重试"""
        entry = self._create_log_entry(
            LogType.RETRY,
            LogLevel.WARNING,
            f"重试: {node_name} (第 {retry_count}/{max_retries} 次)",
            node_name=node_name,
            retry_count=retry_count,
            max_retries=max_retries,
            reason=reason
        )
        self._log(LogLevel.WARNING, entry)

    def log_human_intervention(self, node_name: str, reason: str = None):
        """记录人工干预"""
        entry = self._create_log_entry(
            LogType.HUMAN_INTERVENTION,
            LogLevel.WARNING,
            f"需要人工干预: {node_name}",
            node_name=node_name,
            reason=reason
        )
        self._log(LogLevel.WARNING, entry)

    def log_performance(self, operation: str, duration: float, details: Dict = None):
        """记录性能指标"""
        entry = self._create_log_entry(
            LogType.PERFORMANCE,
            LogLevel.INFO,
            f"性能: {operation} 耗时 {duration:.2f}s",
            operation=operation,
            duration=duration,
            details=details
        )
        self._log(LogLevel.INFO, entry)

    def log_metric(self, name: str, value: Union[int, float], unit: str = None, labels: Dict = None):
        """记录指标"""
        entry = self._create_log_entry(
            LogType.METRIC,
            LogLevel.DEBUG,
            f"指标: {name} = {value}{unit if unit else ''}",
            metric_name=name,
            metric_value=value,
            metric_unit=unit,
            labels=labels
        )
        self._log(LogLevel.DEBUG, entry)

    def debug(self, message: str, **kwargs):
        """记录调试日志"""
        entry = self._create_log_entry(
            LogType.METRIC,
            LogLevel.DEBUG,
            message,
            **kwargs
        )
        self._log(LogLevel.DEBUG, entry)

    def info(self, message: str, **kwargs):
        """记录信息日志"""
        entry = self._create_log_entry(
            LogType.METRIC,
            LogLevel.INFO,
            message,
            **kwargs
        )
        self._log(LogLevel.INFO, entry)

    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        entry = self._create_log_entry(
            LogType.METRIC,
            LogLevel.WARNING,
            message,
            **kwargs
        )
        self._log(LogLevel.WARNING, entry)

    def error(self, message: str, **kwargs):
        """记录错误日志"""
        entry = self._create_log_entry(
            LogType.ERROR,
            LogLevel.ERROR,
            message,
            **kwargs
        )
        self._log(LogLevel.ERROR, entry)


class WorkflowLogFormatter:
    """日志格式化工具"""

    @staticmethod
    def format_node_execution(node_name: str, start_time: float, end_time: float,
                              success: bool, error: str = None) -> Dict[str, Any]:
        """格式化节点执行日志"""
        return {
            "node": node_name,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "success": success,
            "error": error
        }

    @staticmethod
    def format_workflow_summary(task_id: str, script_id: str, start_time: float,
                                end_time: float, success: bool, error: str = None) -> Dict[str, Any]:
        """格式化工作流摘要日志"""
        return {
            "task_id": task_id,
            "script_id": script_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "success": success,
            "error": error
        }

    @staticmethod
    def format_decision(node_name: str, decision: str, reason: str = None) -> Dict[str, Any]:
        """格式化决策日志"""
        return {
            "node": node_name,
            "decision": decision,
            "reason": reason
        }


# 警告聚合器
class WarningAggregator:
    """警告聚合器，避免重复警告"""

    def __init__(self):
        self._warning_counts: Dict[str, int] = {}
        self._last_warning_time: Dict[str, float] = {}
        self._cooldown_seconds = 60  # 相同警告60秒内只记录一次

    def warn_once(self, key: str, message: str, logger_func,
                  force: bool = False, **kwargs):
        """只警告一次，或冷却期内不重复警告"""
        current_time = time.time()

        if force:
            logger_func(message, **kwargs)
            return

        # 检查冷却期
        if key in self._last_warning_time:
            if current_time - self._last_warning_time[key] < self._cooldown_seconds:
                # 计数但不输出
                self._warning_counts[key] = self._warning_counts.get(key, 0) + 1
                return

        # 输出警告
        if key in self._warning_counts:
            message = f"{message} (之前已忽略 {self._warning_counts[key]} 次)"
            self._warning_counts[key] = 0

        logger_func(message, **kwargs)
        self._last_warning_time[key] = current_time


# 全局警告聚合器
_warning_aggregator = WarningAggregator()
# 全局日志记录器实例
_global_logger = WorkflowLogger()


def warn_once(key: str, message: str, level: LogLevel = LogLevel.WARNING, **kwargs):
    """全局警告一次函数"""
    if level == LogLevel.WARNING:
        _warning_aggregator.warn_once(key, message, warning, **kwargs)
    elif level == LogLevel.INFO:
        _warning_aggregator.warn_once(key, message, info, **kwargs)
    elif level == LogLevel.ERROR:
        _warning_aggregator.warn_once(key, message, error, **kwargs)


def get_workflow_logger(task_id: Optional[str] = None, script_id: Optional[str] = None) -> WorkflowLogger:
    """
    获取工作流日志记录器
    
    Args:
        task_id: 任务ID（可选）
        script_id: 剧本ID（可选）
    
    Returns:
        工作流日志记录器
    """
    if task_id or script_id:
        return WorkflowLogger(task_id, script_id)
    return _global_logger
