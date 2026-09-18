---
trigger: always_on
alwaysApply: true
---

# PenShot 编码规范

> 本规则补充 `.qoder/rules/SDD-Agent.md`，冲突时以 SDD-Agent.md 为准。  
> 触发方式：on_request —— 在处理代码生成、代码审查或重构任务时，由用户或 Skill 显式启用。

---

## 1. 适用范围

本规范约束 `src/penshot/` 及 `tests/` 下的 Python 代码、Markdown 文档和配置文件。

---

## 2. Python 版本与环境

- 支持 Python 3.10、3.11、3.12（以 `pyproject.toml` 的 `requires-python` 为准）。
- 优先使用标准库；引入新第三方依赖须经确认并更新 `pyproject.toml`。

---

## 3. 命名规范

| 类型 | 规范 | 示例 |
|---|---|---|
| 包/模块 | 小写、下划线分隔 | `penshot`、`workflow_nodes` |
| 类 | PascalCase | `PenshotFunction`、`WorkflowNodes` |
| 函数/方法 | snake_case | `create_task_factory`、`get_saver` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_TASK_TTL_SECONDS` |
| 私有成员 | 单下划线前缀 | `_create_agent`、`_should_use_llm_split` |
| 类型变量 | 大写单字母或 PascalCase | `T`、`TaskResponse` |

---

## 4. 导入顺序

1. 标准库
2. 第三方库
3. 本项目模块（按从通用到具体排序：config → logger → utils → neopen）

示例：

```python
import asyncio
from typing import Dict, Optional

from pydantic import BaseModel

from penshot.config.config import settings
from penshot.logger import info, error
from penshot.neopen.task.task_factory import create_task_factory
```

---

## 5. 类型注解

- 函数参数与返回值必须加类型注解（公共 API 强制，内部函数鼓励）。
- 使用 `Optional[Type]` 而非 `Type | None`（与现有代码风格保持一致）。
- 复杂结构优先使用 Pydantic 模型或 dataclass，避免裸 `Dict[str, Any]` 在公共接口中泛滥。

---

## 6. 文档字符串与注释

- 所有模块、类、公共函数必须包含中文文档字符串，说明职责、参数、返回值与异常。
- 文件头模板沿用现有风格：

  ```python
  """
  @FileName: xxx.py
  @Description: 一句话说明
  @Author: HiPeng
  @Time: 2026/x/x xx:xx
  """
  ```

- 行内注释用于解释"为什么"，而非复述代码。

---

## 7. 异常与错误处理

- 捕获异常时必须记录日志，禁止静默吞掉异常。
- 使用 `penshot.logger`（info/error/warning/debug）或 `penshot.utils.log_utils.print_log_exception`。
- 对外 API 应抛出语义清晰的异常，并在 FastAPI/CLI 层映射为友好错误信息。

---

## 8. 日志规范

- 使用 `from penshot.logger import info, error, warning, debug`。
- 避免在热路径使用字符串拼接，优先使用 f-string 或 `%` 占位符。
- 注意：`penshot.logger.warning` 签名仅接受单参数，不支持 `%` 参数格式，需使用 f-string。

---

## 9. 测试规范

- 测试框架：`pytest`，异步测试使用 `pytest-asyncio`（配置以 `pyproject.toml` 为准）。
- 测试文件命名：`test_*.py`。
- 测试应覆盖正常路径、边界条件与异常分支。
- 涉及外部依赖（LLM/Redis/Chroma）的测试，优先使用 fixture 模拟或标记为 integration/e2e。

---

## 10. 工具链

- 格式化：`ruff-format`
- Linter：`ruff`
- 类型检查：`mypy`（`--ignore-missing-imports --show-error-codes --pretty`）
- Markdown 格式化：`mdformat --number`
- 预提交：`.pre-commit-config.yaml`

---

## 11. 安全红线

- 不在代码、测试、日志、文档中硬编码 API key、token、密码。
- 不提交 `.env`、数据文件、模型文件、日志文件（已配置 `.gitignore`）。
- 共享配置使用 `.env.example` 作为模板。
