# PenShot 项目理解（代码导览）

> 整理时间：2026-07-20 ｜ 最近更新：2026-08-28 ｜ 基于当前工作区代码与 docs/ 文档
> 用途：帮助快速建立对项目的整体认知，作为后续开发/调试的上下文底稿。
>
> **状态说明**：本导览描述的是截至整理时的整体架构与业务定位。部分细节（如依赖版本、模块拆分、入口命令）可能随代码演进发生变化。进行具体开发时，请以当前源码、`pyproject.toml`、`.pre-commit-config.yaml` 为准，并结合 `.qoder/repowiki/` 中的模块知识卡获取最新模块信息。

---

## 一、业务定位

**PenShot** 是一个"剧本 → 分镜 → AI 视频提示词"的多智能体协作系统。

- **要解决的问题**：主流 AI 视频模型（Sora / Veo / Runway / Kling / Pika / SVD）单次只能生成 5–10 秒视频，且跨片段角色/场景/风格一致性差。PenShot 充当"上游剧本理解"与"下游视频生成"之间的**中间生产层**。
- **核心闭环**：`Script → Structured Breakdown → Prompt Fragments`
  - 输入：任意格式的剧本（自然语言 / 标准剧本 / 结构化场景）
  - 输出：镜头级 JSON 片段，含英文 prompt、negative_prompt、时长、目标模型、风格、音频提示词（audio_prompt），可直接投喂文生视频/音频模型
- **关键卖点**：
  1. 智能解析 + 精准时序规划（片段时长严格适配模型约束）
  2. 连续性守护（多级记忆 + Chroma 向量检索 + 一致性契约）
  3. 多协议接入（Python SDK / REST / MCP / LangGraph 节点 / A2A）
  4. 多 LLM 可插拔（OpenAI / Qwen / DeepSeek / Ollama / HuggingFace）

**命名对照（易混淆）**：
| 名称 | 用途 |
|---|---|
| `video-shot-agent` | 本地工作区目录名 |
| `story-shot-agent` | GitHub 仓库名 |
| `penshot` | PyPI 包名 / Python 包名（`src/penshot`） |
| `neopen` | 核心领域模块名（`src/penshot/neopen`），也是组织名 |
| `PenShot` | 产品品牌名 |

---

## 二、技术栈

- Python 3.10+（Docker 用 3.11-slim）
- 编排：**LangChain 1.2+ / LangGraph 1.1+**（StateGraph 工作流）+ `langgraph-checkpoint-sqlite`（断点续传）
- RAG：**ChromaDB** + llama-index（`llama-index-core`、`llama-index-embeddings-langchain`），本地重排序模型 `data/models/bge-reranker-large`
- 服务：FastAPI + Uvicorn（可选依赖组 `api`）
- 任务持久化：Redis（可选）/ 内存双后端
- 配置：pydantic v2 + pydantic-settings + PyYAML，环境变量前缀 `PENSHOT_`，嵌套用双下划线（如 `PENSHOT_LLM__DEFAULT__API_KEY`）
- 其他：jieba（中文分词）、tiktoken、numpy、colorama
- 构建：setuptools（src 布局，`src/penshot`），版本 0.4.0

---

## 三、分层架构总览

