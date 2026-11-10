"""PenShot 领域常量统一出口。

按领域拆分模块，避免出现单一“万能常量文件”：
- ``schema``：跨节点契约版本
- ``rag``：检索与向量索引默认参数
- ``character``：角色相关词表（如非角色占位词）
- ``appearance``：角色外观词表（按语言分组）
"""

from penshot.neopen.constants.appearance import (
    ACCESSORY_KEYWORDS,
    ACCESSORY_ONLY_KEYWORDS,
    BODY_KEYWORDS,
    EXCLUDE_KEYWORDS,
    FACE_KEYWORDS,
    GARMENT_NOUNS,
    HAIR_KEYWORDS,
    STATE_KEYWORDS,
)
from penshot.neopen.constants.character import (
    NON_CHARACTER_NAMES,
    NON_CHARACTER_NAMES_EN,
    NON_CHARACTER_NAMES_ZH,
)
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
    "ACCESSORY_KEYWORDS",
    "ACCESSORY_ONLY_KEYWORDS",
    "BODY_KEYWORDS",
    "CONTRACT_SCHEMA_VERSION",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "EXCLUDE_KEYWORDS",
    "FACE_KEYWORDS",
    "GARMENT_NOUNS",
    "HAIR_KEYWORDS",
    "MAX_METADATA_LENGTH",
    "NON_CHARACTER_NAMES",
    "NON_CHARACTER_NAMES_EN",
    "NON_CHARACTER_NAMES_ZH",
    "PROMPT_TEMPLATE_METADATA_KEYS",
    "PROMPT_TEMPLATE_METADATA_TYPE",
    "SCRIPT_KB_CHUNK_SIZE",
    "STATE_KEYWORDS",
]
