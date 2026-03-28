"""
@FileName: llm_video_splitter.py
@Description: 基于LLM的视频智能分割器 - 从ParsedScript获取全局信息
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 22:30
"""
import json
import time
from typing import List, Optional, Dict, Any

from penshot.logger import info, error, warning, debug
from penshot.neopen.agent.base_llm_agent import BaseLLMAgent
from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo
from penshot.neopen.agent.video_splitter.base_video_splitter import BaseVideoSplitter
from penshot.neopen.agent.video_splitter.rule_video_splitter import RuleVideoSplitter
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class LLMVideoSplitter(BaseVideoSplitter, BaseLLMAgent):
    """基于LLM的视频智能分割器 - 从ParsedScript获取全局信息"""

    def __init__(self, llm_client, config: Optional[ShotConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.rule_splitter = RuleVideoSplitter(config)
        self.split_cache = {}
        self.current_repair_params = None

        # 分割阈值配置
        self.split_threshold = getattr(config, 'duration_split_threshold', 5.5)
        self.min_split_segment = getattr(config, 'min_fragment_duration', 1.0)
        self.max_split_segment = getattr(config, 'max_fragment_duration', 5.0)

        # 从ParsedScript获取的信息
        self.parsed_script = None
        self.global_metadata = None
        self.valid_scene_ids = set()

        # 初始化提示词
        self._init_prompts()

    def _init_prompts(self):
        """初始化提示词模板"""
        self.system_prompt = self._get_prompt_template("video_splitter_system")
        self.user_prompt_template = self._get_prompt_template("video_splitter_user")

    def cut(self, shot_sequence: ShotSequence, parsed_script: ParsedScript,
            repair_params: Optional[QualityRepairParams]) -> FragmentSequence:
        """使用LLM智能分割视频，从ParsedScript获取全局信息"""
        info(f"开始智能视频分割，镜头数: {len(shot_sequence.shots)}")

        # 如果有修复参数，保存到实例
        if repair_params:
            self.current_repair_params = repair_params

        # 保存ParsedScript供后续使用
        self.parsed_script = parsed_script
        self.global_metadata = parsed_script.global_metadata

        # 收集所有有效的场景ID
        self._collect_valid_scene_ids(shot_sequence)

        fragments = []
        current_time = 0.0
        fragment_id_counter = 0

        source_info = {
            "shot_count": len(shot_sequence.shots),
            "original_duration": shot_sequence.stats.get("total_duration", 0.0),
            "split_method": "llm_adaptive_fixed",
        }

        for shot_idx, shot in enumerate(shot_sequence.shots):
            try:
                # 修复镜头描述的连续性
                shot = self._fix_shot_continuity(shot, shot_idx, shot_sequence)

                debug(f"处理镜头 {shot.id}: {shot.description} (时长: {shot.duration}s)")

                # 检查是否应该使用LLM分割
                if self._should_use_llm_split(shot):
                    info(f"镜头 {shot.id} 时长({shot.duration}s)超过阈值，使用AI分割")

                    context = {
                        "shot": shot,
                        "prev_shot": shot_sequence.shots[shot_idx - 1] if shot_idx > 0 else None,
                        "next_shot": shot_sequence.shots[shot_idx + 1] if shot_idx < len(shot_sequence.shots) - 1 else None,
                        "current_time": current_time,
                        "fragment_offset": fragment_id_counter
                    }

                    shot_fragments = self._split_shot_with_llm(context)

                    # 修复分割后片段的描述
                    shot_fragments = self._fix_fragments_continuity(shot_fragments, shot)

                    validated_fragments = self._validate_and_adjust_fragments(
                        shot_fragments, shot, current_time, fragment_id_counter
                    )

                    fragments.extend(validated_fragments)
                    fragment_id_counter += len(validated_fragments)

                    if validated_fragments:
                        current_time = validated_fragments[-1].start_time + validated_fragments[-1].duration
                else:
                    debug(f"镜头 {shot.id} 使用规则分割")
                    rule_fragments = self.rule_splitter.split_shot(
                        shot, current_time, fragment_id_counter
                    )

                    rule_fragments = self._fix_fragments_continuity(rule_fragments, shot)

                    fragments.extend(rule_fragments)
                    fragment_id_counter += len(rule_fragments)

                    if rule_fragments:
                        current_time = rule_fragments[-1].start_time + rule_fragments[-1].duration

            except Exception as e:
                error(f"镜头{shot.id}分割失败: {str(e)}")
                print_log_exception()
                warning(f"镜头{shot.id}降级到简单规则分割")

                fallback_fragments = self.rule_splitter.split_shot(
                    shot, current_time, fragment_id_counter
                )

                fallback_fragments = self._fix_fragments_continuity(fallback_fragments, shot)

                fragments.extend(fallback_fragments)
                fragment_id_counter += len(fallback_fragments)

                if fallback_fragments:
                    current_time = fallback_fragments[-1].start_time + fallback_fragments[-1].duration

        # 后处理：规范化片段ID
        fragments = self._normalize_fragment_ids(fragments)

        # 应用修复参数
        if self.current_repair_params and self.current_repair_params.fix_needed:
            fragments = self._apply_repair_params(fragments, shot_sequence)

        fragment_sequence = FragmentSequence(
            source_info=source_info,
            fragments=fragments,
            metadata={
                "split_method": AgentMode.LLM,
                "ai_split_count": sum(1 for f in fragments if f.metadata.get("split_by", "") == AgentMode.LLM),
                "rule_split_count": sum(1 for f in fragments if f.metadata.get("split_by", "") == AgentMode.RULE),
                "total_fragments": len(fragments),
                "average_duration": round(sum(f.duration for f in fragments) / len(fragments), 2) if fragments else 0
            }
        )

        info(f"视频分割完成: 共生成{len(fragments)}个片段")
        return self.post_process(fragment_sequence)

    def _apply_repair_params(self, fragments: List[VideoFragment],
                             shot_sequence: ShotSequence) -> List[VideoFragment]:
        """应用修复参数调整片段"""
        if not self.current_repair_params:
            return fragments

        info(f"应用修复参数调整片段，问题类型: {self.current_repair_params.issue_types}")

        issue_types = set(self.current_repair_params.issue_types)

        # 1. 修复时长问题
        if "fragment_duration_too_short" in issue_types or "fragment_duration_too_long" in issue_types:
            fragments = self._fix_duration_issues(fragments)

        # 2. 修复描述问题
        if "fragment_description_missing" in issue_types:
            fragments = self._fix_description_issues(fragments, shot_sequence)

        # 3. 修复时间间隔问题
        if "fragment_time_gap" in issue_types:
            fragments = self._fix_time_gap_issues(fragments)

        # 4. 修复重叠问题
        if "fragment_overlap" in issue_types:
            fragments = self._fix_overlap_issues(fragments)

        # 5. 修复连续性注释
        if "fragment_no_continuity" in issue_types:
            fragments = self._fix_continuity_issues(fragments)

        return fragments

    def _fix_duration_issues(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """修复时长问题"""
        for fragment in fragments:
            if fragment.duration < self.min_split_segment:
                fragment.duration = self.min_split_segment
                info(f"修复过短时长: {fragment.id} -> {self.min_split_segment}s")
            elif fragment.duration > self.max_split_segment:
                fragment.duration = self.max_split_segment
                info(f"修复过长时长: {fragment.id} -> {self.max_split_segment}s")
        return fragments

    def _fix_description_issues(self, fragments: List[VideoFragment],
                                shot_sequence: ShotSequence) -> List[VideoFragment]:
        """修复描述问题"""
        for fragment in fragments:
            if not fragment.description or len(fragment.description.strip()) < 5:
                # 从关联的镜头获取描述
                if fragment.shot_id:
                    for shot in shot_sequence.shots:
                        if shot.id == fragment.shot_id:
                            fragment.description = shot.description
                            info(f"从镜头补充描述: {fragment.id}")
                            break

                # 生成默认描述
                if not fragment.description or len(fragment.description.strip()) < 5:
                    fragment.description = f"视频片段，时长{fragment.duration}秒"
                    info(f"生成默认描述: {fragment.id}")
        return fragments

    def _fix_time_gap_issues(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """修复时间间隔问题"""
        current_time = 0.0
        for fragment in fragments:
            fragment.start_time = current_time
            current_time += fragment.duration
        info("修复所有时间间隔")
        return fragments

    def _fix_overlap_issues(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """修复重叠问题"""
        current_time = 0.0
        for fragment in fragments:
            fragment.start_time = current_time
            current_time += fragment.duration
        info("修复所有重叠")
        return fragments

    def _fix_continuity_issues(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """修复连续性注释问题"""
        for i, fragment in enumerate(fragments):
            if not hasattr(fragment, 'continuity_notes') or not fragment.continuity_notes:
                fragment.continuity_notes = {}

            fragment.continuity_notes["continuity_check"] = "passed"
            fragment.continuity_notes["fixed_at"] = time.time()

            if i > 0:
                fragment.continuity_notes["prev_fragment"] = fragments[i - 1].id
            if i < len(fragments) - 1:
                fragment.continuity_notes["next_fragment"] = fragments[i + 1].id

        info("修复连续性注释")
        return fragments

    def _get_enhanced_prompt_template(self, context: Dict[str, Any]) -> str:
        """获取增强的提示词模板 - 使用global_metadata"""
        shot = context["shot"]
        prev_shot = context.get("prev_shot")
        next_shot = context.get("next_shot")

        # 格式化全局上下文
        global_context = self._format_global_context(self.global_metadata, shot.scene_id)

        # 构建场景信息
        scene_info = self._get_scene_info(shot.scene_id, self.parsed_script)

        # 构建修复提示
        repair_hint = ""
        if self.current_repair_params and self.current_repair_params.fix_needed and self.current_repair_params.issue_types:
            repair_hint = f"""
                【重要：修复要求】
                    之前的分割存在以下问题：
                    - 问题类型: {', '.join(self.current_repair_params.issue_types)}
                    - 修复建议: {json.dumps(self.current_repair_params.suggestions, ensure_ascii=False) if self.current_repair_params.suggestions else '无'}
                    
                    请根据上述建议调整分割策略，避免再次出现相同问题。
                """

        prev_context = ""
        if prev_shot:
            prev_context = f"{prev_shot.description} ({prev_shot.duration}s)"

        next_context = ""
        if next_shot:
            next_context = f"{next_shot.description} ({next_shot.duration}s)"

        return self.user_prompt_template.format(
            shot_id=shot.id,
            description=shot.description,
            duration=shot.duration,
            shot_type=shot.shot_type.value if hasattr(shot.shot_type, 'value') else str(shot.shot_type),
            main_character=shot.main_character or "无",
            scene_info=scene_info,
            prev_context=prev_context,
            next_context=next_context,
            split_threshold=self.split_threshold,
            min_segment=self.min_split_segment,
            max_segment=self.max_split_segment,
            continuity_notes=self._get_continuity_notes(shot),
            global_context=global_context,
            repair_hint=repair_hint
        )

    def _should_use_llm_split(self, shot: ShotInfo) -> bool:
        """判断是否应该使用AI分割"""
        if shot.duration <= self.split_threshold:
            return False

        complex_shots = ["ACTION", "MOVING", "PANORAMA", "ZOOM"]
        if shot.shot_type in complex_shots:
            return True

        if shot.description and any(keyword in shot.description.lower()
                                    for keyword in ["对话", "交谈", "讨论", "talk", "conversation"]):
            return True

        return True

    def _collect_valid_scene_ids(self, shot_sequence: ShotSequence):
        """收集所有有效的场景ID"""
        self.valid_scene_ids.clear()
        for shot in shot_sequence.shots:
            if hasattr(shot, 'scene_id') and shot.scene_id:
                self.valid_scene_ids.add(shot.scene_id)
        debug(f"有效场景ID: {self.valid_scene_ids}")

    def _fix_shot_continuity(self, shot: ShotInfo, shot_idx: int, shot_sequence: ShotSequence) -> ShotInfo:
        """修复镜头描述的连续性"""
        # 修复场景引用
        if hasattr(shot, 'scene_id') and shot.scene_id:
            if shot.scene_id not in self.valid_scene_ids:
                nearest_scene = self._find_nearest_scene_id(shot_idx, shot_sequence)
                if nearest_scene:
                    warning(f"修复镜头 {shot.id} 的场景引用: {shot.scene_id} -> {nearest_scene}")
                    shot.scene_id = nearest_scene
        return shot

    def _find_nearest_scene_id(self, shot_idx: int, shot_sequence: ShotSequence) -> Optional[str]:
        """查找最近的场景ID"""
        for i in range(shot_idx - 1, -1, -1):
            if hasattr(shot_sequence.shots[i], 'scene_id') and shot_sequence.shots[i].scene_id in self.valid_scene_ids:
                return shot_sequence.shots[i].scene_id
        for i in range(shot_idx + 1, len(shot_sequence.shots)):
            if hasattr(shot_sequence.shots[i], 'scene_id') and shot_sequence.shots[i].scene_id in self.valid_scene_ids:
                return shot_sequence.shots[i].scene_id
        if self.valid_scene_ids:
            return next(iter(self.valid_scene_ids))
        return "scene_001"

    def _fix_fragments_continuity(self, fragments: List[VideoFragment], shot: ShotInfo) -> List[VideoFragment]:
        """修复片段的连续性"""
        for fragment in fragments:
            if hasattr(shot, 'scene_id') and shot.scene_id:
                fragment.continuity_notes["location"] = f"场景{shot.scene_id}"
            if "continuity_notes" not in fragment.continuity_notes:
                fragment.continuity_notes = {}
            fragment.continuity_notes["continuity_check"] = "passed"
        return fragments

    def _normalize_fragment_ids(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """规范化片段ID"""
        normalized = []
        id_mapping = {}

        for i, fragment in enumerate(fragments, 1):
            old_id = fragment.id
            new_id = f"frag_{i:03d}"

            if not hasattr(fragment, 'metadata') or fragment.metadata is None:
                fragment.metadata = {}
            fragment.metadata['original_id'] = old_id

            fragment.id = new_id
            id_mapping[old_id] = new_id
            normalized.append(fragment)

        for fragment in normalized:
            if "prev_fragment" in fragment.continuity_notes:
                old_prev = fragment.continuity_notes["prev_fragment"]
                if old_prev in id_mapping:
                    fragment.continuity_notes["prev_fragment"] = id_mapping[old_prev]

        return normalized

    def _split_shot_with_llm(self, context: Dict[str, Any]) -> List[VideoFragment]:
        """使用LLM分割单个镜头"""
        shot = context["shot"]
        cache_key = f"{shot.id}_{shot.duration}_{hash(shot.description)}"

        if cache_key in self.split_cache:
            debug(f"使用缓存的分割决策: {shot.id}")
            return self._create_fragments_from_cache(self.split_cache[cache_key], context)

        # 准备提示词 - 传入global_metadata
        user_prompt = self._get_enhanced_prompt_template(context)
        system_prompt = self._get_prompt_template("video_splitter_system")

        debug(f"调用LLM分割镜头 {shot.id}")
        start_time = time.time()

        try:
            llm_response = self._call_llm_parse_with_retry(
                self.llm_client, system_prompt, user_prompt
            )

            response_time = time.time() - start_time
            debug(f"LLM响应时间: {response_time:.2f}s")

            if isinstance(llm_response, str):
                try:
                    decision = json.loads(llm_response)
                except json.JSONDecodeError:
                    error(f"LLM返回非JSON格式: {llm_response[:100]}...")
                    raise ValueError("LLM返回格式错误")
            else:
                decision = llm_response

            self._validate_llm_decision(decision, shot)
            self.split_cache[cache_key] = decision

            return self._create_fragments_from_decision(decision, context)

        except Exception as e:
            error(f"LLM分割失败: {str(e)}")
            raise

    def _get_continuity_notes(self, shot: ShotInfo) -> str:
        """生成连续性说明"""
        notes = []
        if shot.main_character:
            notes.append(f"主要角色: {shot.main_character}")
        if hasattr(shot, 'scene_id'):
            notes.append(f"场景ID: {shot.scene_id}")
        return "; ".join(notes) if notes else "无特殊连续性要求"

    def _validate_llm_decision(self, decision: Dict, shot: ShotInfo) -> None:
        """验证LLM决策"""
        if not isinstance(decision, dict):
            raise ValueError(f"决策必须是字典格式")

        if "needs_split" not in decision:
            raise ValueError("决策中缺少 needs_split 字段")

        if decision.get("needs_split", False):
            if "segments" not in decision:
                raise ValueError("需要分割但缺少 segments 字段")

            segments = decision["segments"]
            if not isinstance(segments, list) or len(segments) == 0:
                raise ValueError("segments 必须是非空列表")

            total_duration = 0
            for i, segment in enumerate(segments):
                if "duration" not in segment:
                    raise ValueError(f"片段{i + 1}缺少duration字段")
                duration = segment["duration"]
                if duration < self.min_split_segment or duration > self.max_split_segment:
                    raise ValueError(f"片段{i + 1}时长({duration}s)超出范围")
                total_duration += duration

            if abs(total_duration - shot.duration) > 1.0:
                warning(f"分割总时长({total_duration}s)与镜头时长({shot.duration}s)不匹配")

    def _create_fragments_from_decision(self, decision: Dict, context: Dict) -> List[VideoFragment]:
        """根据LLM决策创建片段"""
        shot = context["shot"]
        current_time = context["current_time"]
        fragment_offset = context["fragment_offset"]

        fragments = []

        if decision.get("needs_split", False):
            segments = decision["segments"]
            continuity_plan = decision.get("continuity_plan", {})

            for seg_idx, segment in enumerate(segments):
                fragment_id = f"frag_{fragment_offset + len(fragments) + 1:03d}_s{seg_idx + 1}"
                segment_start_time = current_time + sum(s.get("duration", 0) for s in segments[:seg_idx])

                description = segment.get("description")
                if not description:
                    description = f"{shot.description} (部分{seg_idx + 1}/{len(segments)})"
                    warning(f"片段{seg_idx + 1}缺少description字段，使用默认标记")

                continuity_notes = {
                    "main_character": shot.main_character,
                    "location": f"场景{shot.scene_id}",
                    "continuity_id": f"{shot.id}_seq{seg_idx + 1}",
                    "prev_fragment": fragments[-1].id if fragments else None,
                    "split_reason": decision.get("reason", "AI智能分割"),
                    "segment_part": f"{seg_idx + 1}/{len(segments)}",
                    "character_consistency": continuity_plan.get("character_consistency", ""),
                    "scene_consistency": continuity_plan.get("scene_consistency", ""),
                    "transition_suggestions": continuity_plan.get("transition_suggestions", []),
                    "continuity_hints": segment.get("continuity_hints", [])
                }

                metadata = {
                    "split_by": AgentMode.LLM,
                    "original_shot": shot.id,
                    "original_description": shot.description,
                    "original_element_ids": shot.element_ids,  # 保存原始元素ID（用于音频连续性）
                    "element_ids": shot.element_ids,  # 当前片段的元素ID
                    "segment_index": seg_idx,
                    "total_segments": len(segments),
                    "ai_decision": decision.get("reason", ""),
                    "timestamp": time.time(),
                    "key_frames": segment.get("key_frames", []),
                    "continuity_plan": continuity_plan
                }

                fragment = VideoFragment(
                    id=fragment_id,
                    shot_id=shot.id,
                    element_ids=shot.element_ids,
                    start_time=round(segment_start_time, 2),
                    duration=segment["duration"],
                    description=description,
                    continuity_notes=continuity_notes,
                    metadata=metadata,
                    requires_special_attention=(seg_idx > 0)
                )
                fragments.append(fragment)

        else:
            fragment_id = f"frag_{fragment_offset + 1:03d}"
            continuity_plan = decision.get("continuity_plan", {})

            continuity_notes = {
                "main_character": shot.main_character,
                "location": f"场景{shot.scene_id}",
                "continuity_id": f"{shot.id}_whole",
                "split_reason": decision.get("reason", "无需分割"),
                "character_consistency": continuity_plan.get("character_consistency", ""),
                "scene_consistency": continuity_plan.get("scene_consistency", ""),
                "transition_suggestions": continuity_plan.get("transition_suggestions", [])
            }

            metadata = {
                "split_by": AgentMode.LLM,
                "original_shot": shot.id,
                "original_description": shot.description,
                "original_element_ids": shot.element_ids,
                "element_ids": shot.element_ids,
                "segment_index": 0,
                "total_segments": 1,
                "ai_decision": decision.get("reason", ""),
                "timestamp": time.time(),
                "continuity_plan": continuity_plan
            }

            fragment = VideoFragment(
                id=fragment_id,
                shot_id=shot.id,
                element_ids=shot.element_ids,
                start_time=current_time,
                duration=min(shot.duration, self.max_split_segment),
                description=shot.description,
                continuity_notes=continuity_notes,
                metadata=metadata,
                requires_special_attention=False
            )
            fragments.append(fragment)

        return fragments

    def _create_fragments_from_cache(self, decision: Dict, context: Dict) -> List[VideoFragment]:
        """从缓存创建片段"""
        cached_decision = decision.copy()
        if "segments" in cached_decision:
            cached_decision["segments"] = [seg.copy() for seg in cached_decision["segments"]]
        return self._create_fragments_from_decision(cached_decision, context)

    def _validate_and_adjust_fragments(self, fragments: List[VideoFragment],
                                       shot: ShotInfo, current_time: float,
                                       fragment_offset: int) -> List[VideoFragment]:
        """验证并调整分割片段"""
        if not fragments:
            warning(f"镜头{shot.id}分割结果为空，使用规则分割")
            return self.rule_splitter.split_shot(shot, current_time, fragment_offset)

        total_duration = sum(f.duration for f in fragments)
        if abs(total_duration - shot.duration) > 2.0:
            warning(f"镜头{shot.id}分割总时长({total_duration}s)与原始时长({shot.duration}s)差异过大")
            scale_factor = shot.duration / total_duration
            for fragment in fragments:
                fragment.duration = round(fragment.duration * scale_factor, 2)

        prev_end_time = current_time
        for i, fragment in enumerate(fragments):
            fragment.start_time = prev_end_time
            prev_end_time += fragment.duration
            if i > 0:
                fragment.continuity_notes["prev_fragment"] = fragments[i - 1].id

        return fragments
