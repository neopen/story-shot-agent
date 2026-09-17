"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_memory.py
@Description: 
@Author: NeoPen
@Time: 2026/4/1 14:15
"""
from langchain.chat_models import ChatOpenAI

from penshot.neopen.knowledge.memory.medium_term_memory import MediumTermMemory
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig

# 配置
config = MemoryConfig(
    # 短期记忆：使用Redis（可选）
    short_term_size=10,
    short_term_ttl=3600,
    short_term_redis_url="redis://localhost:6379",  # 可选

    # 中期记忆：文件持久化
    medium_term_max_tokens=500,

    # 长期记忆：向量数据库
    long_term_enabled=True,
)

# 初始化LLM
llm = ChatOpenAI(model="gpt-4")

# 中期记忆（自动持久化到文件）
medium_memory = MediumTermMemory(llm, config, script_id="script_001")
medium_memory.add("剧本解析", "场景1: 城市夜景...", metadata={"keep_full": True})
medium_memory.add("分镜生成", "镜头1: 广角...")

# 获取摘要
summary = medium_memory.get_summary()
print(f"摘要: {summary}")

# 重启后自动加载
medium_memory2 = MediumTermMemory(llm, config, script_id="script_001")
print(f"重启后摘要: {medium_memory2.get_summary()}")  # 自动加载

# 导出摘要
export = medium_memory.export_summary()
print(f"导出: {export}")
