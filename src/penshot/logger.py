
"""
@FileName: logger.py
@Description: 自定义日志模块，支持按天创建日志文件、日志文件大小限制、控制台彩色输出等功能
            自定义日志模块，按天创建日志文件，最大10MB
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/08 - 2025/11
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml

# 导入自定义的控制台颜色处理模块
from penshot.utils.console_colors import init_console_colors, IS_WINDOWS, HAS_COLORAMA, LevelOnlyColoredFormatter
from penshot.utils.log_utils import _generate_dated_filename
from penshot.utils.path_utils import PathResolver

# 初始化控制台颜色支持
init_console_colors()


class DailyRotatingFileHandler(logging.Handler):
    """自定义每日轮转文件处理器"""

    def __init__(self, log_dir: str, name: str = 'PenShot', max_bytes: int = 10 * 1024 * 1024,
                 backup_count: int = 30, max_days: int = 15):
        """初始化"""
        super().__init__()

        self.log_dir = Path(log_dir)
        self.base_name = name  # 改为 base_name
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.max_days = max_days

        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 生成带日期的文件名
        date_str = datetime.now().strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{self.base_name}_{date_str}.log"

        # 创建实际的文件处理器
        from logging.handlers import RotatingFileHandler

        self.file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )

    def setFormatter(self, fmt):
        """设置格式化器"""
        self.file_handler.setFormatter(fmt)

    def setLevel(self, level):
        """设置日志级别"""
        self.file_handler.setLevel(level)

    def emit(self, record):
        """发射日志记录"""
        self.file_handler.emit(record)

    def close(self):
        """关闭处理器"""
        self.file_handler.close()


class LoggingConfigManager:
    """日志配置管理器"""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化日志配置管理器

        Args:
            config_dir: 配置目录，默认为项目根目录下的 config 目录
        """
        if config_dir is None:
            # 假设当前文件在 src/penshot/ 目录下
            self.config_dir = Path(__file__).parent / "config"
        else:
            self.config_dir = Path(config_dir)

        self.logging_config_file = self.config_dir / "logging.yaml"
        self._config_cache = None
        self._flattened_cache = None

    def load_config(self) -> Dict[str, Any]:
        """加载 logging.yaml 配置"""
        if self._config_cache is not None:
            return self._config_cache

        if not self.logging_config_file.exists():
            print(f"日志配置文件不存在: {self.logging_config_file}")
            self._config_cache = {}
            return self._config_cache

        try:
            with open(self.logging_config_file, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f) or {}
                print(f"加载日志配置: {self.logging_config_file}")
                return self._config_cache
        except Exception as e:
            print(f"加载日志配置失败: {e}")
            self._config_cache = {}
            return self._config_cache

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            *keys: 多个键，如 get("levels", "app")
            default: 默认值

        Returns:
            配置值
        """
        config = self.load_config()
        value = config

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default

            if value is None:
                return default

        return value

    def get_level(self, logger_name: str = "root") -> str:
        """
        获取日志级别

        Args:
            logger_name: logger名称，可选值: root, uvicorn, app, llm

        Returns:
            日志级别字符串
        """
        return self.get("levels", logger_name, default="INFO").upper()

    def get_formatter(self) -> Dict[str, Any]:
        """获取格式化器配置"""
        return self.get("formatter", default={})

    def get_handler_config(self, handler_name: str) -> Dict[str, Any]:
        """获取处理器配置"""
        return self.get(handler_name, default={})

    def get_handlers_for_logger(self, logger_name: str = "root") -> List[str]:
        """获取logger的handlers"""
        return self.get("handlers", logger_name, default=[])

    def get_format_string(self) -> str:
        """获取日志格式字符串"""
        return self.get("formatter", "format",
                        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def get_date_format(self) -> str:
        """获取日期格式"""
        return self.get("formatter", "datefmt", default="%Y-%m-%d %H:%M:%S")

    def get_file_handler_config(self) -> Dict[str, Any]:
        """获取文件处理器配置"""
        file_config = self.get_handler_config("file")

        # 确保必要字段存在
        default_config = {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "formatter",
            "filename": f"logs/penshot_{datetime.now().strftime('%Y-%m-%d')}.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf8"
        }

        return {**default_config, **file_config}

    def get_console_handler_config(self) -> Dict[str, Any]:
        """获取控制台处理器配置"""
        console_config = self.get_handler_config("console")

        default_config = {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "formatter",
            "stream": "ext://sys.stdout"
        }

        return {**default_config, **console_config}

    def to_logging_dict(self) -> Dict[str, Any]:
        """
        转换为 logging.config.dictConfig 可用的格式

        Returns:
            logging 模块兼容的配置字典
        """
        config = self.load_config()

        # 构建标准logging配置
        logging_dict = {
            "version": config.get("version", 1),
            "disable_existing_loggers": config.get("disable_existing_loggers", False),
            "formatters": {
                "formatter": self.get_formatter()
            },
            "handlers": {},
            "loggers": {}
        }

        # 添加handlers
        if "console" in config:
            logging_dict["handlers"]["console"] = self.get_console_handler_config()

        if "file" in config:
            logging_dict["handlers"]["file"] = self.get_file_handler_config()

        # 添加loggers
        levels = config.get("levels", {})
        handlers_map = config.get("handlers", {})

        # 根logger
        root_handlers = handlers_map.get("root", ["console"])
        logging_dict["loggers"][""] = {
            "level": levels.get("root", "INFO"),
            "handlers": root_handlers,
            "propagate": False
        }

        # 其他loggers
        logger_names = [k for k in levels.keys() if k != "root"]
        for name in logger_names:
            if name in handlers_map:
                logging_dict["loggers"][name] = {
                    "level": levels.get(name, "INFO"),
                    "handlers": handlers_map[name],
                    "propagate": False
                }

        return logging_dict


# ==================== 全局实例 ====================
# 创建全局实例
_logging_manager = None


def get_logging_manager() -> LoggingConfigManager:
    """获取全局日志配置管理器"""
    global _logging_manager
    if _logging_manager is None:
        _logging_manager = LoggingConfigManager()
    return _logging_manager


class Logger:
    """自定义日志类 - 从配置管理器读取配置"""

    def __init__(self, name: str = 'PenShot', log_dir: Optional[str] = None):
        """
        初始化日志器

        Args:
            name: 日志器名称
            log_dir: 日志目录路径，默认从配置读取或使用项目根目录下的logs目录
        """
        # 获取配置管理器
        self.config_manager = get_logging_manager()

        # 初始化日志器
        self.logger = logging.getLogger(name)

        # 清除已有的处理器，避免重复添加
        self.logger.handlers.clear()

        # 获取配置
        self._load_config()

        # 设置日志级别
        self._set_log_level()

        # 添加处理器
        self._add_handlers(log_dir)

        # 禁用不必要的日志
        self._disable_unnecessary_logs()

        # Windows颜色警告
        self._check_windows_color()

    def _load_config(self):
        """加载配置"""
        # 获取配置字典
        self.config = self.config_manager.to_logging_dict()

        # 获取日志级别映射
        self.level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
            'NOTSET': logging.NOTSET
        }

    def _set_log_level(self):
        """设置日志级别"""
        # 获取logger配置
        logger_name = self.logger.name
        logger_config = None

        # 查找对应的logger配置
        for config_name, config in self.config.get('loggers', {}).items():
            if config_name == logger_name or config_name == "":
                logger_config = config
                break

        # 设置日志级别
        if logger_config:
            level_str = logger_config.get('level', 'INFO')
            level = self.level_map.get(level_str.upper(), logging.INFO)
            self.logger.setLevel(level)
        else:
            self.logger.setLevel(logging.INFO)

    def _add_handlers(self, log_dir: Optional[str]):
        """添加处理器"""
        # 获取logger配置
        logger_name = self.logger.name
        logger_config = None

        # 查找对应的logger配置
        for config_name, config in self.config.get('loggers', {}).items():
            if config_name == logger_name or config_name == "":
                logger_config = config
                break

        if not logger_config:
            return

        # 获取分配的handlers
        handler_names = logger_config.get('handlers', [])

        # 添加每个handler
        for handler_name in handler_names:
            handler_config = self.config.get('handlers', {}).get(handler_name)
            if not handler_config:
                continue

            handler = self._create_handler(handler_name, handler_config, log_dir)
            if handler:
                self.logger.addHandler(handler)

    def _create_handler(self, handler_name: str, handler_config: Dict[str, Any],
                        log_dir: Optional[str]) -> Optional[logging.Handler]:
        """创建处理器"""
        handler_class = handler_config.get('class', '')
        level_str = handler_config.get('level', 'INFO')
        level = self.level_map.get(level_str.upper(), logging.INFO)

        # 获取格式化器
        formatter_config = self.config.get('formatters', {}).get('formatter', {})
        fmt = formatter_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        datefmt = formatter_config.get('datefmt', '%Y-%m-%d %H:%M:%S')

        # 根据handler类型创建处理器
        if 'StreamHandler' in handler_class or handler_name == 'console':
            return self._create_console_handler(handler_config, fmt, datefmt, level)
        elif 'FileHandler' in handler_class or handler_name == 'file':
            return self._create_file_handler(handler_config, fmt, datefmt, level, log_dir)

        return None

    def _create_console_handler(self, handler_config: Dict[str, Any], fmt: str,
                                datefmt: str, level: int) -> logging.Handler:
        """创建控制台处理器 - 只给级别加颜色"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # 检查是否应该使用颜色
        use_color = sys.stdout.isatty() and (HAS_COLORAMA or not IS_WINDOWS)

        if use_color:
            # 使用只给级别加颜色的格式化器
            formatter = LevelOnlyColoredFormatter(fmt, datefmt)
        else:
            formatter = logging.Formatter(fmt, datefmt)

        console_handler.setFormatter(formatter)
        return console_handler

    def _create_file_handler(self, handler_config: Dict[str, Any], fmt: str,
                             datefmt: str, level: int, log_dir: Optional[str] = None) -> logging.Handler:
        """创建文件处理器"""
        # 获取日志目录
        if log_dir is None:
            # 尝试从配置获取
            filename = handler_config.get('filename', 'logs/penshot_%Y-%m-%d.log')
            log_path = Path(filename)

            # 如果配置中是相对路径，转换为绝对路径
            if not log_path.is_absolute():
                project_root = PathResolver.get_project_root()
                log_path = project_root / log_path
        else:
            # 使用指定的目录，但应用日期格式
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_path = _generate_dated_filename()

        # 处理文件名中的日期格式变量
        log_path_str = str(log_path)
        if '%' in log_path_str:
            # 将日期格式变量替换为实际日期
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_path_str = log_path_str.replace('%Y-%m-%d', date_str)
            log_path = Path(log_path_str)

        # 确保目录存在
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 获取配置参数
        max_bytes = handler_config.get('maxBytes', 10 * 1024 * 1024)  # 默认10MB
        backup_count = handler_config.get('backupCount', 30)

        # 创建处理器
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)

        # 设置格式化器
        formatter = logging.Formatter(fmt, datefmt)
        file_handler.setFormatter(formatter)

        return file_handler

    def _disable_unnecessary_logs(self):
        """禁用不必要的第三方库日志"""
        # 从配置获取是否禁用
        disable_unnecessary = True  # 默认禁用

        # 要禁用的库列表
        libraries_to_disable = ['urllib3', 'requests', 'PIL', 'matplotlib',
                                'httpx', 'asyncio', 'aiosqlite']

        for lib_name in libraries_to_disable:
            logging.getLogger(lib_name).setLevel(logging.WARNING)

    def _check_windows_color(self):
        """检查Windows颜色支持"""
        if IS_WINDOWS and not HAS_COLORAMA:
            self.warning("在Windows平台上运行，但未安装colorama库，可能无法显示彩色日志。建议安装: pip install colorama")

    # ==================== 日志方法 ====================

    def debug(self, msg: str, *args, **kwargs):
        """调试级别日志"""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """信息级别日志"""
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """警告级别日志"""
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """错误级别日志"""
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """严重级别日志"""
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        """异常日志"""
        self.logger.exception(msg, *args, exc_info=exc_info, **kwargs)

    def log(self, level: int, msg: str, *args, **kwargs):
        """通用日志方法"""
        self.logger.log(level, msg, *args, **kwargs)


