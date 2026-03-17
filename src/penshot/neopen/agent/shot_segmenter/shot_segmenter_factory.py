"""
@FileName: shot_splitter_factory.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 22:14
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.shot_segmenter.base_shot_segmenter import BaseShotSegmenter
from penshot.neopen.agent.shot_segmenter.llm_shot_segmenter import LLMShotSegmenter
from penshot.neopen.agent.shot_segmenter.rule_shot_segmenter import RuleShotSegmenter
from penshot.neopen.shot_config import ShotConfig


class ShotSegmenterFactory:
    """分镜拆分器工厂"""

    @staticmethod
    def create_segmenter(mode_type: AgentMode, config: Optional[ShotConfig], llm_client = None) -> BaseShotSegmenter:
        """创建分镜拆分器"""
        if mode_type == AgentMode.RULE:
            return RuleShotSegmenter(config)
        elif mode_type == AgentMode.LLM:
            if not llm_client:
                raise ValueError("LLM拆分器需要llm_client参数")
            return LLMShotSegmenter(llm_client, config)
        else:
            raise ValueError(f"未知的拆分器类型: {mode_type}")

# 使用工厂
# segmenter = ShotSegmenterFactory.create_splitter(AgentMode.RULE)
# segmenter = ShotSegmenterFactory.create_splitter(AgentMode.LLM, llm_client=my_llm_client)