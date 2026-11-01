"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: redis_chat_history.py
@Description: 基于 redis-py 的会话历史实现，替代已停止维护的 langchain_community 版本
@Author: NeoPen
@Time: 2026/10/29
"""
import json
from typing import List, Optional

import redis
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict

from penshot.logger import debug


class RedisChatMessageHistory(BaseChatMessageHistory):
    """使用 Redis 列表存储会话历史

    保留 langchain_community 版本的存储格式以便无缝读取历史数据：
    - Redis 列表，``lpush`` 写入（最新消息在列表头部）
    - 列表元素为 ``message_to_dict`` 的 JSON 字符串
    - 读取时反转列表，返回按时间先后排序的消息

    key 结构: ``{key_prefix}{session_id}``
    """

    def __init__(
        self,
        session_id: str,
        url: str = "redis://localhost:6379/0",
        key_prefix: str = "message_store:",
        ttl: Optional[int] = None,
    ):
        """
        初始化 Redis 会话历史

        Args:
            session_id: 会话ID，与 key_prefix 组合成 Redis key
            url: Redis 连接 URL
            key_prefix: Redis key 前缀，保持与历史数据一致
            ttl: 过期时间（秒），每次写入时刷新，None 表示不设置过期
        """
        self.session_id = session_id
        self.key_prefix = key_prefix
        self.ttl = ttl
        # 统一使用 bytes 读写，避免服务端 decode_responses 配置不一致导致解析失败
        self.redis_client = redis.from_url(
            url,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=False,
        )

    @property
    def key(self) -> str:
        """完整的 Redis key"""
        return f"{self.key_prefix}{self.session_id}"

    @property
    def messages(self) -> List[BaseMessage]:
        """按时间顺序返回历史消息"""
        items: List[dict] = []
        for raw in reversed(self.redis_client.lrange(self.key, 0, -1)):
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                items.append(json.loads(raw))
            except (TypeError, ValueError):
                # 单条损坏数据不应拖垮整个会话，仅跳过该条
                debug(f"跳过无法解析的会话历史记录: key={self.key}")
        return messages_from_dict(items)

    @messages.setter
    def messages(self, messages: List[BaseMessage]) -> None:
        raise NotImplementedError(
            "Direct assignment to 'messages' is not allowed."
            " Use the 'add_message' or 'add_messages' instead."
        )

    def add_message(self, message: BaseMessage) -> None:
        """追加一条消息到 Redis"""
        self.redis_client.lpush(self.key, json.dumps(message_to_dict(message), ensure_ascii=False))
        if self.ttl:
            self.redis_client.expire(self.key, self.ttl)

    def clear(self) -> None:
        """清空当前会话历史"""
        self.redis_client.delete(self.key)
