"""
@FileName: prompt_converter_agent.py
@Description: 提示词转换智能体
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/18 14:23
"""
import time
from typing import Optional, List, Dict

from penshot.logger import debug, error, info
from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.base_repairable_agent import BaseRepairableAgent
from penshot.neopen.agent.prompt_converter.prompt_converter_factory import PromptConverterFactory
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions, AIVideoPrompt
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, SeverityLevel, IssueType, RuleType
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception
from penshot.utils.str_count_utils import only_count_en


class PromptConverterAgent(BaseRepairableAgent[AIVideoInstructions, FragmentSequence]):
    """提示指令转换器"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化分镜生成智能体

        Args:
            llm: 语言模型实例
            config: 配置
        """
        super().__init__()
        self.llm = llm
        self.config = config or {}
        if self.config.enable_llm:
            self.converter = PromptConverterFactory.create_converter(AgentMode.LLM, config, llm)
        else:
            self.converter = PromptConverterFactory.create_converter(AgentMode.RULE, config)

        # 历史记录
        self.convert_history = []
        self.last_instructions = None

        # 历史上下文相关变量
        self._common_issue_patterns: Dict[str, int] = {}
        self._focus_on_prompt_quality: bool = False
        self._focus_on_audio_quality: bool = False
        self._focus_on_style_consistency: bool = False
        self._need_extra_validation: bool = False

    def process(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript) -> Optional[AIVideoInstructions]:
        """
        处理提示词转换

        直接使用 self.current_repair_params 和 self.current_historical_context
        """
        # 使用历史上下文优化策略
        if self.current_historical_context:
            debug("使用历史上下文优化提示词转换")

            # 根据历史问题调整转换策略
            if self._focus_on_prompt_quality:
                debug("启用提示词质量增强模式")
            if self._focus_on_audio_quality:
                debug("启用音频质量增强模式")
            if self._focus_on_style_consistency:
                debug("启用风格一致性增强模式")

        return self.prompt_process(
            fragment_sequence,
            parsed_script
        )

    def repair_result(self, instructions: AIVideoInstructions, issues: List[BasicViolation],
                      fragment_sequence: FragmentSequence) -> AIVideoInstructions:
        """实现基类的修复方法"""
        return self.repair_prompts(instructions, issues, fragment_sequence)

    def detect_issues(self, instructions: AIVideoInstructions,
                      fragment_sequence: FragmentSequence) -> List[BasicViolation]:
        return self.detect_prompt_issues(instructions, fragment_sequence)

    def _on_historical_context_applied(self) -> None:
        """历史上下文应用后的自定义处理"""
        if not self.current_historical_context:
            return

        insights = self.get_historical_insights()

        # 使用基类方法获取高频问题
        high_freq_issues = insights.get("high_freq_issues", {})

        if "prompt_too_long" in high_freq_issues:
            info("根据历史经验，提示词过长问题频繁，将加强长度控制")
            self._focus_on_prompt_quality = True

        if "prompt_too_short" in high_freq_issues:
            info("根据历史经验，提示词过短问题频繁，将加强描述完整性")
            self._focus_on_prompt_quality = True

        if "prompt_truncated" in high_freq_issues:
            info("根据历史经验，提示词截断问题频繁，将确保输出完整性")
            self._focus_on_prompt_quality = True

        if "style_inconsistent" in high_freq_issues:
            info("根据历史经验，风格不一致问题频繁，将加强风格统一")
            self._focus_on_style_consistency = True

        if "audio_prompt_missing" in high_freq_issues or "audio_prompt_too_short" in high_freq_issues:
            info("根据历史经验，音频提示词问题频繁，将加强音频生成质量")
            self._focus_on_audio_quality = True

        # 根据质量等级调整
        if self.should_use_enhanced_validation():
            info("启用增强验证模式，将更严格检查提示词质量")
            self._need_extra_validation = True

        # 使用基类方法安全获取统计信息
        historical_stats = self.current_historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_prompt_length = historical_stats.get("avg_prompt_length", 0)
            prompt_count = historical_stats.get("prompt_count", 1)
            audio_count = historical_stats.get("audio_prompt_count", 0)
            audio_count_ratio = audio_count / max(prompt_count, 1)

            if avg_prompt_length:
                debug(f"历史转换统计: 平均提示词长度={avg_prompt_length:.0f}, 音频覆盖率={audio_count_ratio:.0%}")

            if avg_prompt_length and avg_prompt_length > self.config.prompt_length_max_threshold * 0.8:
                self._focus_on_prompt_quality = True
                debug("历史平均提示词长度偏高，将优先控制长度")

            if audio_count_ratio < 0.5:
                self._focus_on_audio_quality = True
                debug("历史音频覆盖率偏低，将加强音频生成")

        # 使用基类方法安全获取成功模式
        successful_patterns = self.current_historical_context.get("successful_patterns")
        if successful_patterns:
            debug(f"已加载 {len(successful_patterns) if isinstance(successful_patterns, list) else 1} 条成功模式")


    def prompt_process(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript) -> Optional[AIVideoInstructions]:
        """视频片段转换提示词"""
        debug("开始视频转换提示词")

        historical_context = self.current_historical_context
        repair_params = self.current_repair_params

        # 记录历史上下文信息
        if historical_context:
            debug(f"历史上下文已加载: 常见问题模式={len(historical_context.get('common_issues', []))}种")

            # 使用历史上下文优化解析策略
            common_issues = historical_context.get("common_issues")
            if common_issues:
                debug(f"加载了 {len(common_issues)} 条常见问题模式，用于优化提示词生成")

            historical_stats = historical_context.get("historical_stats")
            if historical_stats:
                debug(f"历史转换统计: 平均完整度={historical_stats.get('completeness_score', 0)}")

            successful_patterns = historical_context.get("successful_patterns")
            if successful_patterns:
                debug(f"加载了 {len(successful_patterns) if isinstance(successful_patterns, list) else 1} 条成功模式")

        # 记录转换尝试
        attempt = len(self.convert_history) + 1
        self.convert_history.append({"attempt": attempt, "timestamp": time.time()})

        try:
            # 调用转换器 - 传递历史上下文
            instructions = self.converter.convert(
                fragment_sequence,
                parsed_script,
                repair_params,
                historical_context  # 传递历史上下文
            )

            if not instructions:
                error("提示词转换失败")
                return None

            debug(f"提示词转换完成，指令数: {len(instructions.fragments)}")

            # 统计提示词长度
            prompt_lengths = [len(f.prompt) for f in instructions.fragments]
            debug(f"提示词长度统计: 平均={sum(prompt_lengths) / len(prompt_lengths):.0f}, "
                  f"最小={min(prompt_lengths)}, 最大={max(prompt_lengths)}")

            # 记录音频提示词统计
            audio_count = sum(1 for f in instructions.fragments if f.audio_prompt)
            debug(f"音频提示词生成: {audio_count}/{len(instructions.fragments)}个片段")

            # 记录修复历史
            if repair_params and repair_params.fix_needed:
                if not hasattr(instructions, 'metadata'):
                    instructions.metadata = {}
                if "repair_history" not in instructions.metadata:
                    instructions.metadata["repair_history"] = []
                instructions.metadata["repair_history"].append({
                    "timestamp": time.time(),
                    "repair_params": {
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions
                    }
                })

            self.last_instructions = instructions
            return instructions

        except Exception as e:
            print_log_exception()
            error(f"视频转换提示词异常: {e}")
            return None

    def detect_prompt_issues(self, instructions: AIVideoInstructions,
                             fragment_sequence: FragmentSequence) -> List[BasicViolation]:
        """
        检测提示词转换中的问题 - 供质量审查节点调用

        Args:
            instructions: 生成的提示词指令
            fragment_sequence: 原始片段序列

        Returns:
            问题列表
        """
        issues = []

        if not instructions or not instructions.fragments:
            issues.append(BasicViolation(
                rule_code=RuleType.PROMPT_MISSING.code,
                rule_name=RuleType.PROMPT_MISSING.description,
                issue_type=IssueType.PROMPT,
                source_node=PipelineNode.CONVERT_PROMPT,
                description="未能生成任何提示词",
                severity=SeverityLevel.ERROR,
                fragment_id=None,
                suggestion="请检查片段序列是否正确"
            ))
            return issues

        prompts = instructions.fragments

        # 1. 检查提示词为空
        for prompt in prompts:
            if not prompt.prompt or not prompt.prompt.strip():
                issues.append(BasicViolation(
                    rule_code=RuleType.PROMPT_EMPTY.code,
                    rule_name=RuleType.PROMPT_EMPTY.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}的提示词为空",
                    severity=SeverityLevel.ERROR,
                    fragment_id=prompt.fragment_id,
                    suggestion="为片段添加描述性提示词"
                ))

        # 2. 检查提示词长度
        for prompt in prompts:
            prompt_length = only_count_en(prompt.prompt)

            if prompt_length > self.config.prompt_length_max_threshold:
                issues.append(BasicViolation(
                    rule_code=RuleType.PROMPT_TOO_LONG.code,
                    rule_name=RuleType.PROMPT_TOO_LONG.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}提示词过长: {prompt_length}个单词",
                    severity=SeverityLevel.WARNING,
                    fragment_id=prompt.fragment_id,
                    suggestion=f"将提示词缩短到{self.config.max_prompt_length}单词以内"
                ))
            elif prompt_length < self.config.prompt_length_min_threshold:
                issues.append(BasicViolation(
                    rule_code=RuleType.PROMPT_TOO_SHORT.code,
                    rule_name=RuleType.PROMPT_TOO_SHORT.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}提示词过短: {prompt_length}个单词",
                    severity=SeverityLevel.WARNING,
                    fragment_id=prompt.fragment_id,
                    suggestion=f"添加更多描述性内容，至少{self.config.min_prompt_length}个单词"
                ))

        # 3. 检查提示词截断
        for prompt in prompts:
            if prompt.prompt.endswith('...') or prompt.prompt.endswith('…'):
                issues.append(BasicViolation(
                    rule_code=RuleType.PROMPT_TRUNCATED.code,
                    rule_name=RuleType.PROMPT_TRUNCATED.description,
                    issue_type=IssueType.TRUNCATION,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}提示词可能被截断",
                    severity=SeverityLevel.MAJOR,
                    fragment_id=prompt.fragment_id,
                    suggestion="检查提示词是否完整，确保没有被截断"
                ))

        # 4. 检查风格一致性
        styles = set()
        for prompt in prompts:
            if prompt.style:
                styles.add(prompt.style)
        if len(styles) > 3:
            issues.append(BasicViolation(
                rule_code=RuleType.STYLE_INCONSISTENT.code,
                rule_name=RuleType.STYLE_INCONSISTENT.description,
                issue_type=IssueType.STYLE,
                source_node=PipelineNode.CONVERT_PROMPT,
                description=f"检测到{len(styles)}种不同风格，可能导致视觉不连贯",
                severity=SeverityLevel.MODERATE,
                fragment_id=None,
                suggestion="统一使用1-2种视觉风格保持连贯性"
            ))

        # 5. 检查负面提示词
        for prompt in prompts:
            if not prompt.negative_prompt or len(prompt.negative_prompt.strip()) < 10:
                issues.append(BasicViolation(
                    rule_code=RuleType.NEGATIVE_PROMPT_MISSING.code,
                    rule_name=RuleType.NEGATIVE_PROMPT_MISSING.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}缺少负面提示词",
                    severity=SeverityLevel.INFO,
                    fragment_id=prompt.fragment_id,
                    suggestion="添加负面提示词避免生成不良内容"
                ))

        # 6. 检查音频提示词
        for prompt in prompts:
            if prompt.audio_prompt:
                audio = prompt.audio_prompt
                # 检查音频提示词长度
                if len(audio.prompt) < 10:
                    issues.append(BasicViolation(
                        rule_code=RuleType.AUDIO_PROMPT_TOO_SHORT.code,
                        rule_name=RuleType.AUDIO_PROMPT_TOO_SHORT.description,
                        issue_type=IssueType.AUDIO,
                        source_node=PipelineNode.CONVERT_PROMPT,
                        description=f"片段{prompt.fragment_id}音频提示词过短",
                        severity=SeverityLevel.WARNING,
                        fragment_id=prompt.fragment_id,
                        suggestion="添加更详细的音频描述"
                    ))
                # 检查音频时长
                if audio.duration_seconds and abs(audio.duration_seconds - prompt.duration) > 0.5:
                    issues.append(BasicViolation(
                        rule_code=RuleType.AUDIO_DURATION_MISMATCH.code,
                        rule_name=RuleType.AUDIO_DURATION_MISMATCH.description,
                        issue_type=IssueType.DURATION,
                        source_node=PipelineNode.CONVERT_PROMPT,
                        description=f"片段{prompt.fragment_id}音频时长({audio.duration_seconds}s)与视频时长({prompt.duration}s)不匹配",
                        severity=SeverityLevel.MAJOR,
                        fragment_id=prompt.fragment_id,
                        suggestion="调整音频时长使其与视频片段匹配"
                    ))
            else:
                # 检查是否应该有音频提示词（基于原始片段是否有对话）
                if self._should_have_audio(prompt.fragment_id, fragment_sequence):
                    issues.append(BasicViolation(
                        rule_code=RuleType.AUDIO_PROMPT_MISSING.code,
                        rule_name=RuleType.AUDIO_PROMPT_MISSING.description,
                        issue_type=IssueType.AUDIO,
                        source_node=PipelineNode.CONVERT_PROMPT,
                        description=f"片段{prompt.fragment_id}应有音频但未生成",
                        severity=SeverityLevel.MODERATE,
                        fragment_id=prompt.fragment_id,
                        suggestion="检查片段是否包含对话，为有对话的片段生成音频提示词"
                    ))

        # 7. 检查模型支持
        for prompt in prompts:
            if prompt.model != self.config.video_model:
                issues.append(BasicViolation(
                    rule_code=RuleType.MODEL_UNSUPPORTED.code,
                    rule_name=RuleType.MODEL_UNSUPPORTED.description,
                    issue_type=IssueType.MODEL,
                    source_node=PipelineNode.CONVERT_PROMPT,
                    description=f"片段{prompt.fragment_id}使用不支持的模型: {prompt.model}",
                    severity=SeverityLevel.WARNING,
                    fragment_id=prompt.fragment_id,
                    suggestion=f"使用支持的模型: {', '.join(self.config.supported_models)}"
                ))

        return issues

    def _should_have_audio(self, fragment_id: str, fragment_sequence: FragmentSequence) -> bool:
        """判断片段是否应该有音频提示词"""
        for fragment in fragment_sequence.fragments:
            if fragment.id == fragment_id:
                # 检查片段是否有对话相关的元素
                if hasattr(fragment, 'metadata') and fragment.metadata:
                    element_ids = fragment.metadata.get("element_ids", [])
                    if element_ids:
                        # 这里需要检查是否有对话类型，简化处理
                        return True
                # 检查连续性注释中是否有角色
                if fragment.continuity_notes.get("main_character"):
                    return True
                break
        return False

    def repair_prompts(self, instructions: AIVideoInstructions,
                       issues: List[BasicViolation],
                       fragment_sequence: FragmentSequence) -> AIVideoInstructions:
        """
        根据问题列表修复提示词 - 供质量审查节点调用

        Args:
            instructions: 待修复的提示词指令
            issues: 检测到的问题列表
            fragment_sequence: 原始片段序列

        Returns:
            修复后的提示词指令
        """
        info(f"开始修复提示词，发现{len(issues)}个问题")

        # 记录原始状态
        original_stats = {
            "prompt_count": len(instructions.fragments),
            "avg_prompt_length": sum(len(p.prompt) for p in instructions.fragments) / len(instructions.fragments) if instructions.fragments else 0,
            "audio_count": sum(1 for p in instructions.fragments if p.audio_prompt)
        }

        repair_actions = []

        # 问题分类
        empty_issues = [i for i in issues if 'empty' in i.rule_code]
        length_issues = [i for i in issues if 'too_long' in i.rule_code or 'too_short' in i.rule_code]
        truncated_issues = [i for i in issues if 'truncated' in i.rule_code]
        style_issues = [i for i in issues if 'style' in i.rule_code]
        negative_issues = [i for i in issues if 'negative' in i.rule_code]
        audio_issues = [i for i in issues if 'audio' in i.rule_code]

        # 创建片段ID到原始片段的映射
        fragment_map = {f.id: f for f in fragment_sequence.fragments}

        # ========== 1. 修复空提示词 ==========
        if empty_issues:
            for issue in empty_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                prompt = self._find_prompt(instructions, fragment_id)
                if not prompt:
                    continue

                # 从原始片段获取描述
                if fragment_id in fragment_map:
                    fragment = fragment_map[fragment_id]
                    prompt.prompt = fragment.description or "视频片段"
                    repair_actions.append(f"从片段补充提示词: {fragment_id} -> {prompt.prompt[:50]}...")

        # ========== 2. 修复长度问题 ==========
        if length_issues:
            for issue in length_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                prompt = self._find_prompt(instructions, fragment_id)
                if not prompt:
                    continue

                prompt_length = only_count_en(prompt.prompt)
                if '过长' in issue.description and prompt_length > self.config.prompt_length_max_threshold:
                    # 截断提示词
                    prompt.prompt = prompt.prompt[:self.config.prompt_length_max_threshold] + "..."
                    repair_actions.append(f"截断过长提示词: {fragment_id} {prompt_length} -> {self.config.prompt_length_max_threshold} 个单词")

                elif '过短' in issue.description and prompt_length < self.config.prompt_length_min_threshold:
                    # 扩展提示词
                    if fragment_id in fragment_map:
                        fragment = fragment_map[fragment_id]
                        extension = f"，{fragment.description}" if fragment.description else "，高清画质"
                        prompt.prompt = prompt.prompt + extension
                        repair_actions.append(f"扩展过短提示词: {fragment_id} {prompt_length} -> {only_count_en(prompt.prompt)} 个单词")

        # ========== 3. 修复截断问题 ==========
        if truncated_issues:
            for issue in truncated_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                prompt = self._find_prompt(instructions, fragment_id)
                if not prompt:
                    continue

                # 移除末尾的截断标记
                if prompt.prompt.endswith('...') or prompt.prompt.endswith('…'):
                    prompt.prompt = prompt.prompt.rstrip('...').rstrip('…')
                    repair_actions.append(f"修复截断: {fragment_id}")

        # ========== 4. 修复风格不一致 ==========
        if style_issues:
            # 统一使用默认风格
            default_style = self.config.default_style
            for prompt in instructions.fragments:
                if prompt.style and prompt.style != default_style:
                    old_style = prompt.style
                    prompt.style = default_style
                    repair_actions.append(f"统一风格: {prompt.fragment_id} {old_style} -> {default_style}")

        # ========== 5. 修复负面提示词 ==========
        if negative_issues:
            default_negative = self.config.default_negative_prompt or "low quality, blurry, distorted"
            for prompt in instructions.fragments:
                if not prompt.negative_prompt or len(prompt.negative_prompt.strip()) < 10:
                    prompt.negative_prompt = default_negative
                    repair_actions.append(f"添加负面提示词: {prompt.fragment_id}")

        # ========== 6. 修复音频问题 ==========
        if audio_issues:
            for issue in audio_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                prompt = self._find_prompt(instructions, fragment_id)
                if not prompt:
                    continue

                if 'missing' in issue.rule_code:
                    # 创建默认音频提示词
                    from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIAudioPrompt, AudioModelType, AudioVoiceType

                    prompt.audio_prompt = AIAudioPrompt(
                        audio_id=f"audio{fragment_id[4:]}",
                        prompt=f"音频片段，时长{prompt.duration}秒",
                        model_type=AudioModelType.XTTSv2,
                        voice_type=AudioVoiceType.CHARACTER_DIALOGUE,
                        duration_seconds=prompt.duration
                    )
                    repair_actions.append(f"创建默认音频提示词: {fragment_id}")

                elif 'duration_mismatch' in issue.rule_code:
                    # 修复音频时长
                    if prompt.audio_prompt:
                        prompt.audio_prompt.duration_seconds = prompt.duration
                        repair_actions.append(f"修复音频时长: {fragment_id} -> {prompt.duration}s")

        # ========== 7. 更新统计信息 ==========
        new_stats = {
            "prompt_count": len(instructions.fragments),
            "avg_prompt_length": sum(len(p.prompt) for p in instructions.fragments) / len(instructions.fragments) if instructions.fragments else 0,
            "audio_count": sum(1 for p in instructions.fragments if p.audio_prompt)
        }

        # 记录修复历史
        if not hasattr(instructions, 'metadata'):
            instructions.metadata = {}
        if "repair_history" not in instructions.metadata:
            instructions.metadata["repair_history"] = []

        instructions.metadata["repair_history"].append({
            "timestamp": time.time(),
            "actions": repair_actions,
            "issue_count": len(issues),
            "original_stats": original_stats,
            "new_stats": new_stats,
            "fixed_issues": len(repair_actions)
        })

        info(f"提示词修复完成，执行了{len(repair_actions)}个修复操作")
        if repair_actions:
            debug(f"修复操作详情: {repair_actions[:10]}")

        return instructions

    def _find_prompt(self, instructions: AIVideoInstructions, fragment_id: str) -> Optional[AIVideoPrompt]:
        """根据片段ID查找提示词"""
        for prompt in instructions.fragments:
            if prompt.fragment_id == fragment_id:
                return prompt
        return None
