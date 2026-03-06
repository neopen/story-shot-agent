"""
@FileName: path_utils.py.py
@Description: 最可靠的路径获取方案
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/30 17:05
"""

import inspect
import os
from pathlib import Path
from typing import Optional, List


class PathResolver:
    """路径解析器 - 结合多种策略"""

    @staticmethod
    def get_project_root(strategies: Optional[List[str]] = None) -> Path:
        """
        使用多种策略获取项目根目录

        Args:
            strategies: 使用的策略顺序，可选值:
                - "env": 环境变量
                - "marker": 标记文件
                - "cwd": 当前工作目录
                - "caller": 调用者位置
        """
        if strategies is None:
            strategies = ["env", "marker", "caller", "cwd"]

        for strategy in strategies:
            if strategy == "env":
                root = PathResolver._from_env()
                if root:
                    return root

            elif strategy == "marker":
                root = PathResolver._from_marker_files()
                if root:
                    return root

            elif strategy == "caller":
                root = PathResolver._from_caller()
                if root:
                    return root

            elif strategy == "cwd":
                root = PathResolver._from_cwd()
                if root:
                    return root

        # 如果所有策略都失败，返回当前目录
        return Path.cwd()

    @staticmethod
    def _from_env(env_var: str = "PROJECT_ROOT") -> Optional[Path]:
        """从环境变量获取"""
        root_path = os.getenv(env_var)
        if root_path:
            path = Path(root_path).resolve()
            if path.exists():
                return path
        return None

    @staticmethod
    def _from_marker_files(start_path: Optional[Path] = None) -> Optional[Path]:
        """通过标记文件查找"""
        if start_path is None:
            start_path = Path.cwd()

        markers = ["pyproject.toml", "setup.py", ".git", "requirements.txt"]

        current = start_path.resolve()
        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    return current
            current = current.parent

        return None

    @staticmethod
    def _from_caller() -> Optional[Path]:
        """从调用者位置查找"""
        try:
            # 获取调用栈
            frame = inspect.currentframe()
            # 向上查找调用者
            while frame:
                # 获取frame的文件路径
                frame_file = frame.f_globals.get('__file__')
                if frame_file:
                    file_path = Path(frame_file).resolve()
                    # 从这个文件开始向上查找标记文件
                    root = PathResolver._from_marker_files(file_path.parent)
                    if root:
                        return root
                frame = frame.f_back
        except:
            pass

        return None

    @staticmethod
    def _from_cwd() -> Path:
        """从当前工作目录获取"""
        return Path.cwd().resolve()


if __name__ == '__main__':
    # 使用示例
    PROJECT_ROOT = PathResolver.get_project_root()
    DATA_DIR = PROJECT_ROOT / "data"
    LOGS_DIR = PROJECT_ROOT / "logs"

    # 或者指定策略顺序
    PROJECT_ROOT = PathResolver.get_project_root(["env", "marker"])
