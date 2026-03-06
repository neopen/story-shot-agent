"""
@FileName: client_factory.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/10 23:13
"""
from typing import Dict, Type, List

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from hengshot.config.config import settings
from hengshot.hengline.client.base_client import BaseClient
from hengshot.hengline.client.client_config import ClientType, AIConfig, detect_ai_provider_by_url
from hengshot.hengline.client.llm.deepseek_client import DeepSeekClient
from hengshot.hengline.client.llm.ollama_client import OllamaClient
from hengshot.hengline.client.llm.openai_client import OpenAIClient
from hengshot.hengline.client.llm.qwen_client import QwenClient
from hengshot.logger import error, warning, info
from hengshot.utils.log_utils import print_log_exception

CLIENT_REGISTRY: Dict[ClientType, Type[BaseClient]] = {
    ClientType.OPENAI: OpenAIClient,
    ClientType.OLLAMA: OllamaClient,
    ClientType.DEEPSEEK: DeepSeekClient,
    ClientType.QWEN: QwenClient,
}


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


def get_llm_client(config: AIConfig, **kwargs):
    return get_llm_client_by_provider(detect_ai_provider_by_url(config.base_url), config, **kwargs)


def get_llm_client_by_provider(provider: ClientType, config: AIConfig = None, **kwargs):
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


def get_default_llm(**kwargs):
    # 获取配置
    try:
        return _get_default_llm(settings.get_llm_config(), **kwargs)
    except Exception as e:
        warning("默认AI嵌入模型初始化失败，尝试使用备用配置")
        try:
            return _get_default_llm(settings.get_llm_config("fallback"), **kwargs)
        except Exception as e:
            print_log_exception()
            error(f"AI模型初始化失败（错误: {str(e)}），系统将自动使用规则引擎模式继续工作")
            return None


def _get_default_llm(ai_config, **kwargs):
    """
    获取默认的 LLM 客户端的语言模型实例（默认为 OpenAI）

    Returns:
        语言模型实例
    """
    # 获取配置
    provider = detect_ai_provider_by_url(ai_config.base_url)
    info(f"使用AI提供商: {provider}, 模型: {ai_config.model_name}")

    config = AIConfig(
        model_name=ai_config.model_name,
        api_key=ai_config.api_key,
        base_url=ai_config.base_url,
        temperature=ai_config.temperature,
        timeout=ai_config.timeout,
        max_tokens=ai_config.max_tokens,
    )

    fin_config = _fill_default_config(config, **kwargs)

    # 使用client_factory获取对应的LangChain LLM实例
    # client = get_client(get_client_type(provider), fin_config)
    client = get_client(provider, fin_config)

    if not client:
        warning(f"AI模型初始化失败（未能获取 {provider} 的LLM实例），系统将自动使用规则引擎模式继续工作")
        raise ConnectionError(f"LLM client initialization failed for provider: {provider}")

    return client.llm_model()


def _fill_default_config(config: AIConfig = None, **kwargs) -> AIConfig:
    """填充默认配置"""
    config = config or AIConfig(
        model_name=kwargs.get('model_name', 'gpt-4o'),
        base_url=kwargs.get('base_url', ""),
        api_key=kwargs.get("api_key", None),
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 10000),
    )

    if not kwargs:
        return config

    for key, value in kwargs.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)
    return config


def llm_chat_complete(llm: BaseLanguageModel, messages: List[Dict[str, str]], **kwargs) -> str:
    """ LLM 聊天接口封装 """
    # response = self.llm.chat_complete(
    #     messages=[
    #         {"role": "system", "content": "你是一个专业的影视剧本解析分镜师，精通标准剧本格式，输出严格的JSON格式。"},
    #         {"role": "user", "content": prompt}
    #     ],
    #     temperature=0.1,
    #     response_format={"type": "json_object"}
    # )
    response = llm.invoke(_convert_messages(messages), **kwargs)
    return response.content


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
def get_embedding_client(provider: ClientType, config: AIConfig):
    """
    获取指定 LLM 客户端的嵌入模型实例

    Args:
        provider: 支持 'openai', 'ollama', 'deepseek', 'qwen'
        config: 传递给具体客户端的参数（如 model, temperature, api_key 等）
    Returns:
        嵌入模型实例
    """
    client = get_client(provider, config)
    return client.llm_embed()


def get_default_embedding_client(**kwargs):
    # 获取配置
    try:
        ai_config = settings.get_embedding_config()
        return _get_default_embedding_client(ai_config, **kwargs)
    except Exception as e:
        warning("默认AI嵌入模型初始化失败，尝试使用备用配置")
        try:
            ai_config = settings.get_embedding_config("fallback")
            return _get_default_embedding_client(ai_config, **kwargs)
        except Exception as e:
            print_log_exception()
            error(f"AI嵌入模型初始化失败（错误: {str(e)}），系统将自动使用规则引擎模式继续工作")
            return None


def _get_default_embedding_client(ai_config, **kwargs):
    """
    获取默认的 LLM 客户端的嵌入模型实例（默认为 OpenAI）

    Returns:
        嵌入模型实例
    """
    provider = detect_ai_provider_by_url(ai_config.base_url)
    info(f"使用AI提供商: {provider}, 嵌入模型: {ai_config.model_name}")

    config = AIConfig(
        model_name=ai_config.model_name,
        base_url=ai_config.base_url,
        timeout=ai_config.timeout,
        api_key=ai_config.api_key
    )

    fin_config = _fill_default_config(config, **kwargs)

    # 使用client_factory获取对应的嵌入模型实例
    client = get_client(provider, fin_config)

    if not client:
        warning(f"AI嵌入模型初始化失败（未能获取 {provider} 的嵌入实例），系统将自动使用规则引擎模式继续工作")
        raise ConnectionError(f"LLM Embedding client initialization failed for provider: {provider}")

    return client.llm_embed()


def embed_client_query(provider: ClientType, text: str, config: AIConfig = None, **kwargs) -> List[float]:
    """
    获取指定 LLM 客户端的文本嵌入向量

    Args:
        provider: 支持 'openai', 'ollama', 'deepseek', 'qwen'
        config: 传递给具体客户端的参数（如 model, temperature, api_key 等）
        text: 需要嵌入的文本
    Returns:
        文本嵌入向量
    """
    fin_config = _fill_default_config(config, **kwargs)

    client = get_embedding_client(provider, fin_config)
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
