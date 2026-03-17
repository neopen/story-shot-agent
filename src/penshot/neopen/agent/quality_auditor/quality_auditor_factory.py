"""
@FileName: shot_splitter_factory.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 22:14
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.quality_auditor.base_quality_auditor import BaseQualityAuditor
from penshot.neopen.agent.quality_auditor.llm_quality_auditor import LLMQualityAuditor
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import RuleQualityAuditor
from penshot.neopen.shot_config import ShotConfig


class QualityAuditorFactory:
    """分镜拆分器工厂"""

    @staticmethod
    def create_auditor(mode_type: AgentMode, config: Optional[ShotConfig], llm_client = None) -> BaseQualityAuditor:
        """创建分镜拆分器"""
        if mode_type == AgentMode.RULE:
            return RuleQualityAuditor(config)
        elif mode_type == AgentMode.LLM:
            if not llm_client:
                raise ValueError("LLM拆分器需要llm_client参数")
            return LLMQualityAuditor(llm_client, config)
        else:
            raise ValueError(f"未知的拆分器类型: {mode_type}")

# 使用工厂
# auditor = QualityAuditorFactory.create_auditor(AgentMode.RULE)
# auditor = QualityAuditorFactory.create_auditor(AgentMode.LLM, llm_client=llm)
