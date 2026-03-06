"""
@FileName: llm_prompt_converter.py
@Description: 基于LLM的提示词转换器 - 音频参数由LLM直接从CharacterInfo解析
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 23:36
"""
import json
from typing import Optional, Dict, Any

from hengshot.hengline.agent.base_agent import BaseAgent
from hengshot.hengline.agent.base_models import ElementType
from hengshot.hengline.agent.prompt_converter.base_prompt_converter import BasePromptConverter
from hengshot.hengline.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
    AIVideoInstructions,
    AIAudioPrompt,
    AudioModelType,
    AudioVoiceType,
    VideoStyle
)
from hengshot.hengline.agent.prompt_converter.template_prompt_converter import TemplatePromptConverter
from hengshot.hengline.agent.script_parser.script_parser_models import ParsedScript
from hengshot.hengline.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from hengshot.hengline.hengline_config import HengLineConfig
from hengshot.hengline.language_manage import get_language
from hengshot.logger import info, error
from hengshot.utils.log_utils import print_log_exception


class LLMPromptConverter(BasePromptConverter, BaseAgent):
    """基于LLM的提示词转换器 - 音频参数由LLM直接从CharacterInfo解析"""

    def __init__(self, llm_client, config: Optional[HengLineConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.parsed_script = None
        self.global_metadata = None
        self.last_audio_id = None
        self.element_map = {}  # 元素ID到原始内容的映射

    def convert(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript) -> AIVideoInstructions:
        """使用LLM转换提示词 - 同时生成视频和音频提示词"""
        info(f"使用LLM转换提示词，片段数: {len(fragment_sequence.fragments)}")

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
                prompt = self._convert_fragment_with_llm(fragment)
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
        return self.post_process(instructions)

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

    def _convert_fragment_with_llm(self, fragment: VideoFragment) -> AIVideoPrompt:
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

        # 准备提示词 - 要求同时生成视频和音频
        user_prompt = self._get_prompt_template("prompt_converter_user")

        prompt_template = user_prompt.format(
            fragment_id=fragment.id,
            description=fragment.description,
            duration=fragment.duration,
            character=fragment.continuity_notes.get("main_character", ""),
            location=fragment.continuity_notes.get("location", ""),
            original_language=original_language,
            dm_model=self.config.video_model.value,
            video_style=self.config.default_style.value,
            max_length=self.config.max_prompt_length,
            min_length=self.config.min_prompt_length,
            global_context=global_context,
            scene_info=scene_info,
            element_info=element_info,
            full_script_context=full_script_context,
            audio_context=json.dumps(audio_context, ensure_ascii=False, indent=2),
            characters_json=characters_json
        )

        # 调用LLM - 期望返回包含video和audio的完整JSON
        system_prompt = self._get_prompt_template("prompt_converter_system")
        result = self._call_llm_parse_with_retry(self.llm_client, system_prompt, prompt_template)

        # 获取生成的视频提示词
        english_prompt = result.get("prompt", "")
        original_prompt = result.get("original_prompt", "")
        combined_prompt = f"{english_prompt}\n\n{original_prompt}"

        # === 解析LLM返回的音频提示词 ===
        audio_prompt = self._build_audio_prompt_from_llm_result(result, fragment)
        self.last_audio_id = audio_prompt.audio_id if audio_prompt else self.last_audio_id

        return AIVideoPrompt(
            fragment_id=fragment.id,
            prompt=combined_prompt,
            negative_prompt=result.get("negative_prompt", self.config.default_negative_prompt),
            duration=fragment.duration,
            model=self.config.video_model.value,
            style=result.get("style_hint"),
            audio_prompt=audio_prompt
        )

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
