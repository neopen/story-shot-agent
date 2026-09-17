"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: short_term_memory.py
@Description: 短期记忆 - 基于LangChain的缓冲记忆，支持剧本ID数据隔离
@Author: NeoPen
@Time: 2026/4/1
"""
import json
from collections import deque
from pathlib import Path
from typing import Optional, Any, Dict, List

from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from penshot.logger import debug, warning, info, error
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig


class ShortTermMemory:
    """
    短期记忆 - 基于LangChain的缓冲记忆

    数据隔离策略：
    - 每个剧本有独立的 session_id
    - Redis key 格式: penshot:memory:{script_id}:{session_type}
    - 内存缓冲区也按剧本隔离
    """

    def __init__(self, config: MemoryConfig, script_id: str):
        """
        初始化短期记忆

        Args:
            config: 记忆配置
            script_id: 剧本ID，用于数据隔离
        """
        self.config = config
        self.script_id = script_id
        self.max_size = config.short_term_size

        # 为当前剧本生成唯一的 session_id
        self._session_id = self._generate_session_id(script_id)

        # 会话历史存储（每个剧本独立）
        self._session_histories: Dict[str, BaseChatMessageHistory] = {}

        # 手动维护滑动窗口（内存缓冲区）
        self._message_buffer = deque(maxlen=config.short_term_size)

        # Redis 可用性标志
        self._redis_available = False
        self._check_redis_availability()

        # 创建带记忆的链
        self.memory = self._create_memory_chain()

        # 文件持久化路径（Redis 不可用时使用）
        self._persist_path = None
        if not self._redis_available and config.term_persist_path:
            self._persist_path = Path(config.term_persist_path) / script_id / "short_term.json"
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_file()

        info(f"初始化短期记忆: script={script_id}, session_id={self._session_id}, "
             f"size={config.short_term_size}, redis_enabled={self._redis_available}")

    def _generate_session_id(self, script_id: str) -> str:
        """
        生成稳定的 session_id

        Args:
            script_id: 剧本ID

        Returns:
            稳定的会话ID
        """
        # 使用剧本ID的哈希确保一致性
        # script_hash = hashlib.md5(script_id.encode('utf-8')).hexdigest()[:16]
        script_hash = script_id[2:]
        return f"short_term_{script_hash}"

    def _check_redis_availability(self) -> None:
        """检查 Redis 是否可用"""
        if not self.config.short_term_redis_url:
            info("Redis URL 未配置，使用内存存储")
            self._redis_available = False
            return

        try:
            import redis
            # 尝试连接测试
            client = redis.from_url(self.config.short_term_redis_url, socket_connect_timeout=3)
            client.ping()
            client.close()
            self._redis_available = True
            info(f"Redis 连接成功: {self.config.short_term_redis_url}")
        except Exception as e:
            warning(f"Redis 连接失败: {e}，将使用内存存储")
            self._redis_available = False

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """
        获取或创建会话历史

        Args:
            session_id: 会话ID

        Returns:
            会话历史实例
        """
        # 确保使用正确的 session_id
        if session_id not in self._session_histories:
            try:
                if self._redis_available and self.config.short_term_redis_url:
                    # Redis key 格式: penshot:memory:{session_id}
                    redis_key = f"penshot:memory:{session_id}"
                    self._session_histories[session_id] = RedisChatMessageHistory(
                        session_id=redis_key,
                        url=self.config.short_term_redis_url,
                        ttl=self.config.short_term_ttl
                    )
                    debug(f"创建 Redis 会话历史: key={redis_key}, ttl={self.config.short_term_ttl}")
                else:
                    # 使用内存存储
                    self._session_histories[session_id] = InMemoryChatMessageHistory()
                    debug("创建内存会话历史")
            except Exception as e:
                warning(f"创建会话历史失败: {e}，使用内存存储")
                self._session_histories[session_id] = InMemoryChatMessageHistory()

        return self._session_histories[session_id]

    def _create_memory_chain(self):
        """创建带记忆的链"""
        def add_to_memory(input_dict):
            input_text = input_dict.get("input", "")
            output_text = input_dict.get("output", "")
            metadata = input_dict.get("metadata", {})

            if input_text and output_text:
                # 使用固定的 session_id
                history = self._get_session_history(self._session_id)

                try:
                    history.add_user_message(input_text)
                    history.add_ai_message(output_text)

                    # 添加到内存缓冲区
                    self._message_buffer.append({
                        "input": input_text,
                        "output": output_text,
                        "metadata": metadata,
                        "timestamp": None
                    })

                    debug(f"添加记忆: input={input_text[:50]}..., output={output_text[:50]}...")

                except Exception as e:
                    error(f"添加记忆失败: {e}")

            return {"status": "added", "session_id": self._session_id}

        return RunnableLambda(add_to_memory)

    def add(self, input_text: str, output_text: str, metadata: Optional[Dict] = None) -> None:
        """
        添加交互记忆

        Args:
            input_text: 输入文本
            output_text: 输出文本
            metadata: 元数据
        """
        debug(f"短期记忆添加: script={self.script_id}, input={input_text[:50]}...")

        self.memory.invoke({
            "input": input_text,
            "output": output_text,
            "metadata": metadata or {},
            "session_id": self._session_id
        })
        debug(f"短期记忆当前大小: {len(self._message_buffer)}")

        self._save_to_file()  # 添加持久化

    def get_recent(self, n: int = None) -> List[Dict]:
        """
        获取最近的N条记忆

        Args:
            n: 返回数量，默认使用 max_size

        Returns:
            记忆列表
        """
        if n is None:
            n = self.max_size

        # 优先从内存缓冲区获取（更快）
        recent = list(self._message_buffer)[-n:]

        # 如果内存缓冲区为空但有 Redis 数据，尝试从 Redis 加载
        if not recent and self._redis_available:
            recent = self._load_from_redis(n)

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

    def _load_from_redis(self, n: int) -> List[Dict]:
        """
        从 Redis 加载最近的记忆

        Args:
            n: 返回数量

        Returns:
            记忆列表
        """
        try:
            history = self._get_session_history(self._session_id)
            messages = history.messages

            result = []
            # 将消息配对为 input/output
            for i in range(0, len(messages) - 1, 2):
                user_msg = messages[i] if i < len(messages) else None
                ai_msg = messages[i + 1] if i + 1 < len(messages) else None

                if user_msg and isinstance(user_msg, HumanMessage):
                    result.append({
                        "input": user_msg.content,
                        "output": ai_msg.content if ai_msg and isinstance(ai_msg, AIMessage) else "",
                        "metadata": {},
                        "timestamp": None
                    })

            # 返回最近的 n 条
            return result[-n:] if result else []

        except Exception as e:
            warning(f"从 Redis 加载记忆失败: {e}")
            return []

    def get_all_messages(self) -> List[Dict]:
        """
        获取所有消息

        Returns:
            消息列表
        """
        try:
            history = self._get_session_history(self._session_id)
            messages = history.messages

            result = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    result.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    result.append({"role": "assistant", "content": msg.content})

            return result
        except Exception as e:
            warning(f"获取所有消息失败: {e}")
            return []

    def clear(self) -> None:
        """清空当前剧本的记忆"""
        try:
            if self._session_id in self._session_histories:
                history = self._session_histories[self._session_id]
                if hasattr(history, 'clear'):
                    history.clear()
                del self._session_histories[self._session_id]

            self._message_buffer.clear()
            info(f"清空短期记忆: script={self.script_id}, session_id={self._session_id}")

        except Exception as e:
            warning(f"清空记忆失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息 - 修复版"""
        # 确保从正确的来源获取计数
        buffer_count = len(self._message_buffer)

        # 如果缓冲区为空但 Redis 可能有数据，尝试从 Redis 加载
        if buffer_count == 0 and self._redis_available:
            try:
                history = self._get_session_history(self._session_id)
                messages = history.messages
                redis_count = len([m for m in messages if isinstance(m, HumanMessage)])
                buffer_count = redis_count
            except Exception as e:
                debug(f"从 Redis 获取计数失败: {e}")

        return {
            "type": "short_term",
            "script_id": self.script_id,
            "session_id": self._session_id,
            "message_count": buffer_count,  # 确保正确返回
            "max_size": self.max_size,
            "ttl": self.config.short_term_ttl,
            "redis_enabled": self._redis_available,
            "redis_url": self.config.short_term_redis_url if self._redis_available else None
        }

    def get_redis_keys(self) -> List[str]:
        """
        获取 Redis 中的相关 keys（用于调试）

        Returns:
            Redis key 列表
        """
        if not self._redis_available:
            return []

        try:
            import redis
            client = redis.from_url(self.config.short_term_redis_url)
            pattern = f"penshot:memory:{self._session_id}*"
            keys = client.keys(pattern)
            client.close()
            return [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
        except Exception as e:
            warning(f"获取 Redis keys 失败: {e}")
            return []

    def _save_to_file(self) -> None:
        """保存到文件"""
        if not self._persist_path:
            return

        try:
            data = list(self._message_buffer)
            with open(self._persist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            warning(f"保存短期记忆到文件失败: {e}")

    def _load_from_file(self) -> None:
        """从文件加载"""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._message_buffer.extend(data)
            info(f"从文件加载短期记忆: {len(data)} 条")
        except Exception as e:
            warning(f"加载短期记忆文件失败: {e}")
