"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: config.py
@Description: 配置管理模块 - 严格遵循 env > yaml > default 优先级
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/01
"""
import json
import os
from typing import Any, Dict

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from penshot.config.config_loader import ConfigLoader
from penshot.config.config_models import (AppConfig, APIConfig, LLMConfig, EmbeddingConfig,
                                          PathsConfig, StoryboardConfig, LLMBaseConfig, EmbeddingBaseConfig, RetrieverConfig)
from penshot.logger import info, warning
from penshot.utils.dotenv_loader import DotEnvLoader
from penshot.utils.path_utils import PathResolver

# ==================== 路径配置 ====================
# 确定项目根目录
# ENV_FILE = Path.cwd() / ".env"
# 加载 .env 文件（如果存在）
# load_dotenv(ENV_FILE)
# debug(f".env 文件: {ENV_FILE}")

DotEnvLoader().load()


# ==================== 主配置类 ====================
class Settings(BaseSettings):
    """主配置 - 优先级: 环境变量 > YAML > 模型默认值"""

    # 基础配置
    app: AppConfig = Field(default_factory=AppConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    # AI 模型配置
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embed: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    # 检索器配置
    retriever: RetrieverConfig = Field(default_factory=RetrieverConfig)

    # 业务配置
    storyboard: StoryboardConfig = Field(default_factory=StoryboardConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    model_config = SettingsConfigDict(
        case_sensitive=False,  # 大小写不敏感
        env_file_encoding="utf-8",
        # env_file=str(ENV_FILE),  # 明确指定.env文件路径
        extra="ignore",
        env_prefix="PENSHOT_",  # 清除前缀
        env_ignore_empty=True,
        env_nested_delimiter="__",  # 使用双下划线表示嵌套
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
        """
        自定义配置源加载顺序: 优先级链: YAML(settings.yaml → {env}.yaml) → .env → 系统env → init
        1. YAML 配置（基础默认值）
        2. 环境变量（系统环境变量 + .env 文件，覆盖 YAML）
        3. 初始化参数（代码中传入的 kwargs，最高优先级）
        """
        return (
            ConfigLoader(settings_cls),  # 1. 最低优先级
            env_settings,  # 2. 中优先级
            init_settings,  # 3. 最高优先级
        )

    def get_app_config(self) -> AppConfig:
        """获取应用配置"""
        return self.app

    def get_llm_config(self, provider: str = "default") -> LLMBaseConfig:
        """获取LLM配置（安全返回，不暴露 SecretStr 原始值）"""
        return self.llm.fallback if provider == "fallback" else self.llm.default

    def get_embedding_config(self, provider: str = "default") -> EmbeddingBaseConfig:
        """获取嵌入模型配置"""
        return self.embed.fallback if provider == "fallback" else self.embed.default

    def get_config_summary(self) -> Dict[str, Any]:
        """获取当前配置摘要（用于日志/调试）"""
        return {
            "environment": self.app.environment,
            "language": self.app.language,
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "reload": self.api.reload,
            },
            "llm": {
                "default_model": self.llm.default.model_name,
                "fallback_model": self.llm.fallback.model_name if self.llm.fallback else None,
            },
            "embedding": {
                "default_model": self.embed.default.model_name,
                "fallback_model": self.embed.fallback.model_name if self.embed.fallback else None,
            },
            "storyboard": {
                "max_shots": self.storyboard.structure.max_shots,
                "default_style": self.storyboard.generation.default_style,
            },
        }

    def get_supported_styles(self) -> list:
        """
        获取支持的风格列表
        """
        return self.storyboard.generation.supported_styles

    def get_data_paths(self) -> Dict[str, str]:
        """
        获取数据路径配置
        """
        paths_config = self.paths
        app_root = PathResolver.get_project_root()

        # 确保路径是绝对路径
        data_paths = {}
        for key, path in paths_config.model_dump().items():
            if path and not os.path.isabs(path):
                data_paths[key] = os.path.join(app_root, path)
            else:
                data_paths[key] = path

        return data_paths

    def get_retriever_config(self) -> RetrieverConfig:
        return self.retriever


# ==================== 全局配置实例 ====================
settings = Settings()
# 服务启动时配置 HuggingFace 环境
app_config = settings.get_app_config()

# 1. 配置镜像端点（如果提供）
if app_config.hf_endpoint:
    os.environ["HF_ENDPOINT"] = app_config.hf_endpoint
    info(f"已设置 HuggingFace 镜像端点: {app_config.hf_endpoint}")

# 2. 配置 API Token（如果提供）
if app_config.hf_token:
    os.environ["HF_TOKEN"] = app_config.hf_token
    info("已设置 HuggingFace API Token")
else:
    # 没有 Token 时设置离线模式，避免警告和无意义的重试
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    warning("未设置 HF_TOKEN，已启用离线模式，将跳过模型下载")


# ==================== 调试辅助 ====================

if __name__ == "__main__":
    # 打印配置摘要（调试用）

    print("✅ 配置加载成功")
    print(f"🌍 环境: {settings.app.environment}")
    print(f"🌐 API: http://{settings.api.host}:{settings.api.port}{settings.api.docs_url}")
    print(f"🤖 LLM: {settings.llm.default.model_name}")
    print(f"🤖 LLM fallback: {settings.llm.fallback.model_name}")
    print(f"🧠 Embedding: {settings.embed.default.model_name}")
    print(f"🧠 Embedding fallback: {settings.embed.fallback.device}")
    # print("\n📋 完整配置摘要:")
    # print(json.dumps(settings.get_config_summary(), indent=2, ensure_ascii=False))

    print("\n🔍 检索器配置:")
    retriever_config = settings.get_retriever_config()
    print(json.dumps(retriever_config.model_dump(), indent=2, ensure_ascii=False))
