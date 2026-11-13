"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: action_nodes.py
@Description: 动作节点识别与确定性时长计算（0.4.6 FR-075/077）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

import re
from typing import Dict, Optional, Sequence, Tuple

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.prompt_converter.camera_builder import detect_motion_from_text
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    ParsedScript,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo

# 动作节点词表：只收录可判定的具体动作短语，避免使用“站”“走”等过宽的单字
ACTION_NODE_PATTERNS: Tuple[str, ...] = tuple(
    sorted(
        {
            "看了一眼",
            "低下头",
            "抬起头",
            "转过头",
            "转过身",
            "皱起眉",
            "叹口气",
            "打量着",
            "低头",
            "抬头",
            "仰望",
            "凝视",
            "注视",
            "看着",
            "望向",
            "望着",
            "打量",
            "回头",
            "转身",
            "侧身",
            "走过",
            "走出",
            "走进",
            "走向",
            "走上",
            "走下",
            "走回",
            "迈步",
            "迈着",
            "停下",
            "站起",
            "坐下",
            "起身",
            "揉",
            "攥",
            "握紧",
            "握住",
            "握",
            "抓住",
            "拿起",
            "递出",
            "接过",
            "推开",
            "打开",
            "关上",
            "叹气",
            "叹了",
            "点头",
            "摇头",
            "皱眉",
            "微笑",
            "颤抖",
            "伸手",
            "后退",
            "靠近",
            "说道",
        },
        key=len,
        reverse=True,
    )
)

_ACTION_NODE_RE = re.compile(
    "|".join(re.escape(pattern) for pattern in ACTION_NODE_PATTERNS)
)
_DIALOGUE_QUOTE_RE = re.compile(r"[“\"「『]([^”\"」』]+)[”\"」』]")
_TEXT_UNIT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")

_BASE_STATIC_DURATION = 1.5
_BASE_MOTION_DURATION = 2.0
_PER_ACTION_NODE = 0.6
_CHARS_PER_SECOND = 4.0


def extract_action_nodes(text: str) -> Tuple[str, ...]:
    """提取文本中的动作节点词

    与 :func:`count_action_nodes` 使用同一套确定性词表，便于重复检测比较
    动作交集（FR-070）。

    Args:
        text: 镜头或片段描述

    Returns:
        按出现顺序排列的动作节点词，可能重复
    """
    return tuple(_ACTION_NODE_RE.findall(str(text or "")))


def count_action_nodes(text: str) -> int:
    """统计文本中的可识别动作节点数量

    使用最长优先的确定性词表匹配，不调用 LLM（FR-077）。

    Args:
        text: 镜头或片段描述

    Returns:
        动作节点数量
    """
    return len(extract_action_nodes(text))


def _dialogue_text(content: str) -> str:
    """提取台词正文：优先取引号内文本，其次取冒号后的内容"""
    text = str(content or "")
    quoted = _DIALOGUE_QUOTE_RE.findall(text)
    if quoted:
        return "".join(quoted)
    for separator in ("：", ":"):
        if separator in text:
            return text.split(separator, 1)[1]
    return text


def count_text_dialogue_chars(text: str) -> int:
    """统计文本中引号内台词的字数

    Args:
        text: 片段或镜头描述

    Returns:
        引号内 CJK 字符与英文/数字字符数量
    """
    return sum(
        len(_TEXT_UNIT_RE.findall(span))
        for span in _DIALOGUE_QUOTE_RE.findall(str(text or ""))
    )


def count_dialogue_chars_by_elements(
    element_ids: Optional[Sequence[str]],
    script: Optional[ParsedScript],
) -> int:
    """按元素 ID 统计台词字数

    Args:
        element_ids: 剧本元素 ID 列表
        script: 剧本解析结果，可为空

    Returns:
        台词字数
    """
    if script is None or not element_ids:
        return 0

    elements: Dict[str, BaseElement] = {
        element.id: element for scene in script.scenes for element in scene.elements
    }

    total = 0
    for element_id in dict.fromkeys(element_ids):
        element = elements.get(element_id)
        if element is None:
            continue
        element_type = str(getattr(element.type, "value", element.type))
        if element_type != ElementType.DIALOGUE.value:
            continue
        total += len(_TEXT_UNIT_RE.findall(_dialogue_text(element.content)))
    return total


def count_dialogue_chars(shot: ShotInfo, script: Optional[ParsedScript]) -> int:
    """统计镜头关联台词的字数

    只统计 ``shot.element_ids`` 中类型为 ``DIALOGUE`` 的元素，并按引号或
    冒号提取台词正文，避免把叙述性动作计入台词时长。

    Args:
        shot: 镜头信息
        script: 剧本解析结果，可为空

    Returns:
        台词字数（CJK 字符与英文/数字字符逐个计数）
    """
    return count_dialogue_chars_by_elements(shot.element_ids, script)


def compute_duration_from_text(
    text: str,
    *,
    dialogue_chars: int = 0,
    has_motion: Optional[bool] = None,
    max_duration: float = 5.0,
    min_duration: float = 2.5,
) -> float:
    """按动作复杂度计算片段时长（FR-075/FR-076）

    基础值：静态 1.5 秒、含运镜 2.0 秒；每个动作节点 +0.6 秒；台词按
    每 4 字每秒叠加；最终夹取到 ``[min_duration, max_duration]``。

    Args:
        text: 镜头或片段描述
        dialogue_chars: 台词字数
        has_motion: 是否含运镜；为 None 时从文本确定性探测
        max_duration: 单片段上限，默认 5.0 秒
        min_duration: 单片段下限，默认 2.5 秒

    Returns:
        保留两位小数的片段时长
    """
    motion = has_motion
    if motion is None:
        detected_motion, _ = detect_motion_from_text(str(text or ""))
        motion = detected_motion is not None

    base = _BASE_MOTION_DURATION if motion else _BASE_STATIC_DURATION
    action_duration = _PER_ACTION_NODE * count_action_nodes(text)
    dialogue_duration = max(0, dialogue_chars) / _CHARS_PER_SECOND
    raw = base + action_duration + dialogue_duration
    return round(max(min_duration, min(raw, max_duration)), 2)


def compute_duration(
    shot: ShotInfo,
    script: Optional[ParsedScript],
    *,
    max_duration: float = 5.0,
    min_duration: float = 2.5,
) -> float:
    """计算单个镜头时长，台词字数由 ``element_ids`` 反查

    Args:
        shot: 镜头信息
        script: 剧本解析结果，可为空
        max_duration: 单片段上限
        min_duration: 单片段下限

    Returns:
        保留两位小数的镜头时长
    """
    return compute_duration_from_text(
        shot.description,
        dialogue_chars=count_dialogue_chars(shot, script),
        max_duration=max_duration,
        min_duration=min_duration,
    )


__all__ = [
    "ACTION_NODE_PATTERNS",
    "compute_duration",
    "compute_duration_from_text",
    "count_action_nodes",
    "count_dialogue_chars",
    "count_dialogue_chars_by_elements",
    "count_text_dialogue_chars",
    "extract_action_nodes",
]