```
┌─ 接入层 Access ─────────────────────────────────────────────┐
│  Python SDK (api/function_calls.py)                         │
│  REST API (api/rest_api.py + http_server.py, main.py 启动)   │
│  MCP (mcp_server.py / mcp_http_server.py)                   │
│  LangGraph 节点 / A2A 协议（examples/ 演示）                  │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─ 任务层 Task（neopen/task/）────────────────────────────────┐
│  TaskFactory（统一入口：submit/submit_and_wait/batch）        │
│  ├─ AsyncTaskProcessor：后台线程+事件循环+优先级队列           │
│  └─ TaskManager（协调层，保持向后兼容）                       │
│      ├─ TaskLifecycleService：状态机/进度/回调/指标           │
│      ├─ TaskRepository：CRUD/快照/TTL，内存|Redis 双后端      │
│      └─ WorkflowRegistry：Pipeline 实例缓存 + LRU 淘汰        │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─ 工作流层 Workflow（neopen/agent/workflow/）─────────────────┐
│  MultiAgentPipeline (workflow_pipeline.py)：每任务一个实例    │
│  ├─ WorkflowOrchestrator：声明式构图（节点/边/条件边）        │
│  ├─ WorkflowNodes (1712行)：各节点具体执行逻辑               │
│  ├─ PipelineDecision (1050行)：条件路由决策函数              │
│  ├─ workflow_checkpointer：SQLite 持久化（断点续传）          │
│  ├─ workflow_error_handler / workflow_memory /               │
│  │   workflow_output(_fixer) / workflow_logger               │
│  └─ 状态模型：WorkflowState / AgentStage / PipelineNode /    │
│      PipelineState（success|valid|needs_repair|needs_retry|  │
│      needs_human|failed|abort）                              │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─ 智能体层 Agents（neopen/agent/）────────────────────────────┐
│  基类：BaseAgent → BaseLLMAgent → BaseRepairableAgent        │
│  主链路 6 智能体（每个均有 rule/llm 双实现 + factory）：       │
│   script_parser → shot_segmenter → video_splitter →          │
│   prompt_converter → quality_auditor → continuity_guardian   │
│  附属：human_decision（人工干预）、estimator（时长估计器）     │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─ 知识与记忆层（neopen/knowledge/）───────────────────────────┐
│  MemoryManager → ScriptMemory → 短期/中期/长期记忆            │
│  knowledge_manager + llamaIndex（loader/retriever/tool）     │
│  template/prompt_template_knowledge（提示词模板知识库）        │
└──────────────────────────────────────────────────────────────┘
┌─ 基础设施 ──────────────────────────────────────────────────┐
│  client/（LLM 客户端工厂：openai/qwen/deepseek/ollama/hf）    │
│  cache/（llm_cache、adaptive_llm_cache）                     │
│  config/（settings.yaml + pydantic-settings，default/fallback│
│   双 LLM 配置）、prompts/（模板加载）、tools/、utils/          │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、核心领域链路（6 智能体流水线）

| 阶段 | 节点（PipelineNode） | 模块 | 职责 | 实现策略 |
|---|---|---|---|---|
| 1 | PARSE_SCRIPT | `agent/script_parser*` | 剧本→结构化叙事单元（场景/角色/对话/动作） | LLM + 规则兜底 |
| 2 | SEGMENT_SHOT | `agent/shot_segmenter*` | 叙事单元→镜头序列，预估时长 | LLM + 规则 + estimator 增强 |
| 3 | SPLIT_VIDEO | `agent/video_splitter*` | 镜头→≤5s 视频片段（适配模型时长） | LLM(AI分割) + 规则 |
| 4 | CONVERT_PROMPT | `agent/prompt_converter*` | 片段→英文视频 prompt + 负面 prompt + 音频 prompt | LLM + 模板 |
| 5 | AUDIT_QUALITY | `agent/quality_auditor*` | 时长/格式/内容质量审计，产出 issues | LLM + 规则 |
| 6 | CONTINUITY_CHECK | `agent/continuity_guardian/` | 跨片段角色/场景/气象/风格一致性校验 | 契约 + 校验器 |

控制节点：`LOOP_CHECK`（循环/重试控制）、`ERROR_HANDLER`、`HUMAN_INTERVENTION`、`GENERATE_OUTPUT`（+ `WorkflowOutputFixer` 片段序列修复）。

**continuity_guardian 子模块**（连续性是架构分水岭，项目差异化方向）：
- `consistency_contract.py`：全局一致性契约（Planner 前置约束）
- `continuity_guardian_checker.py`：连续性检查（Validator）
- `continuity_repair_generator.py`：修复建议生成（Repairer）
- `long_script_chunker.py` + `cross_chunk_validator.py`：长剧本分块与跨块校验
- `prompt_style_guardian.py`：风格漂移守护

**时长估计器**（`shot_segmenter/estimator/`）：`action_estimator` / `dialogue_estimator` / `scene_estimator` + `estimator_enhancer` + `estimator_factory`，规则与 AI 混合估算镜头时长。

**人工干预**（`agent/human_decision/`）：支持 interactive（控制台）/ auto（自动决策）/ callback 三种模式（见 `ShotConfig.human_intervention_mode`）。

---

## 五、关键运行时行为

### 任务生命周期
```
Client → SDK/REST/MCP → TaskFactory.submit()
  → TaskManager.create_task()（生成 script_id + task_id）
  → AsyncTaskProcessor 入队（优先级队列）
  → 后台事件循环执行 MultiAgentPipeline.run_process()
  → 状态推进 PENDING→PROCESSING→COMPLETED/FAILED
  → 回调（本地 callable / callback_url）+ Future 唤醒等待方
