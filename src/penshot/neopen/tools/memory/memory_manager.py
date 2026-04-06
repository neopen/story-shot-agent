"""
@FileName: memory_manager.py
@Description: 基于LangChain的记忆管理系统
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/4/1
"""
import json
from typing import Optional, Any, Dict, List

from langchain_core.language_models import BaseLLM

from penshot.logger import info, debug
from penshot.neopen.tools.memory.memory_context import MemoryContext
from penshot.neopen.tools.memory.memory_models import MemoryConfig, MemoryLevel
from penshot.neopen.tools.memory.script_memory import ScriptMemory


class MemoryManager:
    """全局记忆管理器 - 统一记忆检索接口"""

    def __init__(self, script_id, llm: BaseLLM, config: Optional[MemoryConfig] = None):
        """
        初始化记忆管理器

        Args:
            script_id: 脚本ID
            llm: 语言模型
            config: 记忆配置
        """
        self.llm = llm
        self.config = config or MemoryConfig()

        # 任务记忆字典
        self._script_memories: Dict[str, ScriptMemory] = {}

        # 当前任务ID
        self._current_script_id: Optional[str] = script_id

        self.set_script(script_id)

        info("初始化记忆管理器")

    def set_script(self, script_id: str):
        """设置当前任务"""
        self._current_script_id = script_id
        if script_id not in self._script_memories:
            self._script_memories[script_id] = ScriptMemory(script_id, self.llm, self.config)
        debug(f"切换到任务: {script_id}")

    def get_script(self, script_id: Optional[str] = None) -> ScriptMemory:
        """获取任务记忆实例"""
        tid = script_id or self._current_script_id
        if not tid:
            raise ValueError("未设置任务ID，请先调用 set_script()")

        if tid not in self._script_memories:
            self._script_memories[tid] = ScriptMemory(tid, self.llm, self.config)

        return self._script_memories[tid]

    # ===================== 添加记忆 =====================

    def add(self, input_text: str, output_text: Any, level: MemoryLevel = MemoryLevel.SHORT_TERM,
            metadata: Optional[Dict] = None, script_id: Optional[str] = None):
        """添加交互记忆，支持任意类型"""
        output_str = self._to_str(output_text)
        script = self.get_script(script_id)
        script.add(input_text, output_str, level, metadata)
        debug(f"添加记忆: script={script.script_id}, level={level.value}")

    def add_raw(self, input_text: str, output_text: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
                metadata: Optional[Dict] = None, script_id: Optional[str] = None):
        """直接添加字符串（不自动转换）"""
        script = self.get_script(script_id)
        script.add(input_text, output_text, level, metadata)
        debug(f"添加原始记忆: script={script.script_id}, level={level.value}")

    def add_stage(self, stage_name: str, content: str, metadata: Optional[Dict] = None,
                  script_id: Optional[str] = None):
        """添加阶段记忆"""
        script = self.get_script(script_id)
        script.add_stage(stage_name, content, metadata)
        debug(f"添加阶段记忆: script={script.script_id}, stage={stage_name}")

    # ===================== 核心检索接口 =====================

    def recall(self, query: str, level: Optional[MemoryLevel] = None,
               k: int = 3, script_id: Optional[str] = None) -> MemoryContext:
        """
        回忆记忆，返回 MemoryContext 对象

        Args:
            query: 查询文本
            level: 记忆级别（None表示所有级别）
            k: 返回数量
            script_id: 任务ID（可选）

        Returns:
            MemoryContext: 包含短期、中期、长期记忆的上下文对象
        """
        script = self.get_script(script_id)
        context = script.recall(query, level, k)

        # 反序列化短期记忆
        for item in context.short_term:
            if "output" in item:
                item["output"] = self._deserialize(
                    item["output"],
                    item.get("metadata", {})
                )

        # 反序列化长期记忆
        for item in context.long_term:
            if "content" in item:
                item["content"] = self._deserialize(
                    item["content"],
                    item.get("metadata", {})
                )

        debug(f"回忆记忆: script={script.script_id}, level={level}, "
              f"short={len(context.short_term)}, medium={'有' if context.medium_term else '无'}, "
              f"long={len(context.long_term)}")
        return context

    # ===================== 便捷检索接口 =====================

    def get(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
            default: Any = None, script_id: Optional[str] = None) -> Any:
        """
        获取单个记忆值（最常用）

        Args:
            key: 记忆键
            level: 记忆级别
            default: 默认值
            script_id: 任务ID

        Returns:
            记忆值（已反序列化）
        """
        context = self.recall(key, level=level, script_id=script_id)

        if level == MemoryLevel.SHORT_TERM:
            if context.short_term:
                return context.short_term[-1].get("output", default)
            return default
        elif level == MemoryLevel.MEDIUM_TERM:
            return context.medium_term if context.medium_term else default
        elif level == MemoryLevel.LONG_TERM:
            if context.long_term:
                return context.long_term[-1].get("content", default)
            return default
        return default

    def get_list(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
                 script_id: Optional[str] = None) -> List[Any]:
        """
        获取记忆列表（用于存储多个值的场景）

        Args:
            key: 记忆键
            level: 记忆级别
            script_id: 任务ID

        Returns:
            记忆值列表（已反序列化）
        """
        context = self.recall(key, level=level, script_id=script_id)

        if level == MemoryLevel.SHORT_TERM:
            if context.short_term:
                return [item.get("output") for item in context.short_term if item.get("output")]
            return []
        elif level == MemoryLevel.LONG_TERM:
            if context.long_term:
                return [item.get("content") for item in context.long_term if item.get("content")]
            return []
        return []

    def get_latest(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
                   default: Any = None, script_id: Optional[str] = None) -> Any:
        """
        获取最新一条记忆（别名，同 get）
        """
        return self.get(key, level, default, script_id)

    def get_latest_deserialized(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
                                default: Any = None, script_id: Optional[str] = None) -> Any:
        """
        获取最新一条记忆并自动反序列化 JSON
        """
        value = self.get(key, level, default, script_id)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except:
                return value
        return value

    def get_all(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
                script_id: Optional[str] = None) -> List[Any]:
        """
        获取所有匹配的记忆（别名，同 get_list）
        """
        return self.get_list(key, level, script_id)

    # ===================== 状态查询接口 =====================

    def exists(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
               script_id: Optional[str] = None) -> bool:
        """
        检查记忆是否存在

        Args:
            key: 记忆键
            level: 记忆级别
            script_id: 任务ID

        Returns:
            是否存在
        """
        if level == MemoryLevel.SHORT_TERM:
            context = self.recall(key, level=level, script_id=script_id)
            return bool(context.short_term)
        elif level == MemoryLevel.MEDIUM_TERM:
            context = self.recall(key, level=level, script_id=script_id)
            return bool(context.medium_term)
        elif level == MemoryLevel.LONG_TERM:
            context = self.recall(key, level=level, script_id=script_id)
            return bool(context.long_term)
        return False

    def count(self, key: str, level: MemoryLevel = MemoryLevel.SHORT_TERM,
              script_id: Optional[str] = None) -> int:
        """
        获取记忆数量

        Args:
            key: 记忆键
            level: 记忆级别
            script_id: 任务ID

        Returns:
            记忆数量
        """
        if level == MemoryLevel.SHORT_TERM:
            context = self.recall(key, level=level, script_id=script_id)
            return len(context.short_term)
        elif level == MemoryLevel.LONG_TERM:
            context = self.recall(key, level=level, script_id=script_id)
            return len(context.long_term)
        return 0

    # ===================== 语义搜索接口 =====================

    def search(self, query: str, k: int = 3, level: MemoryLevel = MemoryLevel.LONG_TERM,
               script_id: Optional[str] = None) -> List[Dict]:
        """
        语义搜索（仅支持长期记忆）

        Args:
            query: 查询文本
            k: 返回数量
            level: 记忆级别
            script_id: 任务ID

        Returns:
            搜索结果列表
        """
        script = self.get_script(script_id)
        results = script.search(query, k, level)

        # 反序列化结果
        for item in results:
            if "content" in item:
                item["content"] = self._deserialize(
                    item["content"],
                    item.get("metadata", {})
                )
        return results

    def search_latest(self, query: str, k: int = 3, script_id: Optional[str] = None) -> List[Dict]:
        """
        搜索最新记忆（别名）
        """
        return self.search(query, k, MemoryLevel.LONG_TERM, script_id)

    # ===================== 上下文接口 =====================

    def get_context_for_llm(self, query: str, max_tokens: int = 2000,
                            script_id: Optional[str] = None) -> str:
        """
        获取用于LLM提示的上下文

        Args:
            query: 查询文本
            max_tokens: 最大 token 数
            script_id: 任务ID

        Returns:
            格式化的上下文字符串
        """
        context = self.recall(query, script_id=script_id)
        return context.to_prompt(max_tokens)

    # ===================== 统计和管理接口 =====================

    def get_stats(self, script_id: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        if script_id:
            script = self.get_script(script_id)
            return script.get_stats()
        else:
            return {
                "total_scripts": len(self._script_memories),
                "scripts": {
                    tid: memory.get_stats()
                    for tid, memory in self._script_memories.items()
                },
                "current_script": self._current_script_id
            }

    def clear_script(self, script_id: Optional[str] = None):
        """清空指定任务的记忆"""
        tid = script_id or self._current_script_id
        if tid and tid in self._script_memories:
            self._script_memories[tid].clear()
            del self._script_memories[tid]
            info(f"清空任务记忆: {tid}")

    def clear_all(self):
        """清空所有任务的记忆"""
        for script_id in list(self._script_memories.keys()):
            self.clear_script(script_id)
        info("清空所有记忆")

    # ===================== 私有辅助方法 =====================

    def _deserialize(self, value: str, metadata: Dict = None) -> Any:
        """反序列化记忆值"""
        if metadata and metadata.get("_serialized"):
            try:
                return json.loads(value)
            except:
                return value
        return value

    def _to_str(self, value: Any) -> str:
        """将任意值转换为字符串"""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except:
            return str(value)
