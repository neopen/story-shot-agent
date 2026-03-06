"""
@FileName: RuleScriptParser.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 14:38
"""
from typing import Any

from hengshot.hengline.agent.base_models import ScriptType
from hengshot.hengline.agent.script_parser.base_script_parser import BaseScriptParser
from hengshot.hengline.agent.script_parser.script_parser_models import ParsedScript


class RuleScriptParser(BaseScriptParser):

    def __init__(self):
        """
        初始化剧本解析智能体

        """

    def parser(self, script_text: Any, script_format: ScriptType) -> ParsedScript | None:
        pass
