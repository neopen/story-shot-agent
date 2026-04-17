"""
@FileName: ollama_client.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:16
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig


class OllamaClient(BaseClient):
    """Ollama 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = self.llm_config.base_url or "http://localhost:11434"  # Ollama 默认本地地址

    def llm_model(self) -> BaseLanguageModel:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            base_url=self.base_url,
            model=self.llm_config.model_name,
            temperature=self.llm_config.temperature,
            num_predict=self.llm_config.max_tokens * 4,
            keep_alive=self.llm_config.timeout * 5,
            seed=self.llm_config.seed,
            num_thread=8,
            client_kwargs=self._get_model_kwargs(),
        )

    def _get_model_kwargs(self):
        """返回模型参数字典"""
        model_kwargs = {
            # "top_p": config.top_p,
            # "presence_penalty": config.presence_penalty,
            # "frequency_penalty": config.frequency_penalty,
        }
        return model_kwargs

    def llm_embed(self) -> Embeddings:
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=self.embed_config.model_name,
            keep_alive=self.embed_config.timeout * 5,
            num_thread=8,
            base_url=self.base_url
        )