# 创建全局日志实例
logger = Logger(name="PenShot")


# 方便使用的函数

def debug(message: str):
    logger.debug(message)


def info(message: str):
    logger.info(message)


def warning(message: str):
    logger.warning(message)


def error(message: str):
    logger.error(message)


def critical(message: str):
    logger.critical(message)


def log_with_context(level: str, message: str, context: dict = None) -> None:
    """
    记录带上下文的日志
    
    Args:
        level: 日志级别
        message: 日志消息
        context: 上下文信息
    """
    if context:
        # 将上下文信息格式化
        context_str = " ".join([f"{k}={v}" for k, v in context.items()])
        full_message = f"{message} | {context_str}"
    else:
        full_message = message

    # 根据级别记录日志
    if level == "DEBUG":
        debug(full_message)
    elif level == "INFO":
        info(full_message)
    elif level == "WARNING":
        warning(full_message)
    elif level == "ERROR":
        error(full_message)
    elif level == "CRITICAL":
        critical(full_message)


def log_function_call(func_name: str, params: dict = None, result=None) -> None:
    """
    记录函数调用信息
    
    Args:
        func_name: 函数名称
        params: 函数参数
        result: 函数返回结果
    """
    context = {"function": func_name}
    if params:
        context.update({f"param_{k}": str(v)[:50] if len(str(v)) > 50 else str(v) for k, v in params.items()})

    if result is not None:
        result_str = str(result)[:100] if len(str(result)) > 100 else str(result)
        context["result"] = result_str

    log_with_context("DEBUG", "Function call", context)


def log_performance(action: str, duration_ms: float, details: dict = None) -> None:
    """
    记录性能信息
    
    Args:
        action: 操作名称
        duration_ms: 耗时（毫秒）
        details: 详细信息
    """
    context = {"action": action, "duration_ms": duration_ms}
    if details:
        context.update(details)

    log_with_context("INFO", "Performance metric", context)
