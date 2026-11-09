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

# 提示词模板召回参数（0.4.4 实测校准）
# 依据：116 条迁移前基线上 11 条锚点查询的 top-1 分数
# min=0.7794 / P50=0.8127 / max=0.8410，阈值 = max(0.45, floor(P50*20)/20) = 0.80
PROMPT_TEMPLATE_MIN_SIMILARITY = 0.80
PROMPT_TEMPLATE_RECALL_TOP_K = 2
PROMPT_TEMPLATE_RECALL_MAX_INJECTED = 6

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
