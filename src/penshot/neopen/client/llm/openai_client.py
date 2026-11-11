"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: openai_client.py
@Description: 
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:15
"""
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig
from penshot.neopen.client.embedding_compat import (
    DimensionFallbackEmbeddings,
    supports_dimensions_field,
)


class OpenAIClient(BaseClient):
    """OpenAI 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = self.llm_config.base_url or "https://api.openai.com/v1"
        os.environ["OPENAI_API_KEY"] = self.llm_config.api_key.get_secret_value()

    def check_package(self) -> bool:
        """检测 OpenAI 客户端所需依赖是否已安装"""
        return self._check_packages((("langchain_openai", "langchain-openai"),))

    def llm_model(self) -> BaseLanguageModel:
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
        embedding_kwargs = {
            "model": self.embed_config.model_name,
            "api_key": self.embed_config.api_key,
            "base_url": self.embed_config.base_url or self.base_url,
            "timeout": self.embed_config.timeout,
            "max_retries": self.embed_config.max_retries,
        }
        # 旧版 langchain-openai 未提供 dimensions 字段时直接跳过该参数
        use_dimensions = (
            bool(self.embed_config.dimensions)
            and supports_dimensions_field(OpenAIEmbeddings)
        )
        if use_dimensions:
            embedding_kwargs["dimensions"] = self.embed_config.dimensions

        primary = OpenAIEmbeddings(**embedding_kwargs)
        if not use_dimensions:
            return primary

        # 部分 OpenAI 兼容服务会拒绝 dimensions 参数，此时自动降级为默认维度
        fallback_kwargs = {
            key: value for key, value in embedding_kwargs.items() if key != "dimensions"
        }
        return DimensionFallbackEmbeddings(
            primary,
            lambda: OpenAIEmbeddings(**fallback_kwargs),
        )
