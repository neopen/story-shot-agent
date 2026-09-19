# 更新日志 (CHANGELOG)

本项目的所有重要变更都将记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

---

## [0.3.8](https://github.com/neopen/story-shot-agent/compare/v0.3.7...v0.3.8) (2026-09-19)


### 🐛 Bug Fixes (问题修复)

* 修复并完善基于本地规则解析剧本，如果LLM异常将自动启用规则解析，但是效果将大打折扣 ([#60](https://github.com/neopen/story-shot-agent/issues/60)) ([f47d086](https://github.com/neopen/story-shot-agent/commit/f47d08650dc665760a18a7692fd77ba0330ff27a))


### 🔧 Other Changes (其他变更)

* Delete .qoder directory ([50dff09](https://github.com/neopen/story-shot-agent/commit/50dff0972ee0af101ef5c4840655a7a64d72c758))
* **deps:** bump actions/dependency-review-action from 4 to 5 ([#52](https://github.com/neopen/story-shot-agent/issues/52)) ([9b5ac0a](https://github.com/neopen/story-shot-agent/commit/9b5ac0abeb2795d6d7a62c8ab6230919d53f05c8))
* 代码合并 ([#57](https://github.com/neopen/story-shot-agent/issues/57)) ([3b2c998](https://github.com/neopen/story-shot-agent/commit/3b2c998b8af68908193773dca3d1c072764f5ff7))
* 合并dev ([#59](https://github.com/neopen/story-shot-agent/issues/59)) ([285fed9](https://github.com/neopen/story-shot-agent/commit/285fed9bfcd2183457ae9b6ef5aef4fe7b311029))

## [Unreleased] - 未发布

### 新增
- Redis 任务持久化支持与服务重启自动恢复功能
- 批量处理接口 (`penshot batch`) 支持
- 基于 Gradio/Streamlit 的 Web UI 演示界面
- 多智能体流水线中的“质量审查智能体”

### 变更
- **任务管理系统重构**：采用任务工厂模式重构队列管理逻辑，提升并发稳定性
- 优化全局错误捕获机制与 Structured Logging 日志格式

### 修复
- 修复高并发请求下异步事件循环 (Event Loop) 阻塞的问题
- 修复长任务排队时的队列饥饿 (Queue Starvation) 现象
- 修复 LangGraph 工作流节点状态缓存导致的内存泄漏问题

---

## [0.1.0] - 2024-01-20

### 新增
- **MVP 核心功能发布**：支持自然语言与标准格式剧本解析
- 智能镜头拆分：基于场景切换与对话流自动分镜（默认支持 5 秒强制片段切割）
- 提示词引擎：支持多模态提示词生成（包含文本描述、风格及音频提示词）
- **多协议集成支持**：
  - REST API 交互：支持同步/异步任务提交、状态查询及任务取消
  - MCP（Model Context Protocol）服务器模式 (`penshot serve`)
  - Python SDK 高级函数接口 (`PenshotFunction`)
- CLI 命令行工具集（`breakdown`, `serve`, `serve-rest`, `status`, `batch`）

### 已知问题
- `v0.1.0` 暂未完全支持 Redis 持久化恢复（将在 `v0.2.0` 正式提供）
- 暂不支持实时 WebSocket 推送状态变化

---

## [0.0.1] - 2024-01-01

### 新增
- 项目脚手架与基础代码架构搭建
- Pydantic-Settings 配置管理与基本 Logging 模块
- GitHub Actions CI/CD 流水线（自动化 pytest 验证与 PyPI 构建发布）

---

## 升级指南与 API 破损性变更

### 从 `0.0.x` 升级至 `0.1.0`

API 交互由直调函数重构为面向对象的 Agent 工厂：

```python
# 旧版 API (0.0.x)
from penshot import generate_storyboard
result = await generate_storyboard(script)

# 新版 API (0.1.0+)
from penshot import PenshotFunction
agent = PenshotFunction()
result = agent.breakdown_script(script)
```

版本控制策略
主版本号 (X.0.0)：包含不兼容的 API 破坏性变更 (Breaking Changes)

次版本号 (0.X.0)：向下兼容的功能性新增 (Features)

修订号 (0.0.X)：向下兼容的紧急修复与性能优化 (Patches)

完整贡献者列表请参阅 [CONTRIBUTORS.md](./contributors.md)。
