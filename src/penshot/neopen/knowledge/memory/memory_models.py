"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: memory_models.py
@Description: 记忆系统配置模型
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/4/1
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from langchain_core.embeddings import Embeddings

from penshot.logger import debug, warning
from penshot.utils.redis_utils import get_redis_url


class MemoryLevel(str, Enum):
    """记忆级别"""
    EPHEMERAL = "ephemeral"  # 瞬时记忆（当前会话）
    SHORT_TERM = "short_term"  # 短期记忆（滑动窗口）
    MEDIUM_TERM = "medium_term"  # 中期记忆（摘要压缩）
    LONG_TERM = "long_term"  # 长期记忆（向量检索）


@dataclass
class MemoryConfig:
    """记忆配置"""
    term_persist_path: Optional[str] = "data/memory/"  # 文件持久化路径

    # 短期记忆配置（可使用Redis）
    short_term_size: int = 20
    short_term_ttl: int = 3600  # 秒
    short_term_redis_url: Optional[str] = get_redis_url()  # Redis URL（可选）

    # 中期记忆配置（文件持久化）
    medium_term_max_tokens: int = 500
    medium_term_summary_prompt: Optional[str] = None

    # 长期记忆配置（向量数据库）
    long_term_enabled: bool = True
    long_term_k: int = 3
    long_term_score_threshold: float = 0.7

    # 嵌入模型配置
    embeddings: Embeddings = None

    def __post_init__(self):
        """未显式提供嵌入模型时复用统一嵌入工厂，避免再初始化一套无关的模型"""
        if not self.embeddings:
            try:
                # LangChain 1.x 已移除 langchain.embeddings，改为复用项目统一嵌入工厂
                from penshot.neopen.client.client_factory import get_default_embedding

                self.embeddings = get_default_embedding()
            except Exception as e:
                warning(f"默认嵌入模型初始化失败: {e}")

        if not self.embeddings:
            debug("未提供嵌入模型，长期记忆的向量检索能力将不可用")
