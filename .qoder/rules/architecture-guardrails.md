---
trigger: always_on
---

# PenShot 架构禁区与调用约定

> 本规则补充 `.qoder/rules/SDD-Agent.md`，冲突时以 SDD-Agent.md 为准。

---

## 1. 分层架构

项目采用四层结构（由内到外）：

```
接入层 (api/ http_server.py mcp_server.py cli.py)
   ↑
任务层 (neopen/task/)
   ↑
工作流层 (neopen/agent/workflow/)
   ↑
智能体层 (neopen/agent/<agent>/)
   ↑
基础设施层 (config/ logger/ utils/ neopen/knowledge/)
```

### 调用方向约定

- **只允许外层调用内层**，禁止反向依赖。
- 禁止智能体层直接调用接入层（如 `PenshotFunction`）。
- 禁止工作流层直接操作 Redis/Chroma 等基础设施（应通过 `task/` 或 `knowledge/` 封装）。

---

## 2. 状态模型使用约束

项目中存在多套状态/模型概念，修改前必须明确区分：

| 模型 | 用途 | 所在位置 |
|---|---|---|
| `AgentStage` | 业务阶段（解析、拆镜、切片等） | `workflow_models.py` |
| `PipelineNode` | 图节点枚举 | `workflow_models.py` |
| `PipelineState` | 决策结果（success/needs_repair/needs_retry 等） | `workflow_state_types.py` |
| `WorkflowState` | LangGraph 图状态 | `workflow_state_types.py` |
| `TaskStage` / `TaskStatus` | 任务生命周期 | `task_models.py` |

### 禁区

- 禁止把 `WorkflowState` 直接作为业务返回值返回给 SDK/REST 调用方。
- 禁止在 `AgentStage` 中混入图控制字段（如 retry_count、loop_count）。
- 新增状态时，必须同步更新对应模型、序列化逻辑和测试。

---

## 3. 工作流节点扩展约定

`workflow_nodes.py` 当前为单体大文件（1700+ 行）。新增节点时：

- 优先在 `workflow_nodes.py` 内按阶段分组，保持与现有节点一致的输入/输出签名。
- 节点函数应接收 `WorkflowState` 并返回 `WorkflowState`（或符合 LangGraph 要求的字典）。
- 节点内部禁止直接调用其他节点的实现函数；应通过图边和条件路由连接。
- 如需新增阶段，必须同步：
  1. `AgentStage` / `PipelineNode`
  2. 节点注册与边连接
  3. 条件决策逻辑（`workflow_decision.py`）
  4. 错误处理与重试配置
  5. 对应测试

---

## 4. 任务层约定

`neopen/task/` 负责任务提交、排队、生命周期、仓储：

- `TaskFactory` 是 SDK 与 REST 的统一入口。
- 当前 SDK 与 REST 各自维护独立 `TaskFactory`（队列、Future 不共享），修改时不得擅自合并为全局单例，除非经过架构确认。
- `TaskRepository` 支持 Redis / 内存双后端，Redis 失败时自动降级；代码中应假设后端可切换。

---

## 5. 配置读取约定

- 统一通过 `penshot.config.config.settings` 读取配置。
- 环境变量前缀为 `PENSHOT_`，嵌套使用双下划线 `__`（如 `PENSHOT_LLM__DEFAULT__API_KEY`）。
- 禁止在业务代码中直接读取 `os.environ`，除非在 `config/` 模块内部。
- `ShotConfig` dataclass 用于运行时镜头级配置，与 `settings` 区分。

---

## 6. 记忆与 RAG 约定

- 短期记忆：`workflow_memory.after_stage_completion` 三级存储（Redis 优先、内存次之）。
- 长期记忆：Chroma + llama-index + 本地 `bge-reranker-large`。
- 禁止绕过 `MemoryManager` / `WorkflowMemory` 直接操作 Chroma client。
- 向量索引、知识库模板变更后，需运行 `tests/knowledge/rebuild_index.py` 重建索引。

---

## 7. 公开接口变更联动

修改以下任一公开接口时，必须检查所有接入方式：

- `PenshotFunction`（SDK）
- REST API（`src/penshot/api/rest_api.py`）
- MCP server（`src/penshot/mcp_server.py`）
- CLI（`src/penshot/cli.py`）
- A2A / LangGraph 节点（`examples/`）

---

## 8. 版本号约定

- 以 `pyproject.toml` 的 `version` 字段为单一事实源（当前为 `0.3.6`）。
- 顶层 `penshot/__init__.py` 的 `__version__` 应与之保持一致。
- 文档中提及版本时优先引用 `pyproject.toml`。
