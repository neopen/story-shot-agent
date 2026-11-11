# 更新日志 (CHANGELOG)

本项目的所有重要变更都将记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

---

## [0.4.4](https://github.com/neopen/story-shot-agent/compare/v0.4.2...v0.4.4) (2026-11-11)


### 🐛 Bug Fixes (问题修复)

* 角色外观锚点：自由文本只保留外观子句，字段白名单首值优先，长度只在子句边界截断，避免情绪/动作词与半截词污染锚点。
* 风格维度：按题材/氛围补齐六维风格前缀，互斥打光只保留一个家族，题材别名归一化并输出溯源。
* 资产引用：角色三视图与道具静帧不再作为首帧，`asset_ref` 只代表片段首帧；回填 `usage.fragments` 并与路由引用保持一致。
* 景别一致性：`camera.shot_type` 以最终提示词为准，保留来源景别与原始值溯源，两个转换器口径统一。
* 提示词模板召回：修复索引加载以旧文件名判空导致零命中、单文档索引覆盖既有索引的问题；新增结构化检索诊断与只读召回快照，支持跨剧本只读召回。
* 模板入库：质量审查与记忆层共用统一入库策略，模板写入 `source` / `audit_status`，legacy 模板默认排除在召回之外。
* 质量门禁：新增外观锚点污染、景别与提示词不一致、互斥打光并存、资产使用范围缺失四条规则，违规在 `quality_auditor_result.json` 中带可定位的 `fragment_id` / `asset_id`。
* 场景连续性：跨场景切换改为确定性插入过渡镜头，修复 `scene_jump` 重试仍反复重跑分镜、问题无法消解的问题。
* 外观连续性：单轮比较改为主体服装集合，配饰与鞋履增删不再被误报为“外观变化”并触发反复修复。
* 首帧提示词：非角色占位名归一为空，修复旧产物首帧提示词拼出“of 无”的残句。
* 图生视频路由：片段所属场景已登记场景资产时不再退化为文生视频，无主角色片段同样以场景首帧走两段式生成。

### ⚠️ 升级与迁移

* `CONTRACT_SCHEMA_VERSION` 提升至 `0.4.4`，`pyproject.toml` 与 `penshot.__version__` 同步；新增字段均为可选，旧 `asset_manifest` 与 SDK 调用方式保持可用。
* 0.4.3 已入库的缺陷模板需一次性迁移：`python scripts/migrate_prompt_templates_044.py` 默认 dry-run（只输出统计，不写文件），确认后加 `--apply` 写入；`--script-id` 可限定单剧本。
* 迁移会先备份各剧本的 `templates_cache.json` 与 `index_store/` 到带时间戳的备份目录；缺陷模板只做隔离标记，不删除底层数据；迁移完成后从活跃缓存全量重建索引。
* 召回阈值默认 `min_similarity_score = 0.80`、`top_k = 2`、`max_injected_patterns = 6`，跨剧本召回默认开启；可通过 `PENSHOT_PROMPT_TEMPLATES__*` 覆盖。

## [0.4.2](https://github.com/neopen/story-shot-agent/compare/v0.4.1...v0.4.2) (2026-11-06)


### ✨ Features (新功能)

* M0.4.2 声明式资产计划、下游交接与人工资产编辑 ([#86](https://github.com/neopen/story-shot-agent/issues/86)) ([b71bcc7](https://github.com/neopen/story-shot-agent/commit/b71bcc7e8e223ff25e2f2ab923df9adeca278869))

## [0.4.1](https://github.com/neopen/story-shot-agent/compare/v0.4.0...v0.4.1) (2026-11-05)


### ✨ Features (新功能)

* M0.4.1 连续性前置约束收尾与报告加固 ([#83](https://github.com/neopen/story-shot-agent/issues/83)) ([ff39355](https://github.com/neopen/story-shot-agent/commit/ff393559abb822da02172942c009aec13ed0fcf9))

## [0.4.0](https://github.com/neopen/story-shot-agent/compare/v0.3.12...v0.4.0) (2026-11-03)


### ✨ Features (新功能)

* 新增 M0.4.0 目标模型适配层并接入主链路 ([#81](https://github.com/neopen/story-shot-agent/issues/81)) ([6da4606](https://github.com/neopen/story-shot-agent/commit/6da460668cf4814b81166878ee9eb80a2399168f))


### 📝 Documentation (文档更新)

* 文档内容更新 ([#78](https://github.com/neopen/story-shot-agent/issues/78)) ([140bd76](https://github.com/neopen/story-shot-agent/commit/140bd769dc6232a134f38e5b9c41eae5ee40f0ea))

## [0.3.12](https://github.com/neopen/story-shot-agent/compare/v0.3.11...v0.3.12) (2026-11-01)


### 🐛 Bug Fixes (问题修复)

* 修复 Qwen 私有 MaaS 连接、嵌入兼容与 JSON 截断，对齐路径配置结构 ([#76](https://github.com/neopen/story-shot-agent/issues/76)) ([c456bd8](https://github.com/neopen/story-shot-agent/commit/c456bd8367f0f681c6d3028ef8144a6b8629e5d2))

## [0.3.11](https://github.com/neopen/story-shot-agent/compare/v0.3.10...v0.3.11) (2026-10-14)


### 🐛 Bug Fixes (问题修复)

* 修复qwen模型依赖问题 ([#69](https://github.com/neopen/story-shot-agent/issues/69)) ([9225455](https://github.com/neopen/story-shot-agent/commit/922545582b0bcae936a0bd74e0566f5d23b5fb37))

## [0.3.10](https://github.com/neopen/story-shot-agent/compare/v0.3.9...v0.3.10) (2026-10-13)


### ♻️ Code Refactoring (代码重构)

* Docker 配置 ([#67](https://github.com/neopen/story-shot-agent/issues/67)) ([d00c0b0](https://github.com/neopen/story-shot-agent/commit/d00c0b0cc7841b7298bb36e98aeec20ae4c9b4e3))

## [0.3.9](https://github.com/neopen/story-shot-agent/compare/v0.3.8...v0.3.9) (2026-10-13)


### 🔧 Other Changes (其他变更)

* 优化LLM客户端，支持OpenAI兼容-Chat，修改默认配置 ([#63](https://github.com/neopen/story-shot-agent/issues/63)) ([ec74762](https://github.com/neopen/story-shot-agent/commit/ec7476276ebceb198d79f33da45dc0707b56463c))

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
- M0.4.1 连续性前置约束收尾：连续性修复回路与 `continuity_report.json` / `repair_history.json` 落盘
- M0.4.1 收尾验收报告（`docs/testing/M0.4.1 收尾验收报告.md`）

### 变更
- **任务管理系统重构**：采用任务工厂模式重构队列管理逻辑，提升并发稳定性
- 优化全局错误捕获机制与 Structured Logging 日志格式

### 修复
- 修复高并发请求下异步事件循环 (Event Loop) 阻塞的问题
- 修复长任务排队时的队列饥饿 (Queue Starvation) 现象
- 修复连续性报告异步落盘无法等待的问题；报告补充累计检测问题统计
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
