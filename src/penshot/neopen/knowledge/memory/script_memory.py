"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: memory_manager.py
@Description: 统一记忆管理器 - 支持剧本级隔离
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 13:10
"""
from datetime import datetime
from typing import Optional, Any, Dict, List

from langchain_core.language_models import BaseLanguageModel

from penshot.logger import info, debug
from penshot.neopen.knowledge.memory.long_term_memory import LongTermMemory
from penshot.neopen.knowledge.memory.medium_term_memory import MediumTermMemory
from penshot.neopen.knowledge.memory.memory_context import MemoryContext
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig, MemoryLevel
from penshot.neopen.knowledge.memory.short_term_memory import ShortTermMemory


class ScriptMemory:
    """剧本级记忆（组合三种记忆）"""

    def __init__(self, script_id: str, llm: BaseLanguageModel, config: MemoryConfig):
        self.script_id = script_id
        self.config = config

        # 初始化三种记忆
        self.short_term = ShortTermMemory(config, script_id)
        self.medium_term = MediumTermMemory(llm, config, script_id)

        self.long_term = None
        if config.long_term_enabled:
            self.long_term = LongTermMemory(config, script_id)
        else:
            # 检查是否已有长期记忆数据
            try:
                test_long_term = LongTermMemory(config, script_id)
                stats = test_long_term.get_stats()
                if stats.get("document_count", 0) > 0:
                    self.long_term = test_long_term
                    info(f"检测到已有长期记忆数据({stats['document_count']}条)，自动启用")
                    # 更新配置标记
                    config.long_term_enabled = True
                else:
                    debug(f"长期记忆未启用且无数据: {script_id}")
            except Exception as e:
                debug(f"检查长期记忆数据失败: {e}")

        # 元数据
        self.metadata: Dict[str, Any] = {
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat()
        }

        info(f"初始化任务记忆: script_id={script_id}")

    def add(self, input_text: str, output_text: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
            metadata: Optional[Dict] = None):
        """添加记忆"""
        self.metadata["last_accessed"] = datetime.now().isoformat()

        # 始终添加到短期记忆
        self.short_term.add(input_text, output_text, metadata)

        # 根据级别或重要性决定是否流转到中期/长期
        if level == MemoryLevel.MEDIUM_TERM:
            self.medium_term.add(input_text, output_text, metadata)
        elif level == MemoryLevel.LONG_TERM and self.long_term:
            combined = f"问题: {input_text}\n回答: {output_text}"
            self.long_term.add(combined, metadata)
        else:
            # 自动流转：重要的短期记忆提升到中期
            if metadata and metadata.get("important", False):
                self.medium_term.add(input_text, output_text, metadata)

            # 达到一定数量后，压缩到中期记忆
            short_term_stats = self.short_term.get_stats()
            if short_term_stats.get("message_count", 0) >= self.short_term.max_size * 0.8:
                # 将短期记忆摘要添加到中期
                recent = self.short_term.get_recent(5)
                summary_content = "\n".join([f"Q: {m['content']}\nA: {m.get('output', '')}" for m in recent])
                self.medium_term.add("short_term_summary", summary_content, {"auto_summary": True})

    def add_stage(self, stage_name: str, content: str, metadata: Optional[Dict] = None):
        """添加阶段记忆（特殊处理）"""
        self.metadata["last_accessed"] = datetime.now().isoformat()

        # 添加到中期记忆
        self.medium_term.add(stage_name, content, metadata)

        # 如果内容重要，也添加到长期记忆
        if metadata and metadata.get("important"):
            self.long_term.add(f"阶段: {stage_name}\n{content}", metadata)

    def recall(self, query: str, level: Optional[MemoryLevel] = None,
               k: int = 3) -> MemoryContext:
        """回忆记忆，返回融合上下文"""
        context = MemoryContext()

        if level is None or level == MemoryLevel.SHORT_TERM:
            # 获取短期记忆
            context.short_term = self.short_term.get_recent(k)

        if level is None or level == MemoryLevel.MEDIUM_TERM:
            # 获取中期摘要
            context.medium_term = self.medium_term.get_summary()

        if (level is None or level == MemoryLevel.LONG_TERM) and self.long_term:
            # 获取长期相关记忆
            context.long_term = self.long_term.search(query, k)

        return context

    def search(self, query: str, k: int = 3, level: MemoryLevel = MemoryLevel.LONG_TERM) -> List[Dict]:
        """语义搜索"""
        if level == MemoryLevel.LONG_TERM and self.long_term:
            return self.long_term.search(query, k)
        elif level == MemoryLevel.SHORT_TERM:
            # 短期记忆的简单关键词搜索
            recent = self.short_term.get_recent(k * 2)
            return [
                       item for item in recent
                       if query.lower() in item.get("content", "").lower()
                   ][:k]
        return []

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "script_id": self.script_id,
            "short_term": self.short_term.get_stats(),
            "medium_term": self.medium_term.get_stats(),
            "long_term": self.long_term.get_stats() if self.long_term else {"enabled": False},
            "metadata": self.metadata
        }

    def clear(self):
        """清空所有记忆"""
        self.short_term.clear()
        self.medium_term.clear()
        if self.long_term:
            self.long_term.clear()
        self.metadata["cleared_at"] = datetime.now().isoformat()
