"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: shot_generator_agent.py
@Description: 分镜生成智能体
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10 - 2025/11
"""
import time
from typing import Optional, List, Dict

from penshot.logger import debug, info, error
from penshot.neopen.agent.base_models import AgentMode, ElementType
from penshot.neopen.agent.base_repairable_agent import BaseRepairableAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_enum import IssueType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, SeverityLevel, RuleType
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.estimator_enhancer import DurationEnhancer
from penshot.neopen.agent.shot_segmenter.estimator.estimator_factory import estimator_factory
from penshot.neopen.agent.shot_segmenter.shot_segmenter_factory import ShotSegmenterFactory
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class ShotSegmenterAgent(BaseRepairableAgent[ShotSequence, ParsedScript]):
    """分镜生成智能体"""

    def __init__(self, llm, config: ShotConfig):
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
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.LLM, self.config, self.llm)
        else:
            self.segmenter = ShotSegmenterFactory.create_segmenter(AgentMode.RULE, self.config)

        # 时长增强器
        self.enhancer = DurationEnhancer() if self.config.enable_enhance else None

        # 配置
        self.llm_confidence = config.llm_confidence or 0.7
        self.always_enhance = config.always_enhance or True

        # 历史记录
        self.segment_history = []
        self.last_shot_sequence = None

        # 用于存储修复参数影响的配置
        self._increase_shot_count = False
        self._prefer_shorter_shots = False

        # 历史上下文相关变量
        self._common_issue_patterns: Dict[str, int] = {}
        self._focus_on_scene_continuity: bool = False
        self._focus_on_character_consistency: bool = False
        self._focus_on_shot_variety: bool = False
        self._need_extra_validation: bool = False

    def process(self, structured_script: ParsedScript) -> Optional[ShotSequence]:
        # 使用当前修复参数影响生成策略
        # if self._increase_shot_count:
        #     # 调整分镜生成器的配置
        #     self.config.set_min_shots_per_scene(3)  # 增加每个场景的镜头数
        #
        # if self._prefer_shorter_shots:
        #     # 调整时长阈值
        #     self.segmenter.set_max_shot_duration(4.0)  # 限制最长4秒

        # 使用历史上下文优化策略
        if self.current_historical_context:
            # 历史上下文已在 apply_historical_context 中处理
            # 这里可以记录使用情况
            debug("使用历史上下文优化分镜生成")

            # 根据历史问题调整生成策略
            if self._focus_on_shot_variety:
                debug("启用镜头多样性增强模式")
            if self._focus_on_character_consistency:
                debug("启用角色一致性增强模式")
            if self._prefer_shorter_shots:
                debug("启用短镜头优先模式")

        return self.shot_process(structured_script)

    def repair_result(self, shot_sequence: ShotSequence, issues: List[BasicViolation],
                      structured_script: ParsedScript) -> ShotSequence:
        return self.repair_shots(shot_sequence, issues, structured_script)

    def detect_issues(self, shot_sequence: ShotSequence, structured_script: ParsedScript) -> List[BasicViolation]:
        return self.detect_shot_issues(shot_sequence, structured_script)

    def _on_repair_params_applied(self) -> None:
        """根据修复参数调整内部配置"""
        if not self.current_repair_params:
            return

        # 重置标志
        self._increase_shot_count = False
        self._prefer_shorter_shots = False

        # 根据问题类型设置标志
        if RuleType.SHOT_INSUFFICIENT.code in self.current_repair_params.issue_types:
            self._increase_shot_count = True
            debug("修复参数：将增加镜头数量")

        if RuleType.SHOT_DURATION_TOO_LONG.code in self.current_repair_params.issue_types:
            self._prefer_shorter_shots = True
            debug("修复参数：将缩短镜头时长")

    def _on_historical_context_applied(self) -> None:
        """历史上下文应用后的自定义处理"""
        if not self.current_historical_context:
            return

        insights = self.get_historical_insights()

        # 使用基类方法获取高频问题
        high_freq_issues = insights.get("high_freq_issues", {})

        if "shot_insufficient" in high_freq_issues:
            info("根据历史经验，镜头数量不足问题频繁，将增加每个场景的镜头数")
            self._focus_on_shot_variety = True
            self._increase_shot_count = True

        if "shot_duration_too_long" in high_freq_issues:
            info("根据历史经验，镜头时长过长问题频繁，将缩短镜头时长")
            self._prefer_shorter_shots = True

        if "shot_type_uniform" in high_freq_issues:
            info("根据历史经验，镜头类型单一问题频繁，将增加镜头类型多样性")
            self._focus_on_shot_variety = True

        if "character_not_in_shots" in high_freq_issues:
            info("根据历史经验，角色缺失问题频繁，将加强角色识别")
            self._focus_on_character_consistency = True

        # 根据质量等级调整
        if self.should_use_enhanced_validation():
            info("启用增强验证模式，将更严格检查镜头质量")
            self._need_extra_validation = True

        # 使用基类方法安全获取统计信息
        historical_stats = self.current_historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_shot_count = historical_stats.get("shot_count", 0)
            avg_duration = historical_stats.get("avg_duration", 0)

            if avg_shot_count:
                debug(f"历史分镜统计: 平均镜头数={avg_shot_count}, 平均时长={avg_duration}")

            if avg_shot_count and avg_shot_count < 5:
                self._focus_on_shot_variety = True
                debug("历史平均镜头数较少，将增加镜头数量")

        # 使用基类方法安全获取历史问题
        historical_issues = self.current_historical_context.get("historical_issues")
        if historical_issues:
            debug(f"历史问题数量: {len(historical_issues)}条，将参考避免这些问题")

    def shot_process(self, structured_script: ParsedScript) -> Optional[ShotSequence]:
        """
        规划剧本的时序分段并估算时长

        Args:
            structured_script: 结构化的剧本

        Returns:
            带时长估算的镜头序列
        """
        debug("开始拆分镜头并估算时长")

        # 记录历史上下文信息
        if self.current_historical_context:
            debug(f"历史上下文已加载: 常见问题模式={len(self.get_historical_insights().get('common_issues', {}))}种")

        # 记录分割尝试
        attempt = len(self.segment_history) + 1
        self.segment_history.append({"attempt": attempt, "timestamp": time.time()})

        try:
            # 1. 先生成分镜（LLM或规则）- 传递历史上下文
            shot_sequence = self.segmenter.split(
                structured_script,
                self.current_repair_params,
                self.current_historical_context
            )

            if not shot_sequence:
                error("分镜生成失败")
                return None

            # 2. 估算每个镜头的时长
            shot_sequence = estimator_factory.estimate_sequence(shot_sequence, structured_script)

            # 3. 如果启用增强，进行后处理优化
            if self.enhancer and (self.always_enhance or self.config.enable_llm):
                debug("应用时长增强优化")
                enhanced_sequence, corrections = self.enhancer.enhance(
                    shot_sequence,
                    structured_script,
                    base_confidence=self.llm_confidence
                )

                if corrections:
                    for corr in corrections[:5]:
                        debug(f"  {corr.shot_id}: {corr.original_duration}s -> {corr.corrected_duration}s ({corr.reasons})")
                shot_sequence = enhanced_sequence

            # 4. 记录修复历史
            repair_params = self.current_repair_params
            if repair_params and repair_params.fix_needed:
                if "repair_history" not in shot_sequence.metadata:
                    shot_sequence.metadata["repair_history"] = []
                shot_sequence.metadata["repair_history"].append({
                    "timestamp": time.time(),
                    "repair_params": {
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions
                    }
                })

            self.last_shot_sequence = shot_sequence
            return shot_sequence

        except Exception as e:
            print_log_exception()
            error(f"镜头拆分异常: {e}")
            return None

    def detect_shot_issues(self, shot_sequence: ShotSequence, structured_script: ParsedScript) -> List[BasicViolation]:
        """
        检测分镜生成中的问题 - 供质量审查节点调用

        Args:
            shot_sequence: 生成的镜头序列
            structured_script: 原始结构化剧本

        Returns:
            问题列表
        """
        issues = []

        if not shot_sequence or not shot_sequence.shots:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.SHOT_MISSING,
                severity=SeverityLevel.ERROR,
                source_node=PipelineNode.SEGMENT_SHOT,
                suggestion="请检查剧本结构是否完整"
            ))
            return issues

        shots = shot_sequence.shots

        # 1. 检查镜头数量合理性
        expected_min_shots = max(1, len(structured_script.scenes) * 2)  # 每场景至少2个镜头
        if len(shots) < expected_min_shots * 0.5:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.SHOT_INSUFFICIENT,
                issue_value=len(shots),
                standard_value=expected_min_shots,
                severity=SeverityLevel.MODERATE,
                source_node=PipelineNode.SEGMENT_SHOT,
                suggestion="每个场景应至少生成2-3个镜头"
            ))

        # 2. 检查镜头时长
        for shot in shots:
            # 时长过短
            if shot.duration < 1.0:
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.SHOT_DURATION_TOO_SHORT,
                    issue_value=shot.duration,
                    standard_value=1.0,
                    severity=SeverityLevel.MAJOR,
                    fragment_id=shot.id,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    suggestion="镜头时长应至少1秒"
                ))
            # 时长过长
            elif shot.duration > 8.0:
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.SHOT_DURATION_TOO_LONG,
                    issue_value=shot.duration,
                    standard_value=8.0,
                    severity=SeverityLevel.WARNING,
                    fragment_id=shot.id,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    suggestion="镜头时长应控制在5秒以内，最多不超过8秒"
                ))

        # 3. 检查镜头描述
        for shot in shots:
            if not shot.description or len(shot.description.strip()) < 10:
                desc_len = len(shot.description.strip()) if shot.description else 0
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.SHOT_DESCRIPTION_MISSING,
                    issue_value=desc_len,
                    standard_value=10,
                    severity=SeverityLevel.MODERATE,
                    fragment_id=shot.id,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    suggestion="为镜头添加详细描述，包括构图、动作、情绪等"
                ))

        # 4. 检查镜头类型
        shot_types = [s.shot_type.value for s in shots]
        if len(set(shot_types)) < 2:
            issues.append(BasicViolation.create_violation(
                rule_type=RuleType.SHOT_TYPE_UNIFORM,
                issue_value=len(set(shot_types)),
                standard_value=2,
                severity=SeverityLevel.WARNING,
                source_node=PipelineNode.SEGMENT_SHOT,
                suggestion="使用多种镜头类型（远景、中景、特写等）增加视觉层次"
            ))

        # 5. 检查镜头连续性（相邻镜头是否合理）
        seen_repetitive_pairs = set()
        for i in range(len(shots) - 1):
            curr_shot = shots[i]
            next_shot = shots[i + 1]

            # 检查是否在同一场景
            if curr_shot.scene_id != next_shot.scene_id:
                continue

            # 检查相似镜头重复
            if curr_shot.shot_type == next_shot.shot_type:
                pair_key = f"{curr_shot.id}_{next_shot.id}"
                if pair_key not in seen_repetitive_pairs:
                    seen_repetitive_pairs.add(pair_key)
                    issues.append(BasicViolation.create_violation(
                        rule_type=RuleType.SHOT_REPETITIVE,
                        severity=SeverityLevel.WARNING,
                        fragment_id=curr_shot.id,
                        source_node=PipelineNode.SEGMENT_SHOT,
                        suggestion="考虑切换不同镜头类型增加变化"
                    ))

        # 检查角色一致性
        characters_in_shots = set()
        for shot in shots:
            if shot.main_character:
                characters_in_shots.add(shot.main_character)

        if structured_script.characters:
            expected_chars = {c.name for c in structured_script.characters}
            missing_chars = expected_chars - characters_in_shots
            if missing_chars:
                issues.append(BasicViolation.create_violation(
                    rule_type=RuleType.CHARACTER_NOT_IN_SHOTS,
                    issue_value=', '.join(sorted(missing_chars)),
                    standard_value=', '.join(sorted(expected_chars)),
                    severity=SeverityLevel.MODERATE,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    suggestion="确保所有主要角色都有对应的镜头"
                ))

        return issues

    def repair_shots(self, shot_sequence: ShotSequence, issues: List[BasicViolation],
                     structured_script: ParsedScript) -> ShotSequence:
        """
        根据问题列表修复分镜 - 供质量审查节点调用

        Args:
            shot_sequence: 待修复的镜头序列
            issues: 检测到的问题列表
            structured_script: 原始结构化剧本

        Returns:
            修复后的镜头序列
        """
        info(f"开始修复分镜，发现{len(issues)}个问题")

        # 记录原始状态
        original_stats = {
            "shot_count": len(shot_sequence.shots),
            "total_duration": sum(s.duration for s in shot_sequence.shots),
            "avg_duration": sum(s.duration for s in shot_sequence.shots) / len(shot_sequence.shots) if shot_sequence.shots else 0
        }

        repair_actions = []

        # 问题分类 - 使用 issue_type 进行主分类，更精确和类型安全
        duration_issues = [i for i in issues if i.issue_type == IssueType.DURATION]
        description_issues = [i for i in issues if i.issue_type == IssueType.PROMPT and
                             ('description' in (i.issue_code or '') or 'desc' in (i.issue_code or ''))]
        type_issues = [i for i in issues if i.issue_code in ['shot_type_uniform', 'shot_type_invalid', 'shot_type_mismatch']]
        repetitive_issues = [i for i in issues if i.issue_code == 'shot_repetitive']
        character_issues = [i for i in issues if i.issue_type == IssueType.CHARACTER]

        # ========== 1. 修复时长问题 ==========
        if duration_issues:
            for issue in duration_issues:
                shot_id = issue.fragment_id
                if not shot_id:
                    continue

                shot = self._find_shot(shot_sequence, shot_id)
                if not shot:
                    continue

                if '过短' in issue.issue_desc:
                    old_duration = shot.duration
                    shot.duration = 2.0  # 修复为2秒
                    repair_actions.append(f"调整过短时长: {shot_id} {old_duration}s -> 2.0s")
                elif '过长' in issue.issue_desc:
                    old_duration = shot.duration
                    shot.duration = min(5.0, old_duration * 0.7)  # 减少30%
                    repair_actions.append(f"调整过长时长: {shot_id} {old_duration}s -> {shot.duration:.1f}s")

        # ========== 2. 修复描述问题 ==========
        if description_issues:
            for issue in description_issues:
                shot_id = issue.fragment_id
                if not shot_id:
                    continue

                shot = self._find_shot(shot_sequence, shot_id)
                if not shot:
                    continue

                # 从剧本中获取元素信息补充描述
                if shot.element_ids:
                    for scene in structured_script.scenes:
                        for elem in scene.elements:
                            if elem.id in shot.element_ids:
                                if elem.type == ElementType.ACTION:
                                    shot.description = f"{shot.description or ''} {elem.content}".strip()
                                    repair_actions.append(f"补充镜头描述: {shot_id} 从动作元素")
                                elif elem.type == ElementType.DIALOGUE:
                                    shot.description = f"{shot.description or ''} {elem.character}说: {elem.content[:50]}".strip()
                                    repair_actions.append(f"补充镜头描述: {shot_id} 从对话元素")
                                break

                # 如果仍然没有描述，生成默认描述
                if not shot.description or len(shot.description.strip()) < 10:
                    shot.description = f"{shot.shot_type.value}镜头，时长{shot.duration}秒"
                    repair_actions.append(f"生成默认描述: {shot_id}")

        # ========== 3. 修复镜头类型单一问题 ==========
        if type_issues:
            # 为不同类型的镜头分配不同shot_type
            shot_types = [ShotType.LONG_SHOT, ShotType.MEDIUM_SHOT, ShotType.CLOSE_UP,
                          ShotType.EXTREME_CLOSE_UP, ShotType.WIDE_SHOT]

            for i, shot in enumerate(shot_sequence.shots):
                if i < len(shot_types):
                    old_type = shot.shot_type
                    shot.shot_type = shot_types[i % len(shot_types)]
                    if old_type != shot.shot_type:
                        repair_actions.append(f"调整镜头类型: {shot.id} {old_type.value} -> {shot.shot_type.value}")

        # ========== 4. 修复重复镜头问题 ==========
        if repetitive_issues:
            # 可用的镜头类型（按视觉冲击力排序）
            shot_type_pool = [
                ShotType.WIDE_SHOT,  # 全景
                ShotType.LONG_SHOT,  # 远景
                ShotType.MEDIUM_SHOT,  # 中景
                ShotType.CLOSE_UP,  # 特写
                ShotType.EXTREME_CLOSE_UP,  # 极特写
                ShotType.OVER_SHOULDER,  # 过肩
                ShotType.POV,  # 主观视角
                ShotType.TWO_SHOT  # 双人
            ]

            # 去重处理：避免重复修复同一对镜头
            processed_pairs = set()
            for i in range(len(shot_sequence.shots) - 1):
                curr = shot_sequence.shots[i]
                next_shot = shot_sequence.shots[i + 1]

                pair_key = f"{curr.id}_{next_shot.id}"
                if pair_key in processed_pairs:
                    continue

                if curr.shot_type == next_shot.shot_type:
                    processed_pairs.add(pair_key)
                    # 选择不同的镜头类型
                    alt_types = [t for t in shot_type_pool if t != curr.shot_type]
                    if alt_types:
                        new_type = alt_types[i % len(alt_types)]
                        old_type = next_shot.shot_type
                        next_shot.shot_type = new_type
                        repair_actions.append(f"调整重复镜头: {next_shot.id} {old_type.value} -> {new_type.value}")

        # ========== 5. 修复角色缺失问题 ==========
        if character_issues and structured_script.characters:
            # 为没有主要角色的镜头分配角色
            for shot in shot_sequence.shots:
                if not shot.main_character:
                    # 查找对应场景的角色
                    for scene in structured_script.scenes:
                        if scene.id == shot.scene_id:
                            # 从场景中提取角色
                            for elem in scene.elements:
                                if elem.character:
                                    shot.main_character = elem.character
                                    repair_actions.append(f"分配主角色: {shot.id} -> {elem.character}")
                                    break
                            break

        # ========== 6. 更新统计信息 ==========
        new_stats = {
            "shot_count": len(shot_sequence.shots),
            "total_duration": sum(s.duration for s in shot_sequence.shots),
            "avg_duration": sum(s.duration for s in shot_sequence.shots) / len(shot_sequence.shots) if shot_sequence.shots else 0
        }

        # 记录修复历史
        if not hasattr(shot_sequence, 'metadata'):
            shot_sequence.metadata = {}
        if "repair_history" not in shot_sequence.metadata:
            shot_sequence.metadata["repair_history"] = []

        shot_sequence.metadata["repair_history"].append({
            "timestamp": time.time(),
            "actions": repair_actions,
            "issue_count": len(issues),
            "original_stats": original_stats,
            "new_stats": new_stats,
            "fixed_issues": len(repair_actions)
        })

        info(f"分镜修复完成，执行了{len(repair_actions)}个修复操作")
        if repair_actions:
            debug(f"修复操作详情: {repair_actions[:10]}")

        return shot_sequence

    def _find_shot(self, shot_sequence: ShotSequence, shot_id: str) -> Optional[ShotInfo]:
        """根据ID查找镜头"""
        for shot in shot_sequence.shots:
            if shot.id == shot_id:
                return shot
        return None
