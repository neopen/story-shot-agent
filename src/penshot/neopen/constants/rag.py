"""RAG 与向量索引的公共默认参数。"""

# 提示词模板等长文本索引的默认分块参数
DEFAULT_CHUNK_SIZE = 1024
DEFAULT_CHUNK_OVERLAP = 20

# 剧本知识库沿用原有分块大小，避免改变既有检索行为
SCRIPT_KB_CHUNK_SIZE = 512

# 向量库 metadata 单字段最大长度
MAX_METADATA_LENGTH = 256

# 提示词模板文档的 metadata 类型标记
PROMPT_TEMPLATE_METADATA_TYPE = "prompt_template"

# 允许进入提示词模板向量库的索引字段白名单。
# 提示词原文只写入 Document.text，禁止重复写入 metadata。
PROMPT_TEMPLATE_METADATA_KEYS = frozenset(
    {
        "type",
        "hash",
        "script_id",
        "timestamp",
        "quality_score",
        "fragment_id",
        "scene",
        "style",
        "shot_type",
        "duration",
        "task_id",
        "source",
    }
)
