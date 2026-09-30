"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: qwen_client.py
@Description: 
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:13
"""
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from langchain_openai import ChatOpenAI

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig


class QwenClient(BaseClient):
    """Qwen LLM 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = self.llm_config.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model_name = self.llm_config.model_name or "qwen3.8-max"
        os.environ["DASHSCOPE_API_KEY"] = self.llm_config.api_key.get_secret_value()

    def check_package(self) -> bool:
        """检测 Qwen 客户端所需依赖是否已安装"""
        return self._check_packages(
            (
                ("langchain_community", "langchain-community"),
                # ("dashscope", "dashscope"),
            )
        )

    def llm_model(self) -> BaseLanguageModel:
        return ChatOpenAI(
            model=self.model_name,
            base_url=self.base_url,
            api_key=self.llm_config.api_key,
            timeout=self.llm_config.timeout,
            temperature=self.llm_config.temperature,
            max_retries=self.llm_config.max_retries,
            max_tokens=self.llm_config.max_tokens,
            model_kwargs=self._get_model_kwargs(),
        )

    def llm_embed(self) -> Embeddings:
        from langchain_community.embeddings import DashScopeEmbeddings
        return DashScopeEmbeddings(
            model=self.embed_config.model_name,
            max_retries=self.embed_config.max_retries,
            dashscope_api_key=self.embed_config.api_key.get_secret_value()
        )

    def _get_model_kwargs(self):
        """返回模型参数字典"""
        model_kwargs = {
        }
        return model_kwargs
