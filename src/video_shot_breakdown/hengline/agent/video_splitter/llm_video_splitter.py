"""
@FileName: llm_video_splitter.py
@Description: 基于LLM的视频智能分割器，保持视频连贯性与一致性
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 22:30
"""
import re
from typing import List, Optional, Dict, Any
import json
import time

from video_shot_breakdown.hengline.agent.base_agent import BaseAgent
from video_shot_breakdown.hengline.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo
from video_shot_breakdown.hengline.agent.video_splitter.base_video_splitter import BaseVideoSplitter
from video_shot_breakdown.hengline.agent.video_splitter.rule_video_splitter import RuleVideoSplitter
from video_shot_breakdown.hengline.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from video_shot_breakdown.hengline.hengline_config import HengLineConfig
from video_shot_breakdown.logger import info, error, warning, debug
from video_shot_breakdown.utils.log_utils import print_log_exception


class LLMVideoSplitter(BaseVideoSplitter, BaseAgent):
    """基于LLM的视频智能分割器 - 保持连贯性与一致性"""

    def __init__(self, llm_client, config: Optional[HengLineConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.rule_splitter = RuleVideoSplitter(config)  # 备用规则分割器
        self.split_cache = {}  # 缓存分割决策，避免重复计算

        # 分割阈值配置
        self.split_threshold = getattr(config, 'llm_split_threshold', 5.0)  # 超过5秒触发AI分割
        self.min_split_segment = getattr(config, 'min_fragment_duration', 1.0)  # 最小分割片段
        self.max_split_segment = getattr(config, 'max_fragment_duration', 5.0)  # 最大分割片段

        # 新增：气象一致性配置
        self.enforce_weather_consistency = True
        self.valid_scene_ids = set()
        self.overall_weather = None

    def cut(self, shot_sequence: ShotSequence) -> FragmentSequence:
        """使用LLM智能分割视频，保持连贯性"""
        info(f"开始智能视频分割，镜头数: {len(shot_sequence.shots)}")

        fragments = []
        current_time = 0.0
        fragment_id_counter = 0

        # 第一步：收集场景和角色信息，用于保持一致性
        scene_context = self._collect_scene_context(shot_sequence)

        # 第二步：收集所有有效的场景ID
        self._collect_valid_scene_ids(shot_sequence)

        # 第三步：分析整体气象基调
        self.overall_weather = self._detect_overall_weather(shot_sequence)
        info(f"检测到整体气象基调: {self.overall_weather}")

        source_info = {
            "shot_count": len(shot_sequence.shots),
            "original_duration": shot_sequence.stats.get("total_duration", 0.0),
            "split_method": "llm_adaptive_fixed",
            "scene_context": scene_context,
            "overall_weather": self.overall_weather
        }

        for shot_idx, shot in enumerate(shot_sequence.shots):
            try:
                # 在分割前修复镜头描述中的气象和场景引用
                shot = self._fix_shot_continuity(shot, shot_idx, shot_sequence)

                debug(f"处理镜头 {shot.id}: {shot.description} (时长: {shot.duration}s)")

                # 判断是否需要AI分割
                if self._should_use_llm_split(shot):
                    info(f"镜头 {shot.id} 时长({shot.duration}s)超过阈值，使用AI分割")

                    context = {
                        "shot": shot,
                        "prev_shot": shot_sequence.shots[shot_idx - 1] if shot_idx > 0 else None,
                        "next_shot": shot_sequence.shots[shot_idx + 1] if shot_idx < len(shot_sequence.shots) - 1 else None,
                        "scene_context": scene_context,
                        "current_time": current_time,
                        "fragment_offset": fragment_id_counter,
                        "overall_weather": self.overall_weather
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

                    # 修复规则分割片段的描述
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

                # 修复降级片段的描述
                fallback_fragments = self._fix_fragments_continuity(fallback_fragments, shot)

                fragments.extend(fallback_fragments)
                fragment_id_counter += len(fallback_fragments)

                if fallback_fragments:
                    current_time = fallback_fragments[-1].start_time + fallback_fragments[-1].duration

        # 后处理：规范化片段ID
        fragments = self._normalize_fragment_ids(fragments)

        fragment_sequence = FragmentSequence(
            source_info=source_info,
            fragments=fragments,
            metadata={
                "split_method": "LLM",
                "ai_split_count": sum(1 for f in fragments if f.metadata.get("split_by", "") == "ai"),
                "rule_split_count": sum(1 for f in fragments if f.metadata.get("split_by", "") == "rule"),
                "total_fragments": len(fragments),
                "average_duration": round(sum(f.duration for f in fragments) / len(fragments), 2) if fragments else 0,
                "overall_weather": self.overall_weather,
                "weather_fixed": True
            }
        )

        info(f"视频分割完成: 共生成{len(fragments)}个片段")
        return self.post_process(fragment_sequence)

    def _should_use_llm_split(self, shot: ShotInfo) -> bool:
        """判断是否应该使用AI分割（从原代码复制）"""
        # 基础条件：时长超过阈值
        if shot.duration <= self.split_threshold:
            return False

        # 复杂镜头类型更适合AI分割
        complex_shots = ["ACTION", "MOVING", "PANORAMA", "ZOOM"]
        if shot.shot_type in complex_shots:
            return True

        # 长对话场景
        if shot.description and any(keyword in shot.description.lower() for keyword in ["对话", "交谈", "讨论", "talk", "conversation"]):
            return True

        return True  # 默认超过阈值就用AI

    def _collect_scene_context(self, shot_sequence: ShotSequence) -> Dict[str, Any]:
        """收集场景上下文信息（从原代码复制）"""
        scene_context = {
            "scenes": {},
            "characters": {},
            "locations": {},
            "mood": {}
        }

        for shot in shot_sequence.shots:
            # 按场景分组
            scene_id = shot.scene_id
            if scene_id not in scene_context["scenes"]:
                scene_context["scenes"][scene_id] = {
                    "shot_ids": [],
                    "duration": 0,
                    "main_characters": set(),
                    "mood": shot.mood if hasattr(shot, 'mood') else "neutral"
                }

            scene_context["scenes"][scene_id]["shot_ids"].append(shot.id)
            scene_context["scenes"][scene_id]["duration"] += shot.duration

            if shot.main_character:
                characters = shot.main_character.split(",")
                for char in characters:
                    char = char.strip()
                    scene_context["scenes"][scene_id]["main_characters"].add(char)

                    # 记录角色出现
                    if char not in scene_context["characters"]:
                        scene_context["characters"][char] = {
                            "scenes": set(),
                            "total_duration": 0
                        }
                    scene_context["characters"][char]["scenes"].add(scene_id)
                    scene_context["characters"][char]["total_duration"] += shot.duration

        return scene_context

    def _collect_valid_scene_ids(self, shot_sequence: ShotSequence):
        """收集所有有效的场景ID"""
        self.valid_scene_ids.clear()
        for shot in shot_sequence.shots:
            if hasattr(shot, 'scene_id') and shot.scene_id:
                self.valid_scene_ids.add(shot.scene_id)
        debug(f"有效场景ID: {self.valid_scene_ids}")

    def _detect_overall_weather(self, shot_sequence: ShotSequence) -> str:
        """检测整体气象基调"""
        weather_keywords = {
            "overcast": ["overcast", "阴天", "灰蒙蒙", "cloudy", "grey"],
            "rainy": ["rain", "rainy", "下雨", "雨", "wet", "drizzle", "raindrop"],
            "golden_hour": ["golden hour", "golden-hour", "金色时刻", "暖阳"],
            "sunny": ["sunny", "晴天", "sunlight", "bright", "阳光"],
            "night": ["night", "夜晚", "dark", "evening", "灯光"],
            "foggy": ["fog", "foggy", "雾", "mist", "氤氲"]
        }

        weather_counts = {weather: 0 for weather in weather_keywords}

        for shot in shot_sequence.shots:
            desc_lower = shot.description.lower()
            for weather, keywords in weather_keywords.items():
                if any(keyword in desc_lower for keyword in keywords):
                    weather_counts[weather] += 1

        # 找出出现次数最多的天气
        if weather_counts:
            dominant_weather = max(weather_counts.items(), key=lambda x: x[1])
            if dominant_weather[1] > 0:
                return dominant_weather[0]

        # 默认返回阴天
        return "overcast"

    def _fix_shot_continuity(self, shot: ShotInfo, shot_idx: int, shot_sequence: ShotSequence) -> ShotInfo:
        """修复镜头描述的连续性"""
        # 修复场景引用
        if hasattr(shot, 'scene_id') and shot.scene_id:
            if shot.scene_id not in self.valid_scene_ids:
                # 尝试找到最近的场景ID
                nearest_scene = self._find_nearest_scene_id(shot_idx, shot_sequence)
                if nearest_scene:
                    warning(f"修复镜头 {shot.id} 的场景引用: {shot.scene_id} -> {nearest_scene}")
                    shot.scene_id = nearest_scene

        # 修复天气一致性
        shot.description = self._fix_weather_in_description(shot.description)

        return shot

    def _find_nearest_scene_id(self, shot_idx: int, shot_sequence: ShotSequence) -> Optional[str]:
        """查找最近的场景ID"""
        # 向前查找
        for i in range(shot_idx - 1, -1, -1):
            if hasattr(shot_sequence.shots[i], 'scene_id') and shot_sequence.shots[i].scene_id in self.valid_scene_ids:
                return shot_sequence.shots[i].scene_id

        # 向后查找
        for i in range(shot_idx + 1, len(shot_sequence.shots)):
            if hasattr(shot_sequence.shots[i], 'scene_id') and shot_sequence.shots[i].scene_id in self.valid_scene_ids:
                return shot_sequence.shots[i].scene_id

        # 如果都没有，返回第一个有效场景ID
        if self.valid_scene_ids:
            return next(iter(self.valid_scene_ids))

        return "scene_001"

    def _fix_weather_in_description(self, description: str) -> str:
        """修复描述中的天气一致性"""
        if not self.enforce_weather_consistency or not self.overall_weather:
            return description

        # 检查是否有天气冲突
        has_golden_hour = "golden hour" in description.lower()
        has_rain = any(word in description.lower() for word in ["rain", "rainy", "下雨", "雨", "wet"])
        has_sunny = any(word in description.lower() for word in ["sunny", "sunlight", "晴天", "阳光"])

        # 如果整体是阴雨天，但描述中有 golden hour，需要修复
        if self.overall_weather in ["overcast", "rainy"] and has_golden_hour:
            warning(f"修复天气冲突: golden hour 出现在阴雨天描述中")
            description = description.replace("golden hour", "overcast late afternoon")
            description = description.replace("warm sunlight", "soft diffused light")
            description = description.replace("sunlight", "ambient light")
            description = description.replace("sunny", "overcast")

        # 如果整体是晴天，但描述中有雨，也需要修复
        if self.overall_weather == "sunny" and has_rain:
            warning(f"修复天气冲突: rain 出现在晴天描述中")
            description = re.sub(r'rain[y\s][^,.]*', 'dry', description, flags=re.IGNORECASE)
            description = description.replace("wet", "dry")
            description = description.replace("puddle", "dry ground")

        # 如果整体是阴天，确保没有阳光描述
        if self.overall_weather == "overcast" and has_sunny:
            description = description.replace("sunlight", "ambient light")
            description = description.replace("sunny", "overcast")

        return description

    def _fix_fragments_continuity(self, fragments: List[VideoFragment], shot: ShotInfo) -> List[VideoFragment]:
        """修复片段的连续性"""
        for fragment in fragments:
            # 修复场景引用
            if hasattr(shot, 'scene_id') and shot.scene_id:
                fragment.continuity_notes["location"] = f"场景{shot.scene_id}"

            # 修复天气
            fragment.description = self._fix_weather_in_description(fragment.description)

            # 添加修复标记
            if "continuity_notes" not in fragment.continuity_notes:
                fragment.continuity_notes = {}
            fragment.continuity_notes["weather_fixed"] = self.overall_weather
            fragment.continuity_notes["continuity_check"] = "passed"

        return fragments

    def _normalize_fragment_ids(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """规范化片段ID，统一为 frag_XXX 格式"""
        normalized = []
        id_mapping = {}

        for i, fragment in enumerate(fragments, 1):
            old_id = fragment.id
            new_id = f"frag_{i:03d}"

            # 保存原ID到元数据
            if not hasattr(fragment, 'metadata') or fragment.metadata is None:
                fragment.metadata = {}
            fragment.metadata['original_id'] = old_id

            # 更新ID
            fragment.id = new_id
            id_mapping[old_id] = new_id

            normalized.append(fragment)

        # 更新 continuity_notes 中的 prev_fragment 引用
        for fragment in normalized:
            if "prev_fragment" in fragment.continuity_notes:
                old_prev = fragment.continuity_notes["prev_fragment"]
                if old_prev in id_mapping:
                    fragment.continuity_notes["prev_fragment"] = id_mapping[old_prev]

        debug(f"片段ID规范化完成: {len(fragments)}个片段")
        return normalized

    def _split_shot_with_llm(self, context: Dict[str, Any]) -> List[VideoFragment]:
        """使用LLM分割单个镜头"""
        shot = context["shot"]
        cache_key = f"{shot.id}_{shot.duration}_{hash(shot.description)}"

        # 检查缓存
        if cache_key in self.split_cache:
            debug(f"使用缓存的分割决策: {shot.id}")
            return self._create_fragments_from_cache(
                self.split_cache[cache_key], context
            )

        # 准备提示词
        user_prompt = self._get_enhanced_prompt_template(context)
        system_prompt = self._get_prompt_template("video_splitter_system")

        debug(f"调用LLM分割镜头 {shot.id}")
        start_time = time.time()

        try:
            # 调用LLM
            llm_response = self._call_llm_parse_with_retry(
                self.llm_client, system_prompt, user_prompt
            )

            response_time = time.time() - start_time
            debug(f"LLM响应时间: {response_time:.2f}s")

            # 解析响应
            if isinstance(llm_response, str):
                try:
                    decision = json.loads(llm_response)
                except json.JSONDecodeError:
                    error(f"LLM返回非JSON格式: {llm_response[:100]}...")
                    raise ValueError("LLM返回格式错误")
            else:
                decision = llm_response

            # 验证决策
            self._validate_llm_decision(decision, shot)

            # 缓存决策
            self.split_cache[cache_key] = decision

            # 创建片段
            fragments = self._create_fragments_from_decision(decision, context)

            return fragments

        except Exception as e:
            error(f"LLM分割失败: {str(e)}")
            raise

    def _get_enhanced_prompt_template(self, context: Dict[str, Any]) -> str:
        """获取增强的提示词模板"""
        shot = context["shot"]
        prev_shot = context.get("prev_shot")
        next_shot = context.get("next_shot")
        scene_context = context.get("scene_context", {})
        overall_weather = context.get("overall_weather", "overcast")

        # 构建详细上下文
        scene_info = ""
        if shot.scene_id and shot.scene_id in scene_context.get("scenes", {}):
            scene_data = scene_context["scenes"][shot.scene_id]
            characters = ", ".join(list(scene_data.get("main_characters", [])))
            scene_info = f"场景{shot.scene_id}: 时长{scene_data.get('duration', 0)}秒, 角色[{characters}], 氛围{scene_data.get('mood', '中性')}"

        prev_context = ""
        if prev_shot:
            prev_context = f"{prev_shot.description} ({prev_shot.duration}s)"

        next_context = ""
        if next_shot:
            next_context = f"{next_shot.description} ({next_shot.duration}s)"

        user_template = self._get_prompt_template("video_splitter_user")

        return user_template.format(
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
            overall_weather=overall_weather,
            continuity_notes=self._get_continuity_notes(shot, context)
        )


    def _get_continuity_notes(self, shot: ShotInfo, context: Dict) -> str:
        """生成连续性说明"""
        notes = []

        # 角色连续性
        if shot.main_character:
            notes.append(f"主要角色: {shot.main_character}")

        # 场景连续性
        if hasattr(shot, 'scene_id'):
            notes.append(f"场景ID: {shot.scene_id}")

        # 视觉元素连续性
        if hasattr(shot, 'visual_elements') and shot.visual_elements:
            elements = shot.visual_elements.split(",") if shot.visual_elements else []
            if elements:
                notes.append(f"关键视觉元素: {', '.join(elements[:3])}")

        # 动作连续性
        if "动作" in shot.description or "move" in shot.description.lower():
            notes.append("注意动作的连贯衔接")

        # 添加气象提示
        if self.overall_weather:
            notes.append(f"整体气象: {self.overall_weather}")

        return "; ".join(notes) if notes else "无特殊连续性要求"

    def _validate_llm_decision(self, decision: Dict, shot: ShotInfo) -> None:
        """验证LLM决策的合理性"""
        if not isinstance(decision, dict):
            raise ValueError(f"决策必须是字典格式，实际是{type(decision)}")

        if "needs_split" not in decision:
            raise ValueError("决策中缺少 needs_split 字段")

        if decision.get("needs_split", False):
            if "segments" not in decision:
                raise ValueError("需要分割但缺少 segments 字段")

            segments = decision["segments"]
            if not isinstance(segments, list) or len(segments) == 0:
                raise ValueError("segments 必须是非空列表")

            # 检查每个片段
            total_duration = 0
            for i, segment in enumerate(segments):
                if "duration" not in segment:
                    raise ValueError(f"片段{i + 1}缺少duration字段")

                duration = segment["duration"]
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise ValueError(f"片段{i + 1}的duration必须是正数")

                if duration < self.min_split_segment:
                    raise ValueError(f"片段{i + 1}时长({duration}s)低于最小值({self.min_split_segment}s)")

                if duration > self.max_split_segment:
                    raise ValueError(f"片段{i + 1}时长({duration}s)超过最大值({self.max_split_segment}s)")

                total_duration += duration

            # 检查总时长匹配
            if abs(total_duration - shot.duration) > 1.0:  # 允许1秒误差
                warning(f"分割总时长({total_duration}s)与镜头时长({shot.duration}s)不匹配")

    def _create_fragments_from_decision(self, decision: Dict, context: Dict) -> List[VideoFragment]:
        """
        根据LLM决策创建片段
        核心改动：使用原始描述，不让LLM重新生成描述
        """
        shot = context["shot"]
        current_time = context["current_time"]
        fragment_offset = context["fragment_offset"]
        overall_weather = context.get("overall_weather", "overcast")

        fragments = []

        if decision.get("needs_split", False):
            segments = decision["segments"]

            # 保存原始描述
            original_desc = shot.description

            for seg_idx, segment in enumerate(segments):
                fragment_id = f"frag_{fragment_offset + len(fragments) + 1:03d}_s{seg_idx + 1}"

                # 计算开始时间
                segment_start_time = current_time + sum(
                    s.get("duration", 0) for s in segments[:seg_idx]
                )

                fragment = VideoFragment(
                    id=fragment_id,
                    shot_id=shot.id,
                    element_ids=shot.element_ids if seg_idx == 0 else [],
                    start_time=round(segment_start_time, 2),
                    duration=segment["duration"],
                    # 关键修改：使用原始描述，而不是segment.get("description")
                    description=original_desc,
                    continuity_notes={
                        "main_character": shot.main_character,
                        "location": f"场景{shot.scene_id}",
                        "continuity_id": f"{shot.id}_seq{seg_idx + 1}",
                        "prev_fragment": fragments[-1].id if fragments else None,
                        "split_reason": decision.get("reason", "AI智能分割"),
                        "weather": overall_weather,
                        "segment_hint": f"部分{seg_idx + 1}/{len(segments)}"
                    },
                    metadata={
                        "split_by": "ai",
                        "original_shot": shot.id,
                        "original_description": original_desc,  # 保存原始描述
                        "segment_index": seg_idx,
                        "total_segments": len(segments),
                        "ai_decision": decision.get("reason", ""),
                        "timestamp": time.time()
                    }
                )
                fragments.append(fragment)
        else:
            # 不分割 - 直接使用原始描述
            fragment_id = f"frag_{fragment_offset + 1:03d}"
            fragment = VideoFragment(
                id=fragment_id,
                shot_id=shot.id,
                element_ids=shot.element_ids,
                start_time=current_time,
                duration=min(shot.duration, self.max_split_segment),
                description=shot.description,  # 直接使用原始描述
                continuity_notes={
                    "main_character": shot.main_character,
                    "location": f"场景{shot.scene_id}",
                    "continuity_id": f"{shot.id}_whole",
                    "split_reason": decision.get("reason", "无需分割"),
                    "weather": overall_weather
                },
                metadata={
                    "split_by": "ai",
                    "original_shot": shot.id,
                    "original_description": shot.description,
                    "segment_index": 0,
                    "total_segments": 1,
                    "ai_decision": decision.get("reason", ""),
                    "timestamp": time.time()
                }
            )
            fragments.append(fragment)

        return fragments

    def _create_fragments_from_cache(self, decision: Dict, context: Dict) -> List[VideoFragment]:
        """从缓存创建片段"""
        # 创建副本避免修改缓存
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

        # 验证总时长
        total_duration = sum(f.duration for f in fragments)
        if abs(total_duration - shot.duration) > 2.0:  # 允许2秒误差
            warning(f"镜头{shot.id}分割总时长({total_duration}s)与原始时长({shot.duration}s)差异过大")
            # 重新分配时长
            scale_factor = shot.duration / total_duration
            for fragment in fragments:
                fragment.duration = round(fragment.duration * scale_factor, 2)

        # 确保连续性
        prev_end_time = current_time
        for i, fragment in enumerate(fragments):
            fragment.start_time = prev_end_time
            prev_end_time += fragment.duration

            # 更新连续性ID
            if i > 0:
                fragment.continuity_notes["prev_fragment"] = fragments[i - 1].id

        return fragments