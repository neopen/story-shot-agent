# Skill 内引用：PenShot 编码规范摘要

> 完整规范见 `.qoder/rules/coding-standards.md`。本文件为 Skill 上下文中的快速参考。

## 命名

- 包/模块：小写 + 下划线，如 `penshot`、`workflow_nodes`
- 类：PascalCase，如 `PenshotFunction`
- 函数/方法：snake_case，如 `create_task_factory`
- 常量：UPPER_SNAKE_CASE，如 `DEFAULT_TASK_TTL_SECONDS`
- 私有成员：单下划线前缀

## 导入顺序

1. 标准库
2. 第三方库
3. 本项目模块（config → logger → utils → neopen）

## 类型注解

- 公共函数参数与返回值必须注解。
- 使用 `Optional[Type]`（与现有风格一致）。
- 复杂结构优先 Pydantic/dataclass。

## 文档字符串

- 模块/类/公共函数使用中文文档字符串。
- 文件头沿用 `@FileName / @Description / @Author / @Time` 模板。

## 异常与日志

- 不静默吞异常。
- 使用 `penshot.logger` 或 `print_log_exception`。
- `penshot.logger.warning` 仅接受单参数，用 f-string。

## 测试

- `pytest`，异步用 `pytest-asyncio`。
- 测试文件 `test_*.py`。
- 外部依赖测试使用 fixture 模拟或标记为 integration/e2e。

## 工具链

- `ruff-format`、`ruff`、`mypy`、`mdformat --number`
- 预提交：`.pre-commit-config.yaml`
