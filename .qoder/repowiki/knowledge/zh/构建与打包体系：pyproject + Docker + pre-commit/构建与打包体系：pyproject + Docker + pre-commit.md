---
kind: build_system
name: 构建与打包体系：pyproject + Docker + pre-commit
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - Dockerfile
    - docker-compose.yml
    - scripts/entrypoint.py
    - main.py
    - .pre-commit-config.yaml
    - scripts/download_reranker.py
---

## 1. 使用的系统/工具链
- **包管理与构建**：基于 `pyproject.toml` + setuptools（`setuptools.build_meta`），Python ≥3.10，通过 `[project.scripts]` 暴露 `story-shot-agent`、`vs-agent` 两个 CLI 入口，并通过 entry-points 提供 `story-shot-agent-serve`。
- **依赖声明**：核心依赖集中在 `pyproject.toml` 的 `dependencies` 中，可选能力按分组组织（`dev`、`test`、`video`、`docs`、`api`、`async_db`、`llm-providers`、`full`、`all`、`default`）；Dockerfile 仍引用 `requirements.txt`（当前仓库未包含该文件，实际应以 pyproject 为准）。
- **容器化**：使用单阶段 `Dockerfile`（`python:3.11-slim`）+ `docker-compose.yml`，ENTRYPOINT 指向 `scripts/entrypoint.py`，默认 CMD 为 `start`，对外暴露 8000 端口。
- **代码质量与提交前检查**：`.pre-commit-config.yaml` 集成 ruff（lint/format）、mypy、mdformat、pre-commit-hooks 等钩子。
- **测试运行**：pytest 配置在 `pyproject.toml` 的 `[tool.pytest.ini_options]`，支持 `--strict-markers`、`--strict-config` 与 asyncio auto mode。
- **模型下载辅助**：`scripts/download_reranker.py` 通过 HuggingFace snapshot 下载 BAAI/bge-reranker-large 到 `data/models/bge-reranker-large`。

## 2. 关键文件与位置
- `pyproject.toml` — 项目元信息、依赖、脚本入口、setuptools 打包规则、black/isort/mypy/pytest 工具配置
- `Dockerfile` — 容器镜像构建（安装系统依赖、pip 依赖、复制源码、设置环境变量）
- `docker-compose.yml` — 本地一键编排服务（映射 8000 端口）
- `scripts/entrypoint.py` — 容器入口脚本，支持 `start` / `install-deps` / `check-deps` 命令，并 `os.execv` 替换进程以正确传递信号
- `main.py` — FastAPI 应用启动器，封装 uvicorn 启动逻辑（host/port/reload/workers 解析、SIGINT/SIGTERM 处理）
- `.pre-commit-config.yaml` — 提交前钩子（ruff、mypy、mdformat、large-file/private-key 检测等）
- `src/penshot/app/setup_env.py` — 运行时环境自检与依赖安装引导（参考 requirements.txt 路径）
- `scripts/download_reranker.py` — Reranker 模型离线下载脚本

## 3. 架构与约定
- **包结构**：`package-dir = { "" = "src" }`，仅打包 `src/penshot*`，排除 tests；数据文件（yaml/json/txt/templates 等）通过 `[tool.setuptools.package-data]` 显式包含。
- **版本管理**：`[tool.setuptools.dynamic] version = { attr = "penshot.__version__" }`，从包内 `__version__` 动态读取；同时 `pyproject` 中硬编码 `version = "0.4.0"`，发布时需保持一致。
- **CLI 分发**：通过 `[project.scripts]` 将 `penshot.cli:main` 暴露为可执行命令，方便 pip 安装后直接调用；FastAPI 服务可通过 `story-shot-agent-serve` 或 `python main.py` 启动。
- **容器启动流**：`Dockerfile ENTRYPOINT ["python", "-m", "scripts.entrypoint"]` → `entrypoint.py start` → `os.execv python main.py --host/--port` → `main.py` 内部用 uvicorn 启动 `penshot.app:app`。环境变量优先顺序：`PENSHOT_API__HOST/PENSHOT_API__PORT` > `PENSHOT_HOST/PENSHOT_PORT` > 默认值。
- **开发工作流**：开发者通过 `pip install -e ".[dev,test,api,...]"` 安装可选依赖，配合 pre-commit 钩子在提交前自动执行 ruff/mypy/mdformat 检查。

## 4. 开发者应遵循的规则
- **依赖变更**：新增/升级依赖请同步更新 `pyproject.toml` 对应分组；若需兼容旧流程，请在根目录维护一份 `requirements.txt` 并与 pyproject 保持同步（当前仓库缺失该文件，建议补全）。
- **版本发布**：修改 `src/penshot/__init__.py` 中的 `__version__` 时，务必同步更新 `pyproject.toml` 顶层 `version` 字段，确保动态读取与静态声明一致。
- **容器构建**：`Dockerfile` 依赖 `requirements.txt`，若改用 pyproject 作为唯一来源，应将 `pip install .` 替代 `-r requirements.txt`，避免双源不一致。
- **环境变量**：容器内控制服务绑定地址与端口请使用 `PENSHOT_API__HOST`、`PENSHOT_API__PORT`（或 `PENSHOT_HOST`、`PENSHOT_PORT`）；如需透传额外 uvicorn 参数，可使用 `UVCORN_ARGS`。
- **代码质量**：提交前确保 pre-commit 钩子通过（ruff lint/format、mypy、mdformat、大文件/私钥检测）；本地可先执行 `pre-commit run --all-files` 验证。
- **测试运行**：使用 `pytest` 即可，无需额外 Makefile；异步测试已启用 `asyncio_mode = "auto"`，可直接编写 async test 函数。
- **模型资源**：Reranker 模型通过 `scripts/download_reranker.py` 下载到 `data/models/bge-reranker-large`，建议在 CI 或部署文档中明确此步骤。