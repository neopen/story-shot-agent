---
kind: error_handling
name: 分层错误处理体系：工作流分类重试与 FastAPI 全局异常映射
category: error_handling
scope:
    - '**'
source_files:
    - src/penshot/app/application.py
    - src/penshot/api/rest_api.py
    - src/penshot/neopen/agent/workflow/workflow_error_handler.py
---

## 1. 系统概览

本仓库采用**两层错误处理架构**：
- **HTTP 层（FastAPI）**：通过全局 `exception_handler` 将 `HTTPException` 与普通 `Exception` 统一映射为 JSON 响应，并记录结构化日志。
- **工作流层（Workflow）**：在 `neopen/agent/workflow` 中定义了一套完整的领域错误类型、分类器与自动重试/修复策略，由 `WorkflowErrorHandler` 集中管理。

两者配合，使 API 对外暴露一致的 HTTP 语义，内部工作流具备可观测、可恢复的错误处理能力。

## 2. 关键文件与职责

| 文件 | 职责 |
|------|------|
| `src/penshot/app/application.py` | FastAPI 应用初始化；注册 CORS、请求上下文中间件；定义 `http_exception_handler` 与 `general_exception_handler` 两个全局异常处理器 |
| `src/penshot/api/rest_api.py` | REST 路由实现；各 handler 内使用 `try/except ValueError` 捕获参数校验错误并 `raise HTTPException(400)`，兜底 `except Exception` 返回 500 |
| `src/penshot/neopen/agent/workflow/workflow_error_handler.py` | 工作流错误模型与策略：`ErrorType` / `ErrorSeverity` / `ErrorAction` 枚举；`WorkflowError` 基类及 `NetworkError`、`ValidationError`、`ConfigError`、`BusinessError` 子类；`WorkflowErrorHandler` 提供错误分类、动作决策、指数退避延迟、人工干预标记等；`ErrorHandlerMiddleware` 以装饰器形式包装节点函数 |

## 3. 架构与约定

### 3.1 HTTP 层
- **参数校验**：Pydantic `field_validator` 抛出 `ValueError`，handler 显式捕获后转为 `HTTPException(400)`。
- **业务异常**：handler 直接 `raise HTTPException(status_code, detail=...)`，由全局处理器统一封装为 `{error, status_code, path}`。
- **未捕获异常**：`general_exception_handler` 记录 traceback 并返回 500 JSON。
- **中间件**：`RequestContextMiddleware` 注入请求上下文；自定义 `add_cache_control_header` 中间件仅负责响应头，不吞异常。

### 3.2 工作流层
- **错误分类**：`classify_error` 基于异常消息关键词匹配，将任意 `Exception` 归类为 `NETWORK/TIMEOUT/RATE_LIMIT/VALIDATION/CONFIG/BUSINESS/UNKNOWN` 之一。
- **严重级别**：`LOW/MEDIUM/HIGH/CRITICAL`，决定日志级别（debug/warning/error）。
- **处理动作**：`RETRY`、`DELAY_RETRY`（指数退避）、`REPAIR`（标记需要修复）、`HUMAN`（人工介入）、`ABORT`（中止流程）、`IGNORE`。
- **状态联动**：动作执行会更新 `ExecutionState`（重试计数、recovery_flags、needs_human_review、should_abort），供上层编排器消费。
- **中间件包装**：`ErrorHandlerMiddleware.wrap_node` / `wrap_node_async` 以装饰器方式包裹节点，确保每个节点异常都能被分类、记录并驱动状态机。

### 3.3 跨层协作
- API handler → 调用任务工厂 → 进入工作流 → 工作流内部抛出自定义 `WorkflowError` 或第三方异常 → `WorkflowErrorHandler` 分类并驱动重试/修复 → 最终结果回传至 API，再由全局异常处理器输出 JSON。

## 4. 开发者应遵循的规则

1. **API 层**
   - 输入校验优先用 Pydantic `field_validator` 抛 `ValueError`，不要手动写 if-else。
   - 业务失败路径显式 `raise HTTPException(status_code, detail=...)`，避免返回裸 Python 异常。
   - 仅在确实需要时 catch `Exception` 作为兜底，并记录日志。

2. **工作流层**
   - 新增领域错误时继承 `WorkflowError`，选择合适的 `ErrorType` 与 `ErrorSeverity`。
   - 若需自定义处理逻辑，通过 `register_handler(ErrorType.X, handler)` 注册，而非修改默认分支。
   - 在节点函数中使用 `ErrorHandlerMiddleware.wrap_node` 装饰，确保异常能被分类和记录。
   - 不要在工作流节点内直接 `sys.exit()` 或 `raise SystemExit`，应通过设置 `execution_state.should_abort = True` 让编排器终止。

3. **日志与可观测性**
   - 所有异常路径均通过 `penshot.logger` 的 `info/warning/error/debug` 输出，便于集中采集。
   - 工作流错误报告可通过 `format_error_report(error_state)` 获取完整历史，用于告警或审计。
