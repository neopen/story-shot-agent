---
kind: logging_system
name: 日志系统 — 基于 logging.yaml 配置与自定义 Logger 的分级输出体系
category: logging_system
scope:
    - '**'
source_files:
    - src/pensshot/logger.py
    - src/pensshot/config/logging.yaml
    - src/pensshot/utils/console_colors.py
    - src/pensshot/utils/log_utils.py
---

## 1. 使用的系统与框架
- 基于 Python 标准库 logging，通过 YAML 配置文件集中管理。
- 控制台彩色输出依赖 colorama（Windows）或原生 ANSI 码（Unix）。
- 文件输出使用 RotatingFileHandler，按大小轮转并保留 N 份历史文件。

## 2. 核心文件与包
- src/pensshot/logger.py：自定义 Logger 类、LoggingConfigManager、全局实例 logger 及便捷函数 debug/info/warning/error/critical/exception/log_with_context/log_function_call/log_performance。
- src/pensshot/config/logging.yaml：统一的 formatter、console/file handler、各 logger 级别与 handlers 分配。
- src/pensshot/utils/console_colors.py：ColoredFormatter / LevelOnlyColoredFormatter，仅对级别名着色，自动检测终端与 colorama。
- src/pensshot/utils/log_utils.py：异常堆栈打印工具 _generate_dated_filename 等。

## 3. 架构与设计约定
- 配置驱动：所有日志行为由 config/logging.yaml 控制，包括统一格式、handler 类型、每个 logger 的级别与绑定的 handlers。
- 双通道输出：默认同时写入 console 与文件；文件路径支持 %Y-%m-%d 日期占位符，配合 RotatingFileHandler 实现按天/按大小轮转。
- 结构化辅助：提供 log_with_context(level, message, context)、log_function_call(func_name, params, result)、log_performance(action, duration_ms, details) 三个封装方法，将上下文以 key=value 拼接追加到消息末尾，便于后续解析。
- 第三方噪音抑制：初始化时强制把 urllib3、requests、PIL、matplotlib、httpx、asyncio、aiosqlite 等设为 WARNING，减少无关日志。
- 颜色策略：仅在 stdout 为 TTY 且具备 colorama 或非 Windows 时才启用颜色；只给 levelname 着色，避免污染消息内容。

## 4. 开发者规范
- 获取 logger：优先使用模块级 from pensshot.logger import logger 或直接调用便捷函数 info/debug/...；需要独立命名空间时用 Logger(name="YourModule")。
- 记录结构化信息：复杂上下文使用 log_with_context 或专用 helper（如 log_function_call、log_performance），不要自行拼接长字符串。
- 级别选择：调试用 DEBUG，运行期关键流程用 INFO，可恢复问题用 WARNING，错误与异常用 error/exception；生产环境建议 root=INFO、业务模块 INFO、LLM 子模块 DEBUG。
- 不直接操作底层 logging：避免绕过 pensshot.logger 去创建新的 Handler/Formatter，如需扩展请在 logging.yaml 中新增 handler 并在对应 logger 下引用。
- 异常处理：捕获异常后使用 logger.exception(msg) 自动附带 traceback，或使用 utils.log_utils.print_log_exception 做额外诊断输出。
- 性能指标：耗时统计统一走 log_performance，字段包含 action、duration_ms 及可选 details，便于外部采集分析。