"""
@FileName: qwen_client.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/10 23:13
"""
import os

from langchain_community.chat_models import ChatTongyi  # Qwen via Tongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig


class QwenClient(BaseClient):
    """Qwen LLM 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        os.environ["DASHSCOPE_API_KEY"] = self.llm_config.api_key.get_secret_value()

    def llm_model(self) -> BaseLanguageModel:
        return ChatTongyi(
            model=self.llm_config.model_name,
            model_kwargs=self._get_model_kwargs(),
            api_key=self.llm_config.api_key,
            max_retries=self.llm_config.max_retries,
            streaming=False,
        )

    def llm_embed(self) -> Embeddings:
        return DashScopeEmbeddings(
            model=self.embed_config.model_name,
            max_retries=self.embed_config.max_retries,
            dashscope_api_key=self.embed_config.api_key.get_secret_value()
        )

    def _get_model_kwargs(self):
        """返回模型参数字典"""
        model_kwargs = {
            "temperature": self.llm_config.temperature,
            "timeout": self.llm_config.timeout,
            # "top_p": config.top_p,
            # "presence_penalty": config.presence_penalty,
            # "frequency_penalty": config.frequency_penalty,
            "max_tokens": self.llm_config.max_tokens,
        }
        return model_kwargs
