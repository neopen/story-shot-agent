# PenShot 边界与职责

## 1. 文档目的

本文固定 PenShot 在 NeoTask 生态中的职责边界，作为后续版本设计、契约变更和代码评审的基线。

核心原则：

- 每个智能体只承担单一职责
- PenShot 只做“剧本到镜头指令”的翻译
- 生成、音频、剪辑、成片审核由下游模块负责
- 下游模块只消费 PenShot 的交接清单，不回读剧本

## 2. NeoTask 生态定位

| 模块 | 唯一职责 | 输入 | 输出 | 明确不做 |
| --- | --- | --- | --- | --- |
| PenPlot | 剧情创作 | 创意、剧本 | 剧情、角色、台词 | 分镜、生成、音频 |
| **PenShot** | **剧本分镜** | 剧本、剧情设定 | 场景、镜头、片段、提示词、相机、情绪、节奏、资产规格 | 图像/视频/音频生成、音频同步、剪辑、成片审核、跨模块调度 |
| PenGen | 视频生成 | PenShot 交接清单 | 视频片段 | 分镜、剪辑、音频同步 |
| PenDub | 音频同步 | 台词线索、音频上下文、时间轴 | 音频轨道、唇形对齐 | 分镜、视频生成 |
| PenClip | 视频剪辑 | 视频、音频轨道 | 成片 | 分镜、生成 |
| PenFix | 质量审核 | 成片 | 质量报告、退回意见 | 分镜、生成、剪辑 |
| NeoTask | 任务池、事件总线 | 各模块事件 | 调度、共享状态 | 业务逻辑 |

协作方式：PenShot 完成分镜后发布 `shot_plan.ready` 事件，通过 NeoTask DATA BUS 唤醒 PenGen 与 PenDub。PenShot 不直接调用下游模块。

音频职责说明：原生音频模型（如 Veo、Sora）的音画同出属于视频生成的一部分，由 PenGen 执行；独立音轨的制作与对齐归 PenDub。PenShot 只交接结构化音频意图（台词、氛围、时间），不携带任何 TTS/音效生成执行参数。

## 3. PenShot 定义

**一句话定义**：把剧本翻译成可执行的镜头指令清单，不执行任何生成、音频、剪辑和成片审核。

### 3.1 输入

- 任意格式剧本：纯文本、结构化剧本、分场大纲
- PenPlot 产出的剧情、角色、台词设定
- `ShotConfig`：片段时长、提示词长度、节奏档位、总时长目标
- 历史上下文与记忆：角色、场景、道具、风格
- 可选资产引用：上游已生成的资产 ID 与路径
- 剪辑决策事件 `edit_decisions`（来自 PenClip，经 NeoTask，用于反向适配）

### 3.2 输出

- 场景、镜头、片段结构
- 每个片段不超过 5 秒
- 正向提示词、负向提示词
- 结构化相机控制
- 情绪标签与节奏提示
- 资产规格与资产清单，不含资产二进制
- 台词线索 `dialogue_cues`（说话人、情绪、片段内时间偏移、预计朗读时长）
- 场景音频上下文 `audio_context`（氛围音描述，不含生成参数）
- 目标模型兼容性建议
- 镜头清单 `shot_list`
- 交接清单 `HandoffManifest`

### 3.3 明确不做

- 调用文生图、文生视频、TTS、音效生成客户端
- 音频同步、唇形对齐、配音克隆
- 剪辑时间线、转场执行、成片组装
- 成片质量审核与视频级 VQA
- 跨模块任务编排与调度

## 4. 智能体单一职责

| 组件 | 唯一职责 | 不承担 |
| --- | --- | --- |
| `script_parser` | 剧本解析为结构化场景、角色、台词、动作 | 分镜、生成 |
| `shot_segmenter` | 叙事单元切分为镜头并估算时长 | 片段切分、提示词 |
| `video_splitter` | 镜头切分为不超过 5 秒的片段，维护时间轴不变量 | 提示词、生成 |
| `prompt_converter` | 片段转换为视觉提示词、镜头指令与台词线索 | 音频提示词创作、TTS 执行配置、生成 |
| `quality_auditor` | 指令级自检：格式、时长、长度、完整性 | 成片审核、视频 VQA |
| `continuity_guardian` | 跨片段一致性检查与修复建议生成 | 成片审核、生成 |
| `model_adapter` | 按目标模型能力适配提示词结构（含原生音频模型的音频 cues 渲染） | 最终模型选型与执行 |
| `asset_generator` | 声明资产规格与清单 | 资产二进制生成 |

### 4.1 当前职责偏差

| 组件 | 偏差 | 收口方向 |
| --- | --- | --- |
| `prompt_converter` | 音频提示词混入 TTS 执行参数（模型、音色、语速） | 执行参数迁出归 PenDub；台词与氛围意图改为 `dialogue_cues` + `audio_context` 交接 |
| `model_adapter` / `model_router` | 适配提示词并直接决定目标模型 | 只输出兼容性建议，执行选型归 PenGen |
| `asset_generator` | 声明资产规格，同时内置图像生成执行器 | 只保留声明，执行器移出默认路径 |
| `quality_auditor` | 名称容易被理解为成片审核 | 明确定义为指令自检，成片审核归 PenFix |
| `continuity_guardian` | 检查与修复生成耦合在同一包内 | 保持检查器与修复生成器两个独立组件 |

## 5. 输出字段归属

