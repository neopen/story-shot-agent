"""
@FileName: short_term_memory.py
@Description: 短期记忆 - 基于LangChain的缓冲记忆
@Author: HiPeng
@Time: 2026/4/1
"""
from typing import Optional, Any, Dict, List
from collections import deque

from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain.schema import HumanMessage, AIMessage

from penshot.logger import debug, warning
from penshot.neopen.tools.memory.memory_models import MemoryConfig


class ShortTermMemory:
    """短期记忆 - 基于LangChain的缓冲记忆"""

    def __init__(self, config: MemoryConfig, script_id: str):
        self.config = config
        self.script_id = script_id
        self.max_size = config.short_term_size

        # 初始化消息历史（可选Redis持久化）
        if config.short_term_redis_url:
            message_history = RedisChatMessageHistory(
                session_id=f"{script_id}_short_term",
                url=config.short_term_redis_url,
                key_prefix="penshot:memory:",
                ttl=config.short_term_ttl
            )
        else:
            message_history = None

        # 创建缓冲记忆（不设置k参数）
        self.memory = ConversationBufferMemory(
            chat_memory=message_history,
            return_messages=True,
            memory_key="history",
            input_key="input",
            output_key="output"
        )

        # 手动维护滑动窗口
        self._message_buffer = deque(maxlen=config.short_term_size)

        debug(f"初始化短期记忆: script={script_id}, size={config.short_term_size}")

    def add(self, input_text: str, output_text: str, metadata: Optional[Dict] = None):
        """添加交互"""
        # 保存到LangChain记忆
        self.memory.save_context(
            {"input": input_text},
            {"output": output_text}
        )

        # 手动维护滑动窗口
        self._message_buffer.append({
            "input": input_text,
            "output": output_text,
            "metadata": metadata,
            "timestamp": None  # 可以添加时间戳
        })

        # 如果超过最大大小，从LangChain记忆中移除最旧的消息
        if len(self._message_buffer) > self.max_size:
            self._trim_memory()

    def _trim_memory(self):
        """修剪记忆，保持滑动窗口大小"""
        # 注意：ConversationBufferMemory 没有直接删除消息的方法
        # 这里通过重新构建记忆来实现
        try:
            # 获取最近的消息
            recent_messages = list(self._message_buffer)[-self.max_size:]

            # 清空并重新添加
            self.clear()

            for msg in recent_messages:
                self.memory.save_context(
                    {"input": msg["input"]},
                    {"output": msg["output"]}
                )
        except Exception as e:
            warning(f"修剪记忆失败: {e}")

    def get_recent(self, n: int = None) -> List[Dict]:
        """获取最近的N条记忆"""
        if n is None:
            n = self.max_size

        # 从手动缓冲区获取（更可靠）
        recent = list(self._message_buffer)[-n:]
        return [
            {
                "role": "user",
                "content": msg["input"],
                "output": msg["output"],
                "metadata": msg.get("metadata", {}),
                "timestamp": msg.get("timestamp")
            }
            for msg in recent
        ]

    def get_all_messages(self) -> List[Dict]:
        """获取所有消息（从LangChain记忆）"""
        variables = self.memory.load_memory_variables({})
        messages = variables.get("history", [])

        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})

        return result

    def clear(self):
        """清空记忆"""
        if hasattr(self.memory, 'clear'):
            self.memory.clear()
        elif hasattr(self.memory, 'chat_memory') and hasattr(self.memory.chat_memory, 'clear'):
            self.memory.chat_memory.clear()

        self._message_buffer.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "type": "short_term",
            "message_count": len(self._message_buffer),
            "max_size": self.max_size,
            "ttl": self.config.short_term_ttl,
            "redis_enabled": self.config.short_term_redis_url is not None
        }