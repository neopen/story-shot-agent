"""
@FileName: shot_splitter_factory.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 22:14
"""
from typing import Optional

from hengshot.hengline.agent.base_models import AgentMode
from hengshot.hengline.agent.prompt_converter.base_prompt_converter import BasePromptConverter
from hengshot.hengline.agent.prompt_converter.llm_prompt_converter import LLMPromptConverter
from hengshot.hengline.agent.prompt_converter.template_prompt_converter import TemplatePromptConverter
from hengshot.hengline.hengline_config import HengLineConfig


class PromptConverterFactory:
    """分镜拆分器工厂"""

    @staticmethod
    def create_converter(mode_type: AgentMode, config: Optional[HengLineConfig], llm_client = None) -> BasePromptConverter:
        """创建分镜拆分器"""
        if mode_type == AgentMode.RULE:
            return TemplatePromptConverter(config)
        elif mode_type == AgentMode.LLM:
            if not llm_client:
                raise ValueError("LLM拆分器需要llm_client参数")
            return LLMPromptConverter(llm_client, config)
        else:
            raise ValueError(f"未知的拆分器类型: {mode_type}")

# 使用工厂
# converter = PromptConverterFactory.create_converter(AgentMode.RULE)
# converter = PromptConverterFactory.create_converter(AgentMode.LLM, llm_client=llm)
