"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: continuity.py
@Description: 连续性检查词表：按语言分组，供动作/道具一致性判定使用
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/20
"""

from typing import Dict, FrozenSet, Tuple

# 词表按语言分组维护：新增语言时只追加 ACTION_SYNONYM_GROUPS / HOLDING_VERBS /
# PROP_OBJECT_PATTERN_TEMPLATES 对应条目，检查逻辑无需改动。
# 中文按子串匹配；英文等空格分词语言可在模板中改用单词边界。

# 长剧本跨块校验阈值（与 LongScriptChunker 默认单块场景数保持一致）
CROSS_CHUNK_SCENE_THRESHOLD: int = 30

# 近义动作组：同一组内的动词视为同一动作状态，避免“走 -> 步行”被误报。
# 顺序无关，匹配时组内按词长倒序尝试。
ACTION_SYNONYM_GROUPS_ZH: Tuple[FrozenSet[str], ...] = (
    frozenset({"走", "行走", "步行", "迈步", "踱步"}),
    frozenset({"跑", "奔跑", "疾跑", "冲刺", "飞奔"}),
    frozenset({"跳", "跳跃", "跃起", "蹦"}),
    frozenset({"转身", "回头", "转过来", "背过身"}),
    frozenset({"坐下", "坐着", "落座", "坐"}),
    frozenset({"站起", "起身", "站起来", "站立"}),
    frozenset({"拿起", "拿", "握住", "握", "捡起", "拾起"}),
    frozenset({"放下", "搁下", "松开"}),
    frozenset({"推", "推开", "推门"}),
    frozenset({"拉", "拉开", "拉门"}),
    frozenset({"看", "看向", "望", "凝视", "注视", "盯着"}),
)

ACTION_SYNONYM_GROUPS: Dict[str, Tuple[FrozenSet[str], ...]] = {
    "zh": ACTION_SYNONYM_GROUPS_ZH,
}

# 持握类动词：只用于定位道具对象，本身不代表道具发生变化。
# 需按词长倒序排列，保证“拿”不会先于“拿起”命中。
HOLDING_VERBS_ZH: Tuple[str, ...] = (
    "拿起",
    "端着",
    "抱着",
    "举着",
    "提着",
    "握着",
    "攥着",
    "拿着",
    "拿",
    "举",
    "抱",
    "提",
    "端",
    "持",
    "握",
    "攥",
)

HOLDING_VERBS: Dict[str, Tuple[str, ...]] = {
    "zh": HOLDING_VERBS_ZH,
}

# 道具对象抽取模板：`{verbs}` 由 HOLDING_VERBS 注入正则分支。
# 新增语言时只需提供该语言的模板与动词表。
PROP_OBJECT_PATTERN_TEMPLATES: Dict[str, str] = {
    "zh": r"(?:{verbs})(?:着|了)?\s*([\u4e00-\u9fa5A-Za-z0-9]{1,8})",
}

_DEFAULT_LANGUAGE = "zh"


def get_action_synonym_groups(
    language: str = _DEFAULT_LANGUAGE,
) -> Tuple[FrozenSet[str], ...]:
    """获取指定语言的近义动作组，未配置时回退到默认语言"""
    return ACTION_SYNONYM_GROUPS.get(language, ACTION_SYNONYM_GROUPS_ZH)


def get_holding_verbs(language: str = _DEFAULT_LANGUAGE) -> Tuple[str, ...]:
    """获取指定语言的持握动词表，未配置时回退到默认语言"""
    return HOLDING_VERBS.get(language, HOLDING_VERBS_ZH)


def get_prop_object_pattern_template(language: str = _DEFAULT_LANGUAGE) -> str:
    """获取指定语言的道具对象抽取模板，未配置时回退到默认语言"""
    return PROP_OBJECT_PATTERN_TEMPLATES.get(
        language, PROP_OBJECT_PATTERN_TEMPLATES[_DEFAULT_LANGUAGE]
    )
