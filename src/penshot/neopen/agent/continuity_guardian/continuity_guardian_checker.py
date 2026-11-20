"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: continuity_guardian_checker.py
@Description: 连续性检查器 - 实现连续性检测逻辑
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/3/28 20:45
"""
import re
import time
import uuid
from functools import lru_cache
from typing import Dict, Any, List, Optional, Pattern, Set

from penshot.logger import info
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.constants.appearance import MAIN_GARMENT_KEYWORDS
from penshot.neopen.constants.continuity import (
    CROSS_CHUNK_SCENE_THRESHOLD,
    get_action_synonym_groups,
    get_holding_verbs,
    get_prop_object_pattern_template,
)
from .appearance_anchors import contains_keyword
from .consistency_contract import GlobalConsistencyContract
from .continuity_guardian_models import (
    ContinuityAnchor, ContinuityIssue, ContinuityIssueType, ContinuitySeverity,
    CharacterState, StateSnapshot, StateTimeline, ContinuityCheckResult
)
from .cross_chunk_validator import CrossChunkValidator
from .long_script_chunker import LongScriptChunker

# 只用“主体服装名词集合”比较换装：片段措辞（身穿/佩戴/修饰语增减）与
# 单件细节（鞋袜、配饰）差异都不算外观变化，避免反复误报。


@lru_cache(maxsize=8)
def _prop_object_pattern(language: str = "zh") -> Pattern[str]:
    """按语言构建“持握动词 + 对象”匹配模式（词表与模板见 constants.continuity）"""
    verbs = get_holding_verbs(language)
    template = get_prop_object_pattern_template(language)
    # 用 replace 而非 str.format：模板中的 {1,8} 是正则量词，不是格式占位符
    pattern = template.replace("{verbs}", "|".join(map(re.escape, verbs)))
    return re.compile(pattern)


def _canonical_action(text: str, language: str = "zh") -> Optional[str]:
    """把文本中的动作归一到同义组标识，未命中的返回 None"""
    for group in get_action_synonym_groups(language):
        for keyword in sorted(group, key=len, reverse=True):
            if keyword in text:
                return "|".join(sorted(group))
    return None


def _extract_prop_objects(text: str, language: str = "zh") -> List[str]:
    """提取持握动词后的道具对象短语（仅取对象，不把动词当道具）"""
    objects = []
    for match in _prop_object_pattern(language).finditer(text or ""):
        obj = match.group(1).strip("的了着，。！？、；,.!?; ")
        if len(obj) >= 1:
            objects.append(obj)
    return objects


def _same_object(left: str, right: str) -> bool:
    """道具对象相同：互相包含即视为同一对象（避免“照片/旧照片”误报）"""
    return left in right or right in left


def _main_garment_signature(text: str) -> Set[str]:
    """提取片段中出现的主体服装词，未描述服装时返回空集"""
    return {
        keyword
        for keyword in MAIN_GARMENT_KEYWORDS
        if contains_keyword(text, (keyword,))
    }


class ContinuityGuardianChecker:
    """连续性检查器 - 负责检测跨阶段的连续性问题"""

    def __init__(self) -> None:
        self.timeline = StateTimeline()
        self.snapshot_counter = 0
        self._last_appearance: Dict[str, Set[str]] = {}  # 临时存储上次外观

        # 去重缓存
        self._seen_issues: Set[str] = set()
        self._processed_shots: Set[str] = set()
        self._seen_actions: Set[str] = set()
        self._seen_style_issues: Set[str] = set()
        # 已上报过修复的场景跳转（跨轮保留，避免对结构性场景切换反复重试）
        self._reported_scene_jumps: Set[str] = set()

    def check_all_continuity(self, context: Dict[str, Any]) -> ContinuityCheckResult:
        """执行所有连续性检查"""
        # 清望去重缓存
        self._seen_issues.clear()
        self._processed_shots.clear()
        # 外观基线只在本轮片段序列内有效，跨轮保留会让首片段与上轮末片段误比较
        self._last_appearance.clear()

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
                      severity: ContinuitySeverity, **kwargs: Any) -> Optional[ContinuityIssue]:
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
        character_appearances: Dict[str, List[str]] = {
            char: [] for char in characters.keys()
        }

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
                                               result: ContinuityCheckResult) -> None:
        """检查角色服装连续性

        比较片段间命中的主体服装词：只有片段明确描述了服装、且与上次已知服装
        完全不相交时才算换装；片段未描述服装时沿用上次已知集合，避免
        “这一句没提衣服”被当成换装，也避免“身穿/佩戴”等措辞差异触发误报。
        """
        garments = _main_garment_signature(prompt)
        previous = self._last_appearance.get(character)
        if garments and previous and not previous & garments:
            issue = self._create_issue(
                issue_type=ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
                description=(
                    f"角色'{character}'的服装发生变化: "
                    f"{'、'.join(sorted(previous))} -> {'、'.join(sorted(garments))}"
                ),
                severity=ContinuitySeverity.WARNING,
                fragment_id=fragment_id,
                position=index,
                suggestion="保持角色外观一致性",
                source_stage=PipelineNode.CONVERT_PROMPT.value,
                auto_fixable=True
            )
            if issue:
                result.add_issue(issue)

        if garments:
            self._last_appearance[character] = garments

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

                    # 已尝试过修复仍未消除，说明是剧本固有的场景结构，不再重复触发修复
                    if jump_key in self._reported_scene_jumps:
                        info(f"场景跳转已尝试修复，跳过重复上报: {jump_key}")
                        prev_scene = shot.scene_id
                        continue

                    # 过渡镜头本身或紧随过渡镜头的切点视为已平滑
                    prev_shot = shot_sequence.shots[i - 1]
                    if prev_shot.is_transition or shot.is_transition:
                        prev_scene = shot.scene_id
                        continue

                    # 仅当上一镜头与当前场景首镜头景别相同（缺乏视觉切换提示）时才判定为突兀
                    if prev_shot.shot_type == shot.shot_type:
                        self._reported_scene_jumps.add(jump_key)
                        issue = self._create_issue(
                            issue_type=ContinuityIssueType.SCENE_JUMP,
                            description=f"场景切换突兀: {prev_scene} -> {shot.scene_id}",
                            severity=ContinuitySeverity.WARNING,
                            shot_id=shot.id,
                            scene_id=shot.scene_id,
                            position=i,
                            suggestion="在场景边界插入过渡镜头（空镜/角色反应镜头）",
                            source_stage=PipelineNode.SEGMENT_SHOT.value,
                            auto_fixable=True,
                            metadata={
                                "prev_scene": prev_scene,
                                "next_scene": shot.scene_id,
                                "boundary_shot_id": shot.id,
                                "prev_shot_type": prev_shot.shot_type.value,
                            },
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
                source_stage=PipelineNode.SEGMENT_SHOT.value,
                # 场景数量由剧本结构决定，分镜阶段无法自动削减，仅记录
                auto_fixable=False,
            )
            if issue:
                result.add_issue(issue)

    def check_action_continuity(self, context: Dict[str, Any],
                                result: ContinuityCheckResult) -> None:
        """检查动作连续性"""
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence or len(shot_sequence.shots) < 2:
            return

        action_state: Dict[str, str] = {}

        for i, shot in enumerate(shot_sequence.shots):
            # 注意：不复用场景检查的 _processed_shots，否则动作检查会被整体跳过
            # 近义动作归一后再比较，避免“走 -> 步行”这类同义改写被误报
            current_action = _canonical_action(shot.description)
            if not current_action:
                continue

            if shot.main_character:
                last_action = action_state.get(shot.main_character)
                if last_action and current_action != last_action:
                    # 去重：避免重复报告相同的动作变化
                    action_key = f"{shot.main_character}_{last_action}_{current_action}"
                    if action_key not in self._seen_actions:
                        self._seen_actions.add(action_key)

                        issue = self._create_issue(
                            issue_type=ContinuityIssueType.ACTION_BREAK,
                            description=f"角色'{shot.main_character}'动作不连续: {last_action} -> {current_action}",
                            severity=ContinuitySeverity.MODERATE,
                            shot_id=shot.id,
                            position=i,
                            suggestion="确保动作前后连贯",
                            source_stage=PipelineNode.SEGMENT_SHOT.value,
                            auto_fixable=True
                        )
                        if issue:
                            result.add_issue(issue)
                action_state[shot.main_character] = current_action

    def check_style_continuity(self, context: Dict[str, Any],
                               result: ContinuityCheckResult) -> None:
        """检查视觉风格连续性"""
        instructions = context.get("instructions")

        if not instructions or len(instructions.fragments) < 2:
            return

        styles: List[str] = []
        style_count: Dict[str, int] = {}

        # 记录已处理的关键词
        seen_keywords: Set[str] = set()

        for prompt in instructions.fragments:
            # 注意：不复用角色检查的 _processed_fragments，否则风格检查会被整体跳过
            prompt_style = getattr(prompt, "style", None)
            if prompt_style:
                styles.append(prompt_style)
                style_count[prompt_style] = style_count.get(prompt_style, 0) + 1

                # 检查风格关键词一致性
                style_keywords = prompt_style.lower().split()
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

            # 时间倒流：后一片段的起点早于前一片段起点，属于结构性错误
            if nxt.start_time < curr.start_time - 0.1:
                reverse_key = f"reverse_{pair_key}"
                if reverse_key not in seen_overlaps:
                    seen_overlaps.add(reverse_key)
                    issue = self._create_issue(
                        issue_type=ContinuityIssueType.TIME_REVERSE,
                        description=(
                            f"片段时间倒流: {nxt.id}({nxt.start_time:.2f}s) "
                            f"早于 {curr.id}({curr.start_time:.2f}s)"
                        ),
                        severity=ContinuitySeverity.ERROR,
                        fragment_id=nxt.id,
                        position=i,
                        suggestion="按镜头顺序重排片段时间轴",
                        source_stage=PipelineNode.SPLIT_VIDEO.value,
                        auto_fixable=True
                    )
                    if issue:
                        result.add_issue(issue)
                continue

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

        prop_state: Dict[str, List[Dict[str, Any]]] = {}
        seen_prop_changes: Set[str] = set()

        for scene in parsed_script.scenes:
            for elem in scene.elements:
                if not elem.character:
                    continue
                # 只记录“持有动词 + 对象”，动词变化本身不代表道具变化；
                # 无法抽取对象时不记录，避免纯动词比较产生误报。
                for obj in _extract_prop_objects(elem.content):
                    prop_state.setdefault(elem.character, []).append({
                        "prop": obj,
                        "scene": scene.id,
                        "time": elem.sequence
                    })

        for character, props in prop_state.items():
            if len(props) > 1:
                for i in range(len(props) - 1):
                    previous, current = props[i]["prop"], props[i + 1]["prop"]
                    if _same_object(previous, current):
                        continue
                    change_key = f"{character}_{previous}_{current}"
                    if change_key in seen_prop_changes:
                        continue
                    seen_prop_changes.add(change_key)
                    issue = self._create_issue(
                        issue_type=ContinuityIssueType.PROP_CHANGE,
                        description=f"角色'{character}'持有道具变化: {previous} -> {current}",
                        severity=ContinuitySeverity.WARNING,
                        scene_id=props[i]["scene"],
                        suggestion="确保道具前后一致",
                        source_stage=PipelineNode.PARSE_SCRIPT.value,
                        # 解析阶段没有确定性道具修复能力，避免自动修复空转
                        auto_fixable=False,
                    )
                    if issue:
                        result.add_issue(issue)

    def check_with_contract(self, context: Dict[str, Any],
                            contract: GlobalConsistencyContract) -> ContinuityCheckResult:
        """带契约的连续性检查（主链入口）

        先执行原有六项基础检查，再叠加契约校验、结构化锚点与长剧本跨块校验，
        避免出现“契约方法已定义但主链不生效”的情况。
        """
        result = self.check_all_continuity(context)

        if contract:
            self._apply_contract_checks(context, contract, result)

        return result

    def _apply_contract_checks(self, context: Dict[str, Any],
                               contract: GlobalConsistencyContract,
                               result: ContinuityCheckResult) -> None:
        """契约校验：角色缺席、场景角色、结构化锚点、跨块连续性"""
        # 1. 角色长期缺席：结构性问题，解析/分镜无法确定性修复
        for issue_data in contract.get_character_appearance_consistency():
            issue = self._create_issue(
                issue_type=ContinuityIssueType.CHARACTER_DISAPPEAR,
                description=issue_data.get("suggestion", ""),
                severity=ContinuitySeverity(issue_data.get("severity", "moderate")),
                suggestion=issue_data.get("suggestion"),
                source_stage=PipelineNode.CONTINUITY_CHECK,
                auto_fixable=False,
            )
            if issue:
                result.add_issue(issue)

        # 2. 场景角色一致性
        for issue in self._check_scene_consistency_with_contract(context, contract):
            if issue:
                result.add_issue(issue)

        # 3. 结构化锚点（ContinuityAnchor）：角色外观 / 场景 / 风格
        anchors = self.build_anchors_from_contract(contract)
        self._check_character_appearance_anchors(context, anchors, result)
        self._check_scene_anchors(context, anchors, result)
        self._check_style_anchor(context, anchors, result)

        # 4. 长剧本跨块连续性（CrossChunkValidator）
        self._check_chunk_transitions(context, result)

    def build_anchors_from_contract(
        self, contract: GlobalConsistencyContract
    ) -> List[ContinuityAnchor]:
        """把全局契约转换为结构化连续性锚点，并登记到时间线"""
        anchors: List[ContinuityAnchor] = []

        for name, char in (getattr(contract, "characters", {}) or {}).items():
            anchors.append(ContinuityAnchor(
                anchor_id=f"character_{name}",
                anchor_type="character",
                name=name,
                value=dict(getattr(char, "appearance_anchors", {}) or {}),
                priority=2,
            ))

        for num, scene in (getattr(contract, "scenes", {}) or {}).items():
            anchors.append(ContinuityAnchor(
                anchor_id=f"scene_{num}",
                anchor_type="scene",
                name=str(num),
                value={
                    "location": getattr(scene, "location", ""),
                    "time_of_day": getattr(scene, "time_of_day", ""),
                    "weather": getattr(scene, "weather", ""),
                    "characters": list(getattr(scene, "characters_in_scene", []) or []),
                },
                priority=1,
            ))

        style_anchor = getattr(contract, "style_anchor", {}) or {}
        if style_anchor:
            anchors.append(ContinuityAnchor(
                anchor_id="style",
                anchor_type="style",
                name="global_style",
                value=dict(style_anchor),
                priority=3,
            ))

        self.timeline.continuity_anchors = {
            anchor.anchor_id: anchor.model_dump() for anchor in anchors
        }
        return anchors

    def _check_style_anchor(self, context: Dict[str, Any],
                            anchors: List[ContinuityAnchor],
                            result: ContinuityCheckResult) -> None:
        """校验片段是否落实风格锚点（有锚点但片段缺风格即提示）"""
        style_anchor = next(
            (anchor for anchor in anchors if anchor.anchor_type == "style"), None
        )
        if not style_anchor or not style_anchor.value:
            return

        instructions = context.get("instructions")
        if not instructions:
            return

        missing = [
            prompt.fragment_id
            for prompt in instructions.fragments
            if not (prompt.style or "").strip()
        ]
        if not missing:
            return

        issue = self._create_issue(
            issue_type=ContinuityIssueType.STYLE_INCONSISTENT,
            description=(
                f"{len(missing)}个片段未落实全局风格锚点: "
                f"{', '.join(missing[:5])}"
            ),
            severity=ContinuitySeverity.WARNING,
            fragment_id=missing[0],
            suggestion="按契约风格锚点补齐片段风格描述",
            source_stage=PipelineNode.CONVERT_PROMPT.value,
            auto_fixable=True,
        )
        if issue:
            result.add_issue(issue)

    def _check_character_appearance_anchors(
        self, context: Dict[str, Any], anchors: List[ContinuityAnchor],
        result: ContinuityCheckResult,
    ) -> None:
        """用角色外观锚点校验片段服装；首个片段也有基线，不再只比较上一片段"""
        instructions = context.get("instructions")
        if not instructions:
            return

        anchors_by_name = {
            anchor.name: (anchor.value or {})
            for anchor in anchors
            if anchor.anchor_type == "character"
        }

        for index, prompt in enumerate(instructions.fragments):
            character = getattr(prompt, "main_character", None)
            if not character:
                continue
            anchor_value = anchors_by_name.get(character) or {}
            expected = _main_garment_signature(
                str(anchor_value.get("clothing", "") or "")
            )
            if not expected:
                continue

            actual = _main_garment_signature(getattr(prompt, "prompt", "") or "")
            if not actual or actual & expected:
                continue

            issue = self._create_issue(
                issue_type=ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
                description=(
                    f"角色'{character}'服装与契约锚点不一致: "
                    f"期望 {'、'.join(sorted(expected))}，"
                    f"实际 {'、'.join(sorted(actual))}"
                ),
                severity=ContinuitySeverity.WARNING,
                fragment_id=prompt.fragment_id,
                position=index,
                suggestion="按契约外观锚点修正片段服装描述",
                source_stage=PipelineNode.CONVERT_PROMPT.value,
                auto_fixable=True,
            )
            if issue:
                result.add_issue(issue)

    def _check_scene_anchors(
        self, context: Dict[str, Any], anchors: List[ContinuityAnchor],
        result: ContinuityCheckResult,
    ) -> None:
        """用场景锚点校验分镜场景是否越界，以及相邻场景地点/时间是否冲突"""
        scene_anchors = sorted(
            (anchor for anchor in anchors if anchor.anchor_type == "scene"),
            key=lambda anchor: int(anchor.name) if str(anchor.name).isdigit() else 0,
        )
        if not scene_anchors:
            return

        known_scenes = {
            f"scene_{int(anchor.name):03d}"
            for anchor in scene_anchors
            if str(anchor.name).isdigit()
        }
        reported_scenes: Set[str] = set()
        shots = getattr(context.get("shot_sequence"), "shots", []) or []
        for shot in shots:
            scene_id = getattr(shot, "scene_id", None)
            if not scene_id or scene_id in known_scenes or scene_id in reported_scenes:
                continue
            reported_scenes.add(scene_id)
            issue = self._create_issue(
                issue_type=ContinuityIssueType.SCENE_INCONSISTENT,
                description=f"镜头{shot.id}的场景'{scene_id}'不在契约场景锚点中",
                severity=ContinuitySeverity.WARNING,
                shot_id=shot.id,
                scene_id=scene_id,
                suggestion="检查分镜场景编号，或补登记对应契约场景",
                source_stage=PipelineNode.SEGMENT_SHOT.value,
                auto_fixable=True,
            )
            if issue:
                result.add_issue(issue)

        for previous, current in zip(scene_anchors, scene_anchors[1:]):
            prev_value = previous.value or {}
            curr_value = current.value or {}
            shared_characters = set(prev_value.get("characters") or []) & set(
                curr_value.get("characters") or []
            )
            if (
                prev_value.get("location")
                and prev_value.get("location") == curr_value.get("location")
                and prev_value.get("time_of_day") != curr_value.get("time_of_day")
                and shared_characters
            ):
                issue = self._create_issue(
                    issue_type=ContinuityIssueType.SCENE_INCONSISTENT,
                    description=(
                        f"场景{previous.name}->{current.name} 地点相同但时间不一致: "
                        f"{prev_value.get('time_of_day')} -> {curr_value.get('time_of_day')}"
                    ),
                    severity=ContinuitySeverity.WARNING,
                    scene_id=(
                        f"scene_{int(current.name):03d}"
                        if str(current.name).isdigit() else current.name
                    ),
                    suggestion="补充时间过渡说明或统一场景时间",
                    source_stage=PipelineNode.CONTINUITY_CHECK,
                    auto_fixable=False,
                )
                if issue:
                    result.add_issue(issue)

    def _check_chunk_transitions(self, context: Dict[str, Any],
                                 result: ContinuityCheckResult) -> None:
        """长剧本按场景分块后检查块间角色连续性"""
        parsed_script = context.get("parsed_script")
        if not parsed_script:
            return

        scenes = getattr(parsed_script, "scenes", []) or []
        if len(scenes) <= CROSS_CHUNK_SCENE_THRESHOLD:
            return

        chunks = LongScriptChunker().chunk_script(parsed_script)
        if len(chunks) < 2:
            return

        summaries = [self._summarize_chunk(chunk) for chunk in chunks]
        # 跨多个块出现的角色视为主角，避免把每个客串角色都当作“突然出现”
        chunk_membership: Dict[str, int] = {}
        for summary in summaries:
            for name in summary["characters_in_chunk"]:
                chunk_membership[name] = chunk_membership.get(name, 0) + 1
        main_characters = {
            name for name, count in chunk_membership.items() if count >= 2
        }

        validator = CrossChunkValidator()
        previous = summaries[0]
        for chunk, current in zip(chunks[1:], summaries[1:]):
            for raw in validator.validate_chunk_transition(previous, current):
                character = raw.get("character", "")
                if character not in main_characters:
                    continue
                issue_type = (
                    ContinuityIssueType.CHARACTER_MISSING
                    if raw.get("type") == "character_disappears"
                    else ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE
                )
                issue = self._create_issue(
                    issue_type=issue_type,
                    description=raw.get("suggestion", ""),
                    severity=ContinuitySeverity.WARNING,
                    scene_id=f"chunk_{chunk.chunk_id}",
                    suggestion="在块边界补充角色出场/退场过渡",
                    source_stage=PipelineNode.CONTINUITY_CHECK,
                    auto_fixable=False,
                )
                if issue:
                    result.add_issue(issue)
            previous = current

    @staticmethod
    def _summarize_chunk(chunk: Any) -> Dict[str, Any]:
        """把剧本块归纳为跨块校验器需要的字段"""
        characters: List[str] = []
        first_location = ""
        last_location = ""
        for scene in getattr(chunk, "scenes", []) or []:
            location = getattr(scene, "location", "") or ""
            if location and not first_location:
                first_location = location
            if location:
                last_location = location
            for elem in getattr(scene, "elements", []) or []:
                name = getattr(elem, "character", None)
                if name and name not in characters:
                    characters.append(name)
        return {
            "characters_in_chunk": characters,
            "first_location": first_location,
            "last_location": last_location,
        }

    def check_style_drift_with_guardian(
        self, context: Dict[str, Any], guardian: Any,
        result: ContinuityCheckResult,
    ) -> None:
        """使用 PromptStyleGuardian 检测提示词风格漂移并转为连续性问题"""
        instructions = context.get("instructions")
        if guardian is None or not instructions or not instructions.fragments:
            return

        prompts = [prompt.prompt or "" for prompt in instructions.fragments]
        try:
            drift_issues = guardian.detect_style_drift(prompts)
        except Exception as e:
            info(f"风格漂移检测失败，跳过: {e}")
            return

        for item in drift_issues:
            index = item.get("fragment_index", 0)
            if not 0 <= index < len(instructions.fragments):
                continue
            prompt = instructions.fragments[index]
            is_drift = item.get("issue") == "style_drift"
            issue = self._create_issue(
                issue_type=ContinuityIssueType.STYLE_INCONSISTENT,
                description=(
                    f"片段'{prompt.fragment_id}'风格与全局风格画像差异过大"
                    f"(相似度={item.get('similarity', 0):.2f})"
                ),
                severity=(
                    ContinuitySeverity.MODERATE if is_drift
                    else ContinuitySeverity.WARNING
                ),
                fragment_id=prompt.fragment_id,
                position=index,
                suggestion=item.get("suggestion", "统一片段风格描述"),
                source_stage=PipelineNode.CONVERT_PROMPT.value,
                auto_fixable=True,
            )
            if issue:
                result.add_issue(issue)

    def _check_scene_consistency_with_contract(self, context: Dict[str, Any],
                                               contract: GlobalConsistencyContract) -> List[ContinuityIssue]:
        """检查场景与契约的一致性"""
        issues: List[ContinuityIssue] = []
        shot_sequence = context.get("shot_sequence")

        if not shot_sequence:
            return issues

        # 追踪场景中出现的角色
        scene_characters: Dict[str, Set[str]] = {}
        seen_scene_keys: Set[str] = set()

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
        """创建状态快照（记录角色外观与当前片段进度）"""
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

        # 用最新片段序列补全快照引用，便于按时间回溯“当时执行到哪”
        instructions = context.get("instructions")
        fragments = getattr(instructions, "fragments", None) or []
        if fragments:
            last_fragment = fragments[-1]
            snapshot.references = {
                "fragment_id": getattr(last_fragment, "fragment_id", None),
                "shot_id": None,
                "element_ids": [],
            }
            snapshot.global_state = {
                **snapshot.global_state,
                "fragment_count": len(fragments),
                "fragment_ids": [f.fragment_id for f in fragments[:20]],
                "anchor_count": len(self.timeline.continuity_anchors),
            }

        self.timeline.add_snapshot(snapshot)
        return snapshot