```
- 任务 TTL 默认 24h（SDK 入口 `PenshotFunction` 设为 30 天）
- SQLite checkpoint 支持服务重启后断点续传（`data/checkpoints/{script_id}/`）
- Redis 用于任务记录持久化与跨进程恢复（可选）

### 工作流执行
- 每个任务独立 `MultiAgentPipeline` 实例（含独立 LLM/embedding/记忆），由 `WorkflowRegistry` 缓存复用（LRU）
- 节点执行后经 `PipelineDecision` 决策路由：success→下一节点；needs_repair→回退修复；needs_retry→原地重试；needs_human→人工干预；failed→ERROR_HANDLER
- 全局循环上限 `max_total_loops=20`，工作流总超时 `workflow_timeout=1800s`

### 记忆体系（连续性基础）
- **短期记忆**：当前会话上下文（LangChain message 级）
- **中期记忆**：阶段摘要（summary）
- **长期记忆**：Chroma 向量库文档（跨任务召回）
- 持久化目录：`data/memory/{script_id}/`
- 知识库：llamaIndex 路由（`data/embedding/script_kb`、`prompt_templates`）+ bge-reranker-large 本地重排序

---

## 六、配置体系

| 层 | 文件/类 | 说明 |
|---|---|---|
| 静态默认 | `src/penshot/config/settings.yaml` | app/api/llm/embed/storyboard/paths/vector_store/cache/processing 等 |
| 环境变量 | `.env`（前缀 `PENSHOT_`，`__` 嵌套） | 优先级高于 yaml |
| 运行时 | `neopen/shot_config.py: ShotConfig(AIConfig)` | dataclass，时长阈值、分割策略、人工干预、checkpoint 等 |
| LLM 客户端 | `neopen/client/` | `client_factory` 按 provider 创建，default + fallback 双配置 |

关键默认：片段 1–5s（`max_fragment_duration=5.0`，>5.5s 触发分割）、镜头默认 3s、prompt 20–200 词、并发 10、队列 1000。

---

## 七、数据与产物目录

| 路径 | 内容 |
|---|---|
| `data/checkpoints/{script_id}/` | LangGraph SQLite checkpoint（断点续传） |
| `data/memory/{script_id}/` | 三级记忆持久化 |
| `data/embedding/` | 知识库向量（script_kb、prompt_templates） |
| `data/models/bge-reranker-large/` | 本地重排序模型（含 onnx） |
| `data/output/`、`data/template/` | 输出与模板 |
| `examples/json_demo/` | 各阶段真实输出样例（5 个 agent 的 result JSON） |
| `examples/script_txt/` | 4 种格式示例剧本 |
| `logs/penshot_YYYY-MM-DD.log` | 按日滚动日志 |

---

## 八、版本与质量现状

- 当前版本 **0.4.0**（pyproject）；CHANGELOG 记录至 0.1.0 + 未发布段
- `docs/v0.3 功能完成度评测报告.md`（2026-05-05，脚本《雨中的约定》）：
  - 综合完成度 **73%**（v0.1 MVP 95% 达标 / v0.2 质量保障 75% / v0.3 智能增强 50%）
  - **P0**：AI 分割器未触发（全部走规则分割）、自动修复未执行（repair_applied 全 false）
  - **P1**：短期记忆为空（message_count=0）、置信度评分缺失、跨片段气象不一致
  - **P2**：LlamaIndex 未启用（long_term_enabled=false）、修复历史重复、统计分散
- 架构演进路线（`docs/架构演进：从 MVP 到成品.md`）：MVP → 多智能体流水线 → 服务化任务化 → 工作流编排 → 连续性系统 → 长剧本记忆 → 平台化成品。当前大约处于 Phase 3–4（工作流编排已成形，连续性体系正在从"末端检查"走向"前置约束"）。

---

## 九、测试与工具

- `tests/`：unit / integration / e2e / planner（时长估计器系列测试较全）/ task / workflow / knowledge / api / benchmarks
- pytest 配置在 pyproject（`asyncio_mode=auto`，严格 markers）
- `scripts/cli.py`：命令行入口脚本（注意：不在包内，见疑问清单）
- `examples/`：SDK、REST、MCP、LangGraph、A2A 等集成演示
