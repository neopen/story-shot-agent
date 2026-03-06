"""
@FileName: base_client.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/10 23:12
"""
from abc import ABC, abstractmethod

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from hengshot.hengline.client.client_config import AIConfig


class BaseClient(ABC):
    def __init__(
            self,
            config: AIConfig
    ):
        self.config = config

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

    def check_llm(self) -> bool:
        """ 检查 LLM 服务是否可用 """
        try:
            llm = self.llm_model()
            llm.invoke("Hello, world!")
            return True
        except Exception as e:
            print(f"LLM check failed: {e}")
            return False
