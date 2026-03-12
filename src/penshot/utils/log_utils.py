"""
@FileName: log_utils.py
@Description: 日志工具模块，提供异常信息详细打印等功能
@Author: Haeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/08 - 2025/11
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path


def print_detailed_exception():
    """打印详细的异常信息"""
    exc_type, exc_value, exc_tb = sys.exc_info()

    print_log_exception()

    print("=" * 60)
    print("堆栈帧详情:")
    print("=" * 60)

    # 获取详细的堆栈信息
    tb_list = traceback.extract_tb(exc_tb)
    for i, frame in enumerate(tb_list):
        print(f"{i + 1}. 文件: {frame.filename}")
        print(f"   行号: {frame.lineno}")
        print(f"   函数: {frame.name}")
        print(f"   代码: {frame.line}")
        print(f"   ---")

    print("🟢" * 50 + "\n")


def print_log_exception():
    """打印详细的异常信息"""
    exc_type, exc_value, exc_tb = sys.exc_info()

    print("\n" + "🔴" * 20 + " 异常详情 " + "🔴" * 20)
    print(f"异常类型: {exc_type.__name__}")
    print(f"异常信息: {exc_value}")
    print(f"发生时间: {datetime.now()}")
    print("\n堆栈跟踪:")
    print("=" * 60)

    # 打印完整的堆栈跟踪
    traceback.print_exception(exc_type, exc_value, exc_tb)

    print("🟢" * 50 + "\n")


def _generate_dated_filename(base_name: str = "penshot", log_dir: Path = "logs") -> Path:
    """
    生成带日期的文件名

    Args:
        base_name: 基础文件名（如 'penshot'）
        log_dir: 日志目录

    Returns:
        带完整路径的日期文件名
    """
    date_str = datetime.now().strftime('%Y-%m-%d')
    return log_dir / f"{base_name}_{date_str}.log"