任何新增输出字段必须先在本文登记 owner，再进入契约。

| 输出字段 | Owner | 消费方 | 说明 |
| --- | --- | --- | --- |
| `scenes` / `shots` / `fragments` | PenShot | PenGen、PenClip | 分镜结构 |
| `prompt` / `negative_prompt` | PenShot | PenGen | 视觉提示词 |
| `camera` | PenShot | PenGen | 结构化相机控制 |
| `emotion` | PenShot | PenGen、PenDub | 情绪标签 |
| `pacing` | PenShot | PenGen、PenClip | 节奏提示 |
| `asset_specs` / `asset_manifest` | PenShot | PenPlot、PenGen | 只含规格与引用，不含文件 |
| `dialogue_cues` | PenShot → PenDub/PenGen | PenDub、PenGen（原生音频） | 台词、说话人、情绪、片段内偏移、预计朗读时长 |
| `audio_context` | PenShot → PenDub/PenGen | PenDub、PenGen | 场景级氛围音描述，不含生成参数 |
| `compat` / `route_plan` | PenShot → PenGen | PenGen | 兼容性与音频路径（native/dub）建议，不是执行决策 |
| `shot_list` | PenShot → PenClip/PenFix | PenClip、PenFix | 镜头清单 |
| `audio_prompt` | PenDub | PenDub | 迁出 PenShot |
| `quality_report` | PenFix | PenFix | 不在 PenShot 输出 |

## 6. 交接契约

### 6.1 HandoffManifest

```text
HandoffManifest
├─ schema_version
├─ task_id
├─ shot_plan
│  ├─ scenes
│  ├─ shots
│  └─ fragments（prompt、negative_prompt、camera、emotion、pacing）
├─ asset_specs
├─ compat（required_capabilities、recommended_model、requires_confirmation、audio_path）
├─ dialogue_cues（供 PenDub、PenGen 原生音频）
├─ audio_context（场景级氛围音，供 PenDub、PenGen）
└─ shot_list（供 PenClip、PenFix）
```

### 6.2 台词与音频交接契约

```text
DialogueCue
├─ cue_id
├─ fragment_id               # 归属片段
├─ speaker                   # 说话人（角色 ID 或旁白）
├─ text                      # 台词原文
├─ emotion                   # 与片段情绪一致
├─ start_offset              # 片段内起始秒
├─ end_offset                # 片段内结束秒
└─ expected_speech_duration  # 预计朗读时长（中文按 4–5 字/秒估算）
```

约束：

- `0 ≤ start_offset < end_offset ≤ fragment.duration`
- `expected_speech_duration ≤ end_offset - start_offset`，含台词片段时长必须装得下台词
- 全局时间码由片段起始时间派生，时间轴重建后重新派生
- `audio_context` 为场景级氛围描述（如"雨夜、远处车流"），来源于剧本解析
- `compat.audio_path` 取值 `native | dub`：原生音频模型建议 `native`（口型同步由生成模型保证）；静默模型或需跨片段统一音色时建议 `dub`。最终选择归下游，必要时 `requires_confirmation`
- 音频意图字段只承载结构化意图与时间信息，禁止混入 TTS 模型、音色、语速、音高等执行参数

### 6.3 事件

| 事件 | 发布方 | 消费方 | 时机 |
| --- | --- | --- | --- |
| `shot_plan.ready` | PenShot | PenGen、PenDub | 分镜与提示词转换完成后 |

完整事件目录、事件信封、路由规则与循环控制见 `docs/NeoTask 协作契约.md`。

### 6.4 发布方式

- 定义 `HandoffSink` 协议，由外部注入实现
- 默认 `NullHandoffSink`，不产生网络调用
- 测试使用 `InMemoryHandoffSink`
- 由输出阶段统一发布，不新增工作流节点

## 7. 当前越界点与迁移

| 越界点 | 代码位置 | 迁移目标 |
| --- | --- | --- |
| 音频提示词 | `prompt_converter_models.py` 的 `AIVideoPrompt.audio` | TTS 执行参数归 PenDub；台词/氛围意图改为 `dialogue_cues` + `audio_context` 交接 |
| 目标模型选择 | `model_adapter/model_router.py` 的 `RoutePlan` | 改为兼容性建议，选型执行归 PenGen |
| 资产生成执行器 | `asset_generator/execution_adapter.py` 的 `ImageClientExecutionAdapter` | 移出默认路径，资产生成归 PenPlot/PenGen |
| 成片审核语义 | `quality_auditor_agent.py` 命名 | 明确为指令自检，成片审核归 PenFix |

迁移在 0.5.0 的 M0.5.0.0 里程碑完成，旧字段保留一个版本作为 deprecated 兼容。

## 8. 守护规则

1. 新增输出字段必须先登记 owner
2. 默认工作流禁止实例化任何图像、视频、音频客户端
3. 下游模块不允许回读剧本，只能消费 `HandoffManifest`
4. 任何跨模块调用必须通过 NeoTask 事件，不允许模块间直接导入
5. PR 评审必须检查是否扩大 PenShot 边界
6. 边界测试必须覆盖字段归属、默认路径导入、交接清单结构
7. `dialogue_cues` / `audio_context` 只承载意图与时间信息，禁止携带 TTS 执行参数

## 9. 非目标

- 多租户与计费
- 分布式任务调度
- 视频级质量评估
- 多模态交互与实时预览
- 插件市场与协作编辑
