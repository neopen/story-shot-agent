"""
@FileName: llm_script_parser.py
@Description: LLM 剧本解析智能体实现
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/9 21:23
"""
import json
from typing import Any, Dict, Optional

from penshot.logger import info, warning, error, debug
from penshot.neopen.agent.base_llm_agent import BaseLLMAgent
from penshot.neopen.agent.base_models import ScriptType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.base_script_parser import BaseScriptParser
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.client.client_config import AIConfig
from penshot.neopen.tools.json_parser_tool import parse_json_response


class LLMScriptParser(BaseScriptParser, BaseLLMAgent):

    def __init__(self, llm, config: AIConfig = None):
        """
        初始化剧本解析智能体

        Args:
            llm: 语言模型实例（推荐GPT-4o）
        """
        self.config = config
        self.llm = llm

        self.system_prompts = {
            ScriptType.NATURAL_LANGUAGE: self._get_natural_language_prompt(),
            ScriptType.STANDARD_SCRIPT: self._get_standard_script_prompt(),
            ScriptType.AI_STORYBOARD: self._get_ai_storyboard_prompt(),
            ScriptType.STRUCTURED_SCENE: self._get_structured_scene_prompt(),
            ScriptType.DIALOGUE_ONLY: self._get_dialogue_only_prompt(),
            "default": self._get_default_prompt()
        }

    def parser(self, script_text: Any, script_format: ScriptType,
               repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> Optional[ParsedScript]:

        """
        优化版剧本解析函数
        将整段中文剧本转换为结构化动作序列

        Args:
            script_text: 原始剧本文本
            script_format: 原始剧本类型
            repair_params: 修复参数
            historical_context: 历史上下文（来自记忆模块）

        Returns:
            结构化的剧本动作序列
        """
        # 构建针对格式的系统提示词
        system_prompt = self.system_prompts.get(
            script_format,
            self.system_prompts["default"]
        )

        # 构建修复提示
        repair_hint = ""
        if repair_params and repair_params.fix_needed and repair_params.issue_types:
            repair_hint = f"""
                【重要：修复要求】
                    之前的解析存在以下问题：
                    - 问题类型: {', '.join(repair_params.issue_types)}
                    - 修复建议: {json.dumps(repair_params.suggestions, ensure_ascii=False) if repair_params.suggestions else '无'}

                    请根据上述建议调整解析策略，避免再次出现相同问题。
                """

        # 构建历史上下文提示
        history_hint = ""
        if historical_context:
            history_hint = self._build_history_hint(historical_context)

        # 构建用户提示词
        prompt_template = self._build_user_prompt(script_text, script_format)

        user_prompt = prompt_template.format(
            script_text=script_text,
            repair_hint=repair_hint,
            history_hint=history_hint
        )

        debug(f"AI系统提示词（摘要）: {system_prompt[:150]}...")
        debug(f"AI用户提示词（摘要）: {user_prompt[:150]}...")

        # 调用LLM
        parsed_data = self._call_llm_parse_with_retry(self.llm, system_prompt, user_prompt)

        # 转换为模型对象
        parsed_script = self._build_parsed_script(parsed_data)

        # 后处理
        parsed_script = self.post_process(parsed_script)

        # 验证结果
        if self.validate_parsed_result(parsed_script):
            info("剧本解析成功")
        else:
            warning("剧本解析结果可能存在问题")

        return parsed_script

    def _build_history_hint(self, historical_context: Dict[str, Any]) -> str:
        """构建历史上下文提示"""
        if not historical_context:
            return ""

        hints = []

        # 1. 常见问题模式
        common_issues = historical_context.get("common_issues")
        if common_issues and isinstance(common_issues, list):
            issue_counts = {}
            for issue in common_issues[-30:]:
                if isinstance(issue, dict):
                    issue_type = issue.get("issue_type", {}).get("value", "unknown")
                else:
                    issue_type = getattr(issue, "issue_type", "unknown")
                    if hasattr(issue_type, "value"):
                        issue_type = issue_type.value
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

            sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
            top_issues = [f"{t}({c}次)" for t, c in sorted_issues[:3]]

            if top_issues:
                hints.append(f"常见问题类型: {', '.join(top_issues)}，请特别注意避免这些问题。")

        # 2. 历史统计信息
        historical_stats = historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_completeness = historical_stats.get("completeness_score", 0)
            if avg_completeness < 0.6:
                hints.append(f"历史解析平均完整度较低({avg_completeness:.0%})，请提高解析质量。")
            elif avg_completeness < 0.8:
                hints.append(f"历史解析平均完整度为{avg_completeness:.0%}，请关注关键字段识别。")

        # 3. 最近策略建议
        recent_strategy = historical_context.get("recent_strategy")
        if recent_strategy and isinstance(recent_strategy, dict):
            strategy_hint = recent_strategy.get("suggestion") or recent_strategy.get("strategy")
            if strategy_hint:
                hints.append(f"参考最近成功策略: {strategy_hint}")

        if not hints:
            return ""

        return "\n".join([
            "",
            "【历史参考信息】",
            *[f"  - {hint}" for hint in hints],
            ""
        ])


    def _get_default_prompt(self) -> str:
        """获取默认系统提示词"""
        return self._get_prompt_template("script_parser_system")

    def _get_natural_language_prompt(self) -> str:
        """自然语言描述的系统提示词"""
        return self._get_default_prompt() + self._get_prompt_template("natural_language_script")

    def _get_standard_script_prompt(self) -> str:
        """标准剧本格式的系统提示词"""
        return self._get_default_prompt() + self._get_prompt_template("screenplay_format_script")

    def _get_ai_storyboard_prompt(self) -> str:
        """AI分镜脚本的系统提示词"""
        return self._get_default_prompt() + self._get_prompt_template("ai_storyboard_script")

    def _get_structured_scene_prompt(self) -> str:
        """结构化场景描述的系统提示词"""
        return self._get_default_prompt() + self._get_prompt_template("structured_scene_script")

    def _get_dialogue_only_prompt(self) -> str:
        """纯对话剧本的系统提示词"""
        return self._get_default_prompt() + self._get_prompt_template("dialogue_only_script")

    def _build_user_prompt(self, text: str, format_type: ScriptType) -> str:
        """构建用户提示词"""
        # format_instructions = {
        #     ScriptType.NATURAL_LANGUAGE: "这是一个自然语言描述的剧本，请从中提取结构化信息。",
        #     ScriptType.STANDARD_SCRIPT: "这是一个标准格式的剧本，请按照剧本格式规范解析。",
        #     ScriptType.AI_STORYBOARD: "这是一个AI生成的分镜脚本，请解析镜头描述。",
        #     ScriptType.STRUCTURED_SCENE: "这是一个结构化场景描述，请提取各部分的详细信息。",
        #     ScriptType.DIALOGUE_ONLY: "这是一个纯对话剧本，请补充推断的场景和动作信息。"
        # }
        # instruction = format_instructions.get(format_type, "请解析以下剧本内容：")

        return self._get_prompt_template("script_parser_user")

    def _parse_llm_response(self, ai_response: str) -> Dict[str, Any]:
        """解析AI返回的JSON响应"""
        try:
            parsed_result = parse_json_response(ai_response)

            # 验证基本结构
            required_sections = ["scenes", "characters"]
            for section in required_sections:
                if section not in parsed_result:
                    warning(f" AI响应缺少{section}部分")
                    parsed_result[section] = []

            return parsed_result

        except json.JSONDecodeError as e:
            error(f" AI返回了无效的JSON: {e}")
            # 如果无法提取JSON，返回空结构
            return {
                "scenes": [],
                "characters": []
            }
