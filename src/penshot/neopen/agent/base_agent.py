"""
@FileName: base_agent.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/9 21:23
"""
from abc import ABC

from abc import abstractmethod
from typing import Optional, TypeVar

T = TypeVar('T')  # 输出类型泛型
K = TypeVar('K')  # 输出类型泛型


class BaseAgent(ABC):
    """
        智能体基类

        定义统一的接口，所有需要的智能体都应继承此类
        """

    @abstractmethod
    def process(self, *args, **kwargs) -> Optional[T]:
        """
        核心处理方法 - 子类必须实现

        注意：子类在实现时，应直接使用 self.current_repair_params 和
        self.current_historical_context，无需再通过参数传递

        Returns:
            处理结果
        """
        pass
