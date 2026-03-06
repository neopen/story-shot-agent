"""
@FileName: language_manage.py
@Description: 语言管理模块
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18 14:10
"""
import os
from enum import Enum
from typing import Optional

from hengshot.logger import error


class Language(Enum):
    """
    语言枚举类，统一管理语言标识
    """
    ZH = 'zh'  # 中文
    EN = 'en'  # 英文

    @staticmethod
    def from_string(lang_str: str) -> Optional['Language']:
        """
        从字符串转换为Language枚举
        :param lang_str: 语言字符串，支持'zh'或'en'
        :return: Language枚举对象，如果不支持返回None
        """
        if not lang_str or lang_str.isspace():
            return Language.ZH

        # 先去除空格并转换为小写以支持'Zh', 'EN', '  en  '等输入
        lang_str = lang_str.strip().lower()

        if lang_str in ['zh', '中文']:
            return Language.ZH
        elif lang_str in ['en', '英文']:
            return Language.EN
        return Language.ZH


# 全局语言变量
_current_language = None


def _init_language_from_env():
    """
    从环境变量初始化语言设置
    :return: 初始化的Language枚举对象
    """
    global _current_language
    if _current_language is None:
        # 从环境变量获取语言设置
        try:
            lang_str = os.environ.get("LANGUAGE")
            _current_language = Language.from_string(lang_str) or Language.ZH
        except Exception as e:
            error(f'初始化语言设置失败，使用默认值{Language.ZH.value}：{e}')


def set_language(lang: str) -> bool:
    """
    设置当前语言
    :param lang: 语言字符串，支持'zh', 'en', '中文', '英文'
    :return: 设置成功返回True，失败返回False
    """
    global _current_language
    lang_enum = Language.from_string(lang)
    if lang_enum:
        _current_language = lang_enum
        return True
    return False


def set_language_from_request(lang: str) -> bool:
    """
    从请求参数设置语言
    :param lang: 语言字符串，支持'zh', 'en', '中文', '英文'
    :return: 设置成功返回True，失败返回False
    """
    # 请求参数的优先级高于环境变量
    return set_language(lang)


def get_language() -> Language:
    """
    获取当前语言枚举
    :return: 当前语言枚举对象
    """
    global _current_language
    if _current_language is None:
        _init_language_from_env()
    return _current_language or Language.ZH  # 默认返回中文


def is_chinese() -> bool:
    """
    判断当前语言是否为中文
    :return: 是中文返回True，否则返回False
    """
    return get_language() == Language.ZH


def is_english() -> bool:
    """
    判断当前语言是否为英文
    :return: 是英文返回True，否则返回False
    """
    return get_language() == Language.EN
