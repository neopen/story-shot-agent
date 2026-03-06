"""
@FileName: human_decision_models.py
@Description: 人工决策模型定义
@Author: HengLine
@Time: 2026/2/5 16:58
"""
from enum import Enum


class HumanDecisionType(str, Enum):
    """人工决策类型枚举

    说明：
    这个枚举定义了人工可以做出的决策类型，
    用于标准化人工输入，便于系统处理。
    """
    CONTINUE = "CONTINUE"  # 继续流程
    APPROVE = "APPROVE"  # 批准通过
    RETRY = "RETRY"  # 重试流程
    ADJUST = "ADJUST"  # 调整当前内容
    FIX = "FIX"  # 修复问题
    OPTIMIZE = "OPTIMIZE"  # 优化质量
    ESCALATE = "ESCALATE"  # 升级处理
    ABORT = "ABORT"  # 中止流程
