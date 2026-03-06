"""
@FileName: hengline_config.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/28 12:25
"""
from dataclasses import dataclass

from hengshot.hengline.agent.base_models import VideoStyle, VideoModelType, AudioModelType
from hengshot.hengline.client.client_config import AIConfig

@dataclass
class HengLineConfig(AIConfig):
    """用户请求的参数"""
    prev_continuity_state = None        # 前一个分镜的连续性状态，用于保持连续性
    enable_llm: bool = True    # 开启 LLM 解析，否则使用规则解析
    enable_continuity_check: bool = False   # 开启连续性检查
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

    # ======================视频分割
    duration_split_threshold: float = 5.5  # 超过5秒触发分割
    max_fragment_duration: float = 5.0  # 最大分割片段时长
    min_fragment_duration: float = 1.0  # 最小片段时长
    split_strategy: str = "simple"  # 简单拆分策略
    ai_splitter_enabled: bool = True  # 是否启用AI分割器

    # ======================指令转换
    video_model: VideoModelType = VideoModelType.RUNWAY_GEN2
    audio_model: AudioModelType = AudioModelType.XTTSv2
    default_negative_prompt: str = "blurry, distorted, low quality, cartoonish, bad anatomy"
    default_style: VideoStyle = VideoStyle.CINEMATIC
    max_prompt_length: int = 200    # 提示词最大长度（单词数）
    min_prompt_length: int = 10


