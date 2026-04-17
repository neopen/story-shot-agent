"""
@FileName: shot_language.py
@Description: 语言管理模块
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/12/18 14:10
"""
import os
from enum import Enum
from typing import Optional

from penshot.logger import error


class ShotLanguage(str, Enum):
    """
    语言枚举类，统一管理语言标识
    """
    ZH = 'zh'  # 中文
    EN = 'en'  # 英文

    @staticmethod
    def from_string(lang_str: str) -> Optional['ShotLanguage']:
        """
        从字符串转换为Language枚举
        :param lang_str: 语言字符串，支持'zh'或'en'
        :return: ShotLanguage枚举对象，如果不支持返回None
        """
        if not lang_str or lang_str.isspace():
            return ShotLanguage.ZH

        # 先去除空格并转换为小写以支持'Zh', 'EN', '  en  '等输入
        lang_str = lang_str.strip().lower()

        if lang_str in ['zh', '中文']:
            return ShotLanguage.ZH
        elif lang_str in ['en', '英文']:
            return ShotLanguage.EN
        return ShotLanguage.ZH


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
            _current_language = ShotLanguage.from_string(lang_str) or ShotLanguage.ZH
        except Exception as e:
            error(f'初始化语言设置失败，使用默认值{ShotLanguage.ZH.value}：{e}')


def set_language(lang: ShotLanguage) -> bool:
    """
    设置当前语言
    :param lang: 语言字符串，支持'zh', 'en', '中文', '英文'
    :return: 设置成功返回True，失败返回False
    """
    if lang:
        global _current_language
        lang_enum = lang
        if lang_enum:
            _current_language = lang_enum
            return True
    return False


def set_str_language(lang: str) -> bool:
    """
    从请求参数设置语言
    :param lang: 语言字符串，支持'zh', 'en', '中文', '英文'
    :return: 设置成功返回True，失败返回False
    """
    # 请求参数的优先级高于环境变量
    return set_language(ShotLanguage.from_string(lang))


def get_language() -> ShotLanguage:
    """
    获取当前语言枚举
    :return: 当前语言枚举对象
    """
    global _current_language
    if _current_language is None:
        _init_language_from_env()
    return _current_language or ShotLanguage.ZH  # 默认返回中文


def is_chinese() -> bool:
    """
    判断当前语言是否为中文
    :return: 是中文返回True，否则返回False
    """
    return get_language() == ShotLanguage.ZH


def is_english() -> bool:
    """
    判断当前语言是否为英文
    :return: 是英文返回True，否则返回False
    """
    return get_language() == ShotLanguage.EN
