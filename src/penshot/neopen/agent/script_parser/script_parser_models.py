"""
@FileName: script_parser_models.py
@Description:  剧本解析相关模型
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19 21:44
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field

from penshot.neopen.agent.base_models import ElementType

# ========================= 音频上下文模型 - 包含环境声音、背景音乐等信息 =========================
class EnvironmentSound(BaseModel):
    """环境音信息"""
    sound_type: str = Field(..., description="环境音类型")
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="强度/音量")
    continuous: bool = Field(default=True, description="是否持续")
    description: Optional[str] = Field(None, description="详细描述")
    timing: Optional[str] = Field(None, description="出现时机，如'开场'、'高潮'、'结尾'")


class SceneAudioContext(BaseModel):
    """场景音频上下文"""
    scene_type: str = Field(..., description="场景类型")
    env_sounds: List[EnvironmentSound] = Field(default_factory=list, description="环境音列表")
    has_dialogue: bool = Field(default=False, description="是否有对话")
    has_voiceover: bool = Field(default=False, description="是否有旁白")
    atmosphere: str = Field(default="neutral", description="氛围描述，如'紧张'、'温馨'、'忧伤'")
    reverb: float = Field(default=0.2, ge=0.0, le=1.0, description="混响强度")


class ElementAudioContext(BaseModel):
    """元素级别的音频上下文"""
    sound_type: Optional[str] = Field(None, description="该元素产生的声音类型")
    description: Optional[str] = Field(None, description="声音描述")
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="强度")


# ========================= 基础模型定义 - 包含剧本元素、角色信息、场景信息等核心数据结构 ==================
class EmotionType(str, Enum):
    """情绪类型枚举
    neutral/happy/sad/angry/tense/fear/surprise/disgust/anxious/excited/calm/tender/hesitant/crying/whisper/choking/repression/emotional/other
    """
    NEUTRAL = "neutral"     # 中性的情绪，适用于大多数场景
    HAPPY = "happy"         # 快乐的情绪，适用于喜剧、成功等场景
    SAD = "sad"             # 悲伤的情绪，适用于悲剧、失落等场景
    FEAR = "fear"           # 恐惧的情绪，适用于惊悚、恐怖等场景
    ANGRY = "angry"         # 愤怒的情绪，适用于冲突、争吵等场景
    TENSE = "tense"         # 紧张的情绪，适用于悬疑、惊悚等场景
    SURPRISE = "surprise"   # 惊讶的情绪，适用于突发事件、意外发现等场景
    DISGUST = "disgust"     # 厌恶的情绪，适用于反派角色、恶心场景等
    ANXIOUS = "anxious"     # 焦虑的情绪，适用于角色内心挣扎、压力大的场景
    EXCITED = "excited"     # 兴奋的情绪，适用于喜庆、成功等场景
    CALM = "calm"           # 平静的情绪，适用于安静、温馨等场景
    TENDER = "tender"       # 温柔的情绪，适用于亲密、感人等场景
    HESITANT = "hesitant"   # 犹豫的情绪，适用于角色面临选择、内心矛盾等场景
    CRYING = "crying"       # 哭泣的情绪，适用于悲伤、痛苦等场景
    EMOTIONAL = "emotional" # 激动的情绪，适用于情绪波动较大的场景
    WHISPER = "whisper"     # 低语的情绪，适用于秘密、亲密等场景
    CHOKING = "choking"     # 哽咽的情绪，适用于极度悲伤、痛苦的场景
    HEAVY = "heavy"         # 沉重的心情
    REPRESSION = "repression"   # 压抑的情绪，适用于内心挣扎、无法表达的情感状态
    SHOCK = "shock"             # 震惊的情绪，适用于突发事件、重大转折等场景
    RESIGNED = "resigned"       # 无奈的情绪，适用于角色接受不幸、放弃抵抗等场景
    RESOLUTE = "resolute"       # 坚定的情绪，适用于角色下定决心、迎难而上等场景
    NOSTALGIC = "nostalgic"     # 怀旧的情绪，适用于回忆、过去事件等场景
    OTHER = "other"             # 其他的情绪类型，适用于无法归类的特殊情绪状态


class BaseElement(BaseModel):
    """剧本元素基类 - 所有类型元素的共同字段"""
    id: str = Field(..., description="元素唯一标识，格式：elem_001")
    type: Literal[ElementType.DIALOGUE, ElementType.ACTION, ElementType.SCENE] = Field(
        ...,
        description="元素类型：对话/动作/场景描述"
    )
    sequence: int = Field(
        ...,
        description="全局顺序编号，从1开始，表示在剧本中的出现顺序"
    )

    # 通用时间信息
    duration: float = Field(
        default=3.0,
        ge=0.5,
        description="预估持续时间（秒），基于简单规则估算"
    )

    # 元数据
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="解析置信度，0-1之间"
    )

    # 核心内容
    content: str = Field(..., description="元素内容文本")

    # 角色信息（可选）
    character: Optional[str] = Field(
        default=None,
        description="关联的角色名（对话必填，动作可选）"
    )
    target_character: Optional[str] = Field(
        default=None,
        description="针对的目标角色（如有）"
    )

    description: str = Field(default=None, description="其他的描述文本")

    intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="动作或语气等的强度等级，0-1之间"
    )
    emotion: str = Field(
        default=EmotionType.NEUTRAL.value,
        description="伴随情绪：neutral/happy/angry/sad/fear"
    )
    # 元素音频上下文
    audio_context: Optional[ElementAudioContext] = Field(None, description="元素音频上下文")


# ========================= 角色和场景信息模型 - 包含角色类型、场景描述等关键信息 =========================
class CharacterType(str, Enum):
    """角色类型枚举"""
    DEFAULT = "default"
    CHILD = "child"
    ADULT = "adult"
    ELDER = "elder"
    INJURED = "injured"
    ATHLETE = "athlete"
    ROBOT = "robot"

class CharacterInfo(BaseModel):
    """角色信息模型"""
    name: str = Field(..., description="角色名称")
    gender: str = Field(..., description="角色性别")
    role: str = Field(..., description="角色类型（主角、配角等）")
    type: CharacterType = Field(default=CharacterType.DEFAULT, description="角色类型")
    # 核心特征（可选）
    description: Optional[str] = Field(
        default=None,
        description="简化的角色描述（如有）"
    )

    # MVP中只保留最关键的特征
    key_traits: List[str] = Field(
        default_factory=list,
        description="关键特征列表，如外貌、性格等"
    )


class SceneInfo(BaseModel):
    """场景信息模型"""
    id: str = Field(..., description="场景唯一ID，格式：scene_001")
    location: str = Field(..., description="场景地点")
    # 简化的描述（可选）
    description: Optional[str] = Field(
        default=None,
        description="场景简要描述（如有）"
    )

    # 时间信息
    time_of_day: Optional[str] = Field(
        default=None,
        description="时间（如有）：day/night/dawn/dusk"
    )

    # 天气信息
    weather: Optional[str] = Field(
        default=None,
        description="天气（如有）：sunny/rainy/snowy/cloudy"
    )
    # 音频上下文
    audio_context: SceneAudioContext = Field(default_factory=lambda: SceneAudioContext(
        scene_type="outdoor",
        env_sounds=[]
    ))

    # 扁平化的元素数组（按sequence排序）
    elements: List[BaseElement] = Field(
        default_factory=list,
        description="所有剧本元素，按出现顺序排列"
    )

########################### 全局元数据模型 - 存储全剧关键信息，供后续阶段使用 ###############################
class PropItem(BaseModel):
    """关键道具项"""
    name: str = Field(description="道具名称，如《飞鸟集》、借阅卡")
    description: str = Field(description="道具的详细描述")
    appears_in: List[str] = Field(default_factory=list, description="出现的场景ID列表")
    color: Optional[str] = Field(None, description="道具颜色（如适用）")
    importance: str = Field("high", description="重要性: high/medium/low")


class CharacterOutfit(BaseModel):
    """角色服装"""
    character: str = Field(description="角色名")
    description: str = Field(description="服装详细描述")
    color: Optional[str] = Field(None, description="主色调")
    style: Optional[str] = Field(None, description="款式风格")
    material: Optional[str] = Field(None, description="材质")


class LocationItem(BaseModel):
    """关键地点"""
    name: str = Field(description="地点名称")
    description: str = Field(description="地点描述")
    appears_in: List[str] = Field(default_factory=list, description="出现的场景ID列表")
    visual_cues: List[str] = Field(default_factory=list, description="视觉特征，如'红色招牌'、'绿色长椅'")


class GlobalMetadata(BaseModel):
    """全局元数据 - 贯穿全文需要保持一致的元素"""
    # 关键道具
    key_props: List[PropItem] = Field(default_factory=list, description="贯穿全文的重要道具")
    # 角色服装
    character_outfits: List[CharacterOutfit] = Field(default_factory=list, description="角色专属服装")
    # 关键地点
    key_locations: List[LocationItem] = Field(default_factory=list, description="主要场景地点")
    # 连续性要点
    continuity_notes: str = Field(default="", description="需要特别注意的连续性要点")
    # 全局音频设置
    audio_atmosphere: str = Field(default="neutral", description="全局音频氛围")
    recurring_sounds: List[str] = Field(default_factory=list, description="重复出现的声音")

    def to_dict(self) -> dict:
        """转换为字典表示"""
        return self.model_dump()

############################ 剧本解析结果模型 - 包含核心数据和统计信息 ###############################
class ParsedScript(BaseModel):
    """剧本解析结果 - 阶段1输出"""

    # 元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "parsed_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "parser_type": "unknown"
        },
        description="解析元数据"
    )

    # 核心数据
    title: Optional[str] = Field(
        default=None,
        description="剧本标题（如能识别）"
    )

    # 简化的核心数据
    characters: List[CharacterInfo] = Field(
        default_factory=list,
        description="识别到的角色列表"
    )

    scenes: List[SceneInfo] = Field(
        default_factory=list,
        description="场景列表，按出现顺序排列"
    )

    # 全局元数据 - 贯穿全文需要保持一致的元素，如关键道具、角色服装、重要地点等
    global_metadata: GlobalMetadata = Field(default_factory=GlobalMetadata)

    # 统计数据
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_elements": 0,
            "total_duration": 0.0,
            "dialogue_count": 0,
            "action_count": 0,
            "completeness_score": 0
        },
        description="解析统计数据"
    )

    def to_dict(self) -> dict:
        """转换为字典表示"""
        return self.model_dump()

    def get_elements_by_type(self, element_type: ElementType) -> List[BaseElement]:
        return [
            elem
            for scene in self.scenes
            for elem in scene.elements
            if elem.type == element_type
        ]

    def is_valid(self):
        return len(self.scenes) > 0

    def get_scene_by_id(self, scene_id: str) -> Optional[SceneInfo]:
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None

    def get_character_by_name(self, name: str) -> Optional[CharacterInfo]:
        for character in self.characters:
            if character.name == name:
                return character
        return None
