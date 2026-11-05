# PenShot 版本发布与升级指南

> 适用范围：`main` 分支的自动版本管理、tag、GitHub Release 与 PyPI 发布。
> 相关文件：
> - 工作流：`.github/workflows/release-please.yml`、`.github/workflows/publish-pypi.yml`
> - 配置：`.github/release-please-config.json`
> - 版本基线：`.github/.release-please-manifest.json`
> - 变更记录：`CHANGELOG.md`

## 1. 机制概览

版本号由 release-please 依据 Conventional Commits 自动计算：

| 提交类型 | 0.x 阶段（当前配置） | ≥ 1.0.0 |
| --- | --- | --- |
| `feat` | patch | minor |
| `fix` / `perf` / `refactor` 等 | patch | patch |
| `feat!` / `BREAKING CHANGE` | major | major |

- 当前开启 `bump-patch-for-minor-pre-major`，因此 0.x 阶段 `feat` 也按 patch 递增，例如 `0.4.0 → 0.4.1`。
- 版本基线来自 `.github/.release-please-manifest.json`，**不是** `pyproject.toml`。
- 发布链路：push `main` → release-please 创建发布 PR → 合并发布 PR → 打 tag / 建 Release → `publish-pypi.yml` 发布 PyPI。

## 2. 常规发布流程（不跨版本线）

1. 功能 PR 合入 `main`（使用 Squash and merge）
2. release-please 自动创建 `chore(main): release x.y.z` PR
3. 合并该发布 PR
4. 自动生成 tag、GitHub Release，并触发 PyPI 发布

此流程无需手工修改版本号或打 tag。

### 2.1 Squash 合并的具体操作

`dev → main` 以及 release-please 发布 PR 都使用 **Squash and merge**。原因：squash 后 `main` 上只留下一个提交，
release-please 只解析这个提交的消息；PR 正文中自动生成的提交列表不会被当成独立提交。

#### GitHub 页面操作步骤

1. 打开 `dev → main` 的 PR（或 release-please 生成的发布 PR）
2. 确认 CI / Checks 全部通过
3. 点击 **Squash and merge**，不要选择 `Create a merge commit` 或 `Rebase and merge`
4. 在合并对话框里编辑 **Squash commit message**：
   - 第一行标题必须是 Conventional Commits 格式，它决定版本递增类型：
     - `feat: M0.4.1 连续性收尾`
     - `fix: 修复报告落盘竞态`
     - `feat!: 移除旧版 API`
   - 正文保留 GitHub 自动生成的提交列表即可，不会影响版本计算
   - 如需强制版本，可在正文末尾追加脚注（与空提交方式等价，只影响下一次发布）：

     ```text
     Release-As: 0.4.1
     ```

5. 点击 **Confirm squash and merge**
6. 合并后确认 `main` 上的提交：

   ```bash
   git fetch origin
   git log --oneline -1 origin/main
   # 期望：feat: M0.4.1 ... (#N)
   ```

#### release-please 发布 PR 的处理

- 发布 PR 标题保持 release-please 生成的 `chore(main): release x.y.z`，不要手动改成 `feat` / `fix`
- 同样使用 **Squash and merge**，直接确认即可
- 合并后 release-please 自动创建 tag 与 GitHub Release，并触发 `publish-pypi.yml` 发布 PyPI

#### 常见错误

| 错误做法 | 后果 |
| --- | --- |
| 使用 `Create a merge commit` | merge commit 被 release-please 忽略，仍按被合入的各个提交计算 |
| 使用 `Rebase and merge` | 每个原始提交都落到 `main`，逐条进入 CHANGELOG，`feat` 仍按规则参与版本计算 |
| PR 标题写成 `Dev`、`Merge dev` 等非规范格式 | 无法识别类型，走 `default-bump-level: patch` 兜底 |
| 标题写 `feat!` 但实际没有破坏性变更 | 会直接 bump 到 `1.0.0`，需谨慎 |
| 手动修改发布 PR 的标题 | 可能破坏 release-please 对发布 PR 的识别 |

## 3. 升小版本（例如 0.4.x → 0.5.0）

需要主动跨版本线时，使用 `Release-As` 提交脚注。

1. 同步 `main` 到 `dev`：

   ```bash
   git fetch origin
   git checkout dev
   git merge origin/main
   ```

2. 创建带脚注的空提交：

   ```bash
   git commit --allow-empty -m "chore: release 0.5.0" -m "Release-As: 0.5.0"
   ```

3. 推送 `dev`，创建 `dev → main` 的 PR，使用 Squash and merge 合并
4. 合并 release-please 生成的 `chore(main): release 0.5.0` PR
5. 确认 `v0.5.0` tag 与 PyPI 发布

注意：

- `Release-As` 必须写在普通提交上，merge commit 的消息不会被解析
- 只影响紧随其后的下一次发布，不需要手工修改 `pyproject.toml`、`src/penshot/__init__.py` 或 manifest

## 4. 升大版本（0.x → 1.0.0）

方式 A：显式指定（推荐）

```bash
git commit --allow-empty -m "chore: release 1.0.0" -m "Release-As: 1.0.0"
```

方式 B：使用破坏性变更标记，由 release-please 自动 major bump

```bash
git commit -m "feat!: 移除旧版公共 API"
```

或在提交正文中声明：

```text
feat: 重构公共接口

BREAKING CHANGE: 说明不兼容变更
```

注意：

- 0.x 阶段的 `bump-patch-for-minor-pre-major` 只会把 `feat` 降为 patch，不影响 breaking change 的 major 递增
- 版本达到 1.0.0 后该配置不再生效：`feat → minor`，`feat! → major`

## 5. 在配置中固定版本（可选）

可在 `.github/release-please-config.json` 的 `packages."."` 下临时加入：

```json
"release-as": "0.5.0"
```

发布完成后必须移除，否则后续发布会持续固定在该版本。

## 6. 禁止事项

- 不手工修改 `pyproject.toml`、`src/penshot/__init__.py` 中的 `version`
- 不手工修改 `.github/.release-please-manifest.json`
- 不手工创建 tag 或 GitHub Release
- 不把 `Release-As` 写在 merge commit 上

## 7. 发布前检查

- [ ] `ruff check` 通过
- [ ] `pytest` 通过
- [ ] 目标提交类型符合预期（`feat` / `fix` / `feat!`）
- [ ] `dev` 已合并最新的 `main`
- [ ] 配置改动已随 PR 合入 `main`（release-please 从 `main` 读取配置）

## 8. 常见问题

**Q: 为什么 `feat` 只升了 patch？**

A: 0.x 阶段开启了 `bump-patch-for-minor-pre-major: true`。

**Q: 想升 minor，但 PR 标题是 `feat` 怎么办？**

A: 用带 `Release-As` 的空提交显式指定目标版本。

**Q: 发布 PR 合并了，但 PyPI 没有发布？**

A: 检查 `publish-pypi.yml` 是否由 `release: published` 触发，以及 PyPI environment 与 Trusted Publishing 配置。

**Q: 可以给 `release-please-config.json` 加注释吗？**

A: 不可以。release-please 使用严格 JSON 解析，且 schema 设置了 `additionalProperties: false`，说明统一放在本文件和工作流注释中。
