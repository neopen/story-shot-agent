"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: client_factory.py
@Description: 
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/10 23:13
"""
import hashlib
import threading
from typing import Any, Callable, Dict, Optional, Tuple, Type, List

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from penshot.config.config import settings
from penshot.config.config_models import LLMBaseConfig, EmbeddingBaseConfig
from penshot.logger import error, warning, info, debug
from penshot.neopen.client.base_client import BaseClient
from penshot.neopen.client.client_config import ClientType, AIConfig, detect_ai_provider_by_url
from penshot.neopen.client.llm.deepseek_client import DeepSeekClient
from penshot.neopen.client.llm.ollama_client import OllamaClient
from penshot.neopen.client.llm.openai_client import OpenAIClient
from penshot.neopen.client.llm.qwen_client import QwenClient
from penshot.utils.log_utils import print_log_exception

CLIENT_REGISTRY: Dict[ClientType, Type[BaseClient]] = {
    ClientType.OPENAI: OpenAIClient,
    ClientType.OLLAMA: OllamaClient,
    ClientType.DEEPSEEK: DeepSeekClient,
    ClientType.QWEN: QwenClient,
}

# 进程级嵌入模型缓存：同一配置只初始化一次，避免重建 pipeline 时重复创建客户端
_EMBEDDING_CACHE: Dict[Tuple[Any, ...], Embeddings] = {}
_EMBEDDING_CACHE_LOCK = threading.Lock()


def _resolve_provider_name(base_url: str) -> str:
    """安全解析厂商名：base_url 为空时返回空串，避免缓存键计算抛异常。"""
    try:
        return str(detect_ai_provider_by_url(base_url))
    except Exception:
        return ""


def _embedding_cache_key(
        ai_config: EmbeddingBaseConfig,
        overrides: Optional[Dict[str, Any]] = None
) -> Tuple[Any, ...]:
    """生成嵌入模型缓存键（provider、端点、模型、维度、密钥指纹与覆盖参数）。"""
    api_key = getattr(ai_config, "api_key", "") or ""
    if hasattr(api_key, "get_secret_value"):
        api_key = api_key.get_secret_value()
    api_key_fingerprint = hashlib.sha256(str(api_key).encode("utf-8")).hexdigest()[:16] if api_key else ""

    overrides_key = tuple(sorted((str(k), str(v)) for k, v in (overrides or {}).items()))
    return (
        _resolve_provider_name(ai_config.base_url),
        ai_config.base_url or "",
        ai_config.model_name or "",
        getattr(ai_config, "device", ""),
        getattr(ai_config, "dimensions", ""),
        getattr(ai_config, "normalize_embeddings", ""),
        api_key_fingerprint,
        overrides_key,
    )


def _get_cached_embedding(
        key: Tuple[Any, ...],
        factory: Callable[[], Optional[Embeddings]]
) -> Optional[Embeddings]:
    """按缓存键复用嵌入模型实例（线程安全；初始化失败不写入缓存）。"""
    cached = _EMBEDDING_CACHE.get(key)
    if cached is not None:
        return cached

    with _EMBEDDING_CACHE_LOCK:
        cached = _EMBEDDING_CACHE.get(key)
        if cached is not None:
            return cached

        embedding = factory()
        if embedding is not None:
            _EMBEDDING_CACHE[key] = embedding
            debug(f"嵌入模型已初始化并缓存: {type(embedding).__name__}")
        return embedding


def clear_embedding_cache() -> None:
    """清空嵌入模型缓存（配置热更新或测试时使用）。"""
    with _EMBEDDING_CACHE_LOCK:
        _EMBEDDING_CACHE.clear()


def get_supported_clients() -> Dict[ClientType, Type[BaseClient]]:
    """
    获取支持的客户端类型

    Returns:
        支持的客户端类型字典
    """
    return CLIENT_REGISTRY


################################ 获取 LLM 客户端实例 #################################
def get_client(provider: ClientType, config: AIConfig) -> BaseClient:
    """
    创建指定 LLM 客户端

    Args:
        provider: 支持 'openai', 'ollama', 'deepseek', 'qwen'
        **config: 传递给具体客户端的参数（如 model, temperature, api_key 等）

    Returns:
        BaseClient 实例
    """
    if provider not in CLIENT_REGISTRY:
        raise ValueError(f"Unsupported provider: {provider}. Choose from {list(CLIENT_REGISTRY.keys())}")

    client_class = CLIENT_REGISTRY[provider]
    return client_class(config)


def get_llm_client(config: AIConfig, **kwargs) -> BaseLanguageModel:
    return get_llm_client_by_provider(detect_ai_provider_by_url(config.llm.base_url), config, **kwargs)


def get_llm_client_by_provider(provider: ClientType, config: AIConfig = None, **kwargs) -> BaseLanguageModel:
    """
    获取指定 LLM 客户端的语言模型实例

    Args:
        provider: 支持 'openai', 'ollama', 'deepseek', 'qwen'
        **kwargs: 传递给具体客户端的参数（如 model, temperature, api_key 等）
    Returns:
        BaseClient 实例
    """
    fin_config = _fill_default_config(config, **kwargs)

    return get_client(provider, fin_config).llm_model()


def get_default_llm(**kwargs) -> Optional[BaseLanguageModel]:
    # 获取配置
    try:
        return _get_default_llm(settings.get_llm_config(), **kwargs)
    except Exception as e:
        warning(f"默认LLM模型初始化失败: {str(e)}，尝试使用备用配置")
        try:
            return _get_default_llm(settings.get_llm_config("fallback"), **kwargs)
        except Exception as e:
            # print_log_exception()
            error(f"LLM模型初始化失败（错误: {str(e)}），系统将自动使用规则引擎模式继续工作")
            raise ValueError("LLM 不可用，请检查配置及依赖")


def _get_default_llm(ai_config: LLMBaseConfig, **kwargs) -> BaseLanguageModel:
    """
    获取默认的 LLM 客户端的语言模型实例（默认为 OpenAI）

    Returns:
        语言模型实例
    """
    # 获取配置
    provider = detect_ai_provider_by_url(ai_config.base_url)
    info(f"使用AI提供商: {provider}, 大语言模型: {ai_config.model_name}")

    config = AIConfig(llm=ai_config)

    fin_config = _fill_default_config(config, **kwargs)

    # 使用client_factory获取对应的LangChain LLM实例
    # client = get_client(get_client_type(provider), fin_config)
    client = get_client(provider, fin_config)

    if not client:
        warning(f"AI模型初始化失败（未能获取 {provider} 的LLM实例），系统将自动使用规则引擎模式继续工作")
        raise ConnectionError(f"LLM client initialization failed for provider: {provider}")

    return client.llm_model()


def _fill_default_config(config: AIConfig, **kwargs) -> AIConfig:
    """填充默认配置"""
    if not kwargs:
        return config

    llm_config = config.llm or LLMBaseConfig()
    llm_config.model_name= kwargs.get('model_name', llm_config.model_name)
    llm_config.base_url=kwargs.get('base_url', llm_config.base_url)
    llm_config.api_key=kwargs.get("api_key", llm_config.api_key)
    llm_config.temperature=kwargs.get("temperature", llm_config.temperature)
    llm_config.max_tokens=kwargs.get("max_tokens", llm_config.max_tokens)

    embed_config = config.embed or EmbeddingBaseConfig()
    embed_config.model_name=kwargs.get('embed_model_name', embed_config.model_name)
    embed_config.base_url=kwargs.get('embed_base_url', embed_config.base_url)
    embed_config.api_key=kwargs.get("embed_api_key", embed_config.api_key)

    config.llm = llm_config
    config.embed = embed_config

    return config


def llm_chat_complete(llm: BaseLanguageModel, messages: List[Dict[str, str]], **kwargs) -> str:
    """ LLM 聊天接口封装 """
    content, _ = llm_chat_complete_with_metadata(llm, messages, **kwargs)
    return content


def llm_chat_complete_with_metadata(
    llm: BaseLanguageModel,
    messages: List[Dict[str, str]],
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    """ LLM 聊天接口封装，同时返回响应元数据（含 finish_reason / token 用量） """
    response = llm.invoke(_convert_messages(messages), **kwargs)
    metadata = dict(getattr(response, "response_metadata", {}) or {})
    if metadata.get("finish_reason") == "length":
        warning(
            "LLM 响应被截断（finish_reason=length），JSON 可能不完整；"
            "请增大 max_tokens 或在配置中设置 enable_thinking=false"
        )
    return response.content, metadata


def _convert_messages(messages: List[Dict[str, str]]):
    """Convert dict messages to LangChain message objects"""
    lc_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            # lc_messages.append(AIMessage(content=content, additional_kwargs={"tool_calls": []}))
            lc_messages.append(AIMessage(content=content))
        else:
            raise ValueError(f"Unsupported role: {role}")
    return lc_messages


################################# 获取嵌入模型实例 #################################
def get_embedding_client(config: AIConfig) -> Embeddings:
    """
    获取指定 LLM 客户端的嵌入模型实例

    Args:
        支持 'openai', 'ollama', 'deepseek', 'qwen'
        config: 传递给具体客户端的参数（如 model, temperature, api_key 等）
    Returns:
        嵌入模型实例（相同配置复用同一实例）
    """
    embed_config = config.embed or EmbeddingBaseConfig()
    key = _embedding_cache_key(embed_config)

    def _factory() -> Embeddings:
        client = get_client(detect_ai_provider_by_url(embed_config.base_url), config)
        return client.llm_embed()

    return _get_cached_embedding(key, _factory)


def get_default_embedding(**kwargs) -> Optional[Embeddings]:
    # 获取配置
    try:
        ai_config = settings.get_embedding_config()
        return _get_cached_default_embedding(ai_config, kwargs)
    except Exception as e:
        warning("默认AI嵌入模型初始化失败，尝试使用备用配置")
        try:
            ai_config = settings.get_embedding_config("fallback")
            return _get_cached_default_embedding(ai_config, kwargs)
        except Exception as e:
            print_log_exception()
            error(f"AI嵌入模型初始化失败（错误: {str(e)}），系统将自动使用规则引擎模式继续工作")
            return None


def _get_cached_default_embedding(
        ai_config: EmbeddingBaseConfig,
        kwargs: Dict[str, Any]
) -> Optional[Embeddings]:
    """按配置与覆盖参数缓存默认嵌入模型，避免重复初始化。"""
    key = _embedding_cache_key(ai_config, kwargs)
    return _get_cached_embedding(key, lambda: _get_default_embedding_client(ai_config, **kwargs))


def _get_default_embedding_client(ai_config: EmbeddingBaseConfig, **kwargs):
    """
    获取默认的 LLM 客户端的嵌入模型实例（默认为 OpenAI）

    Returns:
        嵌入模型实例
    """
    provider = detect_ai_provider_by_url(ai_config.base_url)
    info(f"使用AI提供商: {provider}, 嵌入模型: {ai_config.model_name}")

    config = AIConfig(embed=ai_config)

    fin_config = _fill_default_config(config, **kwargs)

    # 使用client_factory获取对应的嵌入模型实例
    client = get_client(provider, fin_config)

    if not client:
        warning(f"AI嵌入模型初始化失败（未能获取 {provider} 的嵌入实例），系统将自动使用规则引擎模式继续工作")
        raise ConnectionError(f"LLM Embedding client initialization failed for provider: {provider}")

    return client.llm_embed()


def embed_client_query(text: str, config: AIConfig, **kwargs) -> List[float]:
    """
    获取指定 LLM 客户端的文本嵌入向量

    Args:
        支持 'openai', 'ollama', 'deepseek', 'qwen'
        config: 传递给具体客户端的参数（如 model, temperature, api_key 等）
        text: 需要嵌入的文本
    Returns:
        文本嵌入向量
    """
    fin_config = _fill_default_config(config, **kwargs)
    client = get_embedding_client(fin_config)
    return client.embed_query(text)


if __name__ == '__main__':
    # 创建 OpenAI 客户端
    # llm = get_llm_client(ClientType.OPENAI, model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
    # response = llm.invoke("Hello, how are you?")
    # print(response.content)

    ###############################################
    # 创建 Ollama 客户端（假设本地运行 llama3.1）
    llm2 = get_llm_client_by_provider(ClientType.OLLAMA, model="qwen3:4b", temperature=0.2)

    messages = [
        {"role": "system", "content": "你是一个专业的影视剧本解析分镜师，精通标准剧本格式，输出严格的JSON格式。"},
        {"role": "user",
         "content": "深夜11点，城市公寓客厅，窗外大雨滂沱。林然裹着旧羊毛毯蜷在沙发里，电视静音播放着黑白老电影。茶几上半杯凉茶已凝出水雾，旁边摊开一本旧相册。手机突然震动，屏幕亮起“未知号码”。她盯着看了三秒，指尖悬停在接听键上方，喉头轻轻滚动。终于，她按下接听，将手机贴到耳边。电话那头沉默两秒，传来一个沙哑的男声：“是我。”  林然的手指瞬间收紧，指节泛白，呼吸停滞了一瞬。  她声音微颤：“……陈默？你还好吗？”  对方停顿片刻，低声说：“我回来了。” 林然猛地坐直，瞳孔收缩，泪水在眼眶中打转。她张了张嘴，却发不出声音，只有毛毯从肩头滑落。”"}
    ]

    print(llm_chat_complete(llm2, messages))
