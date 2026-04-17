"""
@FileName: shot_splitter_factory.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 22:14
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.video_splitter.base_video_splitter import BaseVideoSplitter
from penshot.neopen.agent.video_splitter.llm_video_splitter import LLMVideoSplitter
from penshot.neopen.agent.video_splitter.rule_video_splitter import RuleVideoSplitter
from penshot.neopen.shot_config import ShotConfig


class VideoSplitterFactory:
    """分镜拆分器工厂"""

    @staticmethod
    def create_splitter(mode_type: AgentMode, config: Optional[ShotConfig], llm_client = None) -> BaseVideoSplitter:
        """创建分镜拆分器"""
        if mode_type == AgentMode.RULE:
            return RuleVideoSplitter(config)
        elif mode_type == AgentMode.LLM:
            if not llm_client:
                raise ValueError("LLM拆分器需要llm_client参数")
            return LLMVideoSplitter(llm_client, config)
        else:
            raise ValueError(f"未知的拆分器类型: {mode_type}")

# 使用工厂
# splitter = VideoSplitterFactory.create_splitter(AgentMode.RULE)
# splitter = VideoSplitterFactory.create_splitter(AgentMode.LLM, llm_client=my_llm_client)
