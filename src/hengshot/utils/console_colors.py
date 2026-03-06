"""
@FileName: console_colors.py
@Description: 控制台颜色输出工具，提供带颜色的日志输出功能
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/08 - 2025/11
"""
import logging
import os
import sys

import colorama
from colorama import Fore, Style

# 全局变量存储控制台颜色状态
console_colors_initialized = False

# 尝试导入colorama库
try:
    HAS_COLORAMA = True
    # 定义颜色常量
    COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA
    }
except ImportError:
    HAS_COLORAMA = False
    # 定义ANSI颜色代码作为备选
    COLORS = {
        logging.DEBUG: '\033[94m',  # 蓝色
        logging.INFO: '\033[92m',  # 绿色
        logging.WARNING: '\033[93m',  # 黄色
        logging.ERROR: '\033[91m',  # 红色
        logging.CRITICAL: '\033[95m',  # 紫色
    }
    # 重置颜色代码
    RESET = '\033[0m'

# 检查操作系统
IS_WINDOWS = sys.platform == 'win32'


def init_console_colors():
    """
    初始化控制台颜色支持
    在Windows平台上，使用colorama库启用ANSI颜色代码支持
    """
    global console_colors_initialized

    if console_colors_initialized:
        return

    if IS_WINDOWS:
        if HAS_COLORAMA:
            # 初始化colorama，autoreset=True确保每次打印后自动重置颜色
            colorama.init(autoreset=True)
            # print(f"{Fore.GREEN}[控制台颜色] 已成功初始化colorama库{Style.RESET_ALL}")
            # 测试颜色输出
            # print(f"{Fore.BLUE}DEBUG{Style.RESET_ALL} - {Fore.GREEN}INFO{Style.RESET_ALL} - {Fore.YELLOW}WARNING{Style.RESET_ALL} - {Fore.RED}ERROR{Style.RESET_ALL} - {Fore.MAGENTA}CRITICAL{Style.RESET_ALL}")
        # else:
        #     print("[控制台颜色] 警告: 在Windows平台上运行，但未安装colorama库，可能无法显示彩色日志。")
        #     print("[控制台颜色] 建议安装: pip install colorama")
    else:
        # 非Windows平台通常原生支持ANSI颜色代码
        print("[控制台颜色] 非Windows平台，直接支持ANSI颜色代码")

    console_colors_initialized = True


def get_level_color(level):
    """
    获取日志级别的颜色
    
    Args:
        level: 日志级别
        
    Returns:
        对应的颜色代码或colorama对象
    """
    return COLORS.get(level, '')


def get_reset_code():
    """
    获取重置颜色的代码
    """
    if HAS_COLORAMA:
        return Style.RESET_ALL
    else:
        return RESET


def colored_log_formatter_factory(fmt=None, datefmt=None, style='%'):
    """
    创建一个支持颜色的日志格式化器
    针对Windows平台特别优化
    """
    # 确保控制台颜色已初始化
    init_console_colors()

    class ColoredFormatter(logging.Formatter):
        def format(self, record):
            # 获取颜色代码
            level_color = get_level_color(record.levelno)
            reset_code = get_reset_code()

            original_levelname = None
            # 如果有颜色代码，应用到日志级别
            if level_color:
                # 直接修改record的levelname属性为带颜色的版本
                colored_levelname = f"{level_color}{record.levelname}{reset_code}"
                # 保存原始的levelname
                original_levelname = record.levelname
                # 设置带颜色的levelname
                record.levelname = colored_levelname

            # 格式化日志记录
            formatted_message = super().format(record)

            # 如果修改了levelname，恢复原始值
            if level_color:
                record.levelname = original_levelname

            return formatted_message

    return ColoredFormatter(fmt=fmt, datefmt=datefmt, style=style)


# 尝试导入颜色支持
# try:
#     from colorama import init
#
#     HAS_COLORAMA = True
#     IS_WINDOWS = sys.platform.startswith('win')
#     if IS_WINDOWS:
#         init()
# except ImportError:
#     HAS_COLORAMA = False
#     IS_WINDOWS = False


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器 - 简化版"""

    # 正确的颜色代码
    COLORS = {
        'DEBUG': '\033[36m',  # 青色 - cyan
        'INFO': '\033[32m',  # 绿色 - green
        'WARNING': '\033[33m',  # 黄色 - yellow
        'ERROR': '\033[31m',  # 红色 - red
        'CRITICAL': '\033[35m',  # 品红色 - magenta
        'RESET': '\033[0m'  # 重置
    }

    # 或者使用更鲜艳的颜色（可选）
    BRIGHT_COLORS = {
        'DEBUG': '\033[96m',  # 亮青色
        'INFO': '\033[92m',  # 亮绿色
        'WARNING': '\033[93m',  # 亮黄色
        'ERROR': '\033[91m',  # 亮红色
        'CRITICAL': '\033[95m',  # 亮品红色
        'RESET': '\033[0m'
    }

    def __init__(self, fmt: str, datefmt: str = None):
        super().__init__(fmt, datefmt)
        self.use_color = self._check_color_support()

    def _check_color_support(self) -> bool:
        """检查是否支持颜色"""
        # 检查是否输出到终端
        if not sys.stdout.isatty():
            return False

        # Windows需要colorama
        if IS_WINDOWS:
            return HAS_COLORAMA

        # Unix-like系统检查TERM变量
        term = os.getenv('TERM', '')
        supported_terms = ['xterm', 'xterm-256color', 'screen', 'screen-256color',
                           'linux', 'cygwin', 'vt100', 'vt220', 'ansi']

        for term_type in supported_terms:
            if term_type in term:
                return True

        return False

    def format(self, record):
        """格式化日志记录"""
        # 先调用父类格式化
        result = super().format(record)

        # 如果需要颜色，添加颜色代码
        if self.use_color and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            reset = self.COLORS['RESET']
            result = f"{color}{result}{reset}"

        return result


class LevelOnlyColoredFormatter(logging.Formatter):
    """只给日志级别添加颜色"""

    # 级别颜色映射
    LEVEL_COLORS = {
        logging.DEBUG: '\033[36m',  # 青色
        logging.INFO: '\033[32m',  # 绿色
        logging.WARNING: '\033[33m',  # 黄色
        logging.ERROR: '\033[31m',  # 红色
        logging.CRITICAL: '\033[35m',  # 紫色
    }
    RESET = '\033[0m'

    def __init__(self, fmt=None, datefmt=None):
        if fmt is None:
            fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        super().__init__(fmt, datefmt)

    def format(self, record):
        # 检查是否应该使用颜色
        if sys.stdout.isatty() and (not IS_WINDOWS or HAS_COLORAMA):
            # 获取颜色
            color = self.LEVEL_COLORS.get(record.levelno, '')
            reset = self.RESET if color else ''

            # 在格式化字符串中插入颜色
            # 我们需要修改格式化过程，只给 %(levelname)s 加颜色
            message = super().format(record)

            # 查找并替换级别名称
            # 例如: "INFO" -> "\033[32mINFO\033[0m"
            level_name = logging.getLevelName(record.levelno)
            colored_level = f"{color}{level_name}{reset}"

            # 替换消息中的级别名称
            # 注意：这里假设格式中包含 %(levelname)s
            message = message.replace(level_name, colored_level, 1)

            return message

        return super().format(record)
