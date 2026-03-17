"""
@FileName: deepseek_client.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/10 23:17
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig


class DeepSeekClient(BaseClient):
    """DeepSeek 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.deepseek.com/v1/chat/completions"

    def llm_model(self) -> BaseLanguageModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model_name,
            temperature=self.config.temperature,
            api_key=self.config.api_key,
            base_url=self.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            max_tokens=self.config.max_tokens,
        )

    def llm_embed(self) -> Embeddings:
        raise NotImplementedError("DeepSeek does not provide an embedding API. Consider using OpenAI, Ollama, or Qwen for embeddings.")
