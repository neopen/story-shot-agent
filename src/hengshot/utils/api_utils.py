"""
@FileName: api_utils.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/2/3 12:45
"""
from typing import Union

import aiohttp
import requests
from pydantic import SecretStr  # 如未使用 Pydantic 可移除此导入


async def async_check_llm_provider(base_url: str, api_key: str):
    """检查提供商"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"{base_url}/models",
                headers=headers,
                timeout=20
        ) as response:
            if response.status != 200:
                raise ConnectionError(f"OpenAI API returned status {response.status}")

            data = await response.json()
            if "data" not in data:
                raise ValueError("Invalid OpenAI API response")


def check_llm_provider(base_url: str, api_key: Union[str, SecretStr, None] = None) -> None:
    """
    检查 LLM 服务是否可用（OpenAI/Qwen/DeepSeek/Ollama）
    不可用时抛出异常，可用时静默返回

    Args:
        base_url: API 基础 URL（如 https://api.openai.com/v1）
        api_key: API 密钥（Ollama 本地部署可传 None）

    Raises:
        ConnectionError: 网络错误、超时、认证失败或服务不可用
        ValueError: 响应格式无效
    """
    # 清理 API Key
    key_value = None
    if api_key is not None:
        if isinstance(api_key, SecretStr):
            key_value = api_key.get_secret_value().strip()
        else:
            key_value = str(api_key).strip()
        if not key_value:
            raise ValueError("API key is empty after stripping whitespace")

    # 构建请求
    headers = {"Content-Type": "application/json"}
    if key_value:
        headers["Authorization"] = f"Bearer {key_value}"

    url = f"{base_url.rstrip('/')}/models"

    try:
        response = requests.get(url, headers=headers, timeout=20)

        if response.status_code != 200:
            try:
                err = response.json().get("error", {}).get("message", response.text[:200])
            except Exception:
                err = response.text[:200]
            raise ConnectionError(f"API unavailable (status {response.status_code}): {err}")

        data = response.json()
        # OpenAI/Qwen/DeepSeek 返回 {"data": [...]}，Ollama 返回 {"models": [...]}
        if "data" not in data and "models" not in data:
            raise ValueError("Invalid response: missing 'data' or 'models' field")

    except requests.Timeout:
        raise ConnectionError("Request timed out (20s)")
    except requests.ConnectionError as e:
        raise ConnectionError(f"Connection failed: {e}")
    except requests.RequestException as e:
        raise ConnectionError(f"Request failed: {e}")
