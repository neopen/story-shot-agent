"""
@FileName: huggingface_client.py
@Description: huggingface
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/30 18:24
"""
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from hengshot.hengline.client.base_client import BaseClient
from hengshot.hengline.client.client_config import AIConfig


class HuggingFaceClient(BaseClient):
    """HuggingFace LLM 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        # 常用中文嵌入模型
        self.MODEL_NAMES = {
            # 中文模型
            "bge-small-zh": "BAAI/bge-small-zh-v1.5",  # 推荐：中文小模型
            "bge-base-zh": "BAAI/bge-base-zh-v1.5",  # 中文基础模型
            "bge-large-zh": "BAAI/bge-large-zh-v1.5",  # 中文大模型
            "m3e-small": "moka-ai/m3e-small",  # 轻量级中文模型
            "m3e-base": "moka-ai/m3e-base",  # 基础中文模型
            "text2vec": "GanymedeNil/text2vec-large-chinese",  # 文本转向量

            # 多语言模型
            "paraphrase-multilingual": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "multilingual-e5": "intfloat/multilingual-e5-large",

            # 英文模型
            "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
            "all-mpnet-base-v2": "sentence-transformers/all-mpnet-base-v2",
        }

    def llm_model(self) -> BaseLanguageModel:
        raise NotImplementedError("HuggingFace LLM model is not implemented yet.")

    def llm_embed(self) -> Embeddings:
        return HuggingFaceEmbeddings(**self._get_model_kwargs())

    def _get_model_kwargs(self, **kwargs):
        """创建HuggingFace嵌入模型"""

        # 默认配置
        default_kwargs = {
            "model_name": self.config.model_name or "BAAI/bge-small-zh-v1.5",  # 模型名称
            "model_kwargs": {"device": "cpu"},  # 设备：cpu, cuda, mps
            "encode_kwargs": {
                "normalize_embeddings": True,  # 归一化嵌入向量
                "batch_size": 32,  # 批量大小
            },
            "cache_folder": "./models",  # 模型缓存目录
            "multi_process": False,  # 是否启用多进程
        }

        # 更新配置
        default_kwargs.update(kwargs)

        return default_kwargs
