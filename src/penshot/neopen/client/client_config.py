"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: client_type.py
@Description: 
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/11 16:31
"""
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Optional
from urllib.parse import urlparse

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from pydantic import Field

from penshot.config.config_models import LLMBaseConfig, EmbeddingBaseConfig


@unique
class ClientType(Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    HUGGINGFACE = "huggingface"


def get_client_type(client_type_str):
    for client_type in ClientType:
        if client_type.value == client_type_str.lower():
            return client_type

    raise ValueError(f"Invalid client_type: {client_type_str}")


def detect_ai_provider_by_url(base_url: str) -> ClientType:
    """
    根据 base_url 识别 AI 服务厂商

    支持厂商：
        - openai:   api.openai.com
        - qwen:     dashscope.aliyuncs.com（阿里云 DashScope）
        - deepseek: api.deepseek.com
        - ollama:   端口 11434 或 URL 包含 'ollama'（不区分大小写）

    参数:
        base_url (str): API 基础 URL，例如 "https://api.openai.com/v1"

    返回:
        str | None: 厂商名称（小写）或 None（无法识别）
    """
    if not base_url or not isinstance(base_url, str):
        raise ModuleNotFoundError("未找到默认 LLM 配置")

    parsed = urlparse(base_url)
    host = parsed.hostname.lower() if parsed.hostname else ""

    def _host_matches(domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    # 1. OpenAI - 严格匹配官方域名（含子域）
    if _host_matches("openai.com"):
        return ClientType.OPENAI

    # 2. Qwen (通义千问) - 阿里云 DashScope（含子域）
    if _host_matches("aliyuncs.com"):
        return ClientType.QWEN

    # 3. DeepSeek（含子域）
    if _host_matches("deepseek.com"):
        return ClientType.DEEPSEEK

    # 4. HuggingFace（含子域）
    if _host_matches("huggingface.co"):
        return ClientType.HUGGINGFACE

    # 5. Ollama - 两种识别方式：
    #    a) 默认端口 11434（最可靠特征）
    #    b) URL 中包含 'ollama'（适应 Docker/自定义部署）
    # if ":11434" in url_lower or "ollama" in url_lower:
    #     return ClientType.OLLAMA

    return ClientType.OLLAMA


@dataclass
class AIConfig:
    llm: LLMBaseConfig = field(default_factory=LLMBaseConfig)
    embed: EmbeddingBaseConfig = field(default_factory=EmbeddingBaseConfig)

    # 业务开关
    cinematic_knowledge: bool = Field(default=True, description="注入影视领域知识")
    pacing_principles: bool = Field(default=True, description="启用节奏控制原则")

    # ====================== LLM 缓存配置 ======================
    enable_llm_cache: bool = False  # 默认关闭，因为 LLM 输出不稳定
    cache_ttl_seconds: int = 300  # 5分钟短缓存
    cache_mode: str = "strict"  # strict: 完全相同输入; fuzzy: 相似输入
    cache_only_for: list = None  # 指定哪些 Agent 使用缓存，如 ["video_splitter"]

    #
    def has_llm_config(self):
        return self.llm and self.llm.model_name and self.llm.base_url

    def has_embed_config(self):
        return self.embed and self.embed.model_name and self.embed.base_url

    # LLM
    def get_llm_by_config(self) -> Optional[BaseLanguageModel]:
        from penshot.neopen.client.client_factory import get_llm_client, get_default_llm
        return get_llm_client(self) if self.has_llm_config() else get_default_llm()

    # Embeddings
    def get_embed_by_config(self) -> Optional[Embeddings]:
        from penshot.neopen.client.client_factory import get_embedding_client, get_default_embedding
        return get_embedding_client(self) if self.has_embed_config() else get_default_embedding()
