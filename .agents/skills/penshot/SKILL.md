---
name: penshot
description: PenShot 项目开发 Skill。用于修改或审查 Agent、LangGraph 工作流、任务生命周期、记忆/RAG、配置、REST、MCP、CLI、测试和项目文档；先核实源码与工具配置，再按现有架构实施并验证。
---

# PenShot 项目开发 Skill

## 适用场景

使用本 Skill 处理以下任务：

- 修改 Agent、工作流节点、任务生命周期、记忆/RAG、配置、REST、MCP 或 CLI。
- 新增或调整测试、开发文档和质量检查。
- 排查 LangGraph 状态流转、任务恢复、外部 LLM/Redis/Chroma 集成问题。

## 工作流程

1. 先读取相关源码、测试和配置，再判断实现位置。
2. 按事实来源优先级核实现状，区分已确认、设计目标和待验证内容。
3. 复用现有模块和扩展点，保持 task、workflow、agent、knowledge 分层边界。
4. 只修改需求所需范围，不创建重复规范、虚构配置 schema 或无依据兼容层。
5. 按变更范围运行测试和质量检查，报告实际执行状态。

## 事实来源优先级

出现冲突时按以下顺序核实，不把旧文档当作实现事实：

1. 当前源码与测试。
2. `pyproject.toml`。
3. `.pre-commit-config.yaml`。
4. 根目录 `AGENTS.md`。
5. 本目录 `references/` 中的按需参考资料。
6. 其他设计文档、示例和历史报告。

文档中的结论应区分：**已从当前代码确认**、**设计目标**、**待验证**。

## 当前架构入口

- 接入层：`src/penshot/api/`、`http_server.py`、`mcp_server.py`、`cli.py`。
- 任务层：`src/penshot/neopen/task/`，负责提交、排队、生命周期、仓储和工作流实例注册。
- 工作流层：`src/penshot/neopen/agent/workflow/`，负责状态、节点、条件路由、检查点和输出。
- Agent 层：`src/penshot/neopen/agent/`，遵循现有基类、rule/llm 实现、factory 和 wrapper 结构。
- 知识与记忆层：`src/penshot/neopen/knowledge/`，负责记忆、向量检索和模板知识。
- 测试：`tests/`，按当前测试目录和 `pyproject.toml` 配置选择范围。

需要详细模块导航时，按需读取 `references/project_understanding.md`。该文件是有时效性的参考资料，不替代当前源码、测试和项目配置。

## 变更联动要求

- 新增工作流阶段时，同时检查 `PipelineNode`、节点注册、边、条件决策、状态类型和对应测试。
- 新增 Agent 时先复用现有 Agent 工厂和 wrapper，不套用与当前源码无关的通用模板。
- 修改任务状态时检查生命周期服务、仓储、处理器、恢复逻辑和状态测试。
- 修改配置时检查 YAML、环境变量映射、Pydantic Settings 与运行时 `ShotConfig`。
- 修改公开接口时检查 SDK、REST、MCP、CLI 及其序列化模型的影响。

## 工具链与验证

- Python 版本以 `pyproject.toml` 的 `requires-python` 为准。
- Python 检查以 `.pre-commit-config.yaml` 为准：Ruff、Ruff format、mypy；Markdown 使用 mdformat。
- 测试使用 pytest；异步测试行为以 `pyproject.toml` 的 asyncio 配置为准。
- 先运行受影响范围的测试，再根据变更范围运行 lint、类型检查或完整检查。
- 报告结果时明确区分已执行通过、执行失败、未执行和因外部依赖无法验证。

## 安全与边界

- 不在共享文件、日志、测试输出或文档中写入 API key、token、Authorization header、真实 `.env` 内容或私有凭据。
- 不把设计目标、历史报告、示例配置或未执行的检查写成当前能力或测试结果。
- 涉及真实 LLM、Redis、Chroma、部署、数据清理或其他外部副作用时，先核实环境和操作范围。
- 只修改完成需求所需的范围，不创建未经仓库支持的配置 schema、自动化 hook 或兼容性层。

## 规范职责边界

- 本 Skill：负责 PenShot 任务的工作流程、架构导航和验证要求。
- 根目录 `AGENTS.md`：负责所有会话通用的项目总览、命令和协作约定。
- `pyproject.toml`：负责 Python 版本、依赖、pytest 和工具配置。
- `.pre-commit-config.yaml`：负责实际运行的格式化、lint、类型检查和其他 hook。
- 当前源码与测试：负责实现和行为事实。