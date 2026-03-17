"""
@FileName: template_prompt_converter.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 23:41
"""
from typing import Optional

from penshot.neopen.agent.prompt_converter.base_prompt_converter import BasePromptConverter
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions, AIVideoPrompt
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotType
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info


class TemplatePromptConverter(BasePromptConverter):
    """基于模板的提示词转换器 - MVP版本"""

    def __init__(self, config: Optional[ShotConfig]):
        super().__init__(config)
        # 定义简单模板
        self.templates = {
            ShotType.CLOSE_UP: "{character} close-up shot, {action}, cinematic lighting, detailed facial expression",
            ShotType.MEDIUM_SHOT: "Medium shot of {character}, {action}, {location}, cinematic style",
            ShotType.WIDE_SHOT: "Wide shot, {location}, {description}, cinematic, establishing shot"
        }

    def convert(self, fragment_sequence: FragmentSequence, parsed_script: ParsedScript) -> AIVideoInstructions:
        """使用模板将片段转换为提示词"""
        info(f"开始提示词转换，片段数: {len(fragment_sequence.fragments)}")

        prompts = []

        # 设置项目信息
        project_info = {
            "title": fragment_sequence.source_info.get("title", "AI视频项目"),
            "total_fragments": fragment_sequence.stats.get("fragment_count", 0),
            "total_duration": fragment_sequence.stats.get("total_duration", 0.0)
        }

        # 转换每个片段
        for fragment in fragment_sequence.fragments:
            prompt = self.convert_fragment(fragment)
            prompts.append(prompt)

        # 构建指令集
        instructions = AIVideoInstructions(
            project_info=project_info,
            fragments=prompts,
            global_settings={
                "style_consistency": True,
                "use_common_negative_prompt": True
            }
        )

        # 后处理
        return self.post_process(instructions)

    def convert_fragment(self, fragment: VideoFragment) -> AIVideoPrompt:
        """转换单个片段为提示词"""
        # 解析镜头类型（从描述中推断）
        shot_type = self._infer_shot_type(fragment.description)

        # 获取连续性信息
        continuity = fragment.continuity_notes
        character = continuity.get("main_character", "character")
        location = continuity.get("location", "scene")
        action = continuity.get("main_action", fragment.description)

        # 选择模板并填充
        template = self.templates.get(shot_type, self.templates[ShotType.MEDIUM_SHOT])

        prompt_text = template.format(
            character=character,
            action=action,
            location=location,
            description=fragment.description
        )

        # 添加风格提示
        style_hint = "cinematic"
        if "紧张" in fragment.description or "恐惧" in fragment.description:
            style_hint = "suspense, dramatic lighting"
        elif "开心" in fragment.description or "微笑" in fragment.description:
            style_hint = "warm, bright lighting"

        # 构建完整提示词
        full_prompt = f"{prompt_text}, {style_hint}, high quality, 4K"

        # 截断到合理长度
        # if len(full_prompt) > self.config.max_prompt_length:
        #     full_prompt = full_prompt[:self.config.max_prompt_length - 3] + "..."

        # 创建提示词对象
        return AIVideoPrompt(
            fragment_id=fragment.id,
            prompt=full_prompt,
            negative_prompt=self.config.default_negative_prompt,
            duration=fragment.duration,
            model=self.config.video_model.value,
            style=style_hint,
            requires_special_attention=fragment.requires_special_attention
        )

    def _infer_shot_type(self, description: str) -> ShotType:
        """从描述推断镜头类型"""
        description_lower = description.lower()

        if "特写" in description_lower or ShotType.CLOSE_UP.value in description_lower:
            return ShotType.CLOSE_UP
        elif "全景" in description_lower or ShotType.WIDE_SHOT.value in description_lower:
            return ShotType.WIDE_SHOT
        else:
            return ShotType.MEDIUM_SHOT
