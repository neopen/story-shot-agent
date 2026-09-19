"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: config_vocabulary.py
@Description: 规则解析词表 - 统一收敛规则解析所依赖的配置来源
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import Any, Dict, List

from penshot.neopen.agent.script_parser.script_parser_models import EmotionType
from penshot.neopen.config.keyword_config import get_keyword_config
from penshot.neopen.config.script_parser_config import (
    ScriptParserConfig,
    script_parser_config,
)

# 配置分类名 -> EmotionType 的映射，用于把配置中的中文分类统一成英文情绪值
EMOTION_CATEGORY_MAP: Dict[str, str] = {
    "positive": EmotionType.HAPPY.value,
    "negative": EmotionType.SAD.value,
    "neutral": EmotionType.CALM.value,
    "开心": EmotionType.HAPPY.value,
    "高兴": EmotionType.HAPPY.value,
    "悲伤": EmotionType.SAD.value,
    "愤怒": EmotionType.ANGRY.value,
    "恐惧": EmotionType.FEAR.value,
    "惊讶": EmotionType.SURPRISE.value,
    "紧张": EmotionType.TENSE.value,
    "平静": EmotionType.CALM.value,
    "中性": EmotionType.CALM.value,
}

# 服装描述的合法前缀，用于从外貌词表中筛出真正的服装项
_COSTUME_VALUE_PREFIXES = ("穿着", "戴着", "围着")

_config_guarded = False


def ensure_rule_config_loaded() -> None:
    """幂等加载剧本解析配置

    ScriptParserConfig 在构造时只读取一次 YAML；规则解析依赖其中的词表与模式，
    因此首次取词前显式刷新一次，保证进程内读到的配置是最新的。重复调用不会重复读取。
    """
    global _config_guarded
    if _config_guarded:
        return
    script_parser_config.load_configuration()
    _config_guarded = True


