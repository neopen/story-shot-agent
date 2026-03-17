"""
@FileName: video_assembler_agent.py
@Description: 视频片段分割器
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/22 22:00
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_factory import VideoSplitterFactory
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import debug, error
from penshot.utils.log_utils import print_log_exception


class VideoSplitterAgent:
    """视频片段分割器"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化视频片段智能体

        Args:
            llm: 语言模型实例
        """
        self.llm = llm
        self.config = config or {}
        if self.config.enable_llm:
            self.splitter = VideoSplitterFactory.create_splitter(AgentMode.LLM, self.config, self.llm)
        else:
            self.splitter = VideoSplitterFactory.create_splitter(AgentMode.RULE, self.config)

    def video_process(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> FragmentSequence | None:
        """ 视频片段 """
        debug("开始切割视频片段")
        try:

            return self.splitter.cut(shot_sequence, parsed_script)

        except Exception as e:
            print_log_exception()
            error(f"视频片段切割异常: {e}")
            return None
