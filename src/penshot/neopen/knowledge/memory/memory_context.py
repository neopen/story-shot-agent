"""
@FileName: memory_context.py
@Description: 
@Author: HiPeng
@Time: 2026/4/1 14:01
"""
from typing import Any, Dict, List


class MemoryContext:
    """记忆上下文 - 用于LLM提示"""

    def __init__(self):
        self.short_term: List[Dict] = []
        self.medium_term: str = ""
        self.long_term: List[Dict] = []
        self.metadata: Dict[str, Any] = {}

    def to_prompt(self, max_tokens: int = 2000) -> str:
        """转换为提示词格式"""
        parts = []

        if self.short_term:
            parts.append("=== 最近对话 ===\n" + self._format_short_term())

        if self.medium_term:
            parts.append("=== 历史摘要 ===\n" + self.medium_term)

        if self.long_term:
            parts.append("=== 相关经验 ===\n" + self._format_long_term())

        context = "\n\n".join(parts)
        return self._truncate(context, max_tokens)

    def _format_short_term(self) -> str:
        """格式化短期记忆"""
        formatted = []
        for msg in self.short_term:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    def _format_long_term(self) -> str:
        """格式化长期记忆"""
        formatted = []
        for item in self.long_term[:5]:  # 限制最多5条
            content = item.get("content", "")
            score = item.get("score", 0)
            formatted.append(f"[相关度: {score:.2f}]\n{content}")
        return "\n---\n".join(formatted)

    def _truncate(self, text: str, max_tokens: int) -> str:
        """截断文本"""
        # 粗略估算：1 token ≈ 2 字符
        if len(text) // 2 <= max_tokens:
            return text
        return text[:max_tokens * 2] + "\n[上下文已截断]"
