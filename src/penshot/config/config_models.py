"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: config_models.py
@Description: 
@Author: NeoPen
@Time: 2026/3/31 12:46
"""
import os
import random
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator

from penshot.neopen.agent.base_models import VideoStyle

_ALLOW_ENV_EXPANSION: ContextVar[bool] = ContextVar("_ALLOW_ENV_EXPANSION", default=False)


@contextmanager
def trusted_env_expansion() -> Iterator[None]:
    """仅在加载受信任的本地配置（settings.yaml / .env）时允许展开环境变量引用。"""
    token = _ALLOW_ENV_EXPANSION.set(True)
    try:
        yield
    finally:
        _ALLOW_ENV_EXPANSION.reset(token)


def _resolve_api_key_value(v: Any) -> Any:
    """校验并按信任上下文解析 API 密钥，拒绝在非受信请求负载中展开宿主机环境变量。"""
    if isinstance(v, str) and v.strip().startswith("$"):
        raw = v.strip()
        if not _ALLOW_ENV_EXPANSION.get():
            raise ValueError(
                "Environment variable expansion in api_key is only allowed in trusted local configuration"
            )
        if raw.startswith("${") and raw.endswith("}"):
            inner = raw[2:-1]
            env_var, _, default_val = inner.partition(":")
            return os.getenv(env_var.strip(), default_val)
        env_var = raw[1:]
        return os.getenv(env_var, "")
    return v


class LLMBaseConfig(BaseModel):
    """LLM提供商配置"""
    base_url: str = Field(default="")  # https://api.openai.com/v1
    api_key: Optional[SecretStr] = Field(default=SecretStr(""))
    model_name: str = Field(default="") # gpt-4o
    timeout: int = Field(default=60, ge=1)
    seed: int = Field(default=random.randint(1000000, 99999999999), ge=1)
    response_format: str = Field(default="json_object")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, ge=1)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: int = Field(default=1, ge=0, le=60)
    # 思考模式开关（Qwen3 等支持该参数的模型有效）；默认关闭，避免思考内容占满 max_tokens 导致 JSON 被截断
    enable_thinking: Optional[bool] = Field(default=False)

    @field_validator("base_url", "model_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        """API密钥验证（仅在受信本地配置加载时允许 ${ENV_VAR} 引用）"""
        return _resolve_api_key_value(v)


class ImageBaseConfig(BaseModel):
    """文生图提供商配置（M0.4.2：仅生成静态资产，不做视频生成）"""

    provider: str = Field(default="flux", description="文生图供应商：flux/openai")
    base_url: str = Field(default="", description="OpenAI 兼容的图片生成接口地址")
    api_key: Optional[SecretStr] = Field(default=SecretStr(""))
    model_name: str = Field(default="flux-1.1-pro")
    size: str = Field(default="1024x1024", description="输出尺寸，如 1024x1024")
    timeout: int = Field(default=120, ge=1)
    max_retries: int = Field(default=2, ge=0, le=10)
    output_dir: str = Field(default="", description="资产落盘目录；为空时使用 data_output/assets")
    enabled: bool = Field(default=False, description="是否启用真实文生图调用")

    @field_validator("provider", "base_url", "model_name", "size", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        """API密钥验证（仅在受信本地配置加载时允许 ${ENV_VAR} 引用）"""
        return _resolve_api_key_value(v)


class ImageConfig(BaseModel):
    """文生图主配置（default + fallback）"""

    default: ImageBaseConfig = Field(default_factory=ImageBaseConfig)
    fallback: Optional[ImageBaseConfig] = Field(default=None)


class EmbeddingBaseConfig(BaseModel):
    """嵌入模型提供商配置"""
    base_url: str = Field(default="")  # https://api.openai.com/v1
    api_key: Optional[SecretStr] = Field(default=SecretStr(""))
    model_name: str = Field(default="text-embedding-3-small")
    device: str = Field(default="gpu")
    normalize_embeddings: bool = Field(default=True)
    dimensions: int = Field(default=1536, ge=1)
    timeout: int = Field(default=60, ge=1)
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("base_url", "model_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        """API密钥验证（仅在受信本地配置加载时允许 ${ENV_VAR} 引用）"""
        return _resolve_api_key_value(v)


class LLMConfig(BaseModel):
    """LLM主配置"""
    default: LLMBaseConfig = Field(default_factory=LLMBaseConfig)
    fallback: Optional[LLMBaseConfig] = Field(default_factory=LLMBaseConfig)


class EmbeddingConfig(BaseModel):
    """嵌入模型主配置"""
    default: EmbeddingBaseConfig = Field(default_factory=EmbeddingBaseConfig)
    fallback: Optional[EmbeddingBaseConfig] = Field(default_factory=EmbeddingBaseConfig)


class RetrieverConfig(BaseModel):
    """检索器配置类"""
    rerank_enabled: bool = Field(default=False)
    rerank_model_name: str = Field(default="BAAI/bge-reranker-large")
    rerank_model_local_path: str = Field(default="data/models")
    search_type: str = Field(default="similarity")
    similarity_top_k: int = Field(default=5)


class APIConfig(BaseModel):
    """API配置"""
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=5000, le=65535)
    workers: int = Field(default=1, ge=1, le=10)
    reload: bool = Field(default=False)  # 调试模式下启用热重载
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
        ]
    )
    api_prefix: str = Field(default="/api")
    docs_url: str = Field(default="/docs")


class AppConfig(BaseModel):
    """应用配置"""
    name: str = Field(default="Script-to-Shot AI Agent")
    version: str = Field(default="1.0.0")
    description: str = Field(default="脚本转分镜AI助手")
    environment: Literal["development", "production"] = Field(default="development")
    language: Literal["zh", "en"] = Field(default="zh")
    hf_endpoint: str = Field(default="https://hf-mirror.com")
    hf_token: Optional[str] = Field(default=None)


class StoryboardGenerationConfig(BaseModel):
    """分镜生成配置"""
    default_duration_per_shot: int = Field(default=5, ge=1)
    max_duration_deviation: float = Field(default=0.5, ge=0.0)
    max_retries: int = Field(default=2, ge=0)
    default_style: VideoStyle = Field(default=VideoStyle.REALISTIC)
    supported_styles: List[str] = Field(
        default_factory=lambda: [
            "realistic", "anime", "cinematic", "cartoon", "fantasy", "sci-fi", "documentary"
        ]
    )


class StoryboardStructureConfig(BaseModel):
    """分镜结构配置"""
    min_shots: int = Field(default=1, ge=1)
    max_shots: int = Field(default=50, ge=1)
    default_scenes_per_shot: int = Field(default=5, ge=1)
    enable_transitions: bool = Field(default=True)
    include_dialogue: bool = Field(default=True)
    include_camera_angles: bool = Field(default=True)


class StoryboardOutputConfig(BaseModel):
    """分镜输出配置"""
    format: Literal["json", "yaml", "xml"] = Field(default="json")
    include_timestamps: bool = Field(default=True)
    include_visual_descriptions: bool = Field(default=True)
    include_character_list: bool = Field(default=True)
    include_location_list: bool = Field(default=True)
    include_shot_duration: bool = Field(default=True)


class StoryboardConfig(BaseModel):
    """完整分镜配置"""
    generation: StoryboardGenerationConfig = Field(default_factory=StoryboardGenerationConfig)
    structure: StoryboardStructureConfig = Field(default_factory=StoryboardStructureConfig)
    output: StoryboardOutputConfig = Field(default_factory=StoryboardOutputConfig)


class DataPathsConfig(BaseModel):
    """数据目录配置（对应 settings.yaml 的 paths.data）"""
    input: str = Field(default="./data/input")
    output: str = Field(default="./data/output")
    memory: str = Field(default="./data/memory")
    embedding: str = Field(default="./data/embedding")
    template: str = Field(default="./data/template")
    model: str = Field(default="./data/models")
    checkpoint: str = Field(default="./data/checkpoints")
    cache: str = Field(default="./data/cache")


class LogPathsConfig(BaseModel):
    """日志目录配置（对应 settings.yaml 的 paths.logs）"""
    base: str = Field(default="./logs")
    app: str = Field(default="./logs/app")
    api: str = Field(default="./logs/api")
    errors: str = Field(default="./logs/errors")


class TempPathsConfig(BaseModel):
    """临时目录配置（对应 settings.yaml 的 paths.temp）"""
    base: str = Field(default="./tmp")
    uploads: str = Field(default="./tmp/uploads")
    processed: str = Field(default="./tmp/processed")


class PathsConfig(BaseModel):
    """路径配置（嵌套结构与 settings.yaml 对齐）"""
    data: DataPathsConfig = Field(default_factory=DataPathsConfig)
    logs: LogPathsConfig = Field(default_factory=LogPathsConfig)
    temp: TempPathsConfig = Field(default_factory=TempPathsConfig)
