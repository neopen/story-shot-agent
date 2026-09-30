# .qoder/ 目录说明

> `.qoder/` 是 Qoder Agent 的上下文知识库，集中存放项目理解、行为规则、Agent Skill 与模块级的知识卡。
> 本目录内的文档仅服务于 Agent 与开发者参考，不替代 `docs/` 下的人类架构文档。

---

## 目录结构

```
.qoder/
├── README.md                      # 本文件：目录索引与使用指南
├── SPEC.md                        # 本次整理的范围契约（SDD 阶段2产物）
├── PLAN.md                        # 实现计划（SDD 阶段3产物）
├── TASKS.md                       # 原子任务清单（SDD 阶段4产物）
├── project_understanding.md       # 项目整体导览（人类可读，含业务定位、技术栈、架构分层）
├── rules/                         # Agent 行为规则
│   ├── SDD-Agent.md               # always_on：规格驱动开发流程（最高优先级）
│   ├── coding-standards.md        # on_request：Python 编码规范
│   └── architecture-guardrails.md # on_request：架构禁区与调用约定
├── skills/                        # Agent Skill
│   └── penshot-dev/
│       ├── skill.json             # Skill 元数据
│       ├── SKILL.md               # Skill 使用说明
│       ├── prompts/
│       │   └── system_prompt.md   # 系统提示词
│       └── references/
│           └── coding_standards.md # Skill 内快速参考
└── repowiki/                      # 模块级知识卡（由工具生成/维护）
    ├── knowledge/zh/_index.yaml
    ├── knowledge/zh/<模块名>/...  # 模块知识卡
    ├── zh/content/...             # 内容文档
    └── zh/meta/repowiki-metadata.json
```

---

## 各目录用途

### `rules/`

约束 Agent 在不同场景下的行为。

- `SDD-Agent.md`（always_on）：所有会话自动生效，规定必须按 Spec → Plan → Tasks → 实现的阶段门禁执行。
- `coding-standards.md`（on_request）：代码生成、审查、重构时启用。
- `architecture-guardrails.md`（on_request）：架构调整、新增模块、重构时启用。

### `skills/`

可触发的 Agent Skill，封装特定能力。当前仅 `penshot-dev`：面向 PenShot 项目开发的综合助手。

### `repowiki/`

模块级知识库，按项目模块组织知识卡。由工具导出/维护，提供比 `project_understanding.md` 更细粒度的模块信息。

### `project_understanding.md`

项目的快速导览，帮助新成员或 Agent 建立整体认知。

---

## 阅读顺序建议

1. 新成员/新会话：`README.md` → `project_understanding.md`
2. 进入开发任务：`rules/SDD-Agent.md` → `rules/coding-standards.md` / `rules/architecture-guardrails.md`
3. 需要模块细节：`repowiki/knowledge/zh/_index.yaml` → 对应模块知识卡
4. 使用 Skill：`skills/penshot-dev/SKILL.md` → `prompts/system_prompt.md`

---

## 维护约定

### 新增 Rule

1. 在 `.qoder/rules/` 下新建 `<name>.md`。
2. 文件顶部包含 frontmatter：

   ```yaml
   ---
   trigger: <always_on | on_request | keyword>
   ---
   ```

3. 正文开头明确与 `SDD-Agent.md` 的关系："本规则补充 SDD-Agent.md，冲突时以 SDD-Agent.md 为准。"
4. 在 `README.md` 中注册。

### 新增 Skill

1. 在 `.qoder/skills/` 下新建 `<skill-name>/` 目录。
2. 目录内至少包含 `skill.json`、`SKILL.md`、`prompts/system_prompt.md`。
3. `skill.json` 语法需通过 `python -m json.tool` 验证。
4. 在 `README.md` 中注册。

### 版本号约定

- 以 `pyproject.toml` 的 `version` 字段为单一事实源（当前 `0.3.6`）。
- 文档中提及版本时优先引用 `pyproject.toml`。

### 修改边界

- `.qoder/` 内的文档可自由增删改。
- `repowiki/` 内的知识卡正文建议通过工具重新导出，避免手工修改导致与源码脱节。
- 禁止修改 `.qoder/` 以外的文件（如业务代码、测试、构建配置），除非用户明确授权。
