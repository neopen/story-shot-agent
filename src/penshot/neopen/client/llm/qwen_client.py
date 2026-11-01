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
from urllib.parse import urlparse

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from langchain_openai import ChatOpenAI
from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import AIConfig
from penshot.neopen.client.embedding_compat import (
    DimensionFallbackEmbeddings,
    supports_dimensions_field,
)

from penshot.logger import info

# 阿里云公共 DashScope 域名：仅该域名提供原生 DashScope 接口
PUBLIC_DASHSCOPE_HOST = "dashscope.aliyuncs.com"


class QwenClient(BaseClient):
    """Qwen LLM 客户端实现"""

    def __init__(self, config: AIConfig):
        super().__init__(config)
        self.base_url = self.llm_config.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model_name = self.llm_config.model_name or "qwen3.8-max"
        os.environ["DASHSCOPE_API_KEY"] = self.llm_config.api_key.get_secret_value()

    def check_package(self) -> bool:
        """检测当前连接方式所需依赖是否已安装"""
        if self._use_dashscope_native(self.base_url):
            return self._check_packages(
                (
                    ("langchain_community", "langchain-community"),
                    ("dashscope", "dashscope"),
                )
            )
        # OpenAI 兼容接口只依赖 langchain-openai
        return self._check_packages((("langchain_openai", "langchain-openai"),))

    def llm_model(self) -> BaseLanguageModel:
        return self.create_chat_model()

    @staticmethod
    def _is_public_dashscope(base_url: str) -> bool:
        """判断服务地址是否为阿里云公共 DashScope 域名"""
        host = urlparse(base_url).hostname or ""
        return host.lower() == PUBLIC_DASHSCOPE_HOST

    @staticmethod
    def _use_dashscope_native(base_url: str) -> bool:
        """是否应使用 DashScope 原生 SDK 接口

        只有公共 DashScope（dashscope.aliyuncs.com）才提供原生接口 `/api/v1`；
        私有 MaaS 网关（如 *.maas.aliyuncs.com）只提供 OpenAI 兼容接口，
        其 `/api/v1` 路径必须改走 `compatible-mode/v1`，否则会报 url error。
        """
        normalized = base_url.rstrip("/")
        path = urlparse(normalized).path
        if not QwenClient._is_public_dashscope(normalized):
            return False
        return path in ("", "/") or path.endswith("/api/v1")

    @staticmethod
    def _openai_compatible_base_url(base_url: str) -> str:
        """获取 OpenAI 兼容接口地址

        私有 MaaS 网关误配为 `/api/v1` 时，自动规范到 `/compatible-mode/v1`，
        其余地址（含自建 OpenAI 兼容服务）保持原样。
        """
        normalized = base_url.rstrip("/")
        host = (urlparse(normalized).hostname or "").lower()
        is_private_aliyun = (
            not QwenClient._is_public_dashscope(normalized)
            and host.endswith("aliyuncs.com")
        )
        if is_private_aliyun and normalized.endswith("/api/v1"):
            return normalized[: -len("/api/v1")] + "/compatible-mode/v1"
        return normalized

    def create_chat_model(self):
        """
        根据服务地址选择 Chat 模型：

        - 公共 DashScope 原生接口（dashscope.aliyuncs.com/api/v1） -> ChatTongyi
        - 其余地址（OpenAI 兼容接口，如 compatible-mode/v1）     -> ChatOpenAI
        """
        # 仅公共 DashScope 的原生接口走 ChatTongyi，其余一律走 OpenAI 兼容协议
        if self._use_dashscope_native(self.base_url):
            from langchain_community.chat_models import ChatTongyi  # Qwen via Tongyi

            info("QwenClient -> DashScope 原生接口")
            return ChatTongyi(
                model=self.model_name,
                model_kwargs=self._get_model_kwargs(),
                api_key=self.llm_config.api_key,
                max_retries=self.llm_config.max_retries,
                streaming=False,
            )

        base_url = self._openai_compatible_base_url(self.base_url)
        info(f"QwenClient -> OpenAI 兼容接口: {base_url}")
        # Qwen3 等模型默认开启思考模式，会占用大量 max_tokens 导致正文被截断；
        # 配置 enable_thinking=false 时通过 extra_body 下发关闭开关
        extra_body = None
        if self.llm_config.enable_thinking is not None:
            extra_body = {"enable_thinking": bool(self.llm_config.enable_thinking)}
        return ChatOpenAI(
            model=self.model_name,
            base_url=base_url,
            api_key=self.llm_config.api_key,
            timeout=self.llm_config.timeout,
            temperature=self.llm_config.temperature,
            max_retries=self.llm_config.max_retries,
            max_tokens=self.llm_config.max_tokens,
            extra_body=extra_body,
        )

    def llm_embed(self) -> Embeddings:
        """创建嵌入模型

        公共 DashScope 使用原生 DashScopeEmbeddings；
        私有 MaaS 等 OpenAI 兼容服务使用 OpenAIEmbeddings。
        """
        embed_base_url = self.embed_config.base_url or self.base_url

        if self._use_dashscope_native(embed_base_url):
            from langchain_community.embeddings import DashScopeEmbeddings

            info("QwenClient 嵌入 -> DashScope 原生接口")
            return DashScopeEmbeddings(
                model=self.embed_config.model_name,
                max_retries=self.embed_config.max_retries,
                dashscope_api_key=self.embed_config.api_key.get_secret_value(),
            )

        from langchain_openai import OpenAIEmbeddings

        base_url = self._openai_compatible_base_url(embed_base_url)
        info(f"QwenClient 嵌入 -> OpenAI 兼容接口: {base_url}")
        embedding_kwargs = {
            "model": self.embed_config.model_name,
            "base_url": base_url,
            "api_key": self.embed_config.api_key,
            "timeout": self.embed_config.timeout,
            "max_retries": self.embed_config.max_retries,
            # 私有 MaaS 不接受分词后的 token 数组，必须关闭上下文长度预检
            "check_embedding_ctx_length": False,
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

        # 部分服务端会拒绝 dimensions 参数（400 InvalidParameter），此时自动降级为默认维度
        fallback_kwargs = {
            key: value for key, value in embedding_kwargs.items() if key != "dimensions"
        }
        return DimensionFallbackEmbeddings(
            primary,
            lambda: OpenAIEmbeddings(**fallback_kwargs),
        )

    def _get_model_kwargs(self):
        """返回 DashScope 原生接口的模型参数字典

        注意：timeout 不是 DashScope 生成接口的合法参数，不能放进 model_kwargs，
        否则会作为请求参数下发并触发 400 InvalidParameter。
        """
        model_kwargs = {
            "temperature": self.llm_config.temperature,
            # "top_p": config.top_p,
            # "presence_penalty": config.presence_penalty,
            # "frequency_penalty": config.frequency_penalty,
            "max_tokens": self.llm_config.max_tokens,
        }
        return model_kwargs
