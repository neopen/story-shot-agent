# examples 示例索引

本目录的示例按**功能场景**拆分子目录，脚本**完全自包含**、可直接运行；样例数据统一放
`examples/data/`（各脚本用 `__file__` 相对路径引用，不在示例之间互相 import）。

## 前置条件

1. 安装包：`pip install -e .`
2. 配置 LLM/Embedding 密钥：`cp .env.example .env` 后填写，或导出环境变量
   `PENSHOT_LLM__DEFAULT__API_KEY`（嵌套配置用 `PENSHOT_` 前缀 + `__` 分隔）。

> **需要 LLM key 的示例**在下方标注 🔑；需要先启动对应服务器的标注 🖥️。
> 未配置 key 时，标注 🔑 的脚本会打印提示并优雅结束，仍可作为**接口签名演示**阅读。

## 目录结构

```
examples/
├── data/               # 样例数据（scripts/ 剧本、results/ 阶段产物 JSON）
├── sdk/                # Python 库（PenshotFunction）直调
├── rest/               # REST API 客户端（httpx，需先启动 REST 服务）
├── mcp/                # MCP：stdio 客户端 / HTTP 客户端 / 自测脚本 / 配置文件
├── cli/                # 用子进程驱动命令行（python -m penshot.cli）
├── workflow/           # LangGraph 集成 + 离线阶段演示
└── integrations/       # 上层框架封装（A2A 代理编排 / FastAPI Web 应用）
```

## 各子目录

### sdk/ — SDK 直调（`PenshotFunction`）

| 脚本 | 场景 | 涉及的公开 API | 运行前提 |
| --- | --- | --- | --- |
| `01_sync_breakdown.py` | 同步拆分 + 结果打印 | `breakdown_script` | 🔑 |
| `02_async_submit_poll.py` | 异步提交 + 回调 + 轮询 + 异步等待 | `breakdown_script_async`、`get_task_status`、`wait_for_result*` | 🔑 |
| `03_batch_processing.py` | 批量同步/异步 | `batch_breakdown`、`batch_breakdown_async` | 🔑 |
| `04_queue_and_task_mgmt.py` | 队列/统计/并发/取消 | `get_queue_status`、`get_stats`、`set_max_concurrent`、`cancel_task` | 无需 LLM |
| `05_custom_config.py` | 自定义 ShotConfig（LLM/Embedding） | `ShotConfig`、`LLMBaseConfig`、`EmbeddingBaseConfig` | 无需 LLM（演示配置） |
| `06_parse_result.py` | 解析 `data.instructions` 结构、存 JSON | `result.data` 契约 | 🔑；`--offline` 解析样例 |
| `07_script_from_file.py` | 从文件读取剧本后拆分 | `breakdown_script` | 🔑 |

### rest/ — REST API（httpx）

启动 REST 服务后再运行，端口默认 `8000`：

```bash
python -m penshot.http_server --host 127.0.0.1 --port 8000
# 或 story-shot-agent serve-rest
```

| 脚本 | 场景 | 端点 | 运行前提 |
| --- | --- | --- | --- |
| `01_sync_storyboard.py` | 同步分镜 | `POST /api/v1/storyboard/sync` | 🖥️ 🔑 |
| `02_async_submit_poll.py` | 异步提交 + 轮询 + 拉结果 | `/api/v1/storyboard`、`/status/{id}`、`/result/{id}` | 🖥️ 🔑 |
| `03_batch_storyboard.py` | 批量（同步/异步） | `/api/v1/storyboard/batch[/sync]`、`/batch/status|result/{id}` | 🖥️ 🔑 |
| `04_task_and_queue_admin.py` | 管理类接口 | `health/languages/config/queue/stats/status/result/DELETE task` | 🖥️（部分无需 LLM） |

### mcp/ — MCP

| 文件 | 说明 | 运行前提 |
| --- | --- | --- |
| `mcp_server_demo.py` | 自动拉起 `python -m penshot.mcp_server` 做端到端自测 | 🔑（链路演示可不配） |
| `mcp_client.py` | stdio JSON-RPC 客户端（可被 demo import 复用） | — |
| `mcp_http_client.py` | HTTP MCP 客户端（httpx） | 🖥️ 需先 `python -m penshot.mcp_http_server` 🔑 |
| `mcp_config.json` / `claude_desktop_config.json` | 可复制的 MCP server 配置（`command: python -m penshot.mcp_server`） | 复制使用 |

### cli/ — 命令行

| 脚本 | 场景 | 运行前提 |
| --- | --- | --- |
| `cli_runner.py` | 用子进程依次驱动 `python -m penshot.cli`（`--version`、`queue-status`、`breakdown --sync`、`batch`） | 离线子命令无需 LLM；真实拆分需 🔑 |

### workflow/ — LangGraph 集成与阶段讲解

| 脚本 | 场景 | 运行前提 |
| --- | --- | --- |
| `01_langgraph_integration.py` | 把 SDK 封装成 LangGraph 节点（提交/轮询/等待 + 条件路由） | 编译图无需 LLM；真实执行需 🔑 |
| `02_pipeline_stages_demo.py` | 离线讲解：读取 `data/results/*.json` 并映射到 `PipelineNode`、`PipelineState` 决策语义 | 纯标准库，**无需任何配置**；`--with-penshot` 可对照真实枚举 |

### integrations/ — 上层框架封装

| 脚本 | 场景 | 运行前提 |
| --- | --- | --- |
| `a2a_integration.py` | 把 Penshot 封装为 A2A 代理并编排（least_loaded / round_robin、取消、统计） | 🔑 |
| `fastapi_web_app.py` | 用 FastAPI 包装 SDK：生成/同步/批量/状态/结果/取消/脱敏配置 | 🔑；`python examples/integrations/fastapi_web_app.py --port 8000` |

## 旧文件去向（本次重组迁移）

顶层旧示例已按内容吸收到新目录后删除，引用过旧路径的文档均已更新：

| 旧文件 | 去向 |
| --- | --- |
| `direct_usage.py`、`penshot_demo.py` | 吸收进 `sdk/01_sync_breakdown.py` 等 |
| `penshot_config_demo.py` | 吸收进 `sdk/05_custom_config.py` |
| `langgraph_integration.py` | 修复为 `workflow/01_langgraph_integration.py` |
| `workflow_node_demo.py` | 替换为离线可跑的 `workflow/02_pipeline_stages_demo.py` |
| `web_app.py` | 修复为 `integrations/fastapi_web_app.py` |
| `a2a_integration.py` | 修复为 `integrations/a2a_integration.py` |
| `script_txt/` | 移入 `data/scripts/` |
| `json_demo/`、`function_calls_data.json` | 移入 `data/results/` |

## 结果结构约定（写代码时务必遵守）

- 提交用 `script_id=`（调用方关联 ID），**真实 task_id 由返回值提供**，不存在 `task_id=` 参数。
- 任务状态是 `TaskStatus`（str 枚举），终态成功为 `success`（**没有 `"completed"`**）；
  比较时取 `.value` 或与 `TaskStatus.SUCCESS` 比较。REST/MCP 层的 `status` 已是普通字符串。
- 默认（非 debug）结果取数契约：`result.data["instructions"]`，其内为
  `project_info{total_fragments,total_duration}` 与 `fragments[]`（每项含
  `prompt/negative_prompt/duration/model/audio`，**音频字段是 `audio`**）。
- REST 服务器端点在 `src/penshot/api/rest_api.py`；MCP 工具见 `src/penshot/mcp_server.py`。
