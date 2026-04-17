"""
@FileName: llm_prompt_converter.py
@Description: 基于LLM的提示词转换器 - 音频参数由LLM直接从CharacterInfo解析
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 23:36
"""
import json
from typing import Optional, Dict, Any

from penshot.logger import info, error
from penshot.neopen.agent.base_llm_agent import BaseLLMAgent
from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.prompt_converter.base_prompt_converter import BasePromptConverter
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
    AIVideoInstructions,
    AIAudioPrompt,
    AudioModelType,
    AudioVoiceType,
    VideoStyle
)
from penshot.neopen.agent.prompt_converter.template_prompt_converter import TemplatePromptConverter
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.shot_language import get_language
from penshot.utils.log_utils import print_log_exception
from penshot.utils.str_count_utils import only_count_en


class LLMPromptConverter(BasePromptConverter, BaseLLMAgent):
    """基于LLM的提示词转换器 - 音频参数由LLM直接从CharacterInfo解析"""

    def __init__(self, llm_client, config: Optional[ShotConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.parsed_script = None
        self.global_metadata = None
        self.last_audio_id = None
        self.element_map = {}  # 元素ID到原始内容的映射
        #
        self.current_repair_params = None
        self.current_historical_context = None

        # 初始化提示词
        self._init_prompts()

    def _init_prompts(self):
        """初始化提示词模板"""
        self.system_prompt = self._get_prompt_template("prompt_converter_system")
        self.user_prompt_template = self._get_prompt_template("prompt_converter_user")


    def convert(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript,
                repair_params: Optional[QualityRepairParams],
                historical_context: Optional[Dict[str, Any]]) -> AIVideoInstructions:
        """使用LLM转换提示词 - 同时生成视频和音频提示词"""
        info(f"使用LLM转换提示词，片段数: {len(fragment_sequence.fragments)}")

        # 保存历史上下文
        self.current_historical_context = historical_context

        # 如果有修复参数，保存到实例
        if repair_params:
            self.current_repair_params = repair_params

        # 保存ParsedScript供后续使用
        self.parsed_script = parsed_script
        self.global_metadata = parsed_script.global_metadata

        # === 构建全局元素映射 ===
        self._build_element_map()

        prompts = []
        project_info = {
            "title": fragment_sequence.source_info.get("title", "AI视频项目"),
            "total_fragments": fragment_sequence.stats.get("fragment_count", 0),
            "total_duration": fragment_sequence.stats.get("total_duration", 0.0)
        }

        for fragment in fragment_sequence.fragments:
            try:
                prompt = self._convert_fragment_with_llm(fragment, historical_context)
                prompts.append(prompt)
            except Exception as e:
                print_log_exception()
                error(f"片段{fragment.id}转换失败: {str(e)}")
                # 降级到模板转换
                template_converter = TemplatePromptConverter(self.config)
                fallback_prompt = template_converter.convert_fragment(fragment)
                prompts.append(fallback_prompt)

        instructions = AIVideoInstructions(
            project_info=project_info,
            fragments=prompts
        )

        # 应用修复参数
        if self.current_repair_params and self.current_repair_params.fix_needed:
            instructions = self._apply_repair_params(instructions, fragment_sequence)

        return self.post_process(instructions)


    def _apply_repair_params(self, instructions: AIVideoInstructions,
                             fragment_sequence: FragmentSequence) -> AIVideoInstructions:
        """应用修复参数调整提示词"""
        if not self.current_repair_params:
            return instructions

        info(f"应用修复参数调整提示词，问题类型: {self.current_repair_params.issue_types}")

        issue_types = set(self.current_repair_params.issue_types)

        # 1. 修复空提示词
        if "prompt_empty" in issue_types:
            instructions = self._fix_empty_prompts(instructions, fragment_sequence)

        # 2. 修复长度问题
        if "prompt_too_long" in issue_types or "prompt_too_short" in issue_types:
            instructions = self._fix_length_issues(instructions)

        # 3. 修复截断问题
        if "prompt_truncated" in issue_types:
            instructions = self._fix_truncated_prompts(instructions)

        # 4. 修复风格不一致
        if "style_inconsistent" in issue_types:
            instructions = self._fix_style_consistency(instructions)

        # 5. 修复负面提示词
        if "negative_prompt_missing" in issue_types:
            instructions = self._fix_negative_prompts(instructions)

        # 6. 修复音频问题
        if "audio" in str(issue_types):
            instructions = self._fix_audio_issues(instructions)

        return instructions

    def _fix_empty_prompts(self, instructions: AIVideoInstructions,
                           fragment_sequence: FragmentSequence) -> AIVideoInstructions:
        """修复空提示词"""
        fragment_map = {f.id: f for f in fragment_sequence.fragments}

        for prompt in instructions.fragments:
            if not prompt.prompt or not prompt.prompt.strip():
                if prompt.fragment_id in fragment_map:
                    fragment = fragment_map[prompt.fragment_id]
                    prompt.prompt = fragment.description or "视频片段"
                    info(f"修复空提示词: {prompt.fragment_id}")
                else:
                    prompt.prompt = "默认视频片段"
                    info(f"使用默认提示词: {prompt.fragment_id}")

        return instructions

    def _fix_length_issues(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """修复长度问题"""
        for prompt in instructions.fragments:
            prompt_length = only_count_en(prompt.prompt)

            if prompt_length > self.config.prompt_length_max_threshold:
                # 截断
                prompt.prompt = prompt.prompt[:self.config.prompt_length_max_threshold - 20] + "..."
                info(f"截断过长提示词: {prompt.fragment_id} {prompt_length} -> {self.config.prompt_length_max_threshold}")

            elif prompt_length < self.config.prompt_length_min_threshold:
                # 扩展
                extension = "，高清画质，电影级质感"
                prompt.prompt = prompt.prompt + extension
                info(f"扩展过短提示词: {prompt.fragment_id} {prompt_length} -> {only_count_en(prompt.prompt)}")

        return instructions

    def _fix_truncated_prompts(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """修复截断提示词"""
        for prompt in instructions.fragments:
            if prompt.prompt.endswith('...') or prompt.prompt.endswith('…'):
                prompt.prompt = prompt.prompt.rstrip('...').rstrip('…')
                info(f"修复截断提示词: {prompt.fragment_id}")
        return instructions

    def _fix_style_consistency(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """修复风格一致性"""
        default_style = self.config.default_style
        for prompt in instructions.fragments:
            if prompt.style and prompt.style != default_style:
                old_style = prompt.style
                prompt.style = default_style
                info(f"统一风格: {prompt.fragment_id} {old_style} -> {default_style}")
        return instructions

    def _fix_negative_prompts(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """修复负面提示词"""
        default_negative = self.config.default_negative_prompt or "low quality, blurry, distorted, bad anatomy"
        for prompt in instructions.fragments:
            if not prompt.negative_prompt or len(prompt.negative_prompt.strip()) < 10:
                prompt.negative_prompt = default_negative
                info(f"添加负面提示词: {prompt.fragment_id}")
        return instructions

    def _fix_audio_issues(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """修复音频问题"""
        from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIAudioPrompt, AudioModelType, AudioVoiceType

        for prompt in instructions.fragments:
            if not prompt.audio_prompt:
                # 创建默认音频提示词
                prompt.audio_prompt = AIAudioPrompt(
                    audio_id=f"audio{prompt.fragment_id[4:]}",
                    prompt=f"音频片段，时长{prompt.duration}秒",
                    model_type=AudioModelType.XTTSv2,
                    voice_type=AudioVoiceType.CHARACTER_DIALOGUE,
                    duration_seconds=prompt.duration
                )
                info(f"创建默认音频提示词: {prompt.fragment_id}")
            elif prompt.audio_prompt.duration_seconds and abs(prompt.audio_prompt.duration_seconds - prompt.duration) > 0.5:
                # 修复时长不匹配
                prompt.audio_prompt.duration_seconds = prompt.duration
                info(f"修复音频时长: {prompt.fragment_id} -> {prompt.duration}s")

        return instructions


    def _build_history_hint(self, historical_context: Optional[Dict[str, Any]]) -> str:
        """构建历史上下文提示"""
        if not historical_context:
            return ""

        hints = []

        # 1. 常见问题模式
        common_hint = self._get_common_issues_hint(historical_context, "提示词问题")
        if common_hint:
            hints.append(common_hint)

        # 2. 历史统计信息
        historical_stats = historical_context.get("historical_stats")
        if historical_stats and isinstance(historical_stats, dict):
            avg_prompt_length = historical_stats.get("avg_prompt_length", 0)
            audio_count = historical_stats.get("audio_prompt_count", 0)
            prompt_count = historical_stats.get("prompt_count", 1)
            audio_ratio = audio_count / max(prompt_count, 1)

            if avg_prompt_length > 0:
                hints.append(f"历史转换统计: 平均提示词长度={avg_prompt_length:.0f}字符, 音频覆盖率={audio_ratio:.0%}")

            if avg_prompt_length > 200:
                hints.append("历史数据表明提示词偏长，建议精简描述，保持简洁。")
            elif avg_prompt_length < 50:
                hints.append("历史数据表明提示词偏短，建议增加细节描述。")

            if audio_ratio < 0.5:
                hints.append("历史数据表明音频提示词覆盖率较低，请为有对话或环境音的片段生成音频描述。")

        # 3. 成功模式参考
        successful_patterns = historical_context.get("successful_patterns")
        if successful_patterns and isinstance(successful_patterns, list) and successful_patterns:
            pattern_summary = successful_patterns[0][:100] if isinstance(successful_patterns[0], str) else str(successful_patterns[0])[:100]
            hints.append(f"参考成功模式: {pattern_summary}...")

        if not hints:
            return ""

        return "\n".join([
            "",
            "【历史提示词参考信息】",
            *[f"  - {hint}" for hint in hints],
            ""
        ])


    def _convert_fragment_with_llm(self, fragment: VideoFragment,
                                   historical_context: Optional[Dict[str, Any]]) -> AIVideoPrompt:
        """使用LLM转换单个片段 - 同时生成视频和音频提示词"""

        # 检测原始剧本语言
        original_language = self._detect_original_language(fragment)

        # 获取当前片段对应的场景和元素信息
        scene_info = self._get_scene_info_for_fragment(fragment)
        element_info = self._get_element_info_for_fragment(fragment)

        # 格式化全局上下文
        global_context = self._format_global_context(self.global_metadata)

        # 获取完整剧本上下文
        full_script_context = self._get_full_script_context(fragment)

        # 获取音频相关的上下文
        audio_context = self._get_audio_context_for_fragment(fragment)

        # 获取角色信息JSON
        characters_json = self._get_character_info_json()

        # 构建修复提示
        repair_hint = ""
        if self.current_repair_params and self.current_repair_params.fix_needed and self.current_repair_params.issue_types:
            repair_hint = f"""
            【重要：修复要求】
            之前的提示词存在以下问题：
            - 问题类型: {', '.join(self.current_repair_params.issue_types)}
            - 修复建议: {json.dumps(self.current_repair_params.suggestions, ensure_ascii=False) if self.current_repair_params.suggestions else '无'}
        
            请根据上述建议调整提示词生成策略，避免再次出现相同问题。
            """

        # 构建历史上下文提示
        history_hint = self._build_history_hint(historical_context)

        # 准备提示词 - 要求同时生成视频和音频
        user_prompt = self.user_prompt_template.format(
            fragment_id=fragment.id,
            description=fragment.description,
            duration=fragment.duration,
            character=fragment.continuity_notes.get("main_character", ""),
            location=fragment.continuity_notes.get("location", ""),
            original_language=original_language,
            dm_model=self.config.video_model,
            video_style=self.config.default_style,
            max_length=self.config.max_prompt_length,
            min_length=self.config.min_prompt_length,
            global_context=global_context,
            scene_info=scene_info,
            element_info=element_info,
            full_script_context=full_script_context,
            audio_context=json.dumps(audio_context, ensure_ascii=False, indent=2),
            characters_json=characters_json,
            repair_hint=repair_hint,
            history_hint=history_hint  # 添加历史上下文提示
        )

        # 调用LLM
        result = self._call_llm_parse_with_retry(self.llm_client, self.system_prompt, user_prompt)

        # 获取生成的视频提示词
        english_prompt = result.get("prompt", "")
        original_prompt = result.get("original_prompt", "")
        combined_prompt = f"{english_prompt}\n\n{original_prompt}"

        # 解析LLM返回的音频提示词
        audio_prompt = self._build_audio_prompt_from_llm_result(result, fragment)
        self.last_audio_id = audio_prompt.audio_id if audio_prompt else self.last_audio_id

        return AIVideoPrompt(
            fragment_id=fragment.id,
            prompt=combined_prompt,
            main_character=fragment.continuity_notes.get("main_character", ""),
            negative_prompt=result.get("negative_prompt", self.config.default_negative_prompt),
            duration=fragment.duration,
            model=self.config.video_model,
            style=result.get("style_hint"),
            audio_prompt=audio_prompt
        )


    def _build_element_map(self):
        """构建元素ID到原始内容的映射"""
        if not self.parsed_script:
            return

        for scene in self.parsed_script.scenes:
            for elem in scene.elements:
                self.element_map[elem.id] = {
                    "type": elem.type,
                    "character": elem.character,
                    "content": elem.content,
                    "description": elem.description,
                    "scene_id": scene.id,
                    "sequence": elem.sequence,
                    "emotion": elem.emotion,
                    "intensity": elem.intensity
                }

    def _get_character_info_json(self) -> str:
        """将角色信息格式化为JSON字符串，供LLM直接使用"""
        if not self.parsed_script or not self.parsed_script.characters:
            return "[]"

        characters_data = []
        for char in self.parsed_script.characters:
            char_dict = {
                "name": char.name,
                "gender": char.gender,
                "role": char.role,
                "description": char.description or "",
                "key_traits": char.key_traits or []
            }
            characters_data.append(char_dict)

        return json.dumps(characters_data, ensure_ascii=False, indent=2)

    def _get_audio_context_for_fragment(self, fragment: VideoFragment) -> Dict[str, Any]:
        """从ParsedScript中获取已解析的音频上下文"""
        if not self.parsed_script:
            return {}

        # 找到片段对应的场景
        scene_id = None
        if "location" in fragment.continuity_notes:
            location = fragment.continuity_notes["location"]
            for scene in self.parsed_script.scenes:
                if location in scene.location or scene.id in location:
                    scene_id = scene.id
                    break

        # 获取场景的音频上下文
        scene_audio = None
        if scene_id:
            for scene in self.parsed_script.scenes:
                if scene.id == scene_id:
                    scene_audio = scene.audio_context
                    break

        # 获取元素的音频上下文
        element_audios = []
        element_ids = []
        if hasattr(fragment, 'metadata') and fragment.metadata:
            element_ids = fragment.metadata.get("element_ids", [])

        for scene in self.parsed_script.scenes:
            for elem in scene.elements:
                if elem.id in element_ids and elem.audio_context:
                    element_audios.append(elem.audio_context.dict())

        # 构建完整的音频上下文
        context = {
            "scene_audio": scene_audio.dict() if scene_audio else {},
            "element_audios": element_audios,
            "element_ids": element_ids,
            "global_atmosphere": self.global_metadata.audio_atmosphere if self.global_metadata else "neutral",
            "recurring_sounds": self.global_metadata.recurring_sounds if self.global_metadata else []
        }

        return context

    def _build_audio_prompt_from_llm_result(self, result: Dict[str, Any], fragment: VideoFragment) -> Optional[AIAudioPrompt]:
        """从LLM返回的数据构建AIAudioPrompt对象"""
        if "audio" in result:
            audio_data = result["audio"]

            # 处理模型类型枚举
            model_type_str = audio_data.get("model_type", "XTTSv2")
            try:
                model_type = AudioModelType(model_type_str)
            except ValueError:
                model_type = AudioModelType.XTTSv2

            # 处理人声类型枚举
            voice_type_str = audio_data.get("voice_type")
            voice_type = None
            if voice_type_str:
                try:
                    voice_type = AudioVoiceType(voice_type_str)
                except ValueError:
                    voice_type = AudioVoiceType.CHARACTER_DIALOGUE

            # 处理音频风格
            audio_style_str = audio_data.get("audio_style", "cinematic")
            try:
                audio_style = VideoStyle(audio_style_str)
            except ValueError:
                audio_style = VideoStyle.CINEMATIC

            english_prompt = audio_data.get("prompt", "")
            original_prompt = audio_data.get("original_prompt", "")
            combined_prompt = f"{english_prompt}\n\n{original_prompt}"

            # 创建音频提示词对象
            return AIAudioPrompt(
                audio_id=f"audio{fragment.id[4:]}",
                prompt=combined_prompt,
                negative_prompt=audio_data.get("negative_prompt", "noisy, low quality, distorted, robotic, bad audio"),
                model_type=model_type,
                voice_type=voice_type,
                audio_style=audio_style,
                voice_character=audio_data.get("voice_character"),
                voice_description=audio_data.get("voice_description"),
                speed=audio_data.get("speed", 1.0),
                pitch_shift=audio_data.get("pitch_shift", 0),
                emotion=audio_data.get("emotion", "neutral"),
                stability=audio_data.get("stability", 0.7),
                duration_seconds=audio_data.get("duration_seconds", fragment.duration),
                sound_attributes=audio_data.get("sound_attributes"),
                format=audio_data.get("format", "wav"),
                sample_rate=audio_data.get("sample_rate", 24000),
                seed=audio_data.get("seed"),
                scene_context=audio_data.get("scene_context"),
                previous_audio_id=self.last_audio_id
            )

    def _get_scene_info_for_fragment(self, fragment: VideoFragment) -> str:
        """获取片段对应的场景信息"""
        if not self.parsed_script:
            return ""

        # 从fragment的shot_id中提取场景ID
        scene_id = None

        # 遍历所有场景，找到包含该镜头的场景
        for scene in self.parsed_script.scenes:
            if hasattr(scene, 'elements') and scene.elements:
                if "location" in fragment.continuity_notes:
                    location = fragment.continuity_notes["location"]
                    if location in scene.location or scene.id in location:
                        scene_id = scene.id
                        break

        if not scene_id:
            return ""

        for scene in self.parsed_script.scenes:
            if scene.id == scene_id:
                weather = getattr(scene, 'weather', '未知')
                time_of_day = getattr(scene, 'time_of_day', '未知')
                characters = []
                for elem in scene.elements:
                    if elem.character and elem.character not in characters:
                        characters.append(elem.character)

                return f"当前场景：{scene.location}，天气：{weather}，时间：{time_of_day}，角色：{', '.join(characters)}"
        return ""

    def _get_element_info_for_fragment(self, fragment: VideoFragment) -> str:
        """获取片段对应的原始元素信息 - 基于element_ids精准获取"""
        if not self.parsed_script:
            return ""

        # 从fragment的metadata中获取element_ids
        element_ids = []
        if hasattr(fragment, 'metadata') and fragment.metadata:
            element_ids = fragment.metadata.get("element_ids", [])

            # 如果有original_element_ids（从video_splitter继承的），也加入
            original_ids = fragment.metadata.get("original_element_ids", [])
            if original_ids:
                element_ids.extend(original_ids)

        # 去重
        element_ids = list(set(element_ids))

        if not element_ids:
            return "本片段无对应原始元素"

        # 构建元素ID到原始内容的映射
        if not self.element_map:
            return "本片段无对应原始元素"

        # 格式化输出
        elements_text = []
        for elem_id in element_ids:  # 保持原始顺序
            if elem_id in self.element_map:
                elem = self.element_map[elem_id]
                elem_type = "对话" if elem["type"] == ElementType.DIALOGUE else "动作" if elem["type"] == ElementType.ACTION else "场景"
                char_info = f"（角色：{elem['character']}）" if elem['character'] else ""

                # 优先使用content（包含完整描述），其次使用description
                content = elem['content'] if elem['content'] else elem['description']

                elements_text.append(f"  - [{elem_type}{char_info}] {content}")

        if elements_text:
            return "本片段包含的原始元素：\n" + "\n".join(elements_text)

        return "本片段无对应原始元素"

    def _get_full_script_context(self, fragment: VideoFragment) -> str:
        """获取完整的剧本上下文"""
        if not self.parsed_script:
            return ""

        timeline = []
        for scene_idx, scene in enumerate(self.parsed_script.scenes):
            scene_desc = f"场景{scene_idx + 1}：{scene.location}，{getattr(scene, 'time_of_day', '未知')}，{getattr(scene, 'weather', '未知')}"
            key_elements = []
            for elem in scene.elements[:3]:
                if elem.type == ElementType.DIALOGUE and elem.content:
                    key_elements.append(f"「{elem.character}：{elem.content[:30]}」")
                elif elem.type == ElementType.ACTION and elem.description:
                    key_elements.append(f"[{elem.description[:30]}]")
            if key_elements:
                scene_desc += "：" + "；".join(key_elements)
            timeline.append(scene_desc)

        return "完整剧本时间线：\n" + "\n".join(timeline)

    def _detect_original_language(self, fragment: VideoFragment) -> str:
        """检测原始剧本语言"""
        if hasattr(fragment, 'metadata') and fragment.metadata:
            return fragment.metadata.get("original_language", "zh")
        return get_language().value
