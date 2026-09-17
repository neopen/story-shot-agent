# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

PenShot (`penshot`) is a multi-agent system that converts screenplays/scripts of arbitrary format into shot-level, AI-video-ready prompt fragments (bilingual prompt + negative prompt + duration + audio prompt), ensuring character/scene/plot continuity across fragments. It sits between upstream scriptwriting and downstream text-to-video models (Sora/Veo/Runway/Kling).

Naming — all refer to the same project:
- `story-shot-agent` — local workspace directory
- `story-shot-agent` — GitHub repo name
- `penshot` — PyPI package name AND Python package (`src/penshot`)
- `neopen` — core domain module (`src/penshot/neopen`), also the org name

Stack: Python 3.10+, LangChain/LangGraph (StateGraph workflow + SQLite checkpointer), ChromaDB + llama-index for RAG, FastAPI/uvicorn for REST, Redis (optional) for task persistence, pydantic v2 + pydantic-settings for config.

## Commands

Install editable with dev tooling (pytest, ruff, black, flake8, mypy, isort, pre-commit):

```bash
pip install -e ".[dev]"
```

Config: `cp .env.example .env` then fill in LLM/embedding keys. Env vars use prefix `PENSHOT_` with `__` for nesting (e.g. `PENSHOT_LLM__DEFAULT__API_KEY`).

### Run tests

```bash
pytest                    # whole suite (testpaths=tests, asyncio_mode=auto)
pytest tests/planner/test_action_duration.py            # one file
pytest tests/test_config.py -k "test_name"              # one test by name
```

Tests are async-heavy but use `asyncio_mode=auto` (no explicit `@pytest.mark.asyncio` needed). Many tests require no network; integration/e2e paths hit real LLM APIs and are skipped or need keys.

### Lint / format / type-check

```bash
pre-commit run --all-files    # ruff + ruff-format + mypy + trailing-whitespace etc.
ruff check .                  # lint (ruff is the canonical linter, not flake8)
ruff format .                 # format (ruff-format is the canonical formatter, replaces black)
mypy src/                     # type check (disallow_untyped_defs=true)
```

`pyproject.toml` still contains `black`/`isort`/`flake8` configs, but `.pre-commit-config.yaml` runs **ruff** and **ruff-format** (not black) plus **mypy**.

### Run the app

```bash
story-shot-agent --help                       # CLI (also aliased as vs-agent)
story-shot-agent breakdown "剧本内容" --sync -o out.json   # one-shot
story-shot-agent serve-rest --port 8000       # REST API server
story-shot-agent serve                        # MCP server
python main.py                                # REST server, auto-creates venv + installs deps
python -m penshot.http_server                 # REST server (module form)
python -m penshot.mcp_server --max-concurrent 5 --queue-size 500
```

Note: `main.py` (repo root) is a launcher that inserts `src/` into `sys.path`, creates/activates a venv, installs deps, then starts uvicorn — the package itself is importable only from `src/penshot` unless installed.

## Architecture

Layered, top-to-bottom (deepest details in `docs/ARCHITECTURE.md`; Chinese design docs for the task layer and workflow layer are at `docs/任务层拆分设计与实现文档.md` and `docs/工作流职责拆分设计与实现文档.md`):

**Access layer** (`src/penshot/`)
- `api/function_calls.py` — public SDK: `PenshotFunction` / `create_penshot_agent()`. Entry point for all integrations.
- `api/rest_api.py` + `http_server.py` + `app/` — FastAPI REST service.
- `mcp_server.py` / `mcp_http_server.py` — Model Context Protocol servers.
- `cli.py` — console entry points (`story-shot-agent`, `vs-agent`, `story-shot-agent-serve`).

**Task layer** (`neopen/task/`)
- `TaskFactory` is the unified submission entry (`submit` / `batch` / `wait_for_result`), backed by an async priority-queue processor.
- `TaskManager` is a compatibility coordinator delegating to `TaskLifecycleService` (state machine, progress, callbacks, metrics), `TaskRepository` (CRUD with **memory | Redis** dual backend), and `WorkflowRegistry` (LRU cache of per-task pipeline instances).
- Task lifecycle: `PENDING → PROCESSING → COMPLETED/FAILED`, with SQLite checkpoints enabling resume after restart.

**Workflow layer** (`neopen/agent/workflow/`) — the LangGraph core
- `workflow_pipeline.py` — `MultiAgentPipeline`, one instance per task; builds and runs the graph.
- `workflow_orchestrator.py` — declarative graph builder (add nodes/edges/conditional edges).
- `workflow_nodes.py` — concrete node implementations (~1700 lines, the meat of execution).
- `workflow_decision.py` — `PipelineDecision` conditional routing (per-node `decide_after_*` functions).
- `workflow_state_types.py` — `WorkflowState` (nested `input` / `config` / `domain` / `execution` / `output` / `errors`).

**Agent layer** (`neopen/agent/`) — six main agents, each with `rule` + `llm` implementations behind a factory:
1. `script_parser` — script → structured scenes/characters/dialogue/actions
2. `shot_segmenter` — narrative units → shot sequence with durations (`estimator/` subpackage)
3. `video_splitter` — shots → ≤5s video fragments (AI video model limit)
4. `prompt_converter` — fragments → English prompt + negative + audio prompt
5. `quality_auditor` — rule + LLM audit of duration/format/content
6. `continuity_guardian` — cross-fragment consistency (character/scene/style/props/lighting)

Base classes: `BaseAgent → BaseLLMAgent → BaseRepairableAgent` (`neopen/agent/base_*.py`). Control nodes in the graph: `LOOP_CHECK`, `ERROR_HANDLER`, `HUMAN_INTERVENTION`, `GENERATE_OUTPUT`.

**Knowledge & memory layer** (`neopen/knowledge/`)
- `MemoryManager` + `memory/` (short/medium/long-term) — the basis of continuity. Unified access via `WorkflowMemory.after_stage_completion()`.
- `llamaIndex/` + ChromaDB vector retrieval, local reranker at `data/models/bge-reranker-large`. `data/` is gitignored — on a fresh clone download the reranker once via `python scripts/download_reranker.py`.

**Infrastructure** (`neopen/client/`, `neopen/cache/`, `neopen/config/`, `neopen/tools/`, `utils/`)
- `client/` — LLM client factory per provider (openai/qwen/deepseek/ollama/huggingface), `default` + `fallback` configs.
- `cache/` — `llm_cache` + `adaptive_llm_cache`.

### Config system

Priority: **env vars > YAML > defaults** (`config/config.py`, `Settings` singleton). Nested keys use `__`; prefix `PENSHOT_`. Runtime per-request settings live in `neopen/shot_config.py` `ShotConfig` dataclass (fragment duration 1–5s, `duration_split_threshold=5.5`, prompt 20–200 words, `max_total_loops=20`, `workflow_timeout=1800s`).

## Conventions

- Code comments and docstrings are written in **Chinese**; follow that convention.
- Every agent follows the same shape: `base_*` → `rule_*`/`llm_*` → `*_factory.py` → `*_agent.py` (the wrapper used by the workflow).
- The workflow routes via `PipelineState` values: `success | valid | needs_repair | needs_retry | needs_human | failed | abort` — a node returning `needs_repair`/`needs_retry` loops back to itself or an earlier stage.
- New pipeline stages require: a `PipelineNode` enum value, a node registration + conditional edge in `workflow_pipeline.py`, and a node method + decision function in `workflow_nodes.py` / `workflow_decision.py`.
