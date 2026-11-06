"""向量库元数据清洗策略。

采用可注入的策略对象统一处理字段白名单、默认值和长文本截断，
避免各知识库重复实现清洗逻辑。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping

from penshot.neopen.constants.rag import (
    MAX_METADATA_LENGTH,
    PROMPT_TEMPLATE_METADATA_KEYS,
    PROMPT_TEMPLATE_METADATA_TYPE,
)


@dataclass(frozen=True)
class MetadataPolicy:
    """向量库 metadata 清洗策略

    Attributes:
        allowed_keys: 允许写入 metadata 的字段集合
        max_length: 单个字符串字段的最大长度
        default_fields: 默认兜底字段，调用方可覆盖
        immutable_keys: 强制字段，调用方不可覆盖
    """

    allowed_keys: FrozenSet[str]
    max_length: int = MAX_METADATA_LENGTH
    default_fields: Mapping[str, Any] = field(default_factory=dict)
    immutable_keys: FrozenSet[str] = frozenset()

    def sanitize(self, metadata: Mapping[str, Any]) -> Dict[str, Any]:
        """返回可直接写入向量库的 metadata"""
        result: Dict[str, Any] = dict(self.default_fields)

        for key, value in metadata.items():
            if key not in self.allowed_keys or key in self.immutable_keys:
                continue
            if isinstance(value, str) and len(value) > self.max_length:
                value = value[: self.max_length - 3] + "..."
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value

        return result


PROMPT_TEMPLATE_METADATA_POLICY = MetadataPolicy(
    allowed_keys=PROMPT_TEMPLATE_METADATA_KEYS,
    default_fields={
        "type": PROMPT_TEMPLATE_METADATA_TYPE,
        "quality_score": 0,
        "fragment_id": "",
        "scene": "",
        "style": "",
        "shot_type": "",
        "duration": 0,
    },
    immutable_keys=frozenset({"type"}),
)
