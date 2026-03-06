"""
@FileName: prompt_utils.py
@Description: 提示词处理工具
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/5 23:46
"""

import re
from typing import List, Dict


class PromptUtils:
    """提示词实用工具"""

    @staticmethod
    def split_prompt_by_sections(prompt: str) -> Dict[str, str]:
        """按部分分割提示词"""
        sections = {
            "subject": "",
            "style": "",
            "technical": ""
        }

        # 尝试按分隔符分割
        if "|" in prompt:
            parts = prompt.split("|")
            if len(parts) >= 3:
                sections["subject"] = parts[0].strip()
                sections["style"] = parts[1].strip()
                sections["technical"] = parts[2].strip()
                return sections

        # 尝试按句号分割
        sentences = [s.strip() for s in prompt.split('.') if s.strip()]

        if len(sentences) >= 3:
            # 假设第一句是主体
            sections["subject"] = sentences[0]

            # 中间句子是风格
            style_sentences = sentences[1:-1]
            sections["style"] = '. '.join(style_sentences)

            # 最后一句是技术
            sections["technical"] = sentences[-1]
        else:
            # 无法分割，全部作为主体
            sections["subject"] = prompt

        return sections

    @staticmethod
    def extract_keywords(prompt: str,
                         max_keywords: int = 10) -> List[str]:
        """从提示词中提取关键词"""
        # 移除标点
        clean_prompt = re.sub(r'[^\w\s]', ' ', prompt)

        # 分割单词
        words = clean_prompt.lower().split()

        # 移除停用词
        stop_words = {
            'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'
        }

        keywords = [word for word in words if word not in stop_words]

        # 计算词频
        from collections import Counter
        word_counts = Counter(keywords)

        # 获取最重要的关键词
        most_common = word_counts.most_common(max_keywords)
        return [word for word, count in most_common]

    @staticmethod
    def optimize_prompt_length(prompt: str,
                               target_length: int = 200) -> str:
        """优化提示词长度"""
        if len(prompt) <= target_length:
            return prompt

        # 分割成句子
        sentences = [s.strip() for s in prompt.split('.') if s.strip()]

        # 如果只有一句话，按单词分割
        if len(sentences) == 1:
            words = prompt.split()
            if len(words) > target_length // 5:  # 平均每个单词5个字符
                # 保留前N个单词
                truncated = ' '.join(words[:target_length // 5])
                return truncated + '...'
            return prompt

        # 保留最重要的句子（基于关键词密度）
        important_sentences = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)
            if current_length + sentence_length <= target_length:
                important_sentences.append(sentence)
                current_length += sentence_length + 2  # 句点和空格
            else:
                break

        if not important_sentences:
            # 如果第一句就太长了，截断
            first_sentence = sentences[0]
            if len(first_sentence) > target_length:
                return first_sentence[:target_length - 3] + '...'
            return first_sentence

        return '. '.join(important_sentences) + '.'

    @staticmethod
    def add_emphasis(prompt: str,
                     elements: List[str],
                     emphasis_type: str = "parentheses") -> str:
        """为重点元素添加强调"""
        emphasized_prompt = prompt

        for element in elements:
            if element in emphasized_prompt:
                if emphasis_type == "parentheses":
                    replacement = f"({element})"
                elif emphasis_type == "weight":
                    replacement = f"({element}:1.2)"
                else:
                    replacement = f"**{element}**"

                emphasized_prompt = emphasized_prompt.replace(element, replacement)

        return emphasized_prompt

    @staticmethod
    def generate_prompt_variations(base_prompt: str,
                                   variations_count: int = 3) -> List[str]:
        """生成提示词变体"""
        variations = []

        # 变体1：调整顺序
        sections = PromptUtils.split_prompt_by_sections(base_prompt)
        if sections["style"] and sections["technical"]:
            # 技术部分在前
            variation1 = f"{sections['technical']}, {sections['style']}, {sections['subject']}"
            variations.append(variation1)

        # 变体2：简化
        keywords = PromptUtils.extract_keywords(base_prompt, 8)
        variation2 = f"{', '.join(keywords)}, cinematic, detailed, photorealistic"
        variations.append(variation2)

        # 变体3：添加具体参数
        variation3 = base_prompt + ", 8k resolution, Unreal Engine 5, ray tracing"
        variations.append(variation3)

        return variations[:variations_count]
