---
kind: configuration_system
name: 配置系统：基于 Pydantic Settings 的多源分层加载机制
category: configuration_system
scope:
    - '**'
source_files:
    - src/penshot/config/config.py
    - src/penshot/config/config_loader.py
    - src/penshot/config/config_models.py
    - src/penshot/config/settings.yaml
    - src/penshot/config/env/development.yaml
    - src/penshot/config/env/production.yaml
    - src/penshot/utils/dotenv_loader.py
---

## 系统概述
PenShot 采用 **Pydantic Settings + YAML + .env + 环境变量** 的多源分层配置系统，通过自定义 `ConfigLoader` 实现严格的优先级链：**YAML（基础默认值）→ 环境变量（.env + 系统环境）→ 运行时参数（代码传入）**。

## 核心架构

### 1. 配置模型层 (`config_models.py`)
- 使用 Pydantic BaseModel 定义强类型配置结构
- 支持嵌套配置：`AppConfig`, `APIConfig`, `LLMConfig`, `EmbeddingConfig`, `StoryboardConfig`, `PathsConfig`
- 内置字段验证器：自动去除空白、处理 `${ENV_VAR}` 格式的环境变量引用
- SecretStr 类型保护敏感信息（如 API Key）

### 2. 配置加载器 (`config_loader.py`)
- 继承 `PydanticBaseSettingsSource`，实现自定义配置源
- 支持嵌套字段访问：`llm.default.base_url` → `config['llm']['default']['base_url']`
- 深度合并策略：YAML 与配置文件按层级递归合并
- 智能类型转换：自动识别布尔值、整数、浮点数

### 3. 主设置类 (`config.py`)
- `Settings` 类聚合所有配置模块，提供统一访问接口
- 自定义 `settings_customise_sources` 方法控制加载顺序
- 全局单例 `settings = Settings()` 供全应用共享
- 启动时自动配置 HuggingFace 相关环境变量

### 4. 环境变量管理 (`dotenv_loader.py`)
- 智能 `.env` 文件查找：当前目录 → 父级目录 → 用户配置目录 → 包安装目录 → 开发模式项目根
- 支持多文件叠加加载，后加载的覆盖先加载的
- 跨平台用户配置目录支持（Windows/Mac/Linux）

## 配置文件层次

### 基础配置 (`settings.yaml`)
- 包含所有配置的默认值
- 完整的 LLM、嵌入模型、分镜生成、路径等配置项
- 作为最终降级方案存在

### 环境特定配置 (`env/{environment}.yaml`)
- `development.yaml`: 开发环境优化配置
- `production.yaml`: 生产环境安全配置，大量使用 `${VAR:default}` 语法
- 通过 `ENVIRONMENT` 环境变量选择加载

### 环境变量规范
- 前缀：`PENSHOT_`（可通过 `model_config.env_prefix` 配置）
- 嵌套分隔符：双下划线 `__`（如 `PENSHOT_LLM__DEFAULT__BASE_URL`）
- 大小写不敏感：`case_sensitive=False`

## 关键设计决策

1. **严格优先级链**：确保运行时参数 > 环境变量 > YAML 默认值的覆盖关系
2. **类型安全**：所有配置项都有明确的类型定义和验证规则
3. **环境隔离**：通过环境特定配置文件实现不同部署环境的差异化配置
4. **敏感信息保护**：使用 `SecretStr` 类型避免密钥泄露
5. **向后兼容**：支持传统环境变量格式（无前缀）和环境变量引用语法

## 开发者约定

- 新增配置项需在 `config_models.py` 中定义对应的 Pydantic 模型
- 在 `settings.yaml` 中添加默认值，在 `env/production.yaml` 中使用环境变量引用
- 使用 `PENSHOT_` 前缀命名环境变量，嵌套字段用 `__` 分隔
- 敏感配置使用 `SecretStr` 类型，避免直接暴露原始值
- 通过 `settings.get_*_config()` 方法获取配置，而非直接访问属性