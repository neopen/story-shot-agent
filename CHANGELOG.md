# 更新日志 (CHANGELOG)

本项目的所有重要变更都将记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

---

## [0.4.9](https://github.com/neopen/story-shot-agent/compare/v0.4.8...v0.4.9) (2026-11-26)


### 🐛 Bug Fixes (问题修复)

* **quality:** 分镜链路误报收口（运镜/道具/角色/地点/审计循环） ([#110](https://github.com/neopen/story-shot-agent/issues/110)) ([c9d3d8c](https://github.com/neopen/story-shot-agent/commit/c9d3d8ca623d48ec540f6cebfdf8209188aa1858))


### 🔧 Other Changes (其他变更)

* **license:** 协议由 MIT 迁移为 Apache-2.0 ([#108](https://github.com/neopen/story-shot-agent/issues/108)) ([0c53724](https://github.com/neopen/story-shot-agent/commit/0c537244d2bac6d5dbb0602bae0d1818d52bd3cb))

## [0.4.8](https://github.com/neopen/story-shot-agent/compare/v0.4.7...v0.4.8) (2026-11-21)


### 🐛 Bug Fixes (问题修复)

* **release:** 连续性、记忆与报告一致性收口 ([#106](https://github.com/neopen/story-shot-agent/issues/106)) ([a8a1068](https://github.com/neopen/story-shot-agent/commit/a8a10681d6e23144cab36314333035e7fb190b89))


### 📝 Documentation (文档更新)

* 文档完善 ([#104](https://github.com/neopen/story-shot-agent/issues/104)) ([7ec7e9e](https://github.com/neopen/story-shot-agent/commit/7ec7e9e0215b9d0e368faf63e7a6f16d38a07d2a))


### 🐛 Bug Fixes (问题修复)

* **continuity:** 连续性问题均不可自动修复时记录 `unfixable_skipped` 轮次，报告 `final_status` 由 `not_checked` 修正为 `continued_with_issues`，不再与“检查已执行且流程继续”的事实矛盾。
* **continuity:** 外观连续性状态子句不再混入服装锚点，避免同一角色因动作/情绪被误报为外观变化。
* **reports:** `repair_history.json` 汇总质量审查阶段的修复动作，`repair_count` 与日志中的修复动作数一致；新增 `continuity_repair_count` / `quality_repair` 分列。
* **reports:** `quality_report.json` 增加 `post_repair_score`、`repair_status`、`repair_issue_count`、`repair_action_count`，修复后复检分数不再只存在于审计明细中。
* **audit:** 模型支持校验对齐能力注册表；历史阶段统计缺少完整度时不再误判为 `poor`；修复后重算阶段问题，避免空转循环。
* **workflow:** 声明 `last_audit_result` 状态字段，修复检查点恢复时字段缺失导致的审计状态不一致。

### ✨ Features (功能特性)

* **continuity:** 场景/角色锚点、状态快照、跨块校验与风格漂移检测；道具结构化解析并写入场景契约。
* **memory:** 三层记忆统一 `BaseMemoryLayer`，修复读取链路与工作流键一致性，长期记忆增加保留上限与自动清理。
* **prompt:** 片段固定 `seed`、音频链每轮重置、剧本语言推断与音频提示词归一，支持跨剧本模板迁移。
* **checkpoint:** 稳定 `thread_id` 与断点续跑，工作流缓存按任务隔离并回收检查点连接。

### 🔧 Refactoring (重构)

* **audit:** 修复参数改用确定性问题码并按真实动作结算，修复后强制复审。
* **routing:** 片段模型回写路由结果，计划场景作为首帧唯一权威，必需资产待生成时显式标记。

### ✅ Tests (测试)

* 新增记忆、连续性、审查、路由、检查点回归用例，覆盖快照、锚点、seed、误报与模板迁移。
* 连续性节点测试注入 `style_guardian` 并复用真实检查器快照能力；索引检索测试显式包装 `LangchainEmbedding`，兼容当前 llama-index/langchain-community 版本组合。
* 新增报告一致性用例，锁定质量修复汇总与修复历史的字段契约。

### ⚠️ 升级与迁移

* 无破坏性改动，无需数据迁移；配置项与 SDK 调用方式保持不变。
* 报告新增字段均为可选：`quality_report.json` 的 `post_repair_score` / `repair_status` / `repair_issue_count` / `repair_action_count`，`repair_history.json` 的 `continuity_repair_count` / `quality_repair`。
* `continuity_report.json` 的 `final_status` 新增取值 `continued_with_issues`，对应“已检查、存在不可自动修复问题、流程继续”的场景；依赖旧枚举值的下游请按未知值兜底处理。

## [0.4.7](https://github.com/neopen/story-shot-agent/compare/v0.4.6...v0.4.7) (2026-11-20)


### 🐛 Bug Fixes (问题修复)

* 0.4.7 场景权威、契约修复与 P0~P2 质量收口 ([#101](https://github.com/neopen/story-shot-agent/issues/101)) ([308e7c2](https://github.com/neopen/story-shot-agent/commit/308e7c20011175d84d03b5febd010181ad093d30))
* **continuity:** 复合主角色按角色粒度校验，审计只采信复检 (0.4.7 T-118) ([#103](https://github.com/neopen/story-shot-agent/issues/103)) ([d4fd006](https://github.com/neopen/story-shot-agent/commit/d4fd006dbd1b069cdb0f0b9fd3730c4ec3373a26))

### 场景与首帧

* 片段所属场景已登记首帧资产时，以计划场景作为唯一权威，不再退化为文生视频（T-101）。
* 按计划地点重写提示词；地点冲突直接阻断片段，并在告警中给出计划地点与期望首帧资产（T-102/T-113）。
* 计划场景与首帧资产不一致计入契约违规，参与质量审查与修复（T-103）。
* 景别表述统一归一、收紧景别探测，保留 POV 等主观视角（T-105）。
* 地点解析改为 `scene_id` → `continuity_notes` 场景 → 剧本唯一地点名，歧义时跳过而非猜错；每轮只输出一条改写汇总，单条跳过降为 DEBUG（T-113）。

### 契约与修复回路

* 修复参数改用确定性问题码并按真实动作结算，避免“假修复”与空转重试（T-104）。
* 修复状态按优先级保留；已收敛项、降级项与人工项同源，不再重复计入 `requires_manual_fix`（T-111）。
* `unknown_character` 区分剧本真实角色与生成幻觉：真实角色补登记契约后即收敛，只对幻觉角色派发修复（T-114）。
* 复合主角色（如“李明、张晨”）按角色粒度校验与修复，不再整串误报为未知角色（T-118）。
* 风格问题改为确定性收敛：统一 `[Style: ...]` 前缀并移除冲突风格短语；无可靠风格来源时诚实转人工，不再无效重试或报 `repaired`（T-115）。
* 审计节点与修复后复检只采信最终产物快照，已收敛的历史违规不再重复扣分（T-118）。

### 审计与可观测性

* 审计状态、分数与结论统一按检查通过率计算，结论列出未通过的检查项（P0-2）。
* 测试运行不再写入 `logs/penshot_<date>.log`；新增 `PENSHOT_LOG_TO_FILE` / `PENSHOT_LOG_FILE` 控制文件日志开关与路径（P0-1）。
* 计划模式下资产 pending 日志由 WARNING 降为 INFO，并输出实际待生成数量（T-116）。
* 超长片段截断写入 `dropped_duration` / `manual_review_required`，并在片元序列元数据输出 `truncation_report`，便于下游与人工复核（T-117）。
* 运镜冲突词表与同族判定对齐，减少同义运镜被误判（T-112）。

### 升级说明

* 无破坏性改动，无需数据迁移；契约 schema 版本保持 `0.4.4`。
* 新增元数据均为可选字段：`scene_prompt_realign_summary`、`truncation_report`、截断片段的 `dropped_duration` / `manual_review_required`。
* 需要区分测试与生产日志时，可设置 `PENSHOT_LOG_TO_FILE=0` 关闭文件日志，或用 `PENSHOT_LOG_FILE` 指定日志路径。

## [0.4.6](https://github.com/neopen/story-shot-agent/compare/v0.4.5...v0.4.6) (2026-11-17)


### 🐛 Bug Fixes (问题修复)

* **security:** harden config env expansion, callback_url SSRF, and public config exposure ([#88](https://github.com/neopen/story-shot-agent/issues/88)) ([#89](https://github.com/neopen/story-shot-agent/issues/89)) ([e445f0d](https://github.com/neopen/story-shot-agent/commit/e445f0d7a4b67690a0f43acec59d1ba5c446d401))


### ♻️ Code Refactoring (代码重构)

* **security:** 抽取统一 penshot/security 包并强化扩展性 ([#99](https://github.com/neopen/story-shot-agent/issues/99)) ([95bc4a1](https://github.com/neopen/story-shot-agent/commit/95bc4a1f05f34c75fd6e5d3b52aa98bacb5a82d9))

## [0.4.5](https://github.com/neopen/story-shot-agent/compare/v0.4.4...v0.4.5) (2026-11-14)


### 🐛 Bug Fixes (问题修复)

* 0.4.5 分镜缺陷修复与资产链收口 ([#95](https://github.com/neopen/story-shot-agent/issues/95)) ([4390f32](https://github.com/neopen/story-shot-agent/commit/4390f32243ea11402a55e0901a0cd885a6ae0b42))

## [0.4.4](https://github.com/neopen/story-shot-agent/compare/v0.4.3...v0.4.4) (2026-11-11)


### 🐛 Bug Fixes (问题修复)

* 0.4.4 连续性闭环与首帧语义加固 ([#92](https://github.com/neopen/story-shot-agent/issues/92)) ([db11924](https://github.com/neopen/story-shot-agent/commit/db1192476be63859878bb21a1a2da75b54f302ca))


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


## [0.4.3](https://github.com/neopen/story-shot-agent/compare/v0.4.2...v0.4.3) (2026-11-09)


### ✨ Features (新功能)

* **routing:** 新增模型路由与结构化相机控制（M0.4.3） ([4927378](https://github.com/neopen/story-shot-agent/commit/4927378e44962e0dd200c03353912f6a06d8b1cc))
* 新增模型路由与结构化相机控制（0.4.3） ([#90](https://github.com/neopen/story-shot-agent/issues/90)) ([8c12840](https://github.com/neopen/story-shot-agent/commit/8c128409650543f7c2f0d680904ef1f8826b8a7f))


### 🐛 Bug Fixes (问题修复)

* **continuity:** 修复 time_gap 反复重试与连续性节点崩溃 ([dcbd097](https://github.com/neopen/story-shot-agent/commit/dcbd097764030822aa0edc1f6ccf926abc87f8fc))


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
