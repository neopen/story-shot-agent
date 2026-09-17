"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: enum_utils.py
@Description: 
@Author: NeoPen
@Time: 2026/3/28 20:18
"""
from enum import Enum
from typing import Optional, List, Tuple


class EnumPrefixMatcher:
    """枚举前缀匹配工具类（输入完整值，枚举为前缀）"""

    @staticmethod
    def match(
            enum_class: Enum,
            input_text: str,
            min_length: int = 3,
            case_sensitive: bool = False
    ) -> Optional[Enum]:
        """
        匹配完整输入值到枚举前缀

        Args:
            enum_class: 枚举类
            input_text: 完整输入值（如 "runway_gen2"）
            min_length: 枚举值最小长度
            case_sensitive: 是否区分大小写

        Returns:
            匹配的枚举成员
        """
        if not input_text:
            return None

        compare_input = input_text if case_sensitive else input_text.lower()

        for member in enum_class:
            enum_value = str(member.value)

            if len(enum_value) < min_length:
                continue

            compare_enum = enum_value if case_sensitive else enum_value.lower()

            if compare_input.startswith(compare_enum):
                return member

        return None

    @staticmethod
    def match_all(
            enum_class: Enum,
            input_text: str,
            min_length: int = 3,
            case_sensitive: bool = False
    ) -> List[Enum]:
        """返回所有匹配的枚举成员"""
        if not input_text:
            return []

        compare_input = input_text if case_sensitive else input_text.lower()
        results = []

        for member in enum_class:
            enum_value = str(member.value)

            if len(enum_value) < min_length:
                continue

            compare_enum = enum_value if case_sensitive else enum_value.lower()

            if compare_input.startswith(compare_enum):
                results.append(member)

        return results

    @staticmethod
    def validate(
            enum_class: Enum,
            input_text: str,
            min_length: int = 3,
            case_sensitive: bool = False
    ) -> Tuple[bool, Optional[Enum], str]:
        """
        验证输入并返回详细信息

        Returns:
            (是否有效，匹配的枚举，错误/提示信息)
        """
        if not input_text:
            return False, None, "输入不能为空"

        matched = EnumPrefixMatcher.match(
            enum_class, input_text, min_length, case_sensitive
        )

        if matched:
            return True, matched, ""
        else:
            # 提供建议
            suggestions = [str(m.value) for m in enum_class]
            return False, None, f"未匹配，有效前缀：{', '.join(suggestions)}"

    @staticmethod
    def extract_prefix(input_text: str, enum_class: Enum, min_length: int = 3) -> Optional[str]:
        """
        从输入值中提取匹配的枚举前缀

        Returns:
            匹配的前缀字符串
        """
        matched = EnumPrefixMatcher.match(enum_class, input_text, min_length)
        if matched:
            return str(matched.value)
        return None