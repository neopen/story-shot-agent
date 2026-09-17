"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: RuleScriptParser.py
@Description: 规则剧本解析器 - 基于正则表达式的本地解析，作为 LLM 解析器的备用方案
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 14:38
"""
from typing import Any, Optional, Dict

from penshot.logger import error, info, warning, debug
from penshot.neopen.agent.base_models import ScriptType, ElementType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.base_script_parser import BaseScriptParser
from penshot.neopen.agent.script_parser.script_parser_models import (
    ParsedScript, CharacterInfo, EmotionType, CharacterType, GlobalMetadata
)


class RuleScriptParser(BaseScriptParser):
    """
    规则剧本解析器

    特点：
    1. 基于正则表达式的本地解析，速度快
    2. 不依赖 LLM API，适合离线场景
    3. 作为 LLM 解析器的备用方案
    4. 支持修复参数的简单应用
    """

    def __init__(self):
        """初始化规则解析器"""
        super().__init__()
        info("规则剧本解析器初始化完成")

    def parser(self, script_text: Any, script_format: ScriptType,
               repair_params: Optional[QualityRepairParams],
               historical_context: Optional[Dict[str, Any]]) -> Optional[ParsedScript]:
        """
        规则解析器 - 当 LLM 不可用或失败时的备用方案

        Args:
            script_text: 剧本文本
            script_format: 剧本格式类型
            repair_params: 修复参数
            historical_context: 历史上下文（规则解析不使用）

        Returns:
            ParsedScript 对象或 None
        """
        try:
            debug(f"开始规则解析，格式: {script_format.value if script_format else 'unknown'}")

            from penshot.neopen.tools.script_parser_tool import ScriptParserTool

            tool = ScriptParserTool()
            parsed_script = tool.parse(script_text)

            if not parsed_script or not parsed_script.scenes:
                warning("规则解析未识别到任何场景")
                return self._create_empty_parsed_script()

            # 应用修复参数（如果有）
            if repair_params and repair_params.fix_needed:
                parsed_script = self._apply_repair(parsed_script, repair_params)
                info(f"规则解析完成，已应用修复参数: {repair_params.issue_types}")
            else:
                info(f"规则解析完成: {len(parsed_script.scenes)}个场景, {len(parsed_script.characters)}个角色")

            # 后处理（更新统计信息）
            parsed_script = self.post_process(parsed_script)

            # 验证结果
            if not self.validate_parsed_result(parsed_script):
                warning("规则解析结果验证未通过，但将继续使用")

            return parsed_script

        except Exception as e:
            error(f"规则解析失败: {e}")
            return self._create_empty_parsed_script()

    def _apply_repair(self, parsed_script: ParsedScript, repair_params: QualityRepairParams) -> ParsedScript:
        """
        应用修复参数

        根据问题类型对解析结果进行修复

        Args:
            parsed_script: 原始解析结果
            repair_params: 修复参数

        Returns:
            修复后的解析结果
        """
        if not repair_params or not repair_params.fix_needed:
            return parsed_script

        repair_actions = []
        issue_types = repair_params.issue_types

        # 1. 场景问题修复
        if "scene_insufficient" in issue_types or "scene_missing" in issue_types:
            if len(parsed_script.scenes) < 2:
                # 尝试从原始文本中提取更多场景
                repair_actions.append("场景数不足，请在剧本中添加场景标题（如 INT. 地点 - 时间）")

            # 为缺少描述的场景添加默认描述
            for scene in parsed_script.scenes:
                if not scene.description or len(scene.description) < 5:
                    scene.description = f"场景: {scene.location}"
                    repair_actions.append(f"为场景 {scene.id} 添加默认描述")

        # 2. 角色问题修复
        if "character_missing" in issue_types:
            # 从元素中收集未定义的角色
            undefined_chars = set()
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.character and elem.character not in [c.name for c in parsed_script.characters]:
                        undefined_chars.add(elem.character)

            # 为未定义角色创建默认信息
            for char_name in undefined_chars:
                gender = self._infer_gender(char_name)
                new_char = CharacterInfo(
                    name=char_name,
                    gender=gender,
                    role="supporting",
                    type=CharacterType.DEFAULT,
                    description=f"角色: {char_name}",
                    key_traits=[]
                )
                parsed_script.characters.append(new_char)
                repair_actions.append(f"创建未定义角色: {char_name}")

        # 3. 对话问题修复
        if "dialogue_missing" in issue_types or "dialogue_insufficient" in issue_types:
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.type == ElementType.DIALOGUE:
                        # 为缺少角色的对话添加角色
                        if not elem.character and parsed_script.characters:
                            elem.character = parsed_script.characters[0].name
                            repair_actions.append(f"为对话 {elem.id} 添加默认角色")

                        # 为中性情感的对话推断情感
                        if elem.emotion == EmotionType.NEUTRAL.value:
                            inferred_emotion = self._infer_emotion(elem.content)
                            if inferred_emotion != EmotionType.NEUTRAL.value:
                                elem.emotion = inferred_emotion
                                repair_actions.append(f"为对话 {elem.id} 推断情感: {inferred_emotion}")

        # 4. 动作问题修复
        if "action_insufficient" in issue_types:
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.type == ElementType.ACTION:
                        # 为动作添加描述
                        if not elem.description or len(elem.description) < 10:
                            elem.description = elem.content[:100]
                            repair_actions.append(f"为动作 {elem.id} 添加描述")

                        # 调整动作强度
                        if elem.intensity == 0.5:
                            new_intensity = self._infer_intensity(elem.content)
                            if new_intensity != 0.5:
                                elem.intensity = new_intensity
                                repair_actions.append(f"调整动作强度: {elem.id} -> {new_intensity}")

        # 5. 时长问题修复
        if "duration_invalid" in issue_types:
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    # 调整过短时长
                    if elem.duration < 1.0:
                        old_duration = elem.duration
                        elem.duration = 2.0
                        repair_actions.append(f"调整过短时长: {elem.id} {old_duration}s -> 2.0s")
                    # 调整过长时长
                    elif elem.duration > 10.0:
                        old_duration = elem.duration
                        elem.duration = 5.0
                        repair_actions.append(f"调整过长时长: {elem.id} {old_duration}s -> 5.0s")

        # 6. 顺序问题修复
        if "element_sequence_wrong" in issue_types:
            for scene in parsed_script.scenes:
                # 按 sequence 排序
                scene.elements.sort(key=lambda x: x.sequence)
                # 重新设置连续序号
                for idx, elem in enumerate(scene.elements, 1):
                    if elem.sequence != idx:
                        elem.sequence = idx
                        repair_actions.append(f"调整元素顺序: {elem.id} -> {idx}")

        # 记录修复操作
        if repair_actions:
            info(f"规则解析修复完成，执行了 {len(repair_actions)} 个修复操作")
            debug(f"修复操作详情: {repair_actions[:5]}...")

        return parsed_script

    def _infer_gender(self, character_name: str) -> str:
        """根据角色名推断性别"""
        male_keywords = ["先生", "男士", "哥", "弟", "叔", "伯", "公", "爷", "爸", "爹"]
        female_keywords = ["小姐", "女士", "姐", "妹", "姨", "姑", "妈", "娘"]

        for kw in male_keywords:
            if kw in character_name:
                return "male"
        for kw in female_keywords:
            if kw in character_name:
                return "female"
        return "unknown"

    def _infer_emotion(self, content: str) -> str:
        """根据对话内容推断情感"""
        emotion_keywords = {
            EmotionType.HAPPY.value: ["笑", "开心", "高兴", "哈哈", "嘻嘻", "耶", "棒"],
            EmotionType.SAD.value: ["哭", "伤心", "难过", "泪", "痛", "悲", "哀"],
            EmotionType.ANGRY.value: ["怒", "生气", "恨", "骂", "吼", "可恶", "混蛋"],
            EmotionType.FEAR.value: ["怕", "恐惧", "害怕", "惊", "吓", "慌"],
            EmotionType.TENSE.value: ["紧张", "焦虑", "不安", "紧绷", "窒息"],
            EmotionType.SURPRISE.value: ["惊讶", "吃惊", "意外", "没想到", "竟然"],
            EmotionType.TENDER.value: ["温柔", "体贴", "关心", "爱护", "温暖"],
        }

        content_lower = content.lower()
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    return emotion
        return EmotionType.NEUTRAL.value

    def _infer_intensity(self, content: str) -> float:
        """根据动作内容推断强度"""
        high_intensity = ["猛", "用力", "剧烈", "爆发", "冲刺", "砸", "踢", "打"]
        low_intensity = ["轻轻", "缓缓", "慢慢", "悄悄", "轻柔", "微弱"]

        content_lower = content.lower()
        for kw in high_intensity:
            if kw in content_lower:
                return 0.8
        for kw in low_intensity:
            if kw in content_lower:
                return 0.3
        return 0.5

    def _create_empty_parsed_script(self) -> ParsedScript:
        """创建空的 ParsedScript（解析失败时的回退）"""
        return ParsedScript(
            title="未知",
            characters=[],
            scenes=[],
            global_metadata=GlobalMetadata(),
            stats={
                "total_elements": 0,
                "total_duration": 0,
                "dialogue_count": 0,
                "action_count": 0,
                "completeness_score": 0,
                "scene_count": 0,
                "character_count": 0
            },
            metadata={
                "parser_type": "RuleScriptParser",
                "failed": True
            }
        )

    def _get_script_format_description(self, script_format: ScriptType) -> str:
        """获取剧本格式描述（用于调试）"""
        format_map = {
            ScriptType.NATURAL_LANGUAGE: "自然语言描述",
            ScriptType.STANDARD_SCRIPT: "标准剧本格式",
            ScriptType.AI_STORYBOARD: "AI分镜脚本",
            ScriptType.STRUCTURED_SCENE: "结构化场景",
            ScriptType.DIALOGUE_ONLY: "纯对话",
            ScriptType.MIXED_FORMAT: "混合格式",
        }
        return format_map.get(script_format, "未知格式")
