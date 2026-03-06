"""
@FileName: script_parser_models.py
@Description:  剧本解析相关模型
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/19 21:44
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field

from hengshot.hengline.agent.base_models import ElementType

# ========================= 音频上下文模型 - 包含环境声音、背景音乐等信息 =========================
class SoundType(str, Enum):
    """环境音类型"""
    RAIN = "rain"  # 雨声
    WIND = "wind"  # 风声
    THUNDER = "thunder"  # 雷声
    WATER_DRIP = "water_drip"  # 滴水声
    FOOTSTEP = "footstep"  # 脚步声
    TRAFFIC = "traffic"  # 交通声
    CROWD = "crowd"  # 人群声
    MUSIC = "music"  # 背景音乐
    TV_NOISE = "tv_noise"  # 电视噪音
    BIRD = "bird"  # 鸟叫声
    paper_rustle = "paper_rustle"  # 纸张摩擦声
    SILENCE = "silence"  # 安静/无声
    OTHER = "other"  # 其他未分类的声音


class SceneType(str, Enum):
    """场景类型"""
    INDOOR = "indoor"  # 室内
    OUTDOOR = "outdoor"  # 室外
    CAFE = "cafe"  # 咖啡店
    PARK = "park"  # 公园
    STREET = "street"  # 街道
    LIVING_ROOM = "living_room"  # 客厅
    RAINY_OUTDOOR = "rainy_outdoor"  # 雨天户外
    NIGHT_OUTDOOR = "night_outdoor"  # 夜间户外
    OTHER = "other" # 其他未分类的场景


class EnvironmentSound(BaseModel):
    """环境音信息"""
    sound_type: SoundType = Field(..., description="环境音类型")
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="强度/音量")
    continuous: bool = Field(default=True, description="是否持续")
    description: Optional[str] = Field(None, description="详细描述")
    timing: Optional[str] = Field(None, description="出现时机，如'开场'、'高潮'、'结尾'")


class SceneAudioContext(BaseModel):
    """场景音频上下文"""
    scene_type: SceneType = Field(..., description="场景类型")
    env_sounds: List[EnvironmentSound] = Field(default_factory=list, description="环境音列表")
    has_dialogue: bool = Field(default=False, description="是否有对话")
    has_voiceover: bool = Field(default=False, description="是否有旁白")
    atmosphere: str = Field(default="neutral", description="氛围描述，如'紧张'、'温馨'、'忧伤'")
    reverb: float = Field(default=0.2, ge=0.0, le=1.0, description="混响强度")


class ElementAudioContext(BaseModel):
    """元素级别的音频上下文"""
    sound_type: Optional[SoundType] = Field(None, description="该元素产生的声音类型")
    description: Optional[str] = Field(None, description="声音描述")
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="强度")


# ========================= 基础模型定义 - 包含剧本元素、角色信息、场景信息等核心数据结构 ==================
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
        default="neutral",
        description="伴随情绪：neutral/happy/angry/sad/fear"
    )
    # 元素音频上下文
    audio_context: Optional[ElementAudioContext] = Field(None, description="元素音频上下文")


class CharacterInfo(BaseModel):
    """角色信息模型"""
    name: str = Field(..., description="角色名称")
    gender: str = Field(..., description="角色性别")
    role: str = Field(..., description="角色类型（主角、配角等）")
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
        scene_type=SceneType.OUTDOOR,
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
    recurring_sounds: List[SoundType] = Field(default_factory=list, description="重复出现的声音")

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
