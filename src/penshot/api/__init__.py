"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: __init__.py.py
@Description: Penshot - 智能分镜视频生成
@Author: NeoPen
@Time: 2026/3/6 22:34
"""

"""
使用方式：

1. Python 智能体调用（Function Call）：
    from penshot import PenshotFunction
    agent = PenshotFunction()
    result = agent.breakdown_script("剧本内容")

2. MCP 协议调用：
    python -m penshot.mcp_server

3. REST API 调用：
    POST /api/storyboard
"""
# 版本号以顶层包 penshot.__version__ 为单一事实源（pyproject 动态版本也取自该属性）
from penshot import __version__
from penshot.api.function_calls import PenshotFunction, PenshotResult
from penshot.api.function_calls import create_penshot_agent

__author__ = "HiPeng"

__all__ = [
    "PenshotFunction",
    "PenshotResult",
    "create_penshot_agent",
]