def _merge_keywords(*sources: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """按顺序合并同键词表，靠后的来源追加到已有列表"""
    merged: Dict[str, List[str]] = {}
    for source in sources:
        for key, words in source.items():
            merged.setdefault(key, []).extend(words)
    return merged


class RuleVocabulary:
    """规则解析词表

    数据来源优先级：
    1. `script_parser_config.yaml` 的场景/对话/角色/道具追踪/情绪识别规则；
    2. `keyword_config.yaml` 的服装、天气、状态、道具、强度词表；
    3. `ScriptParserConfig.DEFAULT_*` 内置缺省值，仅在配置缺失时兜底。
    """

    def __init__(self) -> None:
        ensure_rule_config_loaded()
        self._keyword_config = get_keyword_config()

    def _script_rule(self, key: str, default: Any) -> Any:
        """读取 keyword_config.yaml 中的 script_rule_keywords 词表"""
        keywords = self._keyword_config.get_script_rule_keywords() or {}
        value = keywords.get(key)
        return value if value else default

    # ---------------------------- 分段模式 ----------------------------
    @property
    def scene_start_patterns(self) -> List[str]:
        """场景标题起始模式"""
        patterns = script_parser_config.get_value("scene_recognition.start_patterns")
        return patterns or ScriptParserConfig.DEFAULT_SCENE_PATTERNS

    @property
    def scene_transition_patterns(self) -> List[str]:
        """转场模式"""
        return (
            script_parser_config.get_value("scene_recognition.transition_patterns")
            or []
        )

    @property
    def scene_end_patterns(self) -> List[str]:
        """剧本结束标记模式"""
        return script_parser_config.get_value("scene_recognition.end_patterns") or []

    @property
    def dialogue_patterns(self) -> List[str]:
        """对话识别模式，直接引语与间接引语合并"""
        direct = (
            script_parser_config.get_value("dialogue_recognition.direct_patterns") or []
        )
        indirect = (
            script_parser_config.get_value("dialogue_recognition.indirect_patterns")
            or []
        )
        return (direct + indirect) or list(ScriptParserConfig.DEFAULT_DIALOGUE_PATTERNS)

    @property
    def character_name_patterns(self) -> List[str]:
        """角色名模式"""
        patterns = script_parser_config.get_value("character_recognition.name_patterns")
        return patterns or [ScriptParserConfig.DEFAULT_DIALOGUE_PATTERNS[0]]

    @property
    def common_titles(self) -> List[str]:
        """常见称谓，用于角色名归一化"""
        return (
            script_parser_config.get_value("character_recognition.common_titles") or []
        )

    # ---------------------------- 场景属性词表 ----------------------------
    @property
    def time_keywords(self) -> Dict[str, str]:
        """时间词 -> 标准化时间"""
        return ScriptParserConfig.DEFAULT_TIME_KEYWORDS

    @property
    def location_keywords(self) -> Dict[str, str]:
        """地点词 -> 标准化地点"""
        configured = script_parser_config.get_value("location_keywords") or {}
        return configured or ScriptParserConfig.DEFAULT_LOCATION_KEYWORDS

    @property
    def weather_keywords(self) -> Dict[str, str]:
        """天气词 -> 标准化天气值（sunny/rainy/snowy/cloudy/foggy/stormy/windy）"""
        return self._keyword_config.get_weather_keywords() or {}

    @property
    def atmosphere_keywords(self) -> Dict[str, List[str]]:
        """氛围词 -> 氛围标签"""
        return ScriptParserConfig.DEFAULT_ATMOSPHERE_KEYWORDS

    # ---------------------------- 实体词表 ----------------------------
    @property
    def prop_keywords(self) -> Dict[str, List[str]]:
        """道具分类 -> 道具词表"""
        return self._keyword_config.get_prop_keywords() or {}

    @property
    def costume_keywords(self) -> Dict[str, str]:
        """服装词 -> 标准化服装描述"""
        configured = self._keyword_config.get_costume_keywords() or {}
        if configured:
            return configured
        return {
            word: desc
            for word, desc in ScriptParserConfig.DEFAULT_APPEARANCE_KEYWORDS.items()
            if desc.startswith(_COSTUME_VALUE_PREFIXES)
        }

    @property
    def state_keywords(self) -> Dict[str, str]:
        """状态词 -> 状态特征描述"""
        return self._keyword_config.get_state_keywords() or {}

    @property
    def metadata_labels(self) -> List[str]:
        """元数据标签：后接冒号时属场记/说明行，不是角色名也不产生对话"""
        return self._script_rule("metadata_labels", [])

    @property
    def color_words(self) -> List[str]:
        """颜色词，用于抽取道具与服装颜色"""
        return self._script_rule("color_words", [])

    @property
    def visual_cue_words(self) -> List[str]:
        """视觉线索词，所在句子可作为地点或场景的视觉特征"""
        return self._script_rule("visual_cue_words", [])

    @property
    def cue_emotion_map(self) -> Dict[str, str]:
        """表演提示词 -> EmotionType 值"""
        return self._script_rule("cue_emotion_map", {})

    @property
    def voiceover_markers(self) -> List[str]:
        """画外音/旁白标记词"""
        return self._script_rule("voiceover_markers", [])

    @property
    def costume_style_words(self) -> List[str]:
        """服装风格词"""
        return self._script_rule("costume_style_words", [])

    @property
    def costume_material_words(self) -> List[str]:
        """服装材质词"""
        return self._script_rule("costume_material_words", [])

    @property
    def recurring_sound_words(self) -> List[str]:
        """重复音效词"""
        return self._script_rule("recurring_sound_words", [])

    @property
    def weather_exclusions(self) -> List[str]:
        """天气词排除项，避免「风格」被判为 windy"""
        return self._script_rule("weather_exclusions", [])

    @property
    def prop_appearance_markers(self) -> List[str]:
        """道具出现标记"""
        return (
            script_parser_config.get_value("prop_tracking_rules.appearance_markers")
            or []
        )

    @property
    def prop_disappearance_markers(self) -> List[str]:
        """道具消失标记"""
        return (
            script_parser_config.get_value("prop_tracking_rules.disappearance_markers")
            or []
        )

    @property
    def prop_state_change_markers(self) -> List[str]:
        """道具状态变化标记"""
        return (
            script_parser_config.get_value("prop_tracking_rules.state_change_markers")
            or []
        )

    # ---------------------------- 情绪与强度 ----------------------------
    @property
    def emotion_keywords(self) -> Dict[str, List[str]]:
        """EmotionType 值 -> 情绪词表"""
        keywords = script_parser_config.get_value("emotion_recognition.keywords") or {}
        expressions = (
            script_parser_config.get_value("emotion_recognition.emotion_expressions")
            or {}
        )
        configured = _merge_keywords(keywords, expressions)

        mapped: Dict[str, List[str]] = {}
        mapped.update(
            {
                EMOTION_CATEGORY_MAP[category]: words
                for category, words in configured.items()
                if category in EMOTION_CATEGORY_MAP
            }
        )
        if mapped:
            return mapped

        return _merge_keywords(
            {
                EMOTION_CATEGORY_MAP[category]: words
                for category, words in ScriptParserConfig.DEFAULT_EMOTION_KEYWORDS.items()
                if category in EMOTION_CATEGORY_MAP
            }
        )

    @property
    def intensity_high_keywords(self) -> List[str]:
        """高强度词表"""
        action = self._keyword_config.get_action_keywords()
        speed = action.get("speed_keywords", {})
        intensity = action.get("emotion_intensity_keywords", {})
        return (
            list(speed.get("fast", []))
            + list(intensity.get("strong", []))
            + list(intensity.get("dramatic", []))
        )

    @property
    def subject_verbs(self) -> List[str]:
        """主语识别动词：动作类型词 + 补充动作词，长词优先"""
        action = self._keyword_config.get_action_keywords()
        verbs: List[str] = []
        for words in action.get("action_types", {}).values():
            verbs.extend(
                word
                for word in words
                if word and all("\u4e00" <= ch <= "\u9fff" for ch in word)
            )
        verbs.extend(self._script_rule("subject_verbs", []))
        return sorted(set(verbs), key=len, reverse=True)

    @property
    def intensity_low_keywords(self) -> List[str]:
        """低强度词表"""
        action = self._keyword_config.get_action_keywords()
        speed = action.get("speed_keywords", {})
        intensity = action.get("emotion_intensity_keywords", {})
        return list(speed.get("slow", [])) + list(intensity.get("mild", []))
