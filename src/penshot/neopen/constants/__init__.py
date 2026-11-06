"""PenShot 领域常量统一出口。

按领域拆分模块，避免出现单一“万能常量文件”：
- ``schema``：跨节点契约版本
- ``rag``：检索与向量索引默认参数
"""

from penshot.neopen.constants.rag import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MAX_METADATA_LENGTH,
    PROMPT_TEMPLATE_METADATA_KEYS,
    PROMPT_TEMPLATE_METADATA_TYPE,
    SCRIPT_KB_CHUNK_SIZE,
)
from penshot.neopen.constants.schema import CONTRACT_SCHEMA_VERSION

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "MAX_METADATA_LENGTH",
    "PROMPT_TEMPLATE_METADATA_KEYS",
    "PROMPT_TEMPLATE_METADATA_TYPE",
    "SCRIPT_KB_CHUNK_SIZE",
]
