"""
@FileName: openai_client.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:15
"""
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig


class OpenAIClient(BaseClient):
    """OpenAI 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = self.llm_config.base_url or "https://api.openai.com/v1"
        os.environ["OPENAI_API_KEY"] = self.llm_config.api_key.get_secret_value()

    def llm_model(self) -> BaseLanguageModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.llm_config.model_name,
            temperature=self.llm_config.temperature,
            api_key=self.llm_config.api_key,
            base_url=self.base_url,
            timeout=self.llm_config.timeout,
            max_retries=self.llm_config.max_retries,
            max_tokens=self.llm_config.max_tokens,
        )

    def llm_embed(self) -> Embeddings:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=self.embed_config.model_name,
            api_key=self.embed_config.api_key,
            base_url=self.embed_config.base_url or self.base_url,
            dimensions=self.embed_config.dimensions,
            timeout=self.embed_config.timeout,
            max_retries=self.embed_config.max_retries,
        )
