"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 05_custom_config.py
@Description: SDK 直调示例：运行时自定义配置（ShotConfig / LLM / 嵌入模型）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import os
import sys

from pydantic import SecretStr

from penshot import ShotConfig, ShotLanguage
from penshot.api import PenshotFunction
from penshot.config import EmbeddingBaseConfig, LLMBaseConfig

SAMPLE_SCRIPT = "雨夜，街角的咖啡店门外，女孩蹲在长椅旁擦拭被雨水浸湿的诗集。"


def build_custom_config() -> ShotConfig:
    """基于环境变量构造自定义 ShotConfig。

    配置优先级：环境变量(PENSHOT_*) > YAML(config/settings.yaml) > 默认值。
    传入 ShotConfig 的参数会覆盖默认值；LLM 密钥从环境变量读取，避免硬编码。
    """
    api_key = os.getenv("PENSHOT_LLM__DEFAULT__API_KEY", "") or os.getenv("OPENAI_API_KEY", "")

    return ShotConfig(
        llm=LLMBaseConfig(
            base_url=os.getenv("PENSHOT_LLM__DEFAULT__BASE_URL", "https://api.openai.com/v1"),
            model_name=os.getenv("PENSHOT_LLM__DEFAULT__MODEL_NAME", "gpt-4o"),
            api_key=SecretStr(api_key),
            temperature=0.3,
            timeout=60,
            max_tokens=4000,
        ),
        embed=EmbeddingBaseConfig(
            base_url=os.getenv("PENSHOT_EMBED__DEFAULT__BASE_URL", "http://localhost:11434"),
            model_name=os.getenv("PENSHOT_EMBED__DEFAULT__MODEL_NAME", "text-embedding-3-small"),
            api_key=SecretStr(os.getenv("PENSHOT_EMBED__DEFAULT__API_KEY", "")),
            timeout=60,
        ),
        # 以下为 ShotConfig 的运行时业务参数
        video_model="runway_gen2",      # 视频模型（字符串，非枚举）
        max_fragment_duration=5.0,      # AI 视频单片段最大时长（秒）
        min_fragment_duration=1.0,
        max_total_loops=20,             # 工作流最大循环次数
        workflow_timeout=1800,          # 工作流总超时（秒）
    )


def main():
    """使用自定义配置创建智能体并执行一次分镜拆分。"""
    api_key = os.getenv("PENSHOT_LLM__DEFAULT__API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("未配置 LLM API key：请设置 PENSHOT_LLM__DEFAULT__API_KEY（或复制 .env.example 为 .env）。")
        sys.exit(0)

    config = build_custom_config()
    print(f"模型: {config.llm.model_name} @ {config.llm.base_url}")
    print(f"视频模型: {config.video_model}, 最大片段时长: {config.max_fragment_duration}s")

    agent = PenshotFunction(config=config, language=ShotLanguage.ZH, max_concurrent=5)
    try:
        result = agent.breakdown_script(SAMPLE_SCRIPT, wait_timeout=600.0)
        if not result:
            print("未返回结果")
            return
        print(f"成功: {result.success}, 状态: {result.status.value}, 耗时: {result.processing_time_ms}ms")
        if result.success:
            instructions = (result.data or {}).get("instructions", {})
            project_info = instructions.get("project_info", {})
            print(f"片段数: {project_info.get('total_fragments')}, 总时长: {project_info.get('total_duration')}s")
    except Exception as exc:  # noqa: BLE001 - 示例中统一兜底打印
        print(f"调用失败: {exc}")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
