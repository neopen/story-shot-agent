"""
@FileName: prompt_converter_models.py
@Description: 模型
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/18 14:25
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

from pydantic import Field, BaseModel
from pydantic.v1 import validator

from penshot.neopen.agent.base_models import AudioModelType, VideoStyle


class AudioVoiceType(str, Enum):
    """人声类型（适用于台词/旁白）"""
    CHARACTER_DIALOGUE = "character_dialogue"  # 角色对白
    NARRATION = "narration"  # 旁白/画外音
    ANNOUNCER = "announcer"  # 播音/解说
    CREATIVE = "creative"  # 创意表达


class AIAudioPrompt(BaseModel):
    """MVP AI音频提示词模型"""
    audio_id: str = Field(..., description="唯一标识符，关联到片段ID或特定音频需求")
    # 核心提示词
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="核心提示词。对人声：台词文本；对背景声：详细声音描述"
    )

    negative_prompt: Optional[str] = Field(
        default="noisy, low quality, distorted, robotic, bad audio",
        description="负面提示词。不想要的声音特性。不同模型有不同默认值"
    )

    # === 模型与任务配置 ===
    model_type: AudioModelType = Field(
        default=AudioModelType.XTTSv2,
        description="AI音频模型类型。台词/旁白用XTTSv2，背景声用AudioLDM_3。其他AI音频模型：ElevenLabs、ChatGPT-4o、Text-to-Speech、Microsoft Azure Speech。"
    )

    voice_type: Optional[AudioVoiceType] = Field(
        default=AudioVoiceType.CHARACTER_DIALOGUE,
        description="人声类型。仅当model_type为语音模型时有效"
    )

    audio_style: Optional[VideoStyle] = Field(
        default=VideoStyle.CINEMATIC,
        description="音频风格/场景。对音效生成很重要"
    )

    # === 说话人配置（语音模型专用）===
    voice_character: Optional[str] = Field(
        default=None,
        description="说话人ID/名称。可以是：1) 预设语音名 2) 参考音频路径 3) 克隆的语音ID"
    )

    voice_description: Optional[str] = Field(
        default=None,
        description="音色文字描述。例如：'年轻女性，20岁，温柔清澈，略带俏皮'"
    )

    # === 语音参数 ===
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="语速倍数。1.0为正常，>1.0加速，<1.0减速"
    )

    pitch_shift: float = Field(
        default=0,
        ge=-12,
        le=12,
        description="音高偏移（半音）。正数升调，负数降调"
    )

    emotion: str = Field(
        default="neutral",
        description="情感/语调。如：'neutral', 'happy', 'sad', 'angry', 'whisper', 'dramatic'"
    )

    stability: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="语音稳定性/随机性。0.0最大变化，1.0最稳定"
    )

    # === 背景声参数（音效模型专用）===
    duration_seconds: float = Field(
        default=10.0,
        gt=0,
        le=60.0,
        description="音频时长（秒）。背景声可较长，台词按文本自动"
    )

    sound_attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        description="声音属性。如：{'intensity': 0.8, 'reverb': 0.3, 'stereo_width': 0.7}"
    )

    # === 输出配置 ===
    format: str = Field(
        default="wav",
        description="音频格式。推荐：'wav'(无损), 'mp3'(压缩), 'flac'(无损压缩)"
    )

    sample_rate: int = Field(
        default=24000,
        description="采样率。语音：24000, 背景声：48000"
    )

    seed: Optional[int] = Field(
        default=None,
        description="随机种子。用于重现相同结果"
    )

    # === 上下文信息（用于多轮对话/场景连贯性）===
    scene_context: Optional[str] = Field(
        default=None,
        description="场景上下文。如：'激烈战斗后的喘息对话'、'雨夜小巷追逐'"
    )

    previous_audio_id: Optional[str] = Field(
        default=None,
        description="前一段音频ID。用于保持音色/风格连贯性"
    )

    def to_dict(self) -> dict:
        """转换为字典表示"""
        return self.model_dump()

    # === 验证器 ===
    @validator('negative_prompt', pre=True, always=True)
    def set_default_negative_prompt(cls, v, values):
        """根据模型类型设置默认负面提示词"""
        if v is not None:
            return v

        model_type = values.get('model_type', AudioModelType.XTTSv2)

        default_negatives = {
            AudioModelType.XTTSv2: "noisy, distorted, robotic, monotone, bad pronunciation",
            AudioModelType.AUDIOLDM_3: "music, speech, human voice, distorted, low quality, repetitive",
            AudioModelType.BARK: "distorted, robotic, background noise, echo, bad timing",
            AudioModelType.ELEVENLABS: "noise, distortion, robotic, unnatural pauses",
        }

        return default_negatives.get(model_type, "low quality, distorted, bad audio")

    @validator('sample_rate')
    def validate_sample_rate(cls, v, values):
        """根据模型类型验证采样率"""
        model_type = values.get('model_type', AudioModelType.XTTSv2)

        # 语音模型通常用24kHz，音效/音乐模型用48kHz
        if model_type in [AudioModelType.XTTSv2, AudioModelType.ELEVENLABS,
                          AudioModelType.AZURE_TTS, AudioModelType.OPENAI_TTS]:
            if v not in [16000, 24000, 44100]:
                raise ValueError(f"语音模型推荐采样率：16000, 24000, 44100，当前：{v}")
        elif model_type in [AudioModelType.AUDIOLDM_3, AudioModelType.BARK]:
            if v not in [32000, 44100, 48000]:
                raise ValueError(f"音效/音乐模型推荐采样率：32000, 44100, 48000，当前：{v}")

        return v

    @validator('prompt')
    def validate_prompt_by_model(cls, v, values):
        """根据模型类型验证提示词"""
        model_type = values.get('model_type', AudioModelType.XTTSv2)

        if model_type in [AudioModelType.XTTSv2, AudioModelType.ELEVENLABS,
                          AudioModelType.AZURE_TTS, AudioModelType.OPENAI_TTS]:
            # 语音模型：检查是否为台词文本
            if len(v) < 2 or len(v) > 1000:
                raise ValueError("语音提示词应为2-1000字符的台词文本")

        elif model_type in [AudioModelType.AUDIOLDM_3, AudioModelType.BARK]:
            # 音效模型：检查是否为描述性文本
            if len(v) < 10:
                raise ValueError("音效提示词应至少10字符，详细描述声音")

        return v

    # === 辅助方法 ===
    def get_model_specific_config(self) -> Dict[str, Any]:
        """获取模型特定配置"""
        base_config = {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "seed": self.seed,
        }

        if self.model_type in [AudioModelType.XTTSv2, AudioModelType.ELEVENLABS,
                               AudioModelType.OPENAI_TTS, AudioModelType.AZURE_TTS]:
            # 语音模型配置
            config = {
                **base_config,
                "voice_id": self.voice_id,
                "voice_description": self.voice_description,
                "speed": self.speed,
                "pitch_shift": self.pitch_shift,
                "emotion": self.emotion,
                "stability": self.stability,
                "voice_type": self.voice_type,
                "scene_context": self.scene_context,
            }
        else:
            # 音效/背景声模型配置
            config = {
                **base_config,
                "duration": self.duration_seconds,
                "style": self.audio_style.value,
                "sound_attributes": self.sound_attributes or {},
            }

        return config

    def is_speech_model(self) -> bool:
        """是否为语音模型"""
        return self.model_type in [
            AudioModelType.XTTSv2,
            AudioModelType.ELEVENLABS,
            AudioModelType.OPENAI_TTS,
            AudioModelType.AZURE_TTS
        ]

    def is_background_model(self) -> bool:
        """是否为背景声模型"""
        return self.model_type in [
            AudioModelType.AUDIOLDM_3
        ]


class AIVideoPrompt(BaseModel):
    """MVP AI视频提示词模型"""
    fragment_id: str = Field(..., description="对应的片段ID")

    # 核心提示词
    prompt: str = Field(..., description="正向提示词文本")
    negative_prompt: str = Field(
        default="blurry, distorted, low quality, cartoonish, bad anatomy",
        description="负面提示词"
    )

    # 基本技术参数
    duration: float = Field(
        ...,
        ge=0.5,
        description="视频时长（秒）"
    )

    # 模型选择
    model: str = Field(
        default="runway_gen2",
        description="AI视频模型：runway_gen2/sora/pika（MVP先用runway）"
    )

    # 简化的风格提示
    style: Optional[str] = Field(
        default=None,
        description="风格提示：cinematic/realistic/anime/等"
    )

    # 扩展标记
    requires_special_attention: bool = Field(
        default=False,
        description="需要特殊处理的标记"
    )

    audio_prompt: Optional[AIAudioPrompt] = Field(
        default=None,
        description="关联的音频提示词（如果有）"
    )

    def to_dict(self) -> dict:
        """转换为字典表示"""
        return self.model_dump()


class AIVideoInstructions(BaseModel):
    """MVP AI视频指令集输出"""

    # 元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "generated_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "video_model": "runway_gen2",
            "audio_model": "XTTSv2"
        }
    )

    # 项目信息
    project_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "title": "",
            "total_fragments": 0,
            "total_duration": 0.0,
            "source_fragments": []  # 原始片段ID列表
        }
    )

    # 核心指令
    fragments: List[AIVideoPrompt] = Field(
        default_factory=list,
        description="片段提示词列表"
    )

    # 极简全局设置
    global_settings: Dict[str, Any] = Field(
        default_factory=lambda: {
            "style_consistency": True,
            "use_common_negative_prompt": True
        }
    )

    # 简化的执行建议
    execution_suggestions: List[str] = Field(
        default_factory=lambda: [
            "按顺序生成片段",
            "保持相同种子值以获得一致性",
            "生成后检查片段衔接"
        ]
    )

    def to_dict(self) -> dict:
        """转换为字典表示"""
        return self.model_dump()
