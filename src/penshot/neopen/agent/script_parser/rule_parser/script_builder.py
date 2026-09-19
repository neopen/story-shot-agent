"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: script_builder.py
@Description: 结果组装 - 把场景草稿与实体抽取结果组装成对外的 ParsedScript
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    ParseContext,
    SceneDraft,
)
from penshot.neopen.agent.script_parser.rule_parser.scene_attribute_rules import (
    UNSPECIFIED_LOCATION,
)
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    CharacterInfo,
    EnvironmentSound,
    GlobalMetadata,
    ParsedScript,
    SceneAudioContext,
    SceneInfo,
)

# 解析结果元数据里的版本与来源标识
_PARSER_VERSION = "mvp_1.0"
_PARSER_TYPE = "RuleParserEngine"
# 无法识别标题时的占位标题
_UNKNOWN_TITLE = "未知"
# 完成度评分：场景/角色/元素/对话/全局元数据各占 20 分
_SCORE_PER_SECTION = 20


class ParsedScriptBuilder:
    """把解析上下文组装成 ParsedScript

    元素由 ElementBuilder 事先填好，这里只做类型转换、统计与元数据。
    """

    def build(
        self,
        context: ParseContext,
        characters: Sequence[CharacterInfo],
        global_metadata: GlobalMetadata,
    ) -> ParsedScript:
        """组装最终结果"""
        scenes = [self._scene(scene) for scene in context.scenes]
        return ParsedScript(
            title=context.title,
            characters=list(characters),
            scenes=scenes,
            global_metadata=global_metadata,
            stats=self._stats(scenes, characters, global_metadata),
            metadata={
                "parsed_at": datetime.now().isoformat(),
                "version": _PARSER_VERSION,
                "parser_type": _PARSER_TYPE,
            },
        )

    def build_fallback(
        self, title: Optional[str] = None, reason: Optional[str] = None
    ) -> ParsedScript:
        """解析失败或未识别到场景时的兜底结果

        带上 ``failed`` 标记，供上层区分「解析成功但内容为空」与「解析失败」。
        """
        metadata: Dict[str, Any] = {
            "parsed_at": datetime.now().isoformat(),
            "version": _PARSER_VERSION,
            "parser_type": _PARSER_TYPE,
            "failed": True,
        }
        if reason:
            metadata["reason"] = reason
        return ParsedScript(
            title=title or _UNKNOWN_TITLE,
            characters=[],
            scenes=[],
            global_metadata=GlobalMetadata(),
            stats={
                "scene_count": 0,
                "character_count": 0,
                "total_elements": 0,
                "total_duration": 0.0,
                "dialogue_count": 0,
                "action_count": 0,
                "completeness_score": 0,
            },
            metadata=metadata,
        )

    # ---------------------------- 场景与统计 ----------------------------
    @staticmethod
    def _scene(scene: SceneDraft) -> SceneInfo:
        return SceneInfo(
            id=scene.id,
            location=scene.location or UNSPECIFIED_LOCATION,
            description=scene.description,
            time_of_day=scene.time_of_day,
            weather=scene.weather,
            audio_context=SceneAudioContext(
                scene_type=scene.scene_type,
                env_sounds=[
                    EnvironmentSound(sound_type=sound) for sound in scene.env_sounds
                ],
                has_dialogue=scene.has_dialogue,
                has_voiceover=scene.has_voiceover,
                atmosphere=scene.atmosphere,
            ),
            elements=list(scene.elements),
        )

    @staticmethod
    def _stats(
        scenes: Sequence[SceneInfo],
        characters: Sequence[CharacterInfo],
        global_metadata: GlobalMetadata,
    ) -> Dict[str, Any]:
        elements = [element for scene in scenes for element in scene.elements]
        dialogue_count = sum(
            1 for element in elements if element.type is ElementType.DIALOGUE
        )
        action_count = sum(
            1 for element in elements if element.type is ElementType.ACTION
        )
        return {
            "scene_count": len(scenes),
            "character_count": len(characters),
            "total_elements": len(elements),
            "total_duration": round(sum(element.duration for element in elements), 1),
            "dialogue_count": dialogue_count,
            "action_count": action_count,
            "completeness_score": _completeness(
                scenes, characters, elements, dialogue_count, global_metadata
            ),
        }


def _completeness(
    scenes: Sequence[SceneInfo],
    characters: Sequence[CharacterInfo],
    elements: Sequence[BaseElement],
    dialogue_count: int,
    global_metadata: GlobalMetadata,
) -> int:
    """完成度评分（0-100），每项各占 20 分"""
    global_entities = (
        global_metadata.key_props
        or global_metadata.character_outfits
        or global_metadata.key_locations
    )
    checks: List[bool] = [
        bool(scenes),
        bool(characters),
        bool(elements),
        dialogue_count > 0,
        bool(global_entities),
    ]
    return sum(_SCORE_PER_SECTION for passed in checks if passed)
