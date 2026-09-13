"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: prompt_style_guardian.py
@Description: 提示词风格守护者 - 确保多片段提示词风格一致
@Author: NeoPen
@Time: 2026/4/28 15:17
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StyleProfile:
    """风格画像"""
    visual_style: str = ""  # 视觉风格: cinematic, anime, realistic
    color_palette: List[str] = field(default_factory=list)  # 主色调
    lighting_style: str = ""  # 光照风格: natural, dramatic, soft
    camera_movement: str = ""  # 运镜风格: steady, dynamic, handheld
    atmosphere: str = ""  # 氛围: tense, warm, mysterious

    # 关键词集合
    keywords: List[str] = field(default_factory=list)

    def to_prompt_enhancement(self) -> str:
        """转换为提示词增强前缀"""
        parts = []
        if self.visual_style:
            parts.append(f"{self.visual_style} style")
        if self.lighting_style:
            parts.append(f"{self.lighting_style} lighting")
        if self.camera_movement:
            parts.append(f"{self.camera_movement} camera")
        if self.atmosphere:
            parts.append(f"{self.atmosphere} atmosphere")

        return ", ".join(parts) if parts else ""


class PromptStyleGuardian:
    """提示词风格守护者"""

    def __init__(self, knowledge_manager, embedding_model):
        self.knowledge_manager = knowledge_manager
        self.embedding_model = embedding_model
        self.current_style: Optional[StyleProfile] = None
        self.style_history: List[StyleProfile] = []

    def initialize_style(self, parsed_script) -> StyleProfile:
        """
        从剧本内容初始化风格画像
        """
        # 提取剧本中的风格相关描述
        genre = getattr(parsed_script, 'genre', 'general')
        style_desc = getattr(parsed_script, 'style_description', '')

        # 从知识库检索相似剧本的风格
        similar_style = self.knowledge_manager.search_similar_style(genre)

        if similar_style:
            self.current_style = StyleProfile(**similar_style)
        else:
            # 默认风格
            self.current_style = StyleProfile(
                visual_style=self._infer_visual_style(genre),
                lighting_style='natural',
                camera_movement='steady',
                atmosphere='neutral'
            )

        self.style_history.append(self.current_style)
        return self.current_style

    def enhance_prompt_with_style(self, prompt: str,
                                  style: Optional[StyleProfile] = None) -> str:
        """
        用风格信息增强提示词
        """
        style = style or self.current_style
        if not style:
            return prompt

        enhancement = style.to_prompt_enhancement()
        if enhancement:
            # 避免重复添加风格信息
            if enhancement not in prompt:
                return f"{enhancement}. {prompt}"

        return prompt

    def detect_style_drift(self, prompts: List[str]) -> List[Dict]:
        """
        检测提示词风格漂移

        Returns:
            风格漂移问题列表
        """
        if not self.current_style:
            return []

        issues = []
        base_keywords = set(self.current_style.keywords)

        for i, prompt in enumerate(prompts):
            # 提取提示词中的关键词
            prompt_keywords = set(re.findall(r'\b\w+\b', prompt.lower()))

            # 计算关键词重叠度
            overlap = base_keywords & prompt_keywords
            similarity = len(overlap) / max(len(base_keywords), 1)

            if similarity < 0.3:  # 相似度过低
                issues.append({
                    "fragment_index": i,
                    "similarity": similarity,
                    "issue": "style_drift",
                    "suggestion": "提示词风格与基础风格差异过大，建议调整"
                })
            elif similarity < 0.6:
                issues.append({
                    "fragment_index": i,
                    "similarity": similarity,
                    "severity": "warning",
                    "suggestion": "提示词风格有所漂移"
                })

        return issues

    def _infer_visual_style(self, genre: str) -> str:
        """根据类型推断视觉风格"""
        style_map = {
            'action': 'dynamic cinematic',
            'drama': 'naturalistic',
            'comedy': 'bright colorful',
            'horror': 'dark gritty',
            'sci-fi': 'futuristic sleek',
            'fantasy': 'magical epic',
            'romance': 'warm soft',
            'documentary': 'realistic neutral'
        }
        return style_map.get(genre, 'cinematic')
