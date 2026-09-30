---
kind: external_dependency
name: LangGraph 工作流编排与状态持久化
slug: langgraph
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### LangGraph 工作流引擎
- 基于 `StateGraph` 构建多智能体协作流水线，支持声明式节点/边/条件边定义
- 使用 `langgraph-checkpoint-sqlite` 实现断点续传，检查点保存在 `data/checkpoints/{script_id}/` 目录
- 每个任务独立 Pipeline 实例，由 `WorkflowRegistry` 缓存复用（LRU 淘汰）
- 状态模型包含 `WorkflowState/AgentStage/PipelineNode/PipelineState` 等核心枚举
- 全局循环上限 `max_total_loops=20`，工作流总超时 `workflow_timeout=1800s`