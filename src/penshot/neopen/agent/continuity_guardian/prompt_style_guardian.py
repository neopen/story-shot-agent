"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: prompt_style_guardian.py
@Description: 提示词风格守护者 - 确保多片段提示词风格一致
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/4/28 15:17
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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

    def __init__(self, knowledge_manager: Any, embedding_model: Any) -> None:
        self.knowledge_manager = knowledge_manager
        self.embedding_model = embedding_model
        self.current_style: Optional[StyleProfile] = None
        self.style_history: List[StyleProfile] = []

    def initialize_style(self, parsed_script: Any, style_anchor: Optional[Dict[str, Any]] = None) -> StyleProfile:
        """
        从剧本内容初始化风格画像

        Args:
            parsed_script: 剧本解析结果
            style_anchor: 契约风格锚点（优先于知识库召回）
        """
        # 提取剧本中的风格相关描述
        genre = getattr(parsed_script, 'genre', 'general')
        style_desc = getattr(parsed_script, 'style_description', '') or ""

        if style_anchor:
            self.current_style = self._profile_from_anchor(style_anchor)
        else:
            similar_style = self._search_similar_style(genre)
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

        # 关键词是漂移检测的基线，必须显式填充，否则相似度恒为 0
        self.current_style.keywords = self._collect_keywords(
            self.current_style, style_desc
        )
        self.style_history.append(self.current_style)
        return self.current_style

    def _search_similar_style(self, genre: str) -> Optional[Dict[str, Any]]:
        """知识库可选能力：不存在或调用失败时返回 None，回退默认风格"""
        search = getattr(self.knowledge_manager, "search_similar_style", None)
        if not callable(search):
            return None
        try:
            result = search(genre)
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    @staticmethod
    def _profile_from_anchor(anchor: Dict[str, Any]) -> StyleProfile:
        """把契约风格锚点映射为风格画像"""
        palette = anchor.get("palette")
        return StyleProfile(
            visual_style=str(anchor.get("genre") or anchor.get("visual_style") or ""),
            color_palette=[str(palette)] if palette else [],
            lighting_style=str(anchor.get("lighting") or ""),
            camera_movement=str(anchor.get("framing") or ""),
            atmosphere=str(anchor.get("mood") or ""),
        )

    @staticmethod
    def _collect_keywords(profile: StyleProfile, style_desc: str) -> List[str]:
        """从画像字段与剧本风格描述中抽取英文关键词基线"""
        text = " ".join(
            [
                profile.visual_style,
                profile.lighting_style,
                profile.camera_movement,
                profile.atmosphere,
                " ".join(profile.color_palette),
                style_desc,
            ]
        ).lower()
        return sorted({word for word in re.findall(r"[a-z]{3,}", text)})




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

        issues: List[Dict[str, Any]] = []
        base_keywords = set(self.current_style.keywords)
        if not base_keywords:
            # 无基线关键词时无法计算相似度，避免把全部片段误判为漂移
            return issues

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
