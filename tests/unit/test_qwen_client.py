"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_qwen_client.py
@Description: Qwen 客户端连接方式分流与参数传递回归测试
@Author: neopen
"""
from langchain_community.chat_models import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from penshot.config.config_models import EmbeddingBaseConfig, LLMBaseConfig
from penshot.neopen.client.client_config import AIConfig
from penshot.neopen.client.embedding_compat import DimensionFallbackEmbeddings
from penshot.neopen.client.llm.qwen_client import QwenClient

MAAS_API_URL = "https://llm-demo.cn-beijing.maas.aliyuncs.com/api/v1"
MAAS_COMPAT_URL = "https://llm-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
PUBLIC_NATIVE_URL = "https://dashscope.aliyuncs.com/api/v1"


def _build_client(llm_base_url: str, embed_base_url: str = "", **llm_overrides) -> QwenClient:
    """构造使用假密钥的 QwenClient，仅用于分支选择校验（不发起网络请求）"""
    config = AIConfig(
        llm=LLMBaseConfig(
            base_url=llm_base_url,
            api_key="sk-test",
            model_name="qwen-test",
            timeout=30,
            max_tokens=128,
            **llm_overrides,
        ),
        embed=EmbeddingBaseConfig(
            base_url=embed_base_url or llm_base_url,
            api_key="sk-test",
            model_name="qwen-test-embed",
            dimensions=1536,
        ),
    )
    return QwenClient(config)


def test_private_maas_api_path_uses_openai_compatible_route():
    """私有 MaaS 的 /api/v1 应自动规范到 compatible-mode 并走 ChatOpenAI"""
    llm = _build_client(MAAS_API_URL).create_chat_model()

    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == MAAS_COMPAT_URL


def test_public_dashscope_native_path_uses_tongyi():
    """公共 DashScope 的 /api/v1 才使用原生 ChatTongyi"""
    llm = _build_client(PUBLIC_NATIVE_URL).create_chat_model()

    assert isinstance(llm, ChatTongyi)


def test_public_dashscope_compatible_path_uses_openai():
    """公共 DashScope 的 compatible-mode 地址应走 ChatOpenAI"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm = _build_client(url).create_chat_model()

    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == url


def test_model_kwargs_excludes_timeout():
    """timeout 不能作为 DashScope 生成参数下发"""
    client = _build_client(PUBLIC_NATIVE_URL)

    assert "timeout" not in client._get_model_kwargs()


def test_embedding_uses_openai_compatible_route_for_private_maas():
    """私有 MaaS 嵌入应走 OpenAIEmbeddings，并关闭上下文长度预检"""
    embeddings = _build_client(MAAS_API_URL).llm_embed()

    assert isinstance(embeddings, DimensionFallbackEmbeddings)
    primary = embeddings.primary
    assert isinstance(primary, OpenAIEmbeddings)
    assert primary.openai_api_base == MAAS_COMPAT_URL
    assert primary.check_embedding_ctx_length is False
    assert primary.dimensions == 1536


def test_embedding_uses_dashscope_for_public_endpoint():
    """公共 DashScope 嵌入继续使用原生 DashScopeEmbeddings"""
    embeddings = _build_client(PUBLIC_NATIVE_URL).llm_embed()

    assert isinstance(embeddings, DashScopeEmbeddings)


def test_enable_thinking_false_passed_via_extra_body():
    """关闭思考模式时应通过 extra_body 下发 enable_thinking"""
    llm = _build_client(MAAS_API_URL, enable_thinking=False).create_chat_model()

    assert llm.extra_body == {"enable_thinking": False}


def test_enable_thinking_defaults_to_false():
    """默认关闭思考模式（LLMBaseConfig.enable_thinking=False），避免思考内容占满 max_tokens"""
    llm = _build_client(MAAS_API_URL).create_chat_model()

    assert llm.extra_body == {"enable_thinking": False}


def test_enable_thinking_none_does_not_send_extra_body():
    """显式配置为 None 时不额外下发参数"""
    llm = _build_client(MAAS_API_URL, enable_thinking=None).create_chat_model()

    assert llm.extra_body is None
