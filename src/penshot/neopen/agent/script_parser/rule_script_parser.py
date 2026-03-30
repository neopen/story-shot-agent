"""
@FileName: RuleScriptParser.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 14:38
"""
from typing import Any, Optional, Dict

from penshot.neopen.agent.base_models import ScriptType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.base_script_parser import BaseScriptParser
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript


class RuleScriptParser(BaseScriptParser):

    def __init__(self):
        """
        初始化剧本解析智能体

        """

    def parser(self, script_text: Any, script_format: ScriptType
               , repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> Optional[ParsedScript]:
        pass
