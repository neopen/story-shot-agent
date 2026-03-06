"""
@FileName: __init__.py
@Description: HengLine 包初始化文件
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10 - 2025/11
"""

# 定义对外暴露的接口
from hengshot.hengline.hengline_agent import generate_storyboard
# 导入主要模块
from hengshot.logger import (debug, info, warning, error, critical, log_with_context
, log_function_call, log_performance)

__all__ = [
    "debug",
    "info",
    "warning",
    "error",
    "critical",
    "log_with_context",
    "log_function_call",
    "log_performance",
    "generate_storyboard"
]

# 包版本
__version__ = "1.0.0"
