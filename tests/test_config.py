"""
@FileName: test_config.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/31 22:03
"""
import os

"""
@FileName: config.py
@Description: 配置管理模块 - 严格遵循 env > yaml > default 优先级
@Author: HiPeng
@Time: 2026/01
"""
from pathlib import Path
from typing import Optional, Any

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# ==================== 路径配置 ====================
# 确定项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = Path.cwd() / ".env"

print(f"项目根目录: {PROJECT_ROOT}")
print(f".env 文件: {ENV_FILE}")


class LLMProviderConfig(BaseModel):
    """LLM提供商配置"""
    base_url: str = Field(default="https://api.openai.com/v1")
    api_key: SecretStr = Field(default=SecretStr(""))
    model_name: str = Field(default="gpt-4o")
    timeout: int = Field(default=60, ge=1)
    response_format: str = Field(default="json_object")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, ge=1)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: int = Field(default=1, ge=0, le=60)

    @field_validator("base_url", "model_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        """API密钥验证"""
        if isinstance(v, str) and v.startswith("$"):
            env_var = v[2:-1] if v.startswith("${") else v[1:]
            return os.getenv(env_var, "")
        return v


class EmbeddingProviderConfig(BaseModel):
    """嵌入模型提供商配置"""
    base_url: str = Field(default="https://api.openai.com/v1")
    api_key: SecretStr = Field(default=SecretStr(""))
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
        """API密钥验证"""
        if isinstance(v, str) and v.startswith("$"):
            env_var = v[2:-1] if v.startswith("${") else v[1:]
            return os.getenv(env_var, "")
        return v


class LLMConfig(BaseModel):
    """LLM主配置"""
    default: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    fallback: Optional[LLMProviderConfig] = Field(default_factory=LLMProviderConfig)


class EmbeddingConfig(BaseModel):
    """嵌入模型主配置"""
    default: EmbeddingProviderConfig = Field(default_factory=EmbeddingProviderConfig)
    fallback: EmbeddingProviderConfig = Field(default_factory=EmbeddingProviderConfig)


# ====== 2. 自定义环境变量源：智能转换键名 ======
# class SmartEnvSettingsSource(PydanticBaseSettingsSource):
#     def __init__(self, settings_cls: type[BaseSettings], env_file: str):
#         super().__init__(settings_cls)
#         self.env_file = env_file
#
#     def _convert_key(self, key: str) -> str:
#         """将 LLM_DEFAULT_BASE_URL → LLM__DEFAULT__BASE_URL（仅转换前两个下划线）"""
#         if key.startswith(("LLM_", "EMBED_")):
#             parts = key.split("_", 2)  # 只分割前两次：['LLM', 'DEFAULT', 'BASE_URL']
#             if len(parts) == 3:
#                 return f"{parts[0]}__{parts[1]}__{parts[2]}"
#         return key
#
#     def get_field_value(self, field: Any, field_name: str) -> Tuple[Any, str, bool]:
#         return None, "", False  # 不实现此方法，由 __call__ 返回完整字典
#
#     def __call__(self) -> Dict[str, Any]:
#         # 1. 读取 .env 文件
#         dotenv_vars = dotenv_values(self.env_file) if os.path.exists(self.env_file) else {}
#         # 2. 读取系统环境变量（覆盖 .env）
#         env_vars = os.environ.copy()
#         merged = {**dotenv_vars, **env_vars}
#         # 3. 转换键名
#         return {self._convert_key(k): v for k, v in merged.items() if v is not None}


# ==================== 主配置类 ====================
class Settings(BaseSettings):
    """主配置 - 优先级: 环境变量 > YAML > 模型默认值"""
    # AI 模型配置
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embed: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    model_config = SettingsConfigDict(
        case_sensitive=False,  # 设置大小写不敏感
        env_file_encoding="utf-8",
        env_file=ENV_FILE,  # 明确指定路径
        extra="ignore",
        env_prefix="",  # 清除前缀
        env_ignore_empty=True,
        env_nested_delimiter="__",  # 支持 LLM_DEFAULT_BASE_URL → llm.default.base_url
    )

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 标准化：将所有环境变量名转为大写
        return (
            dotenv_settings,  # .env 文件
            env_settings,  # 系统环境变量（覆盖 .env）
            init_settings,  # 代码传参（最高优先级）
            file_secret_settings,
        )


settings = Settings()


def test_print_config():
    """测试打印配置"""

    # 直接访问配置
    # print(f"应用名称: {settings.app.name}")
    # print(f"环境: {settings.app.environment}")
    # print(f"语言: {settings.app.language}")
    # print(f"API地址: {settings.api.host}:{settings.api.port}")
    # print(f"调试模式: {settings.app.debug}")

    print(f"\nLLM配置:")
    print(f"  模型: {settings.llm.default.model_name}")
    print(f"  Base URL: {settings.llm.default.base_url}")
    print(f"  备用模型: {settings.llm.fallback.model_name}")
    print(f"  API Key: {'已设置' if settings.llm.default.api_key else '未设置'}")

    print(f"\n嵌入模型配置:")
    print(f"  模型: {settings.embed.default.model_name}")
    print(f"  设备: {settings.embed.default.device}")
    print(f"  维度: {settings.embed.default.dimensions}")
    #
    # print(f"\n故事板配置:")
    # print(f"  默认镜头时长: {settings.storyboard.default_duration_per_shot}秒")
    # print(f"  支持的风格: {', '.join(settings.storyboard.supported_styles)}")
    #
    # print(f"\n路径配置:")
    # print(f"  数据输入: {settings.paths.data_input}")
    # print(f"  数据输出: {settings.paths.data_output}")
