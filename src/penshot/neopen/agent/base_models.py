"""
@FileName: base_models.py
@Description: 基本模型
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/18 14:31
"""
import uuid
from datetime import datetime
from enum import Enum, unique
from typing import Optional

from pydantic import BaseModel, Field


# ==================== 基础枚举和类型定义 ====================
class ScriptType(str, Enum):
    """剧本格式类型"""
    NATURAL_LANGUAGE = "natural_language"  # 自然语言描述
    AI_STORYBOARD = "ai_storyboard"  # AI分镜脚本
    STRUCTURED_SCENE = "structured_scene"  # 结构化场景描述
    STANDARD_SCRIPT = "standard_script"  # 标准剧本格式
    DIALOGUE_ONLY = "dialogue_only"  # 纯对话
    MIXED_FORMAT = "mixed_format"  # 混合格式


class ElementType(str, Enum):
    SCENE = "scene"  # 场景描述
    DIALOGUE = "dialogue"  # 对话节点
    ACTION = "action"  # 动作节点
    TRANSITION = "transition"
    SILENCE = "silence"
    UNKNOWN = "unknown"


class AgentMode(str, Enum):
    """agent 实现的模式"""
    LLM = "llm"  # 基于 LLM 实现
    RULE = "rule"  # 基于本地规则


class VideoStyle(str, Enum):
    """视频风格/场景枚举（适用于背景声）"""
    # 逼真写实
    REALISTIC = 'realistic'
    # 动漫
    ANIME = 'anime'
    # 电影
    CINEMATIC = 'cinematic'
    # 卡通
    CARTOON = 'cartoon'
    # 风格化
    STYLIZED = "stylized"
    # 氛围/环境
    AMBIENT = "ambient"


class VideoModelType(str, Enum):
    """AI视频模型类型枚举"""
    RUNWAY_GEN2 = "runway_gen2"  # Runway Gen-2
    PIKA_LABS = "pika_labs"  # Pika Labs
    STABLE_VIDEO = "stable_video"  # Stable Video Diffusion
    LUMAS = "lumas"  # Luma AI
    KAIBER = "kaiber"  # Kaiber
    MOONVALLEY = "moonvalley"  # Moon Valley


class AudioModelType(str, Enum):
    """AI音频模型类型枚举"""
    XTTSv2 = "XTTSv2"  # 台词、旁白、人声
    AUDIOLDM_3 = "AudioLDM_3"  # 背景声、环境音、音效
    BARK = "Bark"  # 创造性语音（带语气词）
    ELEVENLABS = "ElevenLabs"  # 商业API（如果需要）
    AZURE_TTS = "Azure_TTS"  # 商业TTS
    OPENAI_TTS = "OpenAI_TTS"  # OpenAI TTS


@unique
class GenerationStatus(str, Enum):
    """生成状态"""
    PENDING = "pending"  # 等待生成
    GENERATING = "generating"  # 生成中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    NEEDS_RETRY = "needs_retry"  # 需要重试
    NEEDS_MANUAL_FIX = "needs_manual_fix"  # 需要手动修复


# ==================== 基础模型类 ====================
class BaseMetadata(BaseModel):
    """时间戳混合类"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    version: str = Field(default="1.0", description="模型版本")
