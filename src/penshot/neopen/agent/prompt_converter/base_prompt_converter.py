"""
@FileName: base_prompt_converter.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 23:36
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info, warning


class BasePromptConverter(ABC):
    """提示词转换器抽象基类"""

    def __init__(self, config: Optional[ShotConfig]):
        self.config = config
        self._initialize()

    def _initialize(self):
        """初始化转换器"""
        info(f"初始化提示词转换器: {self.__class__.__name__}")

    @abstractmethod
    def convert(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript,
                repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> AIVideoInstructions:
        """将片段序列转换为AI提示词（抽象方法）"""
        pass

    def post_process(self, instructions: AIVideoInstructions) -> AIVideoInstructions:
        """后处理：填充项目信息等"""
        fragments = instructions.fragments

        if not fragments:
            warning("转换结果为空")
            return instructions

        # 计算项目信息
        total_duration = sum(frag.duration for frag in fragments)

        instructions.project_info.update({
            "title": instructions.project_info.get("title", "AI视频项目"),
            "total_fragments": len(fragments),
            "total_duration": round(total_duration, 2),
            "source_fragments": [frag.fragment_id for frag in fragments]
        })

        # 更新元数据
        instructions.metadata.update({
            "total_prompts": len(fragments),
            "converter_type": self.__class__.__name__
        })

        info(f"转换完成: {len(fragments)}个提示词, 总时长{total_duration:.1f}秒")
        return instructions


    def _generate_base_prompt(self, fragment: VideoFragment) -> str:
        """生成基础提示词（模板方法）"""
        # 基础模板
        base_template = "{description}, {style} style"

        # 获取风格
        style = self.config.default_style

        # 构建描述
        description = fragment.description or f"视频片段 {fragment.id}"

        # 如果有连续性信息，可以加入
        if fragment.continuity_notes.get("main_character"):
            character = fragment.continuity_notes["main_character"]
            description = f"{character}, {description}"

        return base_template.format(
            description=description,
            style=style
        )
