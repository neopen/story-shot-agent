"""
@FileName: shot_generator_agent.py
@Description: 分镜生成智能体
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10 - 2025/11
"""
from typing import Optional

from hengshot.hengline.agent.base_models import AgentMode
from hengshot.hengline.agent.script_parser.script_parser_models import ParsedScript
from hengshot.hengline.agent.shot_segmenter.shot_segmenter_factory import ShotSegmenterFactory
from hengshot.hengline.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from hengshot.hengline.hengline_config import HengLineConfig
from hengshot.logger import debug, error
from hengshot.utils.log_utils import print_log_exception


class ShotSegmenterAgent:
    """分镜生成智能体"""

    def __init__(self, llm, config: Optional[HengLineConfig] = None):
        """
        初始化分镜生成智能体
        
        Args:
            llm: 语言模型实例
        """
        self.llm = llm
        self.config = config or {}

        if self.config.enable_llm:
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.LLM, self.config, self.llm)
        else:
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.RULE, self.config)

    def shot_process(self, structured_script: ParsedScript) -> ShotSequence | None:
        """
        规划剧本的时序分段

        Args:
            structured_script: 结构化的剧本

        Returns:
            分段计划列表
        """
        debug("开始拆分镜头")
        try:

            return self.segmenter.split(structured_script)

        except Exception as e:
            print_log_exception()
            error(f"镜头拆分异常: {e}")
            return None
