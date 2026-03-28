"""
@FileName: shot_generator_agent.py
@Description: 分镜生成智能体
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import time
from typing import Optional, List

from penshot.logger import debug, info, error
from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.base_repairable_agent import BaseRepairableAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, SeverityLevel, IssueType, RuleType, QualityRepairParams
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

    def process(self, structured_script: ParsedScript) -> Optional[ShotSequence]:
        # 使用当前修复参数影响生成策略
        # if self._increase_shot_count:
        #     # 调整分镜生成器的配置
        #     self.config.set_min_shots_per_scene(3)  # 增加每个场景的镜头数
        #
        # if self._prefer_shorter_shots:
        #     # 调整时长阈值
        #     self.segmenter.set_max_shot_duration(4.0)  # 限制最长4秒

        return self.shot_process(structured_script, self.current_repair_params)

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


    def shot_process(self, structured_script: ParsedScript, repair_params: Optional[QualityRepairParams]) -> Optional[ShotSequence]:
        """
        规划剧本的时序分段并估算时长

        Args:
            structured_script: 结构化的剧本
            repair_params: 修复参数（来自工作流）

        Returns:
            带时长估算的镜头序列
        """
        debug("开始拆分镜头并估算时长")

        # 记录分割尝试
        attempt = len(self.segment_history) + 1
        self.segment_history.append({"attempt": attempt, "timestamp": time.time()})

        try:
            # 1. 先生成分镜（LLM或规则）
            shot_sequence = self.segmenter.split(structured_script, repair_params)

            if not shot_sequence:
                error("分镜生成失败")
                return None

            info(f"分镜生成完成: {len(shot_sequence.shots)}个镜头")

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
                    info(f"时长增强: 修正{len(corrections)}个镜头")
                    for corr in corrections[:5]:  # 只显示前5个
                        debug(f"  {corr.shot_id}: {corr.original_duration}s -> {corr.corrected_duration}s ({corr.reasons})")
                shot_sequence = enhanced_sequence

            # 4. 记录修复历史
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
            issues.append(BasicViolation(
                rule_code=RuleType.SHOT_MISSING.code,
                rule_name=RuleType.SHOT_MISSING.description,
                issue_type=IssueType.FRAGMENT,
                source_node=PipelineNode.SEGMENT_SHOT,
                description="未能生成任何镜头",
                severity=SeverityLevel.ERROR,
                fragment_id=None,
                suggestion="请检查剧本结构是否完整"
            ))
            return issues

        shots = shot_sequence.shots

        # 1. 检查镜头数量合理性
        expected_min_shots = max(1, len(structured_script.scenes) * 2)  # 每场景至少2个镜头
        if len(shots) < expected_min_shots * 0.5:
            issues.append(BasicViolation(
                rule_code=RuleType.SHOT_INSUFFICIENT.code,
                rule_name=RuleType.SHOT_INSUFFICIENT.description,
                issue_type=IssueType.FRAGMENT,
                source_node=PipelineNode.SEGMENT_SHOT,
                description=f"镜头数量不足: {len(shots)}个，预期至少{expected_min_shots}个",
                severity=SeverityLevel.MODERATE,
                fragment_id=None,
                suggestion="每个场景应至少生成2-3个镜头"
            ))

        # 2. 检查镜头时长
        for shot in shots:
            # 时长过短
            if shot.duration < 1.0:
                issues.append(BasicViolation(
                    rule_code=RuleType.SHOT_DURATION_TOO_SHORT.code,
                    rule_name=RuleType.SHOT_DURATION_TOO_SHORT.description,
                    issue_type=IssueType.DURATION,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    description=f"镜头{shot.id}时长过短: {shot.duration}秒",
                    severity=SeverityLevel.MAJOR,
                    fragment_id=shot.id,
                    suggestion="镜头时长应至少1秒"
                ))
            # 时长过长
            elif shot.duration > 8.0:
                issues.append(BasicViolation(
                    rule_code=RuleType.SHOT_DURATION_TOO_LONG.code,
                    rule_name=RuleType.SHOT_DURATION_TOO_LONG.description,
                    issue_type=IssueType.DURATION,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    description=f"镜头{shot.id}时长过长: {shot.duration}秒",
                    severity=SeverityLevel.WARNING,
                    fragment_id=shot.id,
                    suggestion="镜头时长应控制在5秒以内，最多不超过8秒"
                ))

        # 3. 检查镜头描述
        for shot in shots:
            if not shot.description or len(shot.description.strip()) < 10:
                issues.append(BasicViolation(
                    rule_code=RuleType.SHOT_DESCRIPTION_MISSING.code,
                    rule_name=RuleType.SHOT_DESCRIPTION_MISSING.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    description=f"镜头{shot.id}描述过短或缺失",
                    severity=SeverityLevel.MODERATE,
                    fragment_id=shot.id,
                    suggestion="为镜头添加详细描述，包括构图、动作、情绪等"
                ))

        # 4. 检查镜头类型
        shot_types = [s.shot_type.value for s in shots]
        if len(set(shot_types)) < 2:
            issues.append(BasicViolation(
                rule_code=RuleType.SHOT_TYPE_UNIFORM.code,
                rule_name=RuleType.SHOT_TYPE_UNIFORM.description,
                issue_type=IssueType.STYLE,
                source_node=PipelineNode.SEGMENT_SHOT,
                description=f"镜头类型过于单一: 只有{shot_types[0] if shot_types else '无'}",
                severity=SeverityLevel.WARNING,
                fragment_id=None,
                suggestion="使用多种镜头类型（远景、中景、特写等）增加视觉层次"
            ))

        # 5. 检查镜头连续性（相邻镜头是否合理）
        for i in range(len(shots) - 1):
            curr_shot = shots[i]
            next_shot = shots[i + 1]

            # 检查是否在同一场景
            if curr_shot.scene_id != next_shot.scene_id:
                continue

            # 检查相似镜头重复
            if curr_shot.shot_type == next_shot.shot_type:
                issues.append(BasicViolation(
                    rule_code=RuleType.SHOT_REPETITIVE.code,
                    rule_name=RuleType.SHOT_REPETITIVE.description,
                    issue_type=IssueType.CONTINUITY,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    description=f"镜头{curr_shot.id}和{next_shot.id}类型相同且连续",
                    severity=SeverityLevel.WARNING,
                    fragment_id=curr_shot.id,
                    suggestion="考虑切换不同镜头类型增加变化"
                ))

        # 6. 检查角色一致性
        characters_in_shots = set()
        for shot in shots:
            if shot.main_character:
                characters_in_shots.add(shot.main_character)

        if structured_script.characters:
            expected_chars = {c.name for c in structured_script.characters}
            missing_chars = expected_chars - characters_in_shots
            if missing_chars:
                issues.append(BasicViolation(
                    rule_code=RuleType.CHARACTER_NOT_IN_SHOTS.code,
                    rule_name=RuleType.CHARACTER_NOT_IN_SHOTS.description,
                    issue_type=IssueType.CHARACTER,
                    source_node=PipelineNode.SEGMENT_SHOT,
                    description=f"角色未在镜头中出现: {', '.join(missing_chars)}",
                    severity=SeverityLevel.MODERATE,
                    fragment_id=None,
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

        # 问题分类
        duration_issues = [i for i in issues if 'duration' in i.rule_code]
        description_issues = [i for i in issues if 'description' in i.rule_code]
        type_issues = [i for i in issues if 'type' in i.rule_code]
        repetitive_issues = [i for i in issues if 'repetitive' in i.rule_code]
        character_issues = [i for i in issues if 'character' in i.rule_code]

        # ========== 1. 修复时长问题 ==========
        if duration_issues:
            for issue in duration_issues:
                shot_id = issue.fragment_id
                if not shot_id:
                    continue

                shot = self._find_shot(shot_sequence, shot_id)
                if not shot:
                    continue

                if '过短' in issue.description:
                    old_duration = shot.duration
                    shot.duration = 2.0  # 修复为2秒
                    repair_actions.append(f"调整过短时长: {shot_id} {old_duration}s -> 2.0s")
                elif '过长' in issue.description:
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
                                if elem.type.value == "action":
                                    shot.description = f"{shot.description or ''} {elem.content}".strip()
                                    repair_actions.append(f"补充镜头描述: {shot_id} 从动作元素")
                                elif elem.type.value == "dialogue":
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
            # 为相邻相同类型的镜头添加变化
            for i in range(len(shot_sequence.shots) - 1):
                curr = shot_sequence.shots[i]
                next_shot = shot_sequence.shots[i + 1]

                if curr.shot_type == next_shot.shot_type:
                    # 改变下一个镜头的类型
                    alt_types = [t for t in ShotType if t != curr.shot_type]
                    if alt_types:
                        next_shot.shot_type = alt_types[i % len(alt_types)]
                        repair_actions.append(f"调整重复镜头: {next_shot.id} 类型改为 {next_shot.shot_type.value}")

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
