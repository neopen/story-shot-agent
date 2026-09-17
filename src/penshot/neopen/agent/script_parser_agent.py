"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: script_parser_agent.py
@Description: 剧本解析智能体，将整段中文剧本转换为结构化动作序列
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10 - 2025/11
"""
import re
import time
from typing import Dict, Tuple, List, Optional

from penshot.logger import debug, info, warning
from penshot.neopen.agent.script_parser.llm_script_parser import LLMScriptParser
from .base_models import AgentMode, ScriptType, ElementType
from .base_repairable_agent import BaseRepairableAgent
from .continuity_guardian.consistency_contract import GlobalConsistencyContract, SceneContract
from .quality_auditor.quality_auditor_models import BasicViolation, SeverityLevel, IssueType, RuleType
from .script_parser.rule_script_parser import RuleScriptParser
from .script_parser.script_parser_models import ParsedScript, SceneInfo, CharacterInfo, CharacterType
from .workflow.workflow_models import PipelineNode
from ..shot_config import ShotConfig


class ScriptParserAgent(BaseRepairableAgent[ParsedScript, str]):
    """优化版剧本解析智能体 - 支持工作流联动和修复"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化剧本解析智能体

        Args:
            llm: 语言模型实例（推荐GPT-4o）
            config: 配置
        """
        super().__init__()
        self.config = config or {}
        self.use_local_rules = self.config.use_local_rules  # 是否启用本地规则校验和补全

        self.script_parser = {
            AgentMode.LLM: LLMScriptParser(llm, self.config),
            AgentMode.RULE: RuleScriptParser(),
        }

        # 解析历史记录（用于修复）
        self.parsing_history = []
        self.last_parsed_script = None

    def process(self, script_text: str, knowledge_manager=None, script_id=None) -> Optional[ParsedScript]:
        """
        处理剧本解析

        Args:
            script_text: 原始剧本文本
            knowledge_manager: 知识管理器（可选）
            script_id: 剧本ID（可选）
        """
        parsed_script = self.parser_process(script_text)

        if parsed_script and knowledge_manager:
            try:
                knowledge_manager.add_parsed_script(parsed_script, script_id)
                info(f"剧本解析结果已存入知识库: {script_id}")
            except Exception as e:
                warning(f"存入知识库失败: {e}")

        return parsed_script

    def repair_result(self, parsed_script: ParsedScript, issues: List[BasicViolation],
                      original_text: str = None) -> ParsedScript:
        return self.repair_script(parsed_script, issues, original_text)

    def detect_issues(self, parsed_script: ParsedScript, original_text: str) -> List[BasicViolation]:
        return self.detect_parse_issues(parsed_script, original_text)

    def _on_historical_context_applied(self) -> None:
        """历史上下文应用后的自定义处理"""
        if not self.current_historical_context:
            return

        insights = self.get_historical_insights()

        # 使用基类方法获取高频问题
        high_freq_issues = insights.get("high_freq_issues", {})

        if "scene_insufficient" in high_freq_issues:
            info("根据历史经验，将加强场景识别")
            # 可以设置内部标志或调整提示词

        if "character_missing" in high_freq_issues:
            info("根据历史经验，将加强角色识别")

        if "dialogue_missing" in high_freq_issues:
            info("根据历史经验，将加强对话识别")

        # 根据质量等级调整
        if self.should_use_enhanced_validation():
            info("启用增强验证模式")

        # 使用基类方法安全获取统计信息
        historical_stats = self.current_historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_completeness = historical_stats.get("completeness_score", 0)
            if avg_completeness:
                debug(f"历史解析平均完整度: {avg_completeness:.0%}")

    def _on_repair_params_applied(self) -> None:
        """修复参数应用后的回调方法"""
        if not self.current_repair_params:
            return

        info(f"应用修复参数: {self.current_repair_params.issue_types}")

        # 可根据修复参数调整解析策略
        if "scene_insufficient" in self.current_repair_params.issue_types:
            self._focus_on_scene_detection = True
        if "character_missing" in self.current_repair_params.issue_types:
            self._focus_on_character_detection = True

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

        # 记录解析尝试
        attempt = len(self.parsing_history) + 1
        self.parsing_history.append({"attempt": attempt, "timestamp": time.time()})

        # 步骤1：识别格式
        format_type = self._detect_format(script_text)
        info(f"识别格式: {format_type.value}")

        # 步骤2：AI深度解析（如果提供了修复参数，传递给LLM）
        debug(" 调用AI进行深度解析...")
        try:
            parsed_script = self.script_parser.get(AgentMode.LLM).parser(
                script_text, format_type, self.current_repair_params, self.current_historical_context
            )

            # 步骤3：规则校验和补全
            if self.use_local_rules:
                info("使用本地规则校验和补全...")
                # parsed_script = self.script_parser.get(ParserType.RULE_PARSER).parser(script_text,format_type)

        except Exception as e:
            warning(f"使用LLM 解析异常: {str(e)}，尝试使用本地规则方式解析")
            parsed_script = self.script_parser.get(AgentMode.RULE).parser(
                script_text, format_type, self.current_repair_params, self.current_historical_context
            )

        # 步骤4：质量评估 - 生成问题列表
        completeness_score, warnings, issues = self._evaluate_completeness(parsed_script, script_text)

        if warnings:
            warning(f"评估解析质量：{warnings}")

        # 步骤5：设置解析置信度
        parsing_confidence = self._calculate_confidence(parsed_script)

        parsed_script.stats.update({
            "completeness_score": round(completeness_score, 2),
            "parsing_confidence": parsing_confidence,
            "parse_attempts": len(self.parsing_history)
        })

        # 保存最后解析结果
        self.last_parsed_script = parsed_script

        info(f"解析完成！最终完整性评分: {completeness_score:.2f}/1.0")
        debug(f"   场景: {len(parsed_script.scenes)}个")
        debug(f"   角色: {len(parsed_script.characters)}个")
        debug(f"   节点: {parsed_script.stats.get('total_elements', 0)}个")
        debug(f"   发现问题: {len(issues)}个")

        return parsed_script

    def process_with_contract(self, script_text: str, knowledge_manager=None,
                              script_id=None, contract: GlobalConsistencyContract = None) -> Tuple[Optional[ParsedScript], GlobalConsistencyContract]:
        """带契约的剧本解析"""

        parsed_script = self.parser_process(script_text)

        if not parsed_script:
            return None, contract

        # 创建或更新契约
        if contract is None:
            contract = GlobalConsistencyContract(
                script_id=script_id or f"script_{int(time.time())}",
                task_id=script_id or f"task_{int(time.time())}"
            )

        # 从解析结果填充契约
        for scene in parsed_script.scenes:
            scene_contract = SceneContract(
                scene_num=scene.number,
                location=getattr(scene, 'location', 'unknown'),
                time_of_day=getattr(scene, 'time_of_day', 'day'),
                characters_in_scene=[c.name for c in parsed_script.characters if c.name in scene.get_characters()],
                main_emotion=getattr(scene, 'emotion', 'neutral')
            )
            contract.register_scene(scene_contract)

        # 提取风格锚点
        if hasattr(parsed_script, 'genre'):
            contract.set_style_anchor("genre", parsed_script.genre)
        if hasattr(parsed_script, 'style_description'):
            contract.set_style_anchor("description", parsed_script.style_description[:200])

        # 保存到知识库
        if knowledge_manager:
            knowledge_manager.add_parsed_script(parsed_script, script_id)
            # 同时保存契约
            knowledge_manager.save_contract(contract)

        return parsed_script, contract

    def detect_parse_issues(self, parsed_script: ParsedScript, original_text: str) -> List[BasicViolation]:
        """
        检测解析问题 - 供质量审查节点调用

        Args:
            parsed_script: 解析后的剧本
            original_text: 原始文本

        Returns:
            问题列表
        """
        issues = []

        # 1. 检查场景完整性
        if not parsed_script.scenes:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.SCENE_MISSING,
                severity=SeverityLevel.ERROR,
                source_node=PipelineNode.PARSE_SCRIPT,
                suggestion="请检查剧本格式是否规范"
            ))
        elif len(parsed_script.scenes) < 2:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.SCENE_INSUFFICIENT,
                severity=SeverityLevel.WARNING,
                source_node=PipelineNode.PARSE_SCRIPT,
                suggestion="剧本可能过于简单或格式不完整"
            ))

        # 2. 检查角色完整性
        if not parsed_script.characters:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.CHARACTER_MISSING,
                severity=SeverityLevel.ERROR,
                source_node=PipelineNode.PARSE_SCRIPT,
                suggestion="剧本中需要包含角色信息"
            ))

        # 3. 检查对话提取
        dialogues = [e for s in parsed_script.scenes for e in s.elements if e.type == ElementType.DIALOGUE]
        dialogue_indicators = ['"', '说', '道', '：', ':']
        has_dialogue_in_original = any(ind in original_text for ind in dialogue_indicators)

        if has_dialogue_in_original and not dialogues:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.DIALOGUE_MISSING,
                severity=SeverityLevel.MAJOR,
                source_node=PipelineNode.PARSE_SCRIPT,
                suggestion="检查对话格式是否正确（需要角色名: 对话内容）"
            ))

        # 4. 检查动作提取
        actions = [e for s in parsed_script.scenes for e in s.elements if e.type == ElementType.ACTION]
        action_verbs = ['走', '跑', '坐', '站', '拿', '看', '笑', '哭', '转身']
        verb_count = sum(1 for verb in action_verbs if verb in original_text)

        if verb_count > 3 and len(actions) < verb_count * 0.3:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.ACTION_INSUFFICIENT,
                severity=SeverityLevel.MODERATE,
                source_node=PipelineNode.PARSE_SCRIPT,
                suggestion="动作描述需要更明确的表述"
            ))

        # 5. 检查角色一致性
        char_names = [c.name for c in parsed_script.characters]
        for scene in parsed_script.scenes:
            for elem in scene.elements:
                if elem.character and elem.character not in char_names:
                    issues.append(BasicViolation.create_violation(
                        rule_type=RuleType.CHARACTER_INCONSISTENT,
                        severity=SeverityLevel.MAJOR,
                        source_node=PipelineNode.PARSE_SCRIPT,
                        suggestion=f"请确保所有引用的角色都在characters列表中（当前引用：'{elem.character}'）"
                    ))

        # ========== 新增：6. 检查时长合理性 ==========
        total_duration = sum(e.duration for s in parsed_script.scenes for e in s.elements)
        if total_duration > 0:
            # 检查是否有过短的片段
            short_elements = [e for s in parsed_script.scenes for e in s.elements if e.duration < 1.0]
            if short_elements:
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.ELEMENT_DURATION_TOO_SHORT,
                    severity=SeverityLevel.WARNING,
                    source_node=PipelineNode.PARSE_SCRIPT,
                    suggestion="每个元素时长应至少1秒"
                ))

        # ========== 新增：7. 检查元素顺序 ==========
        for scene in parsed_script.scenes:
            sequences = [e.sequence for e in scene.elements]
            if sequences != sorted(sequences):
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.ELEMENT_SEQUENCE_WRONG,
                    severity=SeverityLevel.MODERATE,
                    source_node=PipelineNode.PARSE_SCRIPT,
                    suggestion="按剧情发展顺序排列元素"
                ))

        # ========== 新增：8. 检查情感标注 ==========
        for scene in parsed_script.scenes:
            for elem in scene.elements:
                if elem.type == ElementType.DIALOGUE and (not elem.emotion or elem.emotion == "neutral"):
                    # 对话内容可能包含情感，但标注为中性
                    if any(word in elem.content.lower() for word in ["笑", "开心", "哭", "伤心", "怒", "生气"]):
                        issues.append(BasicViolation.create_violation(
                            rule_type=RuleType.EMOTION_MISMATCH,
                            severity=SeverityLevel.INFO,
                            source_node=PipelineNode.PARSE_SCRIPT,
                            suggestion="根据对话内容标注正确的情感"
                        ))

        # ========== 新增：9. 检查角色描述完整性 ==========
        for char in parsed_script.characters:
            if not char.description or len(char.description) < 5:
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.CHARACTER_DESC_MISSING,
                    severity=SeverityLevel.WARNING,
                    source_node=PipelineNode.PARSE_SCRIPT,
                    suggestion=f"为角色'{char.name}'添加外貌、性格等描述信息"
                ))

        return issues

    def repair_script(self, parsed_script: ParsedScript, issues: List[BasicViolation], original_text: str = None) -> ParsedScript:
        """
        根据问题列表修复剧本 - 供质量审查节点调用

        Args:
            parsed_script: 待修复的剧本
            issues: 检测到的问题列表
            original_text: 原始剧本文本（可选，用于参考）

        Returns:
            修复后的剧本
        """
        info(f"开始修复剧本，发现{len(issues)}个问题")

        for issue in issues:
            debug(f"  问题: issue_code={issue.issue_code}, issue_desc={issue.issue_desc[:50]}...")

        # 记录原始状态用于对比
        original_stats = {
            "scene_count": len(parsed_script.scenes),
            "character_count": len(parsed_script.characters),
            "element_count": sum(len(s.elements) for s in parsed_script.scenes)
        }

        # 问题分类
        scene_issues = [i for i in issues if i.issue_type == IssueType.SCENE]
        character_issues = [i for i in issues if IssueType.CHARACTER == i.issue_type]
        dialogue_issues = [i for i in issues if IssueType.DIALOGUE == i.issue_type]
        action_issues = [i for i in issues if IssueType.ACTION == i.issue_type]
        format_issues = [i for i in issues if IssueType.FORMAT == i.issue_type]
        consistency_issues = [i for i in issues if IssueType.CONTINUITY == i.issue_type]

        # 记录修复操作
        repair_actions = []

        # ========== 1. 修复场景问题 ==========
        if scene_issues:
            # 检查是否需要创建默认场景
            if not parsed_script.scenes:
                default_scene = SceneInfo(
                    id="scene_001",
                    location="未指定地点",
                    description="默认场景（自动创建）",
                    time_of_day="未知",
                    weather="未知",
                    elements=[]
                )
                parsed_script.scenes.append(default_scene)
                repair_actions.append("创建默认场景")
                info("创建默认场景")

            # 检查场景数不足
            elif len(parsed_script.scenes) < 2:
                # 如果原始文本可用，尝试从文本中提取更多场景
                if original_text:
                    # 简单处理：按段落分割作为不同场景
                    paragraphs = [p for p in original_text.split('\n\n') if p.strip()]
                    if len(paragraphs) > len(parsed_script.scenes):
                        for i, para in enumerate(paragraphs[len(parsed_script.scenes):]):
                            if i < 3:  # 最多创建3个新场景
                                new_scene = SceneInfo(
                                    id=f"scene_{len(parsed_script.scenes) + i + 1:03d}",
                                    location=f"场景{len(parsed_script.scenes) + i + 1}",
                                    description=para[:100],
                                    time_of_day="未知",
                                    weather="未知",
                                    elements=[]
                                )
                                parsed_script.scenes.append(new_scene)
                                repair_actions.append(f"从段落创建场景: {new_scene.id}")

                    repair_actions.append("场景数不足，建议手动检查剧本结构")

        # ========== 2. 修复角色问题 ==========
        if character_issues:
            # 收集所有未定义的角色
            undefined_chars = set()
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.character and elem.character not in [c.name for c in parsed_script.characters]:
                        undefined_chars.add(elem.character)

            # 为每个未定义角色创建默认角色
            for char_name in undefined_chars:
                # 根据名称推断性别
                gender = "未知"
                if "女" in char_name or "妹" in char_name or "姐" in char_name:
                    gender = "女"
                elif "男" in char_name or "哥" in char_name or "弟" in char_name:
                    gender = "男"

                new_char = CharacterInfo(
                    name=char_name,
                    gender=gender,
                    type=CharacterType.ADULT if "孩" not in char_name else CharacterType.CHILD,
                    role="配角",
                    description=f"自动创建的角色: {char_name}",
                    key_traits=[]
                )
                parsed_script.characters.append(new_char)
                repair_actions.append(f"创建缺失角色: {char_name}")
                info(f"创建缺失角色: {char_name}")

            # 检查是否有重复角色（名称相似）
            char_names = [c.name for c in parsed_script.characters]
            for i, name1 in enumerate(char_names):
                for j, name2 in enumerate(char_names[i + 1:], i + 1):
                    # 简单相似度检查：一个包含另一个
                    if name1 in name2 or name2 in name1:
                        if len(name1) < len(name2) and name1 in name2:
                            # 可能是简称和全称，保留全称
                            repair_actions.append(f"检测到相似角色: {name1} 和 {name2}，建议确认")

        # ========== 3. 修复对话问题 ==========
        if dialogue_issues:
            # 收集所有场景中的对话
            all_dialogues = []
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.type == ElementType.DIALOGUE:
                        all_dialogues.append(elem)

            # 检查对话是否缺少角色
            for elem in all_dialogues:
                if not elem.character:
                    # 尝试从内容推断角色
                    content = elem.content.lower()
                    for char in parsed_script.characters:
                        if char.name.lower() in content:
                            elem.character = char.name
                            repair_actions.append(f"为对话添加角色: {char.name}")
                            break
                    else:
                        # 无法推断，使用默认角色
                        if parsed_script.characters:
                            elem.character = parsed_script.characters[0].name
                            repair_actions.append(f"为对话使用默认角色: {parsed_script.characters[0].name}")

            # 检查对话的情感标注
            for elem in all_dialogues:
                if not elem.emotion or elem.emotion == "neutral":
                    # 根据内容推断情感
                    content = elem.content.lower()
                    if any(word in content for word in ["笑", "开心", "高兴", "哈哈"]):
                        elem.emotion = "happy"
                        repair_actions.append(f"更新对话情感: {elem.id} -> happy")
                    elif any(word in content for word in ["哭", "伤心", "难过", "泪"]):
                        elem.emotion = "sad"
                        repair_actions.append(f"更新对话情感: {elem.id} -> sad")
                    elif any(word in content for word in ["怒", "生气", "骂", "恨"]):
                        elem.emotion = "angry"
                        repair_actions.append(f"更新对话情感: {elem.id} -> angry")

        # ========== 4. 修复动作问题 ==========
        if action_issues:
            # 收集所有动作
            all_actions = []
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.type == ElementType.ACTION:
                        all_actions.append(elem)

            # 检查动作是否缺少描述
            for elem in all_actions:
                if not elem.description or len(elem.description) < 10:
                    # 从content生成简单描述
                    if elem.content:
                        elem.description = f"动作: {elem.content}"
                        repair_actions.append(f"为动作添加描述: {elem.id}")

            # 检查动作强度
            for elem in all_actions:
                if elem.intensity == 0.5:  # 默认值
                    # 根据内容调整强度
                    content = elem.content.lower()
                    if any(word in content for word in ["猛", "用力", "剧烈", "爆发"]):
                        elem.intensity = 0.8
                        repair_actions.append(f"调整动作强度: {elem.id} -> 0.8")
                    elif any(word in content for word in ["轻轻", "缓缓", "慢慢"]):
                        elem.intensity = 0.3
                        repair_actions.append(f"调整动作强度: {elem.id} -> 0.3")

        # ========== 5. 修复格式问题 ==========
        if format_issues:
            # 统一ID格式
            for i, scene in enumerate(parsed_script.scenes, 1):
                if not scene.id.startswith('scene_'):
                    old_id = scene.id
                    scene.id = f"scene_{i:03d}"
                    repair_actions.append(f"统一场景ID: {old_id} -> {scene.id}")

                # 统一元素ID
                for j, elem in enumerate(scene.elements, 1):
                    if not elem.id.startswith('elem_'):
                        old_id = elem.id
                        elem.id = f"elem_{(i - 1) * 100 + j:03d}"
                        repair_actions.append(f"统一元素ID: {old_id} -> {elem.id}")

        # ========== 6. 修复一致性问题 ==========
        if consistency_issues:
            # 检查元素顺序是否合理
            for scene in parsed_script.scenes:
                # 按sequence排序
                scene.elements.sort(key=lambda x: x.sequence)

                # 检查sequence是否连续
                for j, elem in enumerate(scene.elements, 1):
                    if elem.sequence != j:
                        old_seq = elem.sequence
                        elem.sequence = j
                        repair_actions.append(f"调整元素顺序: {elem.id} {old_seq} -> {j}")

            # 检查时长是否合理
            for scene in parsed_script.scenes:
                for elem in scene.elements:
                    if elem.duration < 1.0:
                        elem.duration = 2.0
                        repair_actions.append(f"调整过短时长: {elem.id} 1.0 -> 2.0")
                    elif elem.duration > 10.0:
                        elem.duration = 5.0
                        repair_actions.append(f"调整过长时长: {elem.id} -> 5.0")

        # ========== 7. 更新统计信息 ==========
        new_stats = {
            "scene_count": len(parsed_script.scenes),
            "character_count": len(parsed_script.characters),
            "element_count": sum(len(s.elements) for s in parsed_script.scenes),
            "dialogue_count": sum(1 for s in parsed_script.scenes for e in s.elements if e.type == ElementType.DIALOGUE),
            "action_count": sum(1 for s in parsed_script.scenes for e in s.elements if e.type == ElementType.ACTION),
        }

        # 记录修复历史
        if not hasattr(parsed_script, 'metadata') or parsed_script.metadata is None:
            parsed_script.metadata = {}

        if "repair_history" not in parsed_script.metadata:
            parsed_script.metadata["repair_history"] = []

        parsed_script.metadata["repair_history"].append({
            "timestamp": time.time(),
            "actions": repair_actions,
            "issue_count": len(issues),
            "original_stats": original_stats,
            "new_stats": new_stats,
            "fixed_issues": len(repair_actions)
        })

        # 更新剧本的stats
        parsed_script.stats.update({
            "total_elements": new_stats["element_count"],
            "total_duration": sum(e.duration for s in parsed_script.scenes for e in s.elements),
            "dialogue_count": new_stats["dialogue_count"],
            "action_count": new_stats["action_count"],
            "completeness_score": min(1.0, parsed_script.stats.get("completeness_score", 0) + 0.1 * (len(repair_actions) > 0)),
        })

        info(f"修复完成，执行了{len(repair_actions)}个修复操作")
        if repair_actions:
            debug(f"修复操作详情: {repair_actions[:10]}")

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
                               original_text: str) -> Tuple[float, List[str], List[BasicViolation]]:
        """评估解析完整性，返回评分、警告和问题列表"""
        warnings = []
        issues = []
        score_factors = []
        weights = {
            "scenes": 0.25,
            "characters": 0.25,
            "dialogues": 0.2,
            "actions": 0.2,
            "coverage": 0.1
        }

        # 1. 场景完整性 (权重0.25)
        if not script.scenes:
            warnings.append("未识别到明确场景")
            issues.append(BasicViolation.create_violation(
                RuleType.SCENE_MISSING, severity=SeverityLevel.ERROR,
            ))
            scene_score = 0.0
        else:
            # 考虑场景数量和质量
            scene_count_score = min(1.0, len(script.scenes) / 3.0)
            # 检查场景描述质量
            scene_desc_score = sum(1 for s in script.scenes if s.description and len(s.description) > 10) / max(len(script.scenes), 1)
            scene_score = (scene_count_score + scene_desc_score) / 2
        score_factors.append(scene_score * weights["scenes"])

        # 2. 角色完整性 (权重0.25)
        if not script.characters:
            warnings.append("未识别到明确角色")
            issues.append(BasicViolation.create_violation(
                RuleType.CHARACTER_MISSING, severity=SeverityLevel.ERROR
            ))
            char_score = 0.0
        else:
            char_count_score = min(1.0, len(script.characters) / 2.0)
            char_desc_score = sum(1 for c in script.characters if c.description and len(c.description) > 5) / max(len(script.characters), 1)
            char_score = (char_count_score + char_desc_score) / 2
        score_factors.append(char_score * weights["characters"])

        # 3. 对话完整性 (权重0.2)
        dialogues = [e for s in script.scenes for e in s.elements if e.type == ElementType.DIALOGUE]
        dialogue_indicators = ['"', '说', '道', '：', ':']
        has_dialogue_in_original = any(ind in original_text for ind in dialogue_indicators)

        if has_dialogue_in_original and not dialogues:
            warnings.append("对话提取可能不完整")
            issues.append(BasicViolation.create_violation(
                RuleType.DIALOGUE_INSUFFICIENT, issue_value=len(dialogues), severity=SeverityLevel.MODERATE,
            ))
            dialogue_score = 0.3
        elif dialogues:
            # 对话数量合理性
            expected_dialogues = original_text.count('说') + original_text.count('道') + original_text.count('：')
            dialogue_score = min(1.0, len(dialogues) / max(expected_dialogues, 1))
        else:
            dialogue_score = 0.5
        score_factors.append(dialogue_score * weights["dialogues"])

        # 4. 动作完整性 (权重0.2)
        actions = [e for s in script.scenes for e in s.elements if e.type == ElementType.ACTION]
        action_verbs = ['走', '跑', '坐', '站', '拿', '看', '笑', '哭', '转身', '点头', '摇头', '开门', '关门', '吃', '喝', '打', '跳', '飞', '唱']
        verb_count = sum(1 for verb in action_verbs if verb in original_text)

        if verb_count > 0:
            action_score = min(1.0, len(actions) / max(verb_count * 0.5, 1))
        else:
            action_score = 0.5
        score_factors.append(action_score * weights["actions"])

        # 5. 总体覆盖率 (权重0.1)
        extracted_content = sum(len(str(e)) for s in script.scenes for e in s.elements) + \
                            sum(len(str(c)) for c in script.characters)
        coverage = min(1.0, extracted_content / max(len(original_text), 1) * 2)
        score_factors.append(coverage * weights["coverage"])

        # 计算总分
        completeness_score = sum(score_factors)

        # 根据问题数量调整分数
        issue_penalty = min(0.2, len(issues) * 0.05)
        completeness_score = max(0.0, min(1.0, completeness_score - issue_penalty))

        return round(completeness_score, 2), warnings, issues

    def _calculate_confidence(self, script: ParsedScript) -> Dict[str, float]:
        """计算各部分的解析置信度"""
        confidence = {}

        # 场景置信度：基于场景数量和描述质量
        if script.scenes:
            scene_count_conf = min(1.0, len(script.scenes) / 5.0)
            scene_desc_conf = sum(1 for s in script.scenes if s.description and len(s.description) > 20) / max(len(script.scenes), 1)
            confidence["scenes"] = round((scene_count_conf + scene_desc_conf) / 2, 2)

        # 角色置信度：基于角色数量和描述质量
        if script.characters:
            char_count_conf = min(1.0, len(script.characters) / 4.0)
            char_desc_conf = sum(1 for c in script.characters if c.description and len(c.description) > 10) / max(len(script.characters), 1)
            confidence["characters"] = round((char_count_conf + char_desc_conf) / 2, 2)

        # 对话置信度：基于对话完整性和情感标注
        dialogues = [e for s in script.scenes for e in s.elements if e.type == ElementType.DIALOGUE]
        if dialogues:
            dialogue_emotion_conf = sum(1 for e in dialogues if e.emotion and e.emotion != "neutral") / len(dialogues)
            dialogue_content_conf = sum(1 for e in dialogues if e.content and len(e.content) > 5) / len(dialogues)
            confidence["dialogues"] = round((dialogue_emotion_conf + dialogue_content_conf) / 2, 2)

        # 动作置信度：基于动作描述和强度
        actions = [e for s in script.scenes for e in s.elements if e.type == ElementType.ACTION]
        if actions:
            action_desc_conf = sum(1 for e in actions if e.description and len(e.description) > 10) / len(actions)
            action_intensity_conf = sum(1 for e in actions if e.intensity != 0.5) / len(actions)
            confidence["actions"] = round((action_desc_conf + action_intensity_conf) / 2, 2)

        # 总体置信度
        if confidence:
            confidence["overall"] = round(sum(confidence.values()) / len(confidence), 2)
        else:
            confidence["overall"] = 0.5

        return confidence
