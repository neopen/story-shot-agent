# 贡献指南

我们欢迎您的参与！我们希望让贡献 PenShot 变得尽可能简单和透明。

## 目录

- [行为准则](#行为准则)
- [快速开始](#快速开始)
- [开发流程](#开发流程)
- [Pull Request 流程](#pull-request-流程)
- [编码规范](#编码规范)
- [测试规范](#测试规范)
- [文档规范](#文档规范)
- [Issue 报告规范](#issue-报告规范)

## 行为准则

PenShot 致力于为所有人提供友好、安全、温馨的环境。请阅读并遵守我们的[行为准则](CODE_OF_CONDUCT.md)。

## 快速开始

### 环境要求

```bash
Python 3.9+
pip
virtualenv（推荐）
```



### 搭建开发环境

```bash
# 克隆仓库
git clone https://github.com/neopen/story-shot-agent.git
cd story-shot-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"

# 安装 pre-commit 钩子（可选但推荐）
pre-commit install
```



### 项目结构

```
story-shot-agent/
├── main.py                    # 主入口文件
├── pyproject.toml             # 项目配置和依赖
├── requirements.txt           # Python依赖包
│
├── data/                      # 数据目录
├── docs/                      # 文档
├── logs/                      # 日志目录
├── scripts/                   # 脚本工具
│
├── example/                   # 示例代码
│   ├── json_demo/             # JSON示例数据
│   ├── script_txt/            # 剧本示例文本
│   ├── a2a_integration.py     # A2A集成示例
│   ├── direct_usage.py        # 直接使用示例
│   ├── langgraph_integration.py # LangGraph集成示例
│   ├── mcp_*.py               # MCP相关示例
│   ├── neopen_demo.py         # NeoOpen演示
│   ├── web_app.py             # Web应用示例
│   └── workflow_node_demo     # 工作流节点示例
│
├── src/penshot/               # 核心源代码
│   ├── api/                   # API接口
│   │   ├── function_calls.py  # 函数调用API
│   │   ├── index_api.py       # 索引API
│   │   └── rest_api.py        # REST API
│   ├── app/                   # 应用层
│   │   ├── application.py     # 应用主类
│   │   ├── proxy.py           # 代理
│   │   └── setup_env.py       # 环境设置
│   ├── config/                # 配置模块
│   │   ├── env/               # 环境配置
│   │   ├── config.py          # 配置主文件
│   │   ├── config_loader.py   # 配置加载器
│   │   ├── config_models.py   # 配置模型
│   │   ├── logging.yaml       # 日志配置
│   │   └── settings.yaml      # 设置配置
│   ├── neopen/                # NeoOpen智能体核心
│   │   ├── agent/             # 智能体模块（10个文件，8个子目录）
│   │   ├── client/            # 客户端模块
│   │   ├── config/            # 智能体配置
│   │   ├── prompts/           # 提示词模板
│   │   ├── task/              # 任务管理
│   │   ├── tools/             # 工具集
│   │   ├── shot_config.py     # 分镜配置
│   │   ├── shot_context.py    # 分镜上下文
│   │   └── shot_language.py   # 分镜语言
│   ├── utils/                 # 工具函数
│   ├── http_server.py         # HTTP服务器
│   ├── mcp_http_server.py     # MCP HTTP服务器
│   ├── mcp_server.py          # MCP服务器
│   └── logger.py              # 日志模块
│
└── tests/                     # 测试目录
```



## 开发流程

### 1. 查找 Issue

查找标记为以下标签的 Issue：

- `good-first-issue` - 适合新手
- `help-wanted` - 需要贡献者
- `bug` - 已确认的 Bug
- `enhancement` - 功能请求

### 2. 创建分支

```bash
git checkout -b feature/你的功能名称
# 或
git checkout -b fix/你的修复名称
```



### 3. 编写代码

遵循编码规范。

### 4. 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_script_parser.py

# 运行并生成覆盖率报告
pytest --cov=penshot tests/
```



### 5. 提交代码

```bash
git add .
git commit -m "类型(范围): 修改描述"

# 提交类型：
# feat: 新功能
# fix: Bug 修复
# docs: 文档更新
# style: 代码格式调整
# refactor: 代码重构
# test: 测试相关
# chore: 构建过程或辅助工具变动
```



### 6. 推送并创建 Pull Request

```bash
git push origin 你的分支名
```



然后在 GitHub 上创建 Pull Request。

## Pull Request 流程

1. **更新文档**：如果修改了功能
2. **更新 CHANGELOG.md**：添加修改描述
3. **确保所有测试通过**（CI 会自动运行）
4. **请求审核**：至少一位维护者审核
5. **及时响应审核意见**
6. **按需合并提交**（如维护者要求）

### PR 标题格式

```text
<类型>(<范围>): <主题>

示例：
- feat(parser): 添加 Fountain 格式支持
- fix(task): 解决任务队列阻塞问题
- docs(api): 更新 REST API 文档
```



## 编码规范

### Python 代码风格

遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/)。

```python
# 推荐
def calculate_duration(script_length: int, words_per_second: float = 2.5) -> float:
    """计算剧本预估时长。"""
    return script_length / words_per_second

# 不推荐
def calc(script_len, wps=2.5):
    return script_len/wps
```



### 类型注解

始终使用类型注解：

```python
from typing import List, Optional, Dict, Any

def process_script(script: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """处理剧本并返回结果。"""
    ...
```



### 文档字符串

使用 Google 风格文档字符串：

```python
def split_shots(script: ParsedScript, max_duration: float = 5.0) -> ShotSequence:
    """
    将解析后的剧本拆分为镜头。

    Args:
        script: 包含场景和元素的解析后剧本
        max_duration: 单个镜头的最大时长（秒）

    Returns:
        ShotSequence: 包含时间信息的镜头列表

    Raises:
        ValueError: 剧本为空或无效时抛出

    Example:
        >>> result = split_shots(parsed_script)
        >>> len(result.shots)
        5
    """
    ...
```



### 异步编程

IO 操作使用 async/await：

```python
async def process_async(script: str) -> Dict:
    """异步处理剧本。"""
    result = await async_operation()
    return result
```



## 测试规范

### 编写测试

```python
# tests/test_script_parser.py
import pytest
from penshot import ScriptParser

def test_parse_basic_script():
    parser = ScriptParser()
    result = parser.parse("张三说：你好")
    assert result.characters[0].name == "张三"
    assert len(result.scenes) == 1

@pytest.mark.asyncio
async def test_async_parse():
    parser = ScriptParser()
    result = await parser.parse_async("李四回答：你好吗？")
    assert result is not None
```



### 测试覆盖率

目标 >80%：

```bash
pytest --cov=penshot --cov-report=html
```



## 文档规范

### 代码注释

- 注释复杂逻辑，而非显而易见的内容
- 使用 `# TODO:` 标记待改进项
- 使用 `# NOTE:` 标记重要说明
- 使用 `# FIXME:` 标记已知问题

### README 更新

添加功能时，更新 README 的相关章节：

- 安装说明
- 快速开始
- API 文档
- 示例代码

## Issue 报告规范

### Bug 报告模板

```markdown
**问题描述**
清晰描述问题是什么。

**复现步骤**
复现行为的步骤：
1. 执行命令 '...'
2. 看到错误

**预期行为**
清晰描述预期结果。

**截图**
如适用，添加截图。

**环境信息：**
- 操作系统：[如 Ubuntu 22.04]
- Python 版本：[如 3.10]
- PenShot 版本：[如 0.1.0]

**补充信息**
添加其他相关背景信息。
```



### 功能请求模板

```markdown
**是否与某个问题相关？**
清晰描述相关问题。

**描述你想要的解决方案**
清晰描述你希望发生什么。

**描述你考虑过的替代方案**
清晰描述替代解决方案。

**补充信息**
添加其他相关背景信息。
```



## 获取帮助

- **GitHub Discussions**：https://github.com/neopen/story-shot-agent/discussions
- **Issue 追踪**：https://github.com/neopen/story-shot-agent/issues
- **Discord/Slack**：[]

## 致谢

贡献者将列入 [CONTRIBUTORS.md](./contributors.md) 名单。

------

感谢您为 PenShot 做出贡献！🎬







