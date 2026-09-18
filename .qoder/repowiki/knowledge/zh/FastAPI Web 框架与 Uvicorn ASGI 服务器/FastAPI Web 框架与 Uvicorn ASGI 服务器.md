---
kind: external_dependency
name: FastAPI Web 框架与 Uvicorn ASGI 服务器
slug: fastapi-uvicorn
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### FastAPI + Uvicorn 服务栈
- Web 框架：FastAPI（可选依赖组 `api`），ASGI 服务器：Uvicorn（核心依赖）
- 启动入口：`main.py` 中的 `NeopenApp` 类，支持热重载和多进程模式
- REST API 路由：`src/penshot/api/rest_api.py`，前缀 `/api/v1`，提供分镜生成、任务管理、批量处理等接口
- 健康检查：`/health` 端点返回服务状态和统计信息