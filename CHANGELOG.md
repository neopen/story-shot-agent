# 更新日志

本文档记录项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 项目初始搭建
- 多智能体流水线架构
- 剧本解析智能体
- 镜头拆分智能体
- 视频片段切割智能体
- 提示词转换智能体
- 质量审查智能体
- REST API 服务器（支持异步任务处理）
- MCP（模型上下文协议）服务器
- Python 集成函数调用接口
- 带队列管理的任务工厂
- Redis 任务持久化支持
- 服务重启后任务恢复
- 批量处理支持
- Web UI 演示界面

### 变更
- 重构任务管理系统
- 改进错误处理和日志记录

### 修复
- 异步事件循环阻塞问题
- 任务队列饥饿问题
- 工作流缓存内存泄漏

## [0.1.0] - 2024-01-20

### 新增
- 首个 MVP 版本发布
- 基础剧本解析（支持自然语言、标准格式）
- 简单镜头拆分（基于场景变化和对话切换）
- 5 秒强制片段切割
- 基础提示词生成（模板 + LLM）
- 基础质量检查（时长、基本连续性）
- REST API 端点：
  - `POST /api/v1/storyboard` - 异步任务提交
  - `POST /api/v1/storyboard/sync` - 同步处理
  - `GET /api/v1/status/{task_id}` - 查询任务状态
  - `GET /api/v1/result/{task_id}` - 获取任务结果
  - `DELETE /api/v1/task/{task_id}` - 取消任务
  - `GET /api/v1/health` - 健康检查
- 命令行工具命令：
  - `penshot breakdown` - 分镜拆分
  - `penshot serve` - 启动 MCP 服务器
  - `penshot serve-rest` - 启动 REST API
  - `penshot status` - 查询任务状态
  - `penshot batch` - 批量处理

### 已知问题
- v0.1.0 中任务恢复功能未完全实现
- WebSocket 支持计划在后续版本实现

## [0.0.1] - 2024-01-01

### 新增
- 项目脚手架搭建
- 基础配置系统
- 日志系统
- GitHub Actions CI/CD 流水线
- PyPI 包配置

---

## 版本策略

我们遵循[语义化版本](https://semver.org/lang/zh-CN/)：

- **主版本号**：不兼容的 API 变更
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修复

### 发布周期

- **Alpha 版本**：每 2 周（功能预览）
- **Beta 版本**：主要版本发布前
- **稳定版本**：每季度或按需发布

---

## 升级指南

### 从 0.0.x 升级到 0.1.0

```python
# 旧版 API (0.0.x)
from penshot import generate_storyboard
result = await generate_storyboard(script)

# 新版 API (0.1.0)
from penshot import PenshotFunction
agent = PenshotFunction()
result = agent.breakdown_script(script)
```



## 贡献者

完整贡献者列表请查看 [CONTRIBUTORS.md](./contributors.md)。