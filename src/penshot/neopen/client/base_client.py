"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: base_client.py
@Description: 
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:12
"""
import importlib.util
from abc import ABC, abstractmethod
from typing import Sequence, Tuple

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from penshot.logger import warning
from penshot.neopen.client.client_config import AIConfig


class BaseClient(ABC):
    def __init__(
            self,
            config: AIConfig
    ):
        self.llm_config = config.llm
        self.embed_config = config.embed

    @abstractmethod
    def check_package(self) -> bool:
        """ 检测 package 是否可用 """
        pass

    @abstractmethod
    def llm_model(self) -> BaseLanguageModel:
        """返回 LangChain 兼容的 LLM 实例"""
        pass

    @abstractmethod
    def llm_embed(self) -> Embeddings:
        """返回文本的 embedding 向量"""
        pass

    def _get_model_kwargs(self):
        """返回模型参数字典"""
        pass

    def _check_packages(self, requirements: Sequence[Tuple[str, str]]) -> bool:
        """
        检测所需依赖包是否已在当前环境安装

        使用 importlib.util.find_spec 探测，不会真正导入模块，
        避免加载 torch 等重型依赖。

        Args:
            requirements: (导入模块名, pip 安装名) 二元组序列

        Returns:
            全部已安装返回 True，否则记录缺失依赖并返回 False
        """
        missing = [
            pip_name
            for module_name, pip_name in requirements
            if importlib.util.find_spec(module_name) is None
        ]

        if missing:
            warning(
                f"{type(self).__name__} 缺少依赖: {', '.join(missing)}，"
                f"请执行 pip install {' '.join(missing)}"
            )
            return False

        return True

    def check_llm(self) -> bool:
        """ 检查 LLM 服务是否可用 """
        try:
            llm = self.llm_model()
            llm.invoke("Hello, world!")
            return True
        except Exception as e:
            print(f"LLM check failed: {e}")
            return False
