"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character_names.py
@Description: 角色名归一化：把各语言的“无角色”占位词统一视为空
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

import re
from typing import Any, List, Optional

from penshot.neopen.constants.character import NON_CHARACTER_NAMES

# 复合角色字段的常见分隔符（中英文逗号、顿号、斜杠、竖线、分号）
_SEPARATOR_PATTERN = re.compile(r"[,，、/|;；]+")


def normalize_character_name(value: Any) -> str:
    """去首尾空白，并把非角色占位词归一为空串

    词表位于 `constants.character`，按语言分组；本函数只做大小写无关匹配，
    新增语言无需改动。

    Args:
        value: 原始角色名（可能是任意类型）

    Returns:
        归一化后的角色名；占位词/空值/非字符串返回空串
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "" if text.casefold() in NON_CHARACTER_NAMES else text


def split_character_names(value: Any) -> List[str]:
    """把复合角色字段拆成归一化名字列表

    分镜 LLM 偶尔把同框角色写成 ``"李明, 张晨"`` 这类复合值；按常见分隔符
    拆分后逐个归一化，使契约校验按角色粒度判断，而不是把整串当成一个
    未知角色而误报。

    Args:
        value: 原始角色字段（可能是任意类型）

    Returns:
        去重且保序的角色名列表；空值/占位词/非字符串返回空列表
    """
    if not isinstance(value, str):
        return []
    names = [normalize_character_name(part) for part in _SEPARATOR_PATTERN.split(value)]
    return list(dict.fromkeys(name for name in names if name))


def optional_character_name(value: Any) -> Optional[str]:
    """同 `normalize_character_name`，但空值返回 None，适配 Optional 字段"""
    return normalize_character_name(value) or None
