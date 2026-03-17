"""
@FileName: script_parser_agent.py
@Description: 剧本解析智能体，将整段中文剧本转换为结构化动作序列
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import re
from typing import Dict, Tuple, List, Optional

from penshot.neopen.agent.script_parser.llm_script_parser import LLMScriptParser
from penshot.logger import debug, info, warning
from .base_models import AgentMode, ScriptType, ElementType
from .script_parser.rule_script_parser import RuleScriptParser
from .script_parser.script_parser_models import ParsedScript
from ..shot_config import ShotConfig


class ScriptParserAgent:
    """优化版剧本解析智能体"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化剧本解析智能体
        
        Args:
            llm: 语言模型实例（推荐GPT-4o）
        """
        self.config = config or {}
        self.use_local_rules = self.config.use_local_rules  # 是否启用本地规则校验和补全

        self.script_parser = {
            AgentMode.LLM: LLMScriptParser(llm, self.config),
            AgentMode.RULE: RuleScriptParser(),
        }

    def parser_process(self, script_text: str) -> Optional[ParsedScript]:
        """
        优化版剧本解析函数
        将整段中文剧本转换为结构化动作序列
        
        Args:
            script_text: 原始剧本文本

        Returns:
            结构化的剧本动作序列
        """
        debug(f"开始解析剧本: {script_text[:100]}...")

        # 步骤1：识别格式
        format_type = self._detect_format(script_text)
        info(f"识别格式: {format_type.value}")

        # 步骤2：AI深度解析
        debug(" 调用AI进行深度解析...")
        parsed_script = self.script_parser.get(AgentMode.LLM).parser(script_text, format_type)

        # 步骤3：规则校验和补全
        if self.use_local_rules:
            info("使用本地规则校验和补全...")
            # parsed_script = self.script_parser.get(ParserType.RULE_PARSER).parser(script_text,format_type)

        # 步骤4：质量评估
        completeness_score, warnings = self._evaluate_completeness(parsed_script, script_text)
        if warnings:
            warning(f"评估解析质量：{warnings}")

        # 步骤5：设置解析置信度
        parsing_confidence = self._calculate_confidence(parsed_script)

        parsed_script.stats.update({
            "completeness_score": round(completeness_score, 2),
            "parsing_confidence": parsing_confidence
        })
        info(f"解析完成！最终完整性评分: {completeness_score:.2f}/1.0")
        debug(f"   场景: {len(parsed_script.scenes)}个")
        debug(f"   角色: {len(parsed_script.characters)}个")
        debug(f"   节点: {parsed_script.stats.get('total_elements', 0)}个")

        return parsed_script

    def _detect_format(self, text: str) -> ScriptType:
        """识别剧本格式"""
        text_lower = text.lower()

        # 检查标准剧本格式标记
        if re.search(r'(INT\.|EXT\.|INT/EXT|内景|外景|场景\d+[:：])', text):
            return ScriptType.STANDARD_SCRIPT

        # 检查AI分镜格式
        if re.search(r'(镜头\d+|shot \d+|分镜\d+|画面描述[:：])', text_lower):
            return ScriptType.AI_STORYBOARD

        # 检查结构化场景
        if re.search(r'(场景[:：]|地点[:：]|时间[:：]|角色[:：])', text_lower):
            return ScriptType.STRUCTURED_SCENE

        # 检查纯对话
        dialogue_lines = re.findall(r'^[^:：]{1,20}[:：].+$', text, re.MULTILINE)
        if len(dialogue_lines) > len(text.split('\n')) * 0.7:  # 70%以上是对话行
            return ScriptType.DIALOGUE_ONLY

        # 检查是否主要是叙述性描述
        if len(re.findall(r'[。！？]', text)) > len(re.findall(r'[:："\']', text)):
            return ScriptType.NATURAL_LANGUAGE

        # 默认：混合格式
        return ScriptType.MIXED_FORMAT

    def _evaluate_completeness(self, script: ParsedScript,
                               original_text: str) -> Tuple[float, List[str]]:
        """评估解析完整性"""
        warnings = []
        score_factors = []

        # 1. 场景完整性
        if not script.scenes:
            warnings.append("未识别到明确场景")
            score_factors.append(0.3)
        else:
            scene_score = min(1.0, len(script.scenes) / 3.0)  # 至少3个场景得满分
            score_factors.append(scene_score * 0.2)

        # 2. 角色完整性
        if not script.characters:
            warnings.append("未识别到明确角色")
            score_factors.append(0.2)
        else:
            char_score = min(1.0, len(script.characters) / 2.0)  # 至少2个角色得满分
            score_factors.append(char_score * 0.2)

        # 3. 对话完整性
        dialogues = script.get_elements_by_type(ElementType.DIALOGUE)
        dialogue_density = len(dialogues) / (len(original_text) / 1000)  # 每200字符的对话数
        if dialogue_density < 0.1 and '"' in original_text or '说' in original_text:
            warnings.append("对话提取可能不完整")
            dialogue_score = 0.5
        else:
            dialogue_score = min(1.0, dialogue_density)
        score_factors.append(dialogue_score * 0.2)

        # 4. 动作完整性
        actions = script.get_elements_by_type(ElementType.ACTION)
        action_verbs = ['走', '跑', '坐', '站', '拿', '看', '笑', '哭', '转身', '点头', '摇头', '开门', '关门', '吃', '喝', '打', '跳', '飞', '唱']
        verb_count = sum(1 for verb in action_verbs if verb in original_text)
        if verb_count > 0 and len(actions) < verb_count * 0.5:
            warnings.append("动作提取可能不完整")
            action_score = 0.6
        else:
            action_score = min(1.0, len(actions) / max(verb_count, 1))
        score_factors.append(action_score * 0.2)

        # 5. 总体覆盖率
        # 计算提取的信息占文本的比例（简化的估计）
        extracted_content = sum(len(str(item)) for item in
                                script.scenes + script.characters +
                                dialogues + actions)
        coverage = min(1.0, extracted_content / len(original_text) * 3)  # 乘以3因为解析会扩展信息
        score_factors.append(coverage * 0.2)

        # 计算总分
        completeness_score = sum(score_factors)

        # 根据警告数量调整分数
        warning_penalty = min(0.3, len(warnings) * 0.05)
        completeness_score = max(0.0, completeness_score - warning_penalty)

        return round(completeness_score, 2), warnings

    def _calculate_confidence(self, script: ParsedScript) -> Dict[str, float]:
        """计算各部分的解析置信度"""
        confidence = {}

        # 基于元素数量和完整性计算置信度
        if script.scenes:
            confidence["scenes"] = min(1.0, round(len(script.scenes) * 0.3), 2)

        if script.characters:
            confidence["characters"] = min(1.0, round(len(script.characters) * 0.4), 2)

        dialogues = script.get_elements_by_type(ElementType.DIALOGUE)
        if dialogues:
            confidence["dialogues"] = min(1.0, round(len(dialogues) * 0.2), 2)

        actions = script.get_elements_by_type(ElementType.ACTION)
        if actions:
            confidence["actions"] = min(1.0, round(len(actions) * 0.3), 2)

        # 总体置信度
        if confidence:
            confidence["overall"] = round(sum(confidence.values()) / len(confidence), 2)
        else:
            confidence["overall"] = 0.5

        return confidence
