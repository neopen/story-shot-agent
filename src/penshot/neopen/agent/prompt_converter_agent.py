"""
@FileName: prompt_converter_agent.py
@Description: 提示词转换智能体
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/18 14:23
"""
from typing import Optional

from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.prompt_converter.prompt_converter_factory import PromptConverterFactory
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import debug, error
from penshot.utils.log_utils import print_log_exception


class PromptConverterAgent:
    """提示指令转换器"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化分镜生成智能体

        Args:
            llm: 语言模型实例
        """
        self.llm = llm
        self.config = config or {}
        if self.config.enable_llm:
            self.converter = PromptConverterFactory.create_converter(AgentMode.LLM, config, llm)
        else:
            self.converter = PromptConverterFactory.create_converter(AgentMode.RULE, config)

    def prompt_process(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript) -> AIVideoInstructions | None:
        """ 视频片段 """
        debug("开始视频转换提示词")
        try:

            return self.converter.convert(fragment_sequence, parsed_script)

        except Exception as e:
            print_log_exception()
            error(f"视频转换提示词异常: {e}")
            return None
