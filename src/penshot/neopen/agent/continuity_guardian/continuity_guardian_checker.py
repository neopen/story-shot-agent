"""
@FileName: continuity_guardian_checker.py
@Description: 连续性检查器 - 实现连续性检测逻辑
@Author: HiPeng
@Time: 2026/3/28 20:45
"""
import time
import uuid
from typing import Dict, Any

from penshot.neopen.agent.workflow.workflow_models import PipelineNode
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

    def check_all_continuity(self, context: Dict[str, Any]) -> ContinuityCheckResult:
        """执行所有连续性检查"""
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

        return result

    def _create_issue(self, issue_type: ContinuityIssueType, description: str,
                      severity: ContinuitySeverity, **kwargs) -> ContinuityIssue:
        """创建连续性问题"""
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
                if char not in character_appearances or not character_appearances[char]:
                    result.add_issue(self._create_issue(
                        issue_type=ContinuityIssueType.CHARACTER_MISSING,
                        description=f"角色'{char}'在场景{scene.id}中有对话但无对应镜头",
                        severity=ContinuitySeverity.MAJOR,
                        scene_id=scene.id,
                        suggestion=f"为角色'{char}'添加镜头",
                        source_stage=PipelineNode.SEGMENT_SHOT.value
                    ))

        # 检查角色外观连续性（基于提示词）
        instructions = context.get("instructions")
        if instructions:
            for i, prompt in enumerate(instructions.fragments):
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
                    result.add_issue(self._create_issue(
                        issue_type=ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
                        description=f"角色'{character}'的{category}发生变化: {last.get(category)} -> {feature}",
                        severity=ContinuitySeverity.WARNING,
                        fragment_id=fragment_id,
                        position=index,
                        suggestion="保持角色外观一致性",
                        source_stage=PipelineNode.CONVERT_PROMPT.value,
                        auto_fixable=True
                    ))

        self._last_appearance[character] = current_features

    def check_scene_continuity(self, context: Dict[str, Any],
                               result: ContinuityCheckResult) -> None:
        """检查场景连续性"""
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence or len(shot_sequence.shots) < 2:
            return

        prev_scene = None
        scene_jump_count = 0

        for i, shot in enumerate(shot_sequence.shots):
            if prev_scene and prev_scene != shot.scene_id:
                if i > 0 and i < len(shot_sequence.shots) - 1:
                    prev_shot = shot_sequence.shots[i - 1]
                    next_shot = shot_sequence.shots[i + 1] if i + 1 < len(shot_sequence.shots) else None

                    if next_shot and prev_shot.shot_type == next_shot.shot_type:
                        scene_jump_count += 1
                        result.add_issue(self._create_issue(
                            issue_type=ContinuityIssueType.SCENE_JUMP,
                            description=f"场景切换突兀: {prev_scene} -> {shot.scene_id}",
                            severity=ContinuitySeverity.WARNING,
                            shot_id=shot.id,
                            position=i,
                            suggestion="添加过渡镜头使场景切换更自然",
                            source_stage=PipelineNode.SEGMENT_SHOT.value,
                            auto_fixable=True
                        ))
            prev_scene = shot.scene_id

        if scene_jump_count > len(shot_sequence.shots) * 0.3:
            result.add_issue(self._create_issue(
                issue_type=ContinuityIssueType.SCENE_TOO_FREQUENT,
                description=f"场景切换过于频繁: {scene_jump_count}次切换",
                severity=ContinuitySeverity.MODERATE,
                suggestion="减少场景切换频率或增加过渡效果",
                source_stage=PipelineNode.SEGMENT_SHOT.value
            ))

    def check_action_continuity(self, context: Dict[str, Any],
                                result: ContinuityCheckResult) -> None:
        """检查动作连续性"""
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence or len(shot_sequence.shots) < 2:
            return

        action_state = {}

        for i, shot in enumerate(shot_sequence.shots):
            action_keywords = ["走", "跑", "跳", "转身", "坐下", "站起", "拿起", "放下"]
            current_actions = [kw for kw in action_keywords if kw in shot.description]

            if shot.main_character and current_actions:
                if shot.main_character in action_state:
                    last_action = action_state[shot.main_character]
                    if last_action and current_actions[0] != last_action:
                        result.add_issue(self._create_issue(
                            issue_type=ContinuityIssueType.ACTION_BREAK,
                            description=f"角色'{shot.main_character}'动作不连续: {last_action} -> {current_actions[0]}",
                            severity=ContinuitySeverity.MODERATE,
                            shot_id=shot.id,
                            position=i,
                            suggestion="确保动作前后连贯",
                            source_stage=PipelineNode.SEGMENT_SHOT.value,
                            auto_fixable=True
                        ))
                action_state[shot.main_character] = current_actions[0]

    def check_style_continuity(self, context: Dict[str, Any],
                               result: ContinuityCheckResult) -> None:
        """检查视觉风格连续性"""
        instructions = context.get("instructions")

        if not instructions or len(instructions.fragments) < 2:
            return

        styles = []
        style_count = {}

        for prompt in instructions.fragments:
            if prompt.style:
                styles.append(prompt.style)
                style_count[prompt.style] = style_count.get(prompt.style, 0) + 1

        unique_styles = set(styles)
        if len(unique_styles) > 2:
            result.add_issue(self._create_issue(
                issue_type=ContinuityIssueType.STYLE_INCONSISTENT,
                description=f"检测到{len(unique_styles)}种不同风格: {', '.join(unique_styles)}",
                severity=ContinuitySeverity.MODERATE,
                suggestion="统一使用1-2种视觉风格保持连贯性",
                source_stage=PipelineNode.CONVERT_PROMPT.value
            ))

        prev_style = None
        for i, prompt in enumerate(instructions.fragments):
            if prev_style and prompt.style and prev_style != prompt.style:
                result.add_issue(self._create_issue(
                    issue_type=ContinuityIssueType.STYLE_SUDDEN_CHANGE,
                    description=f"风格突变: {prev_style} -> {prompt.style}",
                    severity=ContinuitySeverity.WARNING,
                    fragment_id=prompt.fragment_id,
                    position=i,
                    suggestion="考虑添加风格过渡",
                    source_stage=PipelineNode.CONVERT_PROMPT.value,
                    auto_fixable=True
                ))
            prev_style = prompt.style

    def check_time_continuity(self, context: Dict[str, Any],
                              result: ContinuityCheckResult) -> None:
        """检查时间连续性"""
        fragment_sequence = context.get("fragment_sequence")

        if not fragment_sequence or len(fragment_sequence.fragments) < 2:
            return

        fragments = fragment_sequence.fragments

        for i in range(len(fragments) - 1):
            curr = fragments[i]
            nxt = fragments[i + 1]

            expected_start = curr.start_time + curr.duration

            if abs(nxt.start_time - expected_start) > 0.1:
                if nxt.start_time > expected_start:
                    gap = nxt.start_time - expected_start
                    result.add_issue(self._create_issue(
                        issue_type=ContinuityIssueType.TIME_GAP,
                        description=f"片段间存在时间间隙: {gap:.2f}秒",
                        severity=ContinuitySeverity.MAJOR,
                        fragment_id=curr.id,
                        position=i,
                        suggestion="修复时间连续性，确保片段首尾相接",
                        source_stage=PipelineNode.SPLIT_VIDEO.value,
                        auto_fixable=True
                    ))
                else:
                    overlap = expected_start - nxt.start_time
                    result.add_issue(self._create_issue(
                        issue_type=ContinuityIssueType.TIME_OVERLAP,
                        description=f"片段间存在时间重叠: {overlap:.2f}秒",
                        severity=ContinuitySeverity.ERROR,
                        fragment_id=curr.id,
                        position=i,
                        suggestion="调整片段时间，避免重叠",
                        source_stage=PipelineNode.SPLIT_VIDEO.value,
                        auto_fixable=True
                    ))

    def check_prop_continuity(self, context: Dict[str, Any],
                              result: ContinuityCheckResult) -> None:
        """检查道具连续性"""
        parsed_script = context.get("parsed_script")

        if not parsed_script:
            return

        prop_state = {}

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
                        result.add_issue(self._create_issue(
                            issue_type=ContinuityIssueType.PROP_CHANGE,
                            description=f"角色'{character}'道具变化: {props[i]['prop']} -> {props[i + 1]['prop']}",
                            severity=ContinuitySeverity.WARNING,
                            scene_id=props[i]["scene"],
                            suggestion="确保道具前后一致",
                            source_stage=PipelineNode.PARSE_SCRIPT.value
                        ))

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
