"""
@FileName: video_assembler_agent.py
@Description: 视频片段分割器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/22 22:00
"""
import time
from typing import Optional, List, Dict

from penshot.logger import debug, error, info
from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.base_repairable_agent import BaseRepairableAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, SeverityLevel, IssueType, RuleType
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_factory import VideoSplitterFactory
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class VideoSplitterAgent(BaseRepairableAgent[FragmentSequence, ShotSequence]):
    """视频片段分割器"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化视频片段智能体

        Args:
            llm: 语言模型实例
            config: 配置
        """
        super().__init__()
        self.llm = llm
        self.config = config or {}
        if self.config.enable_llm:
            self.splitter = VideoSplitterFactory.create_splitter(AgentMode.LLM, self.config, self.llm)
        else:
            self.splitter = VideoSplitterFactory.create_splitter(AgentMode.RULE, self.config)

        # 历史记录
        self.split_history = []
        self.last_fragment_sequence = None

        # 历史上下文相关变量
        self._common_issue_patterns: Dict[str, int] = {}
        self._focus_on_duration_control: bool = False
        self._focus_on_continuity: bool = False
        self._focus_on_description_quality: bool = False
        self._need_extra_validation: bool = False


    def process(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> Optional[FragmentSequence]:
        """
        处理视频分割

        直接使用 self.current_repair_params 和 self.current_historical_context
        """
        # 使用历史上下文优化策略
        if self.current_historical_context:
            debug("使用历史上下文优化视频分割")

            # 根据历史问题调整分割策略
            if self._focus_on_duration_control:
                debug("启用时长控制增强模式")
            if self._focus_on_continuity:
                debug("启用连续性增强模式")
            if self._focus_on_description_quality:
                debug("启用描述质量增强模式")

        return self.video_process(shot_sequence, parsed_script)

    def repair_result(self, fragment_sequence: FragmentSequence, issues: List[BasicViolation],
                      shot_sequence: ShotSequence) -> FragmentSequence:
        """实现基类的修复方法"""
        return self.repair_fragments(fragment_sequence, issues, shot_sequence)

    def detect_issues(self, fragment_sequence: FragmentSequence,
                      shot_sequence: ShotSequence) -> List[BasicViolation]:
        return self.detect_video_issues(fragment_sequence, shot_sequence)

    def _on_historical_context_applied(self) -> None:
        """历史上下文应用后的自定义处理"""
        if not self.current_historical_context:
            return

        insights = self.get_historical_insights()

        # 使用基类方法获取高频问题
        high_freq_issues = insights.get("high_freq_issues", {})

        if "fragment_duration_too_long" in high_freq_issues:
            info("根据历史经验，片段时长过长问题频繁，将加强时长控制")
            self._focus_on_duration_control = True

        if "fragment_duration_too_short" in high_freq_issues:
            info("根据历史经验，片段时长过短问题频繁，将调整分割策略")
            self._focus_on_duration_control = True

        if "fragment_time_gap" in high_freq_issues or "fragment_overlap" in high_freq_issues:
            info("根据历史经验，时间连续性问题频繁，将加强连续性检查")
            self._focus_on_continuity = True

        if "fragment_description_missing" in high_freq_issues:
            info("根据历史经验，描述缺失问题频繁，将加强描述生成")
            self._focus_on_description_quality = True

        if "fragment_no_continuity" in high_freq_issues:
            info("根据历史经验，连续性注释缺失问题频繁，将自动添加注释")
            self._focus_on_continuity = True

        # 根据质量等级调整
        if self.should_use_enhanced_validation():
            info("启用增强验证模式，将更严格检查分割质量")
            self._need_extra_validation = True

        # 使用基类方法安全获取统计信息
        historical_stats = self.current_historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_fragment_count = historical_stats.get("fragment_count", 0)
            avg_duration = historical_stats.get("avg_duration", 0)
            split_ratio = historical_stats.get("ai_split_count", 0) / max(historical_stats.get("fragment_count", 1), 1)

            if avg_fragment_count:
                debug(f"历史分割统计: 平均片段数={avg_fragment_count}, 平均时长={avg_duration:.1f}s, AI分割比例={split_ratio:.0%}")

            if avg_duration and avg_duration > 4.0:
                self._focus_on_duration_control = True
                debug("历史平均时长偏长，将优先使用更精细的分割")

        # 使用基类方法安全获取历史问题
        historical_issues = self.current_historical_context.get("historical_issues")
        if historical_issues:
            debug(f"历史问题数量: {len(historical_issues)}条，将参考避免这些问题")


    def video_process(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> Optional[FragmentSequence]:
        """视频片段分割"""
        debug("开始切割视频片段")

        # 记录历史上下文信息
        if self.current_historical_context:
            debug(f"历史上下文已加载: 常见问题模式={len(self.get_historical_insights().get('common_issues', {}))}种")

        repair_params = self.current_repair_params

        # 记录分割尝试
        attempt = len(self.split_history) + 1
        self.split_history.append({"attempt": attempt, "timestamp": time.time()})

        try:
            # 调用分割器 - 传递历史上下文
            fragment_sequence = self.splitter.cut(
                shot_sequence,
                parsed_script,
                repair_params,
                self.current_historical_context  # 传递历史上下文
            )

            if not fragment_sequence:
                error("视频片段分割失败")
                return None

            total_duration = sum(f.duration for f in fragment_sequence.fragments)
            debug(f"总时长: {total_duration:.1f}秒")
            debug(f"平均时长: {total_duration / len(fragment_sequence.fragments):.1f}秒")

            # 记录分割统计
            metadata = getattr(fragment_sequence, 'metadata', {})
            debug(f"分割统计: AI分割={metadata.get('ai_split_count', 0)}, "
                  f"规则分割={metadata.get('rule_split_count', 0)}")

            # 记录修复历史
            if repair_params and repair_params.fix_needed:
                if "repair_history" not in fragment_sequence.metadata:
                    fragment_sequence.metadata["repair_history"] = []
                fragment_sequence.metadata["repair_history"].append({
                    "timestamp": time.time(),
                    "repair_params": {
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions
                    }
                })

            self.last_fragment_sequence = fragment_sequence
            return fragment_sequence

        except Exception as e:
            print_log_exception()
            error(f"视频片段切割异常: {e}")
            return None

    def detect_video_issues(self, fragment_sequence: FragmentSequence,
                            shot_sequence: ShotSequence) -> List[BasicViolation]:
        """
        检测视频分割中的问题 - 供质量审查节点调用

        Args:
            fragment_sequence: 生成的片段序列
            shot_sequence: 原始镜头序列

        Returns:
            问题列表
        """
        issues = []

        if not fragment_sequence or not fragment_sequence.fragments:
            issues.append(BasicViolation(
                rule_code=RuleType.FRAGMENT_MISSING.code,
                rule_name=RuleType.FRAGMENT_MISSING.description,
                issue_type=IssueType.FRAGMENT,
                source_node=PipelineNode.SPLIT_VIDEO,
                description="未能生成任何视频片段",
                severity=SeverityLevel.ERROR,
                fragment_id=None,
                suggestion="请检查镜头分割结果是否正确"
            ))
            return issues

        fragments = fragment_sequence.fragments

        # 1. 检查片段数量合理性
        expected_min_fragments = max(1, len(shot_sequence.shots))
        if len(fragments) < expected_min_fragments * 0.5:
            issues.append(BasicViolation(
                rule_code=RuleType.FRAGMENT_INSUFFICIENT.code,
                rule_name=RuleType.FRAGMENT_INSUFFICIENT.description,
                issue_type=IssueType.FRAGMENT,
                source_node=PipelineNode.SPLIT_VIDEO,
                description=f"片段数量不足: {len(fragments)}个，预期至少{expected_min_fragments}个",
                severity=SeverityLevel.MODERATE,
                fragment_id=None,
                suggestion="每个镜头应至少生成1个片段"
            ))

        # 2. 检查片段时长
        for fragment in fragments:
            # 时长过短
            if fragment.duration < self.config.min_fragment_duration:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_DURATION_TOO_SHORT.code,
                    rule_name=RuleType.FRAGMENT_DURATION_TOO_SHORT.description,
                    issue_type=IssueType.DURATION,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{fragment.id}时长过短: {fragment.duration}秒",
                    severity=SeverityLevel.MAJOR,
                    fragment_id=fragment.id,
                    suggestion=f"片段时长应至少{self.config.min_fragment_duration}秒"
                ))
            # 时长过长
            elif fragment.duration > self.config.duration_split_threshold:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_DURATION_TOO_LONG.code,
                    rule_name=RuleType.FRAGMENT_DURATION_TOO_LONG.description,
                    issue_type=IssueType.DURATION,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{fragment.id}时长过长: {fragment.duration}秒",
                    severity=SeverityLevel.WARNING,
                    fragment_id=fragment.id,
                    suggestion=f"片段时长应控制在{self.config.duration_split_threshold}秒以内"
                ))

        # 3. 检查片段描述
        for fragment in fragments:
            if not fragment.description or len(fragment.description.strip()) < 5:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_DESCRIPTION_MISSING.code,
                    rule_name=RuleType.FRAGMENT_DESCRIPTION_MISSING.description,
                    issue_type=IssueType.PROMPT,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{fragment.id}描述过短或缺失",
                    severity=SeverityLevel.MODERATE,
                    fragment_id=fragment.id,
                    suggestion="为片段添加描述性内容"
                ))

        # 4. 检查连续性
        for i in range(len(fragments) - 1):
            curr = fragments[i]
            next_frag = fragments[i + 1]

            # 检查时间连续性
            expected_next_start = curr.start_time + curr.duration
            if abs(next_frag.start_time - expected_next_start) > 0.1:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_TIME_GAP.code,
                    rule_name=RuleType.FRAGMENT_TIME_GAP.description,
                    issue_type=IssueType.CONTINUITY,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{curr.id}和{next_frag.id}之间存在时间间隔: "
                                f"预期{expected_next_start}s，实际{next_frag.start_time}s",
                    severity=SeverityLevel.MAJOR,
                    fragment_id=curr.id,
                    suggestion="修复时间连续性，确保片段首尾相接"
                ))

        # 5. 检查片段重叠
        for i in range(len(fragments) - 1):
            curr = fragments[i]
            next_frag = fragments[i + 1]

            curr_end = curr.start_time + curr.duration
            if next_frag.start_time < curr_end - 0.1:  # 允许微小误差
                overlap = curr_end - next_frag.start_time
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_OVERLAP.code,
                    rule_name=RuleType.FRAGMENT_OVERLAP.description,
                    issue_type=IssueType.CONTINUITY,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{curr.id}和{next_frag.id}存在重叠: {overlap:.2f}秒",
                    severity=SeverityLevel.ERROR,
                    fragment_id=curr.id,
                    suggestion="调整片段时间，避免重叠"
                ))

        # 6. 检查元素引用
        for fragment in fragments:
            if not fragment.element_ids:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_NO_ELEMENTS.code,
                    rule_name=RuleType.FRAGMENT_NO_ELEMENTS.description,
                    issue_type=IssueType.FRAGMENT,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{fragment.id}没有关联任何剧本元素",
                    severity=SeverityLevel.WARNING,
                    fragment_id=fragment.id,
                    suggestion="为片段关联对应的剧本元素"
                ))

        # 7. 检查连续性注释
        for fragment in fragments:
            continuity_notes = getattr(fragment, 'continuity_notes', {})
            if not continuity_notes:
                issues.append(BasicViolation(
                    rule_code=RuleType.FRAGMENT_NO_CONTINUITY.code,
                    rule_name=RuleType.FRAGMENT_NO_CONTINUITY.description,
                    issue_type=IssueType.CONTINUITY,
                    source_node=PipelineNode.SPLIT_VIDEO,
                    description=f"片段{fragment.id}缺少连续性注释",
                    severity=SeverityLevel.WARNING,
                    fragment_id=fragment.id,
                    suggestion="添加连续性注释，包括角色、场景等信息"
                ))

        return issues

    def repair_fragments(self, fragment_sequence: FragmentSequence,
                         issues: List[BasicViolation],
                         shot_sequence: ShotSequence) -> FragmentSequence:
        """
        根据问题列表修复片段 - 供质量审查节点调用

        Args:
            fragment_sequence: 待修复的片段序列
            issues: 检测到的问题列表
            shot_sequence: 原始镜头序列

        Returns:
            修复后的片段序列
        """
        info(f"开始修复视频片段，发现{len(issues)}个问题")

        # 记录原始状态
        original_stats = {
            "fragment_count": len(fragment_sequence.fragments),
            "total_duration": sum(f.duration for f in fragment_sequence.fragments),
            "avg_duration": sum(f.duration for f in fragment_sequence.fragments) / len(fragment_sequence.fragments) if fragment_sequence.fragments else 0
        }

        repair_actions = []

        # 问题分类
        duration_issues = [i for i in issues if 'duration' in i.rule_code]
        description_issues = [i for i in issues if 'description' in i.rule_code]
        time_gap_issues = [i for i in issues if 'time_gap' in i.rule_code]
        overlap_issues = [i for i in issues if 'overlap' in i.rule_code]
        element_issues = [i for i in issues if 'no_elements' in i.rule_code]
        continuity_issues = [i for i in issues if 'no_continuity' in i.rule_code]

        fragments = list(fragment_sequence.fragments)

        # ========== 1. 修复时长问题 ==========
        if duration_issues:
            for issue in duration_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                fragment = self._find_fragment(fragments, fragment_id)
                if not fragment:
                    continue

                if '过短' in issue.description:
                    old_duration = fragment.duration
                    fragment.duration = self.config.min_fragment_duration
                    repair_actions.append(f"调整过短时长: {fragment_id} {old_duration}s -> {self.config.min_fragment_duration}s")
                elif '过长' in issue.description:
                    old_duration = fragment.duration
                    fragment.duration = self.config.duration_split_threshold
                    repair_actions.append(f"调整过长时长: {fragment_id} {old_duration}s -> {self.config.duration_split_threshold}s")

        # ========== 2. 修复描述问题 ==========
        if description_issues:
            for issue in description_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                fragment = self._find_fragment(fragments, fragment_id)
                if not fragment:
                    continue

                # 从关联的镜头获取描述
                if fragment.shot_id:
                    for shot in shot_sequence.shots:
                        if shot.id == fragment.shot_id:
                            fragment.description = shot.description
                            repair_actions.append(f"从镜头补充描述: {fragment_id} -> {shot.description[:50]}...")
                            break

                # 如果仍然没有描述，生成默认描述
                if not fragment.description or len(fragment.description.strip()) < 5:
                    fragment.description = f"视频片段，时长{fragment.duration}秒"
                    repair_actions.append(f"生成默认描述: {fragment_id}")

        # ========== 3. 修复时间间隔问题 ==========
        if time_gap_issues:
            # 重新计算时间，确保连续性
            current_time = 0.0
            for i, fragment in enumerate(fragments):
                old_start = fragment.start_time
                fragment.start_time = current_time
                if abs(old_start - current_time) > 0.01:
                    repair_actions.append(f"修复时间间隔: {fragment.id} {old_start}s -> {current_time}s")
                current_time += fragment.duration

        # ========== 4. 修复重叠问题 ==========
        if overlap_issues:
            # 重新调整时间，消除重叠
            current_time = 0.0
            for fragment in fragments:
                fragment.start_time = current_time
                current_time += fragment.duration
            repair_actions.append("重新调整所有片段时间，消除重叠")

        # ========== 5. 修复元素引用 ==========
        if element_issues:
            for issue in element_issues:
                fragment_id = issue.fragment_id
                if not fragment_id:
                    continue

                fragment = self._find_fragment(fragments, fragment_id)
                if not fragment:
                    continue

                # 从关联的镜头获取元素ID
                if fragment.shot_id:
                    for shot in shot_sequence.shots:
                        if shot.id == fragment.shot_id:
                            fragment.element_ids = shot.element_ids or []
                            repair_actions.append(f"关联元素: {fragment_id} -> {fragment.element_ids}")
                            break

        # ========== 6. 修复连续性注释 ==========
        if continuity_issues:
            for fragment in fragments:
                if not hasattr(fragment, 'continuity_notes') or not fragment.continuity_notes:
                    fragment.continuity_notes = {}

                # 添加默认连续性注释
                fragment.continuity_notes["continuity_check"] = "fixed"
                fragment.continuity_notes["fixed_at"] = time.time()
                repair_actions.append(f"添加连续性注释: {fragment.id}")

        # ========== 7. 更新片段ID（如果需要） ==========
        fragments = self._renormalize_fragments(fragments)

        # 更新片段序列
        fragment_sequence.fragments = fragments

        # 更新统计信息
        new_stats = {
            "fragment_count": len(fragments),
            "total_duration": sum(f.duration for f in fragments),
            "avg_duration": sum(f.duration for f in fragments) / len(fragments) if fragments else 0
        }

        # 更新metadata
        if "repair_history" not in fragment_sequence.metadata:
            fragment_sequence.metadata["repair_history"] = []

        fragment_sequence.metadata["repair_history"].append({
            "timestamp": time.time(),
            "actions": repair_actions,
            "issue_count": len(issues),
            "original_stats": original_stats,
            "new_stats": new_stats,
            "fixed_issues": len(repair_actions)
        })

        info(f"视频片段修复完成，执行了{len(repair_actions)}个修复操作")
        if repair_actions:
            debug(f"修复操作详情: {repair_actions[:10]}")

        return fragment_sequence

    def _find_fragment(self, fragments: List[VideoFragment], fragment_id: str) -> Optional[VideoFragment]:
        """根据ID查找片段"""
        for fragment in fragments:
            if fragment.id == fragment_id:
                return fragment
        return None

    def _renormalize_fragments(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """重新规范化片段ID"""
        for i, fragment in enumerate(fragments, 1):
            old_id = fragment.id
            new_id = f"frag_{i:03d}"
            if old_id != new_id:
                fragment.id = new_id
                if hasattr(fragment, 'metadata') and fragment.metadata:
                    fragment.metadata['original_id'] = old_id
        return fragments
