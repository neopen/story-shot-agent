---
kind: external_dependency
name: Redis 任务持久化与缓存
slug: redis
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### Redis 任务存储与缓存
- 可选依赖，用于任务记录持久化和跨进程恢复
- 连接配置：`PENSHOT_REDIS_URL` 或独立的 host/port/db/password 参数
- 连接池配置：最大连接数、超时时间、重试策略等
- 与内存后端并存，通过 TaskRepository 抽象切换