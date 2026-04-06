"""
@FileName: short_term_memory.py
@Description: 短期记忆 - 基于LangChain的缓冲记忆
@Author: HiPeng
@Time: 2026/4/1
"""
from collections import deque
from typing import Optional, Any, Dict, List

from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from penshot.logger import debug, warning
from penshot.neopen.tools.memory.memory_models import MemoryConfig


class ShortTermMemory:
    """短期记忆 - 基于LangChain的缓冲记忆"""

    def __init__(self, config: MemoryConfig, script_id: str):
        self.config = config
        self.script_id = script_id
        self.max_size = config.short_term_size

        # 会话历史存储
        self._session_histories: Dict[str, BaseChatMessageHistory] = {}

        # 手动维护滑动窗口
        self._message_buffer = deque(maxlen=config.short_term_size)

        # 创建带记忆的链
        self.memory = self._create_memory_chain()

        debug(f"初始化短期记忆: script={script_id}, size={config.short_term_size}")

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取或创建会话历史"""
        if session_id not in self._session_histories:
            # 如果配置了Redis，使用Redis消息历史
            if self.config.short_term_redis_url:
                self._session_histories[session_id] = RedisChatMessageHistory(
                    session_id=session_id,
                    url=self.config.short_term_redis_url,
                    key_prefix="penshot:memory:",
                    ttl=self.config.short_term_ttl
                )
            else:
                # 使用内存消息历史（导入正确的类型）
                from langchain_core.chat_history import InMemoryChatMessageHistory
                self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    def _create_memory_chain(self):
        """创建带记忆的链"""
        def add_to_memory(input_dict):
            """添加消息到记忆"""
            input_text = input_dict.get("input", "")
            output_text = input_dict.get("output", "")

            if input_text and output_text:
                session_id = input_dict.get("session_id", "default")
                history = self._get_session_history(session_id)
                history.add_user_message(input_text)
                history.add_ai_message(output_text)

                # 手动维护滑动窗口
                self._message_buffer.append({
                    "input": input_text,
                    "output": output_text,
                    "metadata": input_dict.get("metadata"),
                    "timestamp": None
                })

                # 如果超过最大大小，修剪记忆
                if len(self._message_buffer) > self.max_size:
                    self._trim_memory()

            return {"status": "added"}

        return RunnableLambda(add_to_memory)

    def add(self, input_text: str, output_text: str, metadata: Optional[Dict] = None):
        """添加交互"""
        session_id = f"script_{self.script_id}"
        self.memory.invoke({
            "input": input_text,
            "output": output_text,
            "metadata": metadata,
            "session_id": session_id
        })

    def _trim_memory(self):
        """修剪记忆，保持滑动窗口大小"""
        try:
            # 获取最近的消息
            recent_messages = list(self._message_buffer)[-self.max_size:]

            # 清空并重新添加
            self.clear()

            for msg in recent_messages:
                session_id = f"script_{self.script_id}"
                history = self._get_session_history(session_id)
                history.add_user_message(msg["input"])
                history.add_ai_message(msg["output"])

                self._message_buffer.append(msg)
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
        session_id = f"script_{self.script_id}"
        history = self._get_session_history(session_id)
        messages = history.messages

        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})

        return result

    def clear(self):
        """清空记忆"""
        session_id = f"script_{self.script_id}"
        if session_id in self._session_histories:
            history = self._session_histories[session_id]
            if hasattr(history, 'clear'):
                history.clear()
            del self._session_histories[session_id]

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