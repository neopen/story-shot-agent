# PenShot Project SKILL Framework

## S - Structure & Architecture (结构与架构)
| 维度 | 规范要求 | 状态 |
| :--- | :--- | :--- |
| **架构范式** | **Multi-Agent (LangGraph)**: 采用 Plan-and-Execute 模式，包含解析、规划、生成、审计等智能体节点。 | [x] |
| **核心模块划分** | **感知层**: Script Parser, Video Splitter<br>**决策层**: Temporal Planner, Continuity Guardian<br>**执行层**: Prompt Converter, Auxiliary Generator<br>**记忆层**: Short/Mid/Long-term Memory + Chroma Vector Store | [x] |
| **Python 技术栈** | Python 3.10+ \| LangGraph \| Pydantic v2 \| AsyncIO \| ChromaDB \| Redis | [x] |
| **代码规范** | PEP 8 + ruff 格式化 \| mypy 严格类型检查 \| 结构化日志 (`penshot.logger`) | [x] |
| **状态管理** | **显式图工作流 (StateGraph)**: 通过 `TaskStage` 枚举管理生命周期，支持断点续跑与任务持久化。 | [x] |

## K - Knowledge & Context Management (知识与上下文)
| 维度 | 规范要求 | 状态 |
| :--- | :--- | :--- |
| **知识源类型** | 静态模板 (Prompt Templates) \| 向量库 (Chroma) \| 实时 LLM API \| Redis 缓存 | [x] |
| **上下文策略** | **滑动窗口 + 摘要压缩**: 针对长剧本进行分块处理，利用多级记忆系统保持跨镜头连贯性。 | [x] |
| **检索增强 (RAG)** | **混合检索**: 结合语义相似度 (Embedding) 与元数据过滤，确保角色/场景一致性。 | [x] |
| **知识更新机制** | 事件驱动入库：每个分镜生成后自动向 Chroma 写入向量索引。 | [x] |
| **幻觉控制** | **事实校验层**: Quality Auditor Agent 负责交叉验证提示词与原剧本的逻辑一致性。 | [x] |

## I - Integration & Tooling (集成与工具链)
| 维度 | 规范要求 | 状态 |
| :--- | :--- | :--- |
| **工具定义规范** | 基于 Pydantic 声明 Schema \| 纯函数设计 \| 保证幂等性 (通过 `task_id` 去重) | [x] |
| **内置工具清单** | `breakdown_script` (分镜拆分) \| `get_task_status` (进度查询) \| `cancel_task` (任务取消) | [x] |
| **外部系统对接** | **统一 API Gateway**: 支持 REST API (FastAPI) 与 MCP Protocol 双协议接入。 | [x] |
| **执行安全** | 异步任务沙箱隔离 \| 禁止隐式 Shell 执行 \| LLM 调用超时熔断机制 | [x] |
| **扩展机制** | 插件式 Agent 注册 \| 动态 Prompt 加载 \| 支持 Function Call 标准协议 | [x] |

## L - Lifecycle & Deployment (生命周期与部署)
| 维度 | 规范要求 | 状态 |
| :--- | :--- | :--- |
| **开发流程** | 需求评审 -> 架构设计 -> 编码 -> 单元/集成测试 (`pytest`) -> 压测 -> 灰度发布 | [x] |
| **工程化配置** | `pyproject.toml` 管理依赖 \| `uv` 锁版本 \| pre-commit 钩子 (lint/format) | [x] |
| **部署形态** | Docker 容器化 \| CPU/GPU 资源隔离 \| 环境变量注入配置 | [x] |
| **可观测性** | 全链路 TraceID 追踪 \| 关键指标监控 (Token 消耗/处理延迟/队列长度) | [x] |
| **版本管理** | Git Flow \| Semantic Versioning \| 蓝绿部署支持 | [x] |

## L - Limits, Security & Evaluation (边界、安全与评估)
| 维度 | 规范要求 | 状态 |
| :--- | :--- | :--- |
| **能力边界声明** | **不支持**: 实时视频渲染、复杂物理仿真。<br>**拦截**: 敏感/违规内容自动拒答并记录审计日志。 | [x] |
| **安全合规** | Prompt 注入防御 \| API Key 环境变量隔离 \| 审计日志留存 > 180天 | [x] |
| **评估体系** | 任务完成率 \| 提示词可用性评分 \| 叙事连贯性 (Continuity Score) \| Token 成本 | [x] |
| **评估工具** | Pytest 自动化测试 \| LangSmith 链路追踪 \| 自定义 Benchmark 数据集 | [x] |
| **持续优化闭环** | A/B 测试不同 LLM 模型效果 \| 用户反馈收集 -> 提示词迭代 -> 回归测试 | [x] |

---

### ⚠️ 工程落地检查清单 (Checklist for AI)
1.  **架构一致性**: 新增代码是否符合 LangGraph 的状态流转逻辑？是否避免了全局变量污染？
2.  **上下文完整性**: 在处理长文本时，是否正确调用了 `settings.get_data_paths()` 并维护了记忆上下文？
3.  **工具安全性**: 所有工具调用是否具备 Pydantic 校验、超时设置及异常重试逻辑？
4.  **安全扫描**: 是否已对输入剧本进行了基础的敏感词过滤？日志中是否脱敏了 API Key？
5.  **可量化评估**: 新增功能是否通过了 `tests/` 目录下的单元测试？是否更新了相关文档？

