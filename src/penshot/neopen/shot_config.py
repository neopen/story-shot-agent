"""
@FileName: neopen_config.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/28 12:25
"""
from dataclasses import dataclass

from penshot.neopen.agent.base_models import VideoStyle, VideoModelType, AudioModelType
from penshot.neopen.client.client_config import AIConfig

@dataclass
class ShotConfig(AIConfig):
    """用户请求的参数"""
    enable_llm: bool = True             # 开启 LLM 解析/分镜/审查，否则使用规则解析
    # prev_continuity_state: str = None        # 前一个分镜的连续性状态，用于保持连续性
    # enable_continuity_check: bool = False   # 开启连续性检查
    # 流程控制
    max_total_loops: int = 20  # 最大总循环次数
    loop_warning_issued: bool = False  # 是否已发出循环警告
    global_loop_exceeded: bool = False  # 全局循环超限标记

    # =====================剧本解析
    use_local_rules: bool = False  # 是否启用本地规则校验和补全

    # ======================镜头拆分
    max_shot_duration: float = 60.0  # 镜头允许的时长范围
    min_shot_duration: float = 1.0
    default_shot_duration: float = 3.0
    llm_confidence: float = 0.6  # LLM 输出的置信度阈值，低于该值将触发规则修正
    always_enhance: bool = True  # 是否始终进行时长增强（即使LLM置信度较高）
    enable_enhance: bool = True  # 是否启用时长增强器进行修正

    # ======================视频分割
    duration_split_threshold: float = 5.5  # 超过5秒触发分割
    max_fragment_duration: float = 5.0  # 最大分割片段时长
    min_fragment_duration: float = 1.0  # 最小片段时长
    split_strategy: str = "simple"  # 简单拆分策略
    ai_splitter_enabled: bool = True  # 是否启用AI分割器

    # ======================指令转换
    video_model: str = VideoModelType.RUNWAY_GEN2.value
    audio_model: str = AudioModelType.XTTSv2.value
    default_negative_prompt: str = "blurry, distorted, low quality, cartoonish, bad anatomy"
    default_style: str = VideoStyle.CINEMATIC.value
    max_prompt_length: int = 200    # 提示词最大长度（单词数）
    min_prompt_length: int = 20

    # ======================质量审查
    # enable_quality_audit: bool = True  # 是否启用质量审查
    # quality_audit_threshold: float = 0.5  # 质量审查的分数阈值，低于该值视为不合格
    prompt_length_max_threshold: int = max_prompt_length + 20   # 提示词长度警告阈值，超过该值将发出警告
    prompt_length_min_threshold: int = min_prompt_length - 10  # 提示词长度警告阈值，超过该值将发出警告

    # ======================其他
    # enable_caching: bool = True  # 是否启用缓存机制，避免重复计算
    # cache_expiry_seconds: int = 3600  # 缓存过期时间


