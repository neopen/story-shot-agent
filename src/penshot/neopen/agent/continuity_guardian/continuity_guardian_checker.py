"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: continuity_guardian_checker.py
@Description: 连续性检查器 - 实现连续性检测逻辑
@Author: NeoPen
@Time: 2026/3/28 20:45
"""
import time
import uuid
from typing import Dict, Any, List, Set, Optional

from penshot.logger import info
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from .consistency_contract import GlobalConsistencyContract
from .continuity_guardian_models import (
    ContinuityIssue, ContinuityIssueType, ContinuitySeverity,
    CharacterState, StateSnapshot, StateTimeline, ContinuityCheckResult
)


class ContinuityGuardianChecker:
    """连续性检查器 - 负责检测跨阶段的连续性问题"""

    def __init__(self):
        self.timeline = StateTimeline()
        self.snapshot_counter = 0
        self._last_appearance = {}  # 临时存储上次外观

        # 去重缓存
        self._seen_issues: Set[str] = set()
        self._processed_shots: Set[str] = set()
        self._processed_fragments: Set[str] = set()

    def check_all_continuity(self, context: Dict[str, Any]) -> ContinuityCheckResult:
        """执行所有连续性检查"""
        # 清望去重缓存
        self._seen_issues.clear()
        self._processed_shots.clear()
        self._processed_fragments.clear()

        result = ContinuityCheckResult()

        # 1. 角色连续性检查
        self.check_character_continuity(context, result)

        # 2. 场景连续性检查
        self.check_scene_continuity(context, result)

        # 3. 动作连续性检查
        self.check_action_continuity(context, result)

        # 4. 视觉风格连续性检查
        self.check_style_continuity(context, result)

        # 5. 时间连续性检查
        self.check_time_continuity(context, result)

        # 6. 道具连续性检查
        self.check_prop_continuity(context, result)

        info(f"连续性检查完成: 发现{len(result.issues)}个问题(去重后)")

        return result

    def _create_issue(self, issue_type: ContinuityIssueType, description: str,
                      severity: ContinuitySeverity, **kwargs) -> Optional[ContinuityIssue]:
        """创建连续性问题"""
        # 生成唯一签名用于去重
        fragment_id = kwargs.get("fragment_id", "") or kwargs.get("shot_id", "") or ""
        scene_id = kwargs.get("scene_id", "") or ""
        position = kwargs.get("position", 0)
        description_hash = description[:100] if description else ""

        signature = f"{issue_type.value}_{fragment_id}_{scene_id}_{severity.value}_{position}_{description_hash}"

        # 跳过已存在的问题
        if signature in self._seen_issues:
            return None

        self._seen_issues.add(signature)

        # 截断过长的描述（限制500字符）
        if len(description) > 500:
            description = description[:497] + "..."

        return ContinuityIssue(
            id=f"{issue_type.value}_{uuid.uuid4().hex[:8]}",
            type=issue_type,
            description=description,
            severity=severity,
            **kwargs
        )

    def check_character_continuity(self, context: Dict[str, Any],
                                   result: ContinuityCheckResult) -> None:
        """检查角色连续性"""
        parsed_script = context.get("parsed_script")
        shot_sequence = context.get("shot_sequence")

        if not parsed_script or not shot_sequence:
            return

        # 收集所有角色
        characters = {c.name: c for c in parsed_script.characters}

        # 跟踪角色出现情况
        character_appearances = {char: [] for char in characters.keys()}

        # 去重：跟踪已处理的角色-场景对
        processed_character_scene = set()

        for shot in shot_sequence.shots:
            if shot.main_character and shot.main_character in character_appearances:
                character_appearances[shot.main_character].append(shot.id)

        # 检查角色是否在应该出现的场景中出现
        for scene in parsed_script.scenes:
            scene_characters = set()
            for elem in scene.elements:
                if elem.character:
                    scene_characters.add(elem.character)

            for char in scene_characters:
                # 去重：避免重复报告同一角色在同一场景的问题
                char_scene_key = f"{char}_{scene.id}"
                if char_scene_key in processed_character_scene:
                    continue

                if char not in character_appearances or not character_appearances[char]:
                    processed_character_scene.add(char_scene_key)

                    issue = self._create_issue(
                        issue_type=ContinuityIssueType.CHARACTER_MISSING,
                        description=f"角色'{char}'在场景{scene.id}中有对话但无对应镜头",
                        severity=ContinuitySeverity.MAJOR,
                        scene_id=scene.id,
                        suggestion=f"为角色'{char}'添加镜头",
                        source_stage=PipelineNode.SEGMENT_SHOT.value,
                        auto_fixable=True
                    )
                    if issue:
                        result.add_issue(issue)

        # 检查角色外观连续性（基于提示词）
        instructions = context.get("instructions")
        if instructions:
            for i, prompt in enumerate(instructions.fragments):
                # 去重：跳过已处理的片段
                if prompt.fragment_id in self._processed_fragments:
                    continue
                self._processed_fragments.add(prompt.fragment_id)

                if prompt.main_character:
                    self._check_character_appearance_continuity(
                        prompt.main_character,
                        prompt.prompt,
                        i,
                        prompt.fragment_id,
                        result
                    )

    def _check_character_appearance_continuity(self, character: str, prompt: str,
                                               index: int, fragment_id: str,
                                               result: ContinuityCheckResult):
        """检查角色外观连续性"""
        # 检测关键外观特征是否一致
        appearance_keywords = {
            "服装": ["穿", "戴", "着", "衣服", "裙子", "裤子", "衬衫"],
            "发型": ["长发", "短发", "马尾", "卷发", "直发"],
            "配饰": ["眼镜", "帽子", "围巾", "项链", "耳环"]
        }

        current_features = {}
        for category, keywords in appearance_keywords.items():
            for kw in keywords:
                if kw in prompt:
                    current_features[category] = kw
                    break

        if character in self._last_appearance:
            last = self._last_appearance[character]
            for category, feature in current_features.items():
                if category in last and last[category] != feature:
                    issue = self._create_issue(
                        issue_type=ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
                        description=f"角色'{character}'的{category}发生变化: {last.get(category)} -> {feature}",
                        severity=ContinuitySeverity.WARNING,
                        fragment_id=fragment_id,
                        position=index,
                        suggestion="保持角色外观一致性",
                        source_stage=PipelineNode.CONVERT_PROMPT.value,
                        auto_fixable=True
                    )
                    if issue:
                        result.add_issue(issue)

        self._last_appearance[character] = current_features

    def check_scene_continuity(self, context: Dict[str, Any],
                               result: ContinuityCheckResult) -> None:
        """检查场景连续性"""
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence or len(shot_sequence.shots) < 2:
            return

        prev_scene = None
        scene_jump_count = 0
        seen_jumps = set()  # 场景跳过去重

        for i, shot in enumerate(shot_sequence.shots):
            # 去重：跳过已处理的镜头
            if shot.id in self._processed_shots:
                continue
            self._processed_shots.add(shot.id)

            if prev_scene and prev_scene != shot.scene_id:
                # 去重：避免重复报告相同的场景跳转
                jump_key = f"{prev_scene}_{shot.scene_id}"
                if jump_key not in seen_jumps:
                    seen_jumps.add(jump_key)
                    scene_jump_count += 1

                    # 检查是否需要过渡镜头
                    if i > 0 and i < len(shot_sequence.shots) - 1:
                        prev_shot = shot_sequence.shots[i - 1]
                        next_shot = shot_sequence.shots[i + 1] if i + 1 < len(shot_sequence.shots) else None

                        if next_shot and prev_shot.shot_type == next_shot.shot_type:
                            issue = self._create_issue(
                                issue_type=ContinuityIssueType.SCENE_JUMP,
                                description=f"场景切换突兀: {prev_scene} -> {shot.scene_id}",
                                severity=ContinuitySeverity.WARNING,
                                shot_id=shot.id,
                                position=i,
                                suggestion="添加过渡镜头使场景切换更自然",
                                source_stage=PipelineNode.SEGMENT_SHOT.value,
                                auto_fixable=True
                            )
                            if issue:
                                result.add_issue(issue)
            prev_scene = shot.scene_id

        if scene_jump_count > len(shot_sequence.shots) * 0.3:
            issue = self._create_issue(
                issue_type=ContinuityIssueType.SCENE_TOO_FREQUENT,
                description=f"场景切换过于频繁: {scene_jump_count}次切换于{len(shot_sequence.shots)}个镜头中",
                severity=ContinuitySeverity.MODERATE,
                suggestion="减少场景切换频率或增加过渡效果",
                source_stage=PipelineNode.SEGMENT_SHOT.value
            )
            if issue:
                result.add_issue(issue)

    def check_action_continuity(self, context: Dict[str, Any],
                                result: ContinuityCheckResult) -> None:
        """检查动作连续性"""
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence or len(shot_sequence.shots) < 2:
            return

        action_state = {}
        action_keywords = ["走", "跑", "跳", "转身", "坐下", "站起", "拿起", "放下"]

        for i, shot in enumerate(shot_sequence.shots):
            # 去重：跳过已处理的镜头
            if shot.id in self._processed_shots:
                continue

            current_actions = [kw for kw in action_keywords if kw in shot.description]

            if shot.main_character and current_actions:
                if shot.main_character in action_state:
                    last_action = action_state[shot.main_character]
                    if last_action and current_actions[0] != last_action:
                        # 去重：避免重复报告相同的动作变化
                        action_key = f"{shot.main_character}_{last_action}_{current_actions[0]}"
                        if not hasattr(self, '_seen_actions'):
                            self._seen_actions = set()
                        if action_key not in self._seen_actions:
                            self._seen_actions.add(action_key)

                            issue = self._create_issue(
                                issue_type=ContinuityIssueType.ACTION_BREAK,
                                description=f"角色'{shot.main_character}'动作不连续: {last_action} -> {current_actions[0]}",
                                severity=ContinuitySeverity.MODERATE,
                                shot_id=shot.id,
                                position=i,
                                suggestion="确保动作前后连贯",
                                source_stage=PipelineNode.SEGMENT_SHOT.value,
                                auto_fixable=True
                            )
                            if issue:
                                result.add_issue(issue)
                action_state[shot.main_character] = current_actions[0]

    def check_style_continuity(self, context: Dict[str, Any],
                               result: ContinuityCheckResult) -> None:
        """检查视觉风格连续性"""
        instructions = context.get("instructions")

        if not instructions or len(instructions.fragments) < 2:
            return

        styles = []
        style_count = {}

        # 记录已处理的关键词
        seen_keywords = set()

        for prompt in instructions.fragments:
            # 去重：跳过已处理的片段
            if prompt.fragment_id in self._processed_fragments:
                continue
            self._processed_fragments.add(prompt.fragment_id)

            if prompt.style:
                styles.append(prompt.style)
                style_count[prompt.style] = style_count.get(prompt.style, 0) + 1

                # 检查风格关键词一致性
                style_keywords = prompt.style.lower().split()
                for kw in style_keywords:
                    if len(kw) > 3:  # 忽略过短的词
                        seen_keywords.add(kw)

        unique_styles = set(styles)
        if len(unique_styles) > 2:
            # 限制风格列表长度，避免描述过长
            style_list = list(unique_styles)
            if len(style_list) > 5:
                style_list = style_list[:5] + ["..."]

            # 去重：避免重复报告
            style_key = f"style_{len(unique_styles)}_{hash(str(sorted(style_list)))}"
            if not hasattr(self, '_seen_style_issues'):
                self._seen_style_issues = set()
            if style_key not in self._seen_style_issues:
                self._seen_style_issues.add(style_key)

                issue = self._create_issue(
                    issue_type=ContinuityIssueType.STYLE_INCONSISTENT,
                    description=f"检测到{len(unique_styles)}种不同风格: {', '.join(style_list)}",
                    severity=ContinuitySeverity.MODERATE,
                    suggestion="统一使用1-2种视觉风格保持连贯性",
                    source_stage=PipelineNode.CONVERT_PROMPT.value
                )
                if issue:
                    result.add_issue(issue)

    def check_time_continuity(self, context: Dict[str, Any],
                              result: ContinuityCheckResult) -> None:
        """检查时间连续性"""
        fragment_sequence = context.get("fragment_sequence")

        if not fragment_sequence or len(fragment_sequence.fragments) < 2:
            return

        fragments = fragment_sequence.fragments

        # 记录已处理的间隔
        seen_gaps = set()
        seen_overlaps = set()

        for i in range(len(fragments) - 1):
            curr = fragments[i]
            nxt = fragments[i + 1]

            # 去重：跳过已处理的片段对
            pair_key = f"{curr.id}_{nxt.id}"

            expected_start = curr.start_time + curr.duration

            if abs(nxt.start_time - expected_start) > 0.1:
                if nxt.start_time > expected_start:
                    gap = nxt.start_time - expected_start
                    if pair_key not in seen_gaps:
                        seen_gaps.add(pair_key)
                        issue = self._create_issue(
                            issue_type=ContinuityIssueType.TIME_GAP,
                            description=f"片段间存在时间间隙: {gap:.2f}秒 ({curr.id} -> {nxt.id})",
                            severity=ContinuitySeverity.MAJOR,
                            fragment_id=curr.id,
                            position=i,
                            suggestion="修复时间连续性，确保片段首尾相接",
                            source_stage=PipelineNode.SPLIT_VIDEO.value,
                            auto_fixable=True
                        )
                        if issue:
                            result.add_issue(issue)
                else:
                    overlap = expected_start - nxt.start_time
                    if pair_key not in seen_overlaps:
                        seen_overlaps.add(pair_key)
                        issue = self._create_issue(
                            issue_type=ContinuityIssueType.TIME_OVERLAP,
                            description=f"片段间存在时间重叠: {overlap:.2f}秒 ({curr.id} -> {nxt.id})",
                            severity=ContinuitySeverity.ERROR,
                            fragment_id=curr.id,
                            position=i,
                            suggestion="调整片段时间，避免重叠",
                            source_stage=PipelineNode.SPLIT_VIDEO.value,
                            auto_fixable=True
                        )
                        if issue:
                            result.add_issue(issue)

    def check_prop_continuity(self, context: Dict[str, Any],
                              result: ContinuityCheckResult) -> None:
        """检查道具连续性"""
        parsed_script = context.get("parsed_script")

        if not parsed_script:
            return

        prop_state = {}
        seen_prop_changes = set()

        for scene in parsed_script.scenes:
            for elem in scene.elements:
                prop_keywords = ["拿", "举", "抱", "提", "端", "持", "握"]
                for kw in prop_keywords:
                    if kw in elem.content:
                        if elem.character:
                            if elem.character not in prop_state:
                                prop_state[elem.character] = []
                            prop_state[elem.character].append({
                                "prop": kw,
                                "scene": scene.id,
                                "time": elem.sequence
                            })

        for character, props in prop_state.items():
            if len(props) > 1:
                for i in range(len(props) - 1):
                    if props[i]["prop"] != props[i + 1]["prop"]:
                        change_key = f"{character}_{props[i]['prop']}_{props[i+1]['prop']}"
                        if change_key not in seen_prop_changes:
                            seen_prop_changes.add(change_key)
                            issue = self._create_issue(
                                issue_type=ContinuityIssueType.PROP_CHANGE,
                                description=f"角色'{character}'道具变化: {props[i]['prop']} -> {props[i + 1]['prop']}",
                                severity=ContinuitySeverity.WARNING,
                                scene_id=props[i]["scene"],
                                suggestion="确保道具前后一致",
                                source_stage=PipelineNode.PARSE_SCRIPT.value
                            )
                            if issue:
                                result.add_issue(issue)

    def check_with_contract(self, context: Dict[str, Any],
                            contract: GlobalConsistencyContract) -> ContinuityCheckResult:
        """带契约的连续性检查"""
        # 清望去重缓存
        self._seen_issues.clear()

        result = ContinuityCheckResult()

        # 1. 基础检查
        self.check_character_continuity(context, result)
        self.check_scene_continuity(context, result)
        self.check_time_continuity(context, result)

        # 2. 契约验证
        if contract:
            # 检查角色出现一致性
            for issue_data in contract.get_character_appearance_consistency():
                issue_key = f"contract_char_{issue_data.get('suggestion', '')[:50]}"
                if issue_key not in self._seen_issues:
                    self._seen_issues.add(issue_key)
                    issue = self._create_issue(
                        issue_type=ContinuityIssueType.CHARACTER_MISSING,
                        description=issue_data.get("suggestion", ""),
                        severity=ContinuitySeverity(issue_data.get("severity", "moderate")),
                        suggestion=issue_data.get("suggestion"),
                        source_stage=PipelineNode.CONTINUITY_CHECK,
                        auto_fixable=issue_data.get("auto_fixable", True)
                    )
                    if issue:
                        result.add_issue(issue)

            # 检查场景一致性
            scene_issues = self._check_scene_consistency_with_contract(context, contract)
            for issue in scene_issues:
                if issue:
                    result.add_issue(issue)

        return result

    def _check_scene_consistency_with_contract(self, context: Dict,
                                               contract: GlobalConsistencyContract) -> List[ContinuityIssue]:
        """检查场景与契约的一致性"""
        issues = []
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence:
            return issues

        # 追踪场景中出现的角色
        scene_characters = {}
        seen_scene_keys = set()

        for shot in shot_sequence.shots:
            if shot.scene_id not in scene_characters:
                scene_characters[shot.scene_id] = set()
            if shot.main_character:
                scene_characters[shot.scene_id].add(shot.main_character)

        # 验证每个场景是否有契约中定义的角色
        for scene_num, scene_contract in contract.scenes.items():
            scene_key = f"scene_{scene_num:03d}"
            if scene_key in scene_characters:
                missing_chars = set(scene_contract.characters_in_scene) - scene_characters[scene_key]
                if missing_chars:
                    missing_key = f"{scene_key}_missing_{','.join(sorted(missing_chars))}"
                    if missing_key not in seen_scene_keys:
                        seen_scene_keys.add(missing_key)
                        issue = self._create_issue(
                            issue_type=ContinuityIssueType.CHARACTER_MISSING,
                            description=f"场景{scene_num}缺失角色: {', '.join(missing_chars)}",
                            severity=ContinuitySeverity.MAJOR,
                            scene_id=scene_key,
                            suggestion="为缺失的角色添加镜头",
                            source_stage=PipelineNode.CONTINUITY_CHECK,
                            auto_fixable=True
                        )
                        if issue:
                            issues.append(issue)

        return issues

    def take_snapshot(self, context: Dict[str, Any]) -> StateSnapshot:
        """创建状态快照"""
        self.snapshot_counter += 1

        snapshot = StateSnapshot(
            timestamp=time.time(),
            snapshot_id=f"snapshot_{self.snapshot_counter:04d}",
            character_states={},
            scene_state=None
        )

        parsed_script = context.get("parsed_script")
        if parsed_script:
            for char in parsed_script.characters:
                snapshot.character_states[char.name] = CharacterState(
                    character_name=char.name,
                    appearance={"description": char.description or ""},
                    emotion={"type": "neutral", "intensity": 0.5}
                )

        self.timeline.add_snapshot(snapshot)
        return snapshot