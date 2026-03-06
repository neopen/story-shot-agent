"""
@FileName: client_type.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/11 16:31
"""
from dataclasses import dataclass
from enum import Enum, unique
from random import Random
from typing import Optional, List

from pydantic import SecretStr


@unique
class ClientType(Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"


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
        return ClientType.OLLAMA

    # 统一转为小写便于匹配
    url_lower = base_url.lower()

    # 1. OpenAI - 严格匹配官方域名
    if "openai.com" in url_lower:
        return ClientType.OPENAI

    # 2. Qwen (通义千问) - 阿里云 DashScope
    if "aliyuncs.com" in url_lower:
        return ClientType.QWEN

    # 3. DeepSeek
    if "deepseek.com" in url_lower:
        return ClientType.DEEPSEEK

    # 4. Ollama - 两种识别方式：
    #    a) 默认端口 11434（最可靠特征）
    #    b) URL 中包含 'ollama'（适应 Docker/自定义部署）
    if ":11434" in url_lower or "ollama" in url_lower:
        return ClientType.OLLAMA

    return ClientType.OLLAMA


@dataclass
class AIConfig:
    """AI配置"""
    model_name: str = None  # 或 "claude-3", "deepseek-chat", "gpt-4"
    base_url: str = None  # 用于本地部署或特定API端点
    api_key: Optional[SecretStr] = None
    temperature: float = 0.1
    max_tokens: int = 10000
    max_retries: int = 3  # 最大重试次数
    seed: int = Random().randint(1000, 999999999999999)
    response_format: str = "json"  # 响应格式，默认为JSON
    timeout: int = 60  # 请求超时时间，单位秒
    enable_cot: bool = True  # 启用思维链推理
    include_visual_hints: bool = True  # 包含视觉生成提示

    retry_delay: float = 1.0  # 重试延迟
    top_p: float = 1.0  # 核采样概率
    frequency_penalty: float = 0.0  # 频率惩罚
    presence_penalty: float = 0.0  # 存在惩罚

    streaming: bool = False  # 是否流式响应
    function_call: str = None  # 函数调用模式
    functions: List = None  # 可用函数列表

    # 嵌入向量维度
    dimensions: int = 1024

    # 专业领域知识注入
    cinematic_knowledge: bool = True
    pacing_principles: bool = True

    def get_llm_by_config(self):
        from hengshot.hengline.client.client_factory import get_llm_client, get_default_llm
        return get_llm_client(self) if self.model_name and self.base_url else get_default_llm()
