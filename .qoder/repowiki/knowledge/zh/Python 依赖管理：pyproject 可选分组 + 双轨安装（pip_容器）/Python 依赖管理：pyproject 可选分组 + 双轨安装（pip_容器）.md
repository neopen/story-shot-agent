---
kind: dependency_management
name: Python 依赖管理：pyproject 可选分组 + 双轨安装（pip/容器）
category: dependency_management
scope:
    - '**'
source_files:
    - pyproject.toml
    - src/penshot/app/setup_env.py
    - scripts/entrypoint.py
    - Dockerfile
    - docker-compose.yml
    - scripts/download_reranker.py
---

## 1. 使用的系统与方法
- **包清单与构建**：使用 `pyproject.toml`（setuptools 后端）声明项目元数据、核心依赖与可选依赖分组，版本通过 `penshot.__version__` 动态读取。
- **虚拟环境**：提供 `src/penshot/app/setup_env.py`，在本地首次启动时自动检测 Python、创建 `.venv`、校验并安装依赖，再启动应用；Docker 场景则由 `scripts/entrypoint.py` 负责。
- **容器化依赖**：`Dockerfile` 通过 `COPY requirements.txt && pip install -r requirements.txt` 安装运行时依赖，`docker-compose.yml` 仅做服务编排，不引入额外依赖管理工具。
- **第三方模型下载**：`scripts/download_reranker.py` 通过 `sentence-transformers` / `modelscope` 按需拉取 BAAI/bge-reranker-large 模型，属于“运行时资源”而非 Python 包依赖。

## 2. 关键文件与位置
- `pyproject.toml`：唯一权威依赖源，定义 core、dev、test、video、docs、api、async_db、llm-providers、full、all、default 等分组。
- `src/penshot/app/setup_env.py`：本地开发一键初始化脚本（venv + pip install -r requirements.txt）。
- `scripts/entrypoint.py`：容器入口，支持 `install-deps` / `check-deps` / `start` 子命令。
- `Dockerfile` / `docker-compose.yml`：镜像构建与服务编排，依赖安装基于 `requirements.txt`。
- `main.py`：FastAPI 服务入口，被 entrypoint 以 `python main.py --host/--port` 方式启动。
- `scripts/download_reranker.py`：BAAI/bge-reranker-large 模型下载辅助脚本。

## 3. 架构与约定
- **单一事实来源**：所有 Python 包依赖集中在 `pyproject.toml` 的 `[project.dependencies]` 与 `[project.optional-dependencies]` 中，按功能域拆分为 dev/test/video/docs/api/async_db/llm-providers 等组，并通过 `full` / `all` / `default` 组合暴露便捷别名。
- **双轨安装路径**：
  - 本地开发：推荐 `pip install -e ".[dev]"`（或 `pip install penshot[full]`），由 `setup_env.py` 兜底自动创建 venv 并执行 `pip install -r requirements.txt`。
  - 容器运行：`Dockerfile` 直接 `pip install -r requirements.txt`，entrypoint 提供 `install-deps` / `check-deps` 子命令用于调试。
- **可选依赖显式化**：LLM 提供商（openai/deepseek/dashscope）、视频处理（opencv/moviepy/pillow）、异步数据库（aiosqlite/asyncpg）均作为可选分组，避免默认安装体积膨胀。
- **构建产物包含配置与模板**：`tool.setuptools.package-data` 将 YAML/JSON/模板等资源打包进 wheel，确保安装后可直接加载提示词与规则配置。
- **无锁文件/私有仓库**：未发现 `poetry.lock`、`uv.lock`、`Pipfile.lock` 或自定义 index URL，依赖解析完全交由 pip/setuptools 完成。

## 4. 开发者应遵循的规则
- **新增依赖必须写入 `pyproject.toml`**：核心依赖放入 `dependencies`，可选能力放入对应 optional group（如 `api`、`video`、`llm-providers`），并在 README/文档中说明安装方式（例如 `pip install penshot[api,video,llm-providers]`）。
- **保持最小默认集**：仅在 `dependencies` 中保留真正“开箱即用”所需的包；对大型或平台相关库一律放入可选分组。
- **本地开发统一走 setup_env**：首次运行优先使用 `setup_env.py` 自动创建 `.venv` 并安装依赖，避免污染全局环境。
- **容器镜像只依赖 `requirements.txt`**：如需调整运行时依赖，同步更新 `requirements.txt`（当前 Dockerfile 未引用 pyproject），确保两者一致。
- **模型资源通过 download_reranker.py 管理**：不要将大模型权重纳入 Git 或 wheel，改用脚本按需下载至 `data/models/...`。
- **发布前验证完整安装**：使用 `pip install .[full]` 和 `pip install .[dev,test,video,docs,api,async_db,llm-providers]` 双重校验可选依赖组合可正常导入。