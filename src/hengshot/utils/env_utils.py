"""
@FileName: env_utils.py
@Description: 环境工具模块，提供环境相关的辅助功能
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/08 - 2025/11
"""
import os

from hengshot.logger import error


def print_large_ascii():
    """
    打印大型ASCII艺术字
    """
    hengline_large = """
    ██╗  ██╗ ███████╗ ███╗   ██╗  ██████╗       ██╗      ██╗ ███╗   ██╗ ███████╗
    ██║  ██║ ██╔════╝ ████╗  ██║ ██╔════╝       ██║      ██║ ████╗  ██║ ██╔════╝
    ███████║ █████╗   ██╔██╗ ██║ ██║  ███╗      ██║      ██║ ██╔██╗ ██║ █████╗  
    ██╔══██║ ██╔══╝   ██║╚██╗██║ ██║   ██║      ██║      ██║ ██║╚██╗██║ ██╔══╝  
    ██║  ██║ ███████╗ ██║ ╚████║ ╚██████╔╝      ███████╗ ██║ ██║ ╚████║ ███████╗
    ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═══╝  ╚═════╝       ╚══════╝ ╚═╝ ╚═╝  ╚═══╝ ╚══════╝
    """

    ascii_art = """
    ============================================================================
    ||                                                                        ||
    ||             ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄         ||
    ||            ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌        ||
    ||            ▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀▀▀ ▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌        ||
    ||            ▐░▌       ▐░▌▐░▌          ▐░▌       ▐░▌▐░▌       ▐░▌        ||
    ||            ▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄▄▄ ▐░█▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌        ||
    ||            ▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌        ||
    ||            ▐░▌       ▐░▌▐░█▀▀▀▀▀▀▀▀▀ ▐░█▀▀▀▀▀▀▀█░▌▐░▌       ▐░▌        ||
    ||            ▐░▌       ▐░▌▐░▌          ▐░▌       ▐░▌▐░▌       ▐░▌        ||
    ||            ▐░█▄▄▄▄▄▄▄█░▌▐░█▄▄▄▄▄▄▄▄▄ ▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄█░▌        ||
    ||            ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌▐░░░░░░░░░░░▌        ||
    ||             ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀         ||
    ||                                                                        ||
    ============================================================================
    """
    print(hengline_large)
    print(ascii_art)


def ensure_directory(path: str) -> bool:
    """
    确保目录存在，如果不存在则创建
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        error(f"创建目录失败: {path}, 错误: {str(e)}")
        return False


def get_relative_path(absolute_path: str, base_path: str = None) -> str:
    """
    获取相对路径
    """
    try:
        if base_path is None:
            base_path = os.getcwd()
        return os.path.relpath(absolute_path, base_path)
    except Exception:
        return absolute_path


def is_path_valid(path: str) -> bool:
    """
    检查路径是否有效
    """
    try:
        # 检查路径字符是否有效
        os.path.normpath(path)
        return True
    except Exception:
        return False
