"""
@FileName: script_parser_agent.py
@Description: LLM 剧本解析基类，包含复杂度评估和路由决策逻辑
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
from abc import abstractmethod, ABC
from datetime import datetime
from typing import Dict, Any, List, Optional

from penshot.logger import info, warning
from penshot.neopen.agent.base_models import ScriptType, ElementType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, SceneInfo, CharacterInfo, BaseElement, \
    GlobalMetadata, PropItem, CharacterOutfit, LocationItem, ElementAudioContext, SceneAudioContext, EnvironmentSound, CharacterType
from penshot.neopen.tools.script_assessor_tool import ComplexityAssessor


class BaseScriptParser(ABC):
    """优化版剧本解析智能体"""

    def __post_init__(self):
        """
        初始化剧本解析智能体
        """
        self.complexity_assessor = ComplexityAssessor()

    @abstractmethod
    def parser(self, script_text: Any, script_format: ScriptType
               , repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> ParsedScript:
        """处理输入数据（子类实现）"""
        raise NotImplementedError("子类必须实现process方法")

    def post_process(self, parsed_script: ParsedScript) -> ParsedScript:
        """后处理：填充统计数据等"""
        # 计算统计数据
        total_elements = 0
        total_duration = 0.0
        dialogue_count = 0
        action_count = 0

        for scene in parsed_script.scenes:
            total_elements += len(scene.elements)
            for element in scene.elements:
                total_duration += element.duration
                if element.type == ElementType.DIALOGUE:
                    dialogue_count += 1
                elif element.type == ElementType.ACTION:
                    action_count += 1

        # 更新统计数据
        parsed_script.stats.update({
            "total_elements": total_elements,
            "total_duration": round(total_duration, 2),
            "dialogue_count": dialogue_count,
            "action_count": action_count
        })

        # 更新元数据
        if not parsed_script.metadata.get("parser_type"):
            parsed_script.metadata["parser_type"] = self.__class__.__name__

        info(f"解析完成: {total_elements}个元素, {len(parsed_script.scenes)}个场景")
        return parsed_script

    def validate_parsed_result(self, parsed_script: ParsedScript) -> bool:
        """验证解析结果的基本有效性"""
        if not parsed_script.scenes:
            warning("解析结果为空：没有找到任何场景")
            return False

        # 检查元素顺序连续性
        all_elements = []
        for scene in parsed_script.scenes:
            all_elements.extend(scene.elements)

        if all_elements:
            sequences = [elem.sequence for elem in all_elements]
            if sorted(sequences) != list(range(1, len(sequences) + 1)):
                warning(f"元素顺序不连续: {sequences}")

        return True

    def _generate_element_id(self, scene_idx: int, elem_idx: int) -> str:
        """生成元素ID"""
        return f"elem_{scene_idx + 1:03d}_{elem_idx + 1:03d}"

    def _generate_scene_id(self, scene_idx: int) -> str:
        """生成场景ID"""
        return f"scene_{scene_idx + 1:03d}"

    def _build_parsed_script(self, data: Dict[str, Any]) -> ParsedScript:
        """构建解析结果对象"""
        # 构建场景列表
        scenes = []
        for scene_idx, scene_data in enumerate(data.get("scenes", [])):
            scene = self._build_scene_data(scene_data, scene_idx)
            scenes.append(scene)

        # 构建角色列表
        characters = self._build_character_data(data)

        # 返回完整解析结果
        return ParsedScript(
            title=data.get("title"),
            characters=characters,
            scenes=scenes,
            global_metadata=self._build_global_metadata(data.get("global_metadata", {})),
            metadata={
                "parsed_at": datetime.now().isoformat(),
                "version": "mvp_1.0",
                "parser_type": self.__class__.__name__
            }
        )

    def _build_character_data(self, data: Dict[str, Any]) -> List[CharacterInfo]:
        """构建角色对象"""
        return [
            CharacterInfo(
                name=char_data["name"],
                gender=char_data["gender"],
                type=CharacterType(char_data.get("type", "default")),
                role=char_data["role"],
                description=char_data.get("description"),
                key_traits=char_data.get("key_traits", [])
            )
            for char_data in data.get("characters", [])
        ]

    def _build_scene_data(self, scene_data: Dict[str, Any], scene_idx: int) -> SceneInfo:
        """构建场景对象"""
        elements = []
        for elem_idx, elem_data in enumerate(scene_data.get("elements", [])):
            # 构建元素对象
            element = self._build_element_data(elem_data, scene_idx, elem_idx)
            elements.append(element)

        return SceneInfo(
            id=scene_data.get("id", self._generate_scene_id(scene_idx)),
            location=scene_data.get("location", "none"),
            description=scene_data.get("description"),
            time_of_day=scene_data.get("time_of_day"),
            weather=scene_data.get("weather"),
            # 处理场景级音频上下文
            audio_context=self._build_audio_context(scene_data.get("audio_context", {})),
            elements=elements
        )

    def _build_element_data(self, elem_data: Dict[str, Any], scene_idx: int, elem_idx: int) -> BaseElement:
        """构建元素对象"""
        # 确保元素类型是ElementType枚举
        elem_type = ElementType(elem_data.get("type", "action"))

        # 处理节点音频上下文
        _element_audio_context = elem_data.get("audio_context")
        element_audio_context = None
        if _element_audio_context and _element_audio_context != {}:
            element_audio_context = ElementAudioContext(
                sound_type=_element_audio_context.get("sound_type", ""),
                description=_element_audio_context.get("description", ""),
                intensity=_element_audio_context.get("intensity", 0.5),
            )

        return BaseElement(
            id=elem_data.get("id", self._generate_element_id(scene_idx, elem_idx)),
            type=elem_type,
            sequence=elem_data.get("sequence", elem_idx + 1),
            duration=elem_data.get("duration", 3.0),
            confidence=elem_data.get("confidence", 0.8),
            content=elem_data.get("content", ""),
            character=elem_data.get("character"),
            target_character=elem_data.get("target_character"),
            description=elem_data.get("description", ""),
            intensity=elem_data.get("intensity", 0.5),
            emotion=elem_data.get("emotion", "neutral"),
            audio_context=element_audio_context,
        )


    def _build_audio_context(self, audio_data: Dict[str, Any]) -> SceneAudioContext:
        """构建场景级音频上下文"""
        if not audio_data:
            return SceneAudioContext(scene_type="other")

        env_sounds = [
            EnvironmentSound(
                sound_type=env_sound.get("sound_type", ""),
                description=env_sound.get("description"),
                continuous=env_sound.get("continuous", True),
                intensity=env_sound.get("intensity", 0.5),
                timing=env_sound.get("timing")
            )
            for env_sound in audio_data.get("env_sounds", [])
        ]

        return SceneAudioContext(
            scene_type=audio_data.get("scene_type", "other"),
            env_sounds=env_sounds,
            has_dialogue=audio_data.get("has_dialogue", False),
            has_voiceover=audio_data.get("has_voiceover", False),
            atmosphere=audio_data.get("atmosphere", "neutral"),
            reverb=audio_data.get("reverb", 0.2),
        )


    def _build_global_metadata(self, global_data: Dict[str, Any]) -> GlobalMetadata:
        """构建全局元数据对象"""
        if not global_data:
            return GlobalMetadata()

        return GlobalMetadata(
            key_props=[
                PropItem(
                    name=prop_data.get("name", "未知道具"),
                    description=prop_data.get("description", ""),
                    importance=prop_data.get("importance", "medium"),
                    color=prop_data.get("color", ""),
                    appears_in=prop_data.get("appears_in", [])
                )
                for prop_data in global_data.get("key_props", [])
            ],
            character_outfits=[
                CharacterOutfit(
                    character=outfit_data.get("character", "未知角色"),
                    description=outfit_data.get("description", ""),
                    style=outfit_data.get("style", ""),
                    color=outfit_data.get("color", ""),
                    material=outfit_data.get("material", "")
                )
                for outfit_data in global_data.get("character_outfits", [])
            ],
            key_locations=[
                LocationItem(
                    name=loc_data.get("name", "未知地点"),
                    description=loc_data.get("description", ""),
                    appears_in=loc_data.get("appears_in", []),
                    visual_cues=loc_data.get("visual_cues", [])
                )
                for loc_data in global_data.get("key_locations", [])
            ],
            continuity_notes=global_data.get("continuity_notes", ""),
            audio_atmosphere=global_data.get("audio_atmosphere", "neutral"),
            recurring_sounds=[sound for sound in global_data.get("recurring_sounds", [])]
        )
