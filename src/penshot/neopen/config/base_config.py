"""
@FileName: base_config.py
@Description: 
@Author: Haeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/13 16:36
"""
from abc import abstractmethod
from pathlib import Path
from typing import Any

import yaml

from penshot.neopen.language_manage import Language, get_language
from penshot.logger import info, error, warning


class BaseConfig:
    """基础配置类"""

    def __init__(self):
        """初始化基础配置"""
        # 处理语言参数
        self._language = get_language()

        # 配置文件路径
        self._set_config_path()
        self._config_data = {}
        # 加载配置
        self._initialize_config()
        self.load_configuration()

    def _set_config_path(self):
        """设置配置文件路径"""
        # 根据语言选择配置文件路径
        if self._language == Language.EN:
            self.config_path =  Path(__file__).parent / "en" / self._config_file_name()
        else:
            self.config_path = Path(__file__).parent / "zh" / self._config_file_name()

    @abstractmethod
    def _config_file_name(self) -> str:
        """配置文件名（子类必须实现）"""
        pass

    @abstractmethod
    def _initialize_config(self, language: Language = Language.ZH):
        """初始化配置（子类必须实现）"""
        pass

    # @abstractmethod
    def _load_config(self):
        """加载配置（子类如果有初始化需求）"""
        pass

    def load_configuration(self):
        """
        加载配置文件
        """
        if not self.config_path.exists():
            warning(f"配置文件不存在: {self.config_path}，使用默认配置")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_data = yaml.safe_load(f) or {}
                # import copy
                # _current_config = copy.deepcopy(yaml.safe_load(f))

            self._load_config()

            info(f"成功加载配置文件: {self.config_path}")
        except FileNotFoundError:
            error(f"配置文件不存在: {self.config_path}")
            self._config_data = {}
        except Exception as e:
            error(f"加载配置文件时发生错误: {str(e)}")
            self._config_data = {}


    def set_language(self, language: Language):
        """
        设置语言

        Args:
            language: 语言，使用Language枚举
        """
        if language.value != self._language:
            self._language = language.value

            # 更新配置文件路径
            self._set_config_path()

            # 重新加载配置
            self.load_configuration()

    def get_value(self, key_path: str, default: Any = None) -> Any:
        """
        通过点分路径（如 'a.b.c'）获取嵌套配置值。
        如果路径不存在，返回 default（默认为 None）。
        """
        keys = key_path.split('.')
        value = self._config_data

        try:
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            return value
        except (TypeError, AttributeError):
            # 如果中间某层不是 dict（比如是字符串、列表等），无法继续索引
            return default
