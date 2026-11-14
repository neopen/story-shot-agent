"""结构化相机控制构建（M0.4.3 / 0.4.4 景别一致性）。

由来源镜头景别与片段描述推导相机参数，供支持运镜的目标模型直出。
景别探测顺序为「来源镜头景别 > 最终提示词文本 > 默认值」：来源景别是镜头
计划的事实源，提示词文本只在其缺失时兜底，避免 LLM 改写把中景升级为特写、
把 POV 主观视角吞成 close_up；文本兜底按短语出现位置取最靠前者，保留
POV、极特写等特殊视角（FR-031）。
别名表覆盖 ``ShotType`` 全部值并按长词优先匹配（FR-030）。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from penshot.logger import warning
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    CameraControl,
    CameraMotion,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotType

DEFAULT_SHOT_TYPE = ShotType.MEDIUM_SHOT.value

# 来源景别精确别名：归一化（小写、空格/连字符转下划线）后精确匹配
_EXACT_ALIASES: Dict[str, str] = {
    "close_up": ShotType.CLOSE_UP.value,
    "closeup": ShotType.CLOSE_UP.value,
    "close": ShotType.CLOSE_UP.value,
    "near": ShotType.CLOSE_UP.value,
    "特写": ShotType.CLOSE_UP.value,
    "近景": ShotType.CLOSE_UP.value,
    "extreme_close_up": ShotType.EXTREME_CLOSE_UP.value,
    "extremecloseup": ShotType.EXTREME_CLOSE_UP.value,
    "极特写": ShotType.EXTREME_CLOSE_UP.value,
    "大特写": ShotType.EXTREME_CLOSE_UP.value,
    "medium_shot": ShotType.MEDIUM_SHOT.value,
    "medium": ShotType.MEDIUM_SHOT.value,
    "中景": ShotType.MEDIUM_SHOT.value,
    "wide_shot": ShotType.WIDE_SHOT.value,
    "wide": ShotType.WIDE_SHOT.value,
    "广角": ShotType.WIDE_SHOT.value,
    "全景": ShotType.WIDE_SHOT.value,
    "long_shot": ShotType.LONG_SHOT.value,
    "long": ShotType.LONG_SHOT.value,
    "远景": ShotType.LONG_SHOT.value,
    "over_shoulder": ShotType.OVER_SHOULDER.value,
    "过肩": ShotType.OVER_SHOULDER.value,
    "pov": ShotType.POV.value,
    "point_of_view": ShotType.POV.value,
    "主观": ShotType.POV.value,
    "第一人称": ShotType.POV.value,
    "two_shot": ShotType.TWO_SHOT.value,
    "双人": ShotType.TWO_SHOT.value,
    "following_shot": ShotType.FOLLOWING_SHOT.value,
    "follow_shot": ShotType.FOLLOWING_SHOT.value,
    "跟拍": ShotType.FOLLOWING_SHOT.value,
    "panorama": ShotType.PANORAMA.value,
    "摇摄": ShotType.PANORAMA.value,
    "全景移动": ShotType.PANORAMA.value,
    "zoom": ShotType.ZOOM.value,
    "变焦": ShotType.ZOOM.value,
    "推拉": ShotType.ZOOM.value,
    "action": ShotType.ACTION.value,
    "动作镜头": ShotType.ACTION.value,
    "moving": ShotType.MOVING.value,
    "移动镜头": ShotType.MOVING.value,
}

# 文本别名（按长度倒序匹配，保证 "extreme close-up" 不被 "close-up" 截胡）
_TEXT_ALIASES: List[Tuple[str, str]] = sorted(
    [
        ("extreme close-up", ShotType.EXTREME_CLOSE_UP.value),
        ("extreme close up", ShotType.EXTREME_CLOSE_UP.value),
        ("extreme_close_up", ShotType.EXTREME_CLOSE_UP.value),
        ("极特写", ShotType.EXTREME_CLOSE_UP.value),
        ("大特写", ShotType.EXTREME_CLOSE_UP.value),
        ("medium close-up", ShotType.CLOSE_UP.value),
        ("medium close up", ShotType.CLOSE_UP.value),
        ("over-the-shoulder", ShotType.OVER_SHOULDER.value),
        ("over the shoulder", ShotType.OVER_SHOULDER.value),
        ("over_shoulder", ShotType.OVER_SHOULDER.value),
        ("过肩", ShotType.OVER_SHOULDER.value),
        ("point-of-view", ShotType.POV.value),
        ("point of view", ShotType.POV.value),
        ("following_shot", ShotType.FOLLOWING_SHOT.value),
        ("following shot", ShotType.FOLLOWING_SHOT.value),
        ("follow shot", ShotType.FOLLOWING_SHOT.value),
        ("跟拍", ShotType.FOLLOWING_SHOT.value),
        ("panoramic shot", ShotType.PANORAMA.value),
        ("medium_shot", ShotType.MEDIUM_SHOT.value),
        ("medium shot", ShotType.MEDIUM_SHOT.value),
        ("中景", ShotType.MEDIUM_SHOT.value),
        ("中近景", ShotType.CLOSE_UP.value),
        ("close-up", ShotType.CLOSE_UP.value),
        ("close up", ShotType.CLOSE_UP.value),
        ("close_up", ShotType.CLOSE_UP.value),
        ("closeup", ShotType.CLOSE_UP.value),
        ("特写", ShotType.CLOSE_UP.value),
        ("近景", ShotType.CLOSE_UP.value),
        ("wide_shot", ShotType.WIDE_SHOT.value),
        ("wide shot", ShotType.WIDE_SHOT.value),
        ("全景", ShotType.WIDE_SHOT.value),
        ("广角", ShotType.WIDE_SHOT.value),
        ("long_shot", ShotType.LONG_SHOT.value),
        ("long shot", ShotType.LONG_SHOT.value),
        ("远景", ShotType.LONG_SHOT.value),
        ("two_shot", ShotType.TWO_SHOT.value),
        ("two shot", ShotType.TWO_SHOT.value),
        ("two-shot", ShotType.TWO_SHOT.value),
        ("双人", ShotType.TWO_SHOT.value),
        ("pov", ShotType.POV.value),
        ("主观", ShotType.POV.value),
        ("第一人称", ShotType.POV.value),
        ("panorama", ShotType.PANORAMA.value),
        ("摇摄", ShotType.PANORAMA.value),
        ("全景移动", ShotType.PANORAMA.value),
        ("zoom shot", ShotType.ZOOM.value),
        ("zoom", ShotType.ZOOM.value),
        ("变焦", ShotType.ZOOM.value),
        ("推拉", ShotType.ZOOM.value),
        ("action shot", ShotType.ACTION.value),
        ("动作镜头", ShotType.ACTION.value),
        ("moving shot", ShotType.MOVING.value),
        ("移动镜头", ShotType.MOVING.value),
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)

_MOTION_KEYWORDS = {
    CameraMotion.PAN: ("pan", "摇镜", "横向移动"),
    CameraMotion.TILT: ("tilt", "俯仰", "上下移动"),
    CameraMotion.DOLLY: (
        "dolly in",
        "dolly out",
        "push in",
        "push-in",
        "pull back",
        "pull-back",
        "tracking shot",
        "tracking",
        "dolly",
        "推镜",
        "拉镜",
        "跟拍",
    ),
    CameraMotion.ZOOM: ("zoom", "变焦", "推近", "拉远"),
    # “手持”单独出现多指“手里拿着道具”，仅保留明确的运镜表述
    CameraMotion.HANDHELD: ("handheld", "手持镜头", "手持拍摄", "手持晃动", "晃动"),
    CameraMotion.CRANE: ("crane", "升降", "摇臂"),
    CameraMotion.ORBIT: ("orbit", "环绕", "绕拍"),
}

# 方向语义相容的运动族：推镜/拉镜/变焦同属 dolly 族，互相不告警
_MOTION_FAMILIES: Dict[CameraMotion, str] = {
    CameraMotion.PAN: "pan",
    CameraMotion.TILT: "tilt",
    CameraMotion.DOLLY: "dolly",
    CameraMotion.ZOOM: "dolly",
    CameraMotion.HANDHELD: "handheld",
    CameraMotion.CRANE: "crane",
    CameraMotion.ORBIT: "orbit",
}

# 提示词明确写死静态时，camera.motion 不应是任何运动族
_STATIC_PROMPT_MARKERS: Tuple[str, ...] = (
    "static camera",
    "fixed camera",
    "locked-off",
    "locked off",
    "固定机位",
    "固定镜头",
    "静止镜头",
    "镜头固定",
)

# 判定 static 但文本含明确运镜动词时的自检词（不含已入表词汇）
_STATIC_CONFLICT_MARKERS: Tuple[str, ...] = (
    "camera move",
    "camera follow",
    "camera push",
    "camera pull",
    "camera track",
    "镜头移动",
    "镜头跟随",
    "运镜",
)


def _keyword_specificity(keyword: str) -> Tuple[int, int]:
    """关键词具体度：多词短语优先于单词，同词数时取更长者"""
    tokens = [part for part in re.split(r"[\s_-]+", keyword.strip()) if part]
    return len(tokens), len(keyword)


def detect_shot_type_from_text(text: Optional[str]) -> str:
    """从最终提示词文本探测景别；无法识别返回空串（FR-031/FR-032）

    按短语出现位置优先：只有开头的景别表述才是构图主体，靠后的
    ``close-up`` 不能截胡开头的 ``POV``/``extreme close-up``；
    同一位置按别名长度取更长者。
    质量审查（FR-061）复用同一份别名表与匹配顺序，保证审计口径与构建口径一致。
    """
    lowered = str(text or "").lower()
    if not lowered:
        return ""
    detected = ""
    first_index = -1
    for alias, normalized in _TEXT_ALIASES:  # 已按长度倒序
        index = lowered.find(alias)
        if index < 0:
            continue
        if first_index < 0 or index < first_index:
            detected, first_index = normalized, index
    return detected


def _normalize_source(shot_type: Optional[str]) -> str:
    """把来源景别归一化为精确匹配键（小写、空格/连字符转下划线）"""
    raw = str(shot_type or "").strip().lower()
    return raw.replace("-", "_").replace(" ", "_")


def _resolve_source(source: str) -> str:
    """解析来源景别：已知别名归一化，未知值保留原文并告警（FR-032/033）"""
    normalized = _EXACT_ALIASES.get(_normalize_source(source))
    if normalized:
        return normalized

    warning(f"未知景别来源，保留原始值: {source}")
    return source


def _normalize_shot_type(
    shot_type: Optional[str], description: str
) -> Tuple[str, str, str]:
    """按「来源景别 > 提示词文本 > 默认值」归一化景别（FR-031~034）

    来源景别是镜头计划的事实源，优先直接采用，避免 LLM 提示词里的
    景别短语把结构化字段升级/降级；仅当来源缺失时才退回提示词文本探测。
    返回 ``(shot_type, source_shot_type, shot_type_raw)``；
    来源景别为已知扩展值时原样输出，完全未知时保留原始值并告警，
    不静默降级为默认景别。
    """
    source_raw = str(shot_type or "").strip()
    source_normalized = _resolve_source(source_raw) if source_raw else ""

    if source_normalized:
        return source_normalized, source_normalized, source_raw

    detected = detect_shot_type_from_text(description)
    if detected:
        return detected, "", source_raw

    return DEFAULT_SHOT_TYPE, "", source_raw


def _warn_static_motion_mismatch(lowered: str) -> None:
    """static 与文本中的明确运镜表述冲突时告警（不静默丢弃）"""
    hits = [marker for marker in _STATIC_CONFLICT_MARKERS if marker in lowered]
    if hits:
        warning(
            "运镜判定为 static，但文本含明确运动表述: " + ", ".join(sorted(set(hits)))
        )


def _detect_motion(description: str) -> tuple[CameraMotion, float]:
    """从描述推断运镜方式与强度

    同一文本命中多个运动族时，按“多词短语 > 单词、长词 > 短词”取最具体者，
    并对冲突词告警，避免 ``slow pull-back`` 被 ``拉远`` 之类的短词截胡。
    """
    lowered = (description or "").lower()
    candidates: List[Tuple[CameraMotion, str]] = [
        (motion, keyword)
        for motion, keywords in _MOTION_KEYWORDS.items()
        for keyword in keywords
        if keyword in lowered
    ]
    if not candidates:
        _warn_static_motion_mismatch(lowered)
        return CameraMotion.STATIC, 0.2

    motion, keyword = candidates[0]
    for candidate_motion, candidate_keyword in candidates[1:]:
        if _keyword_specificity(candidate_keyword) > _keyword_specificity(keyword):
            motion, keyword = candidate_motion, candidate_keyword

    conflicting = sorted({item.value for item, _ in candidates if item != motion})
    if conflicting:
        warning(
            f"运镜关键词冲突: 按具体短语取 {motion.value}"
            f"（命中 {keyword}），同时出现 {', '.join(conflicting)}"
        )

    intensity = 0.6 if motion == CameraMotion.HANDHELD else 0.4
    return motion, intensity


def detect_motion_from_text(text: str) -> Tuple[Optional[CameraMotion], str]:
    """从文本探测最具体的运镜方式，返回 ``(运镜, 命中关键词)``

    与 ``_detect_motion`` 共用词表与具体度排序，但不再默认 static：
    未命中时返回 ``(None, "")``，便于区分“没写运镜”和“明确写静态”。
    """
    lowered = (text or "").lower()
    candidates: List[Tuple[CameraMotion, str]] = [
        (motion, keyword)
        for motion, keywords in _MOTION_KEYWORDS.items()
        for keyword in keywords
        if keyword in lowered
    ]
    if not candidates:
        return None, ""
    motion, keyword = candidates[0]
    for candidate_motion, candidate_keyword in candidates[1:]:
        if _keyword_specificity(candidate_keyword) > _keyword_specificity(keyword):
            motion, keyword = candidate_motion, candidate_keyword
    return motion, keyword


def _normalize_motion(motion: Any) -> Optional[CameraMotion]:
    """把 CameraMotion / 字符串归一为枚举；未知值返回 None"""
    if isinstance(motion, CameraMotion):
        return motion
    text = str(motion or "").strip().lower()
    if not text:
        return None
    try:
        return CameraMotion(text)
    except ValueError:
        return None


def check_motion_consistency(text: str, motion: Any) -> Optional[Tuple[str, str]]:
    """反向校验 camera.motion 与最终提示词运镜表述（0.4.5 任务 5）

    - 提示词没写运镜、motion=static：一致，不告警；
    - 提示词写死 static/fixed camera，但 motion 是运动族：warning；
    - 提示词命中运镜、motion 是相容族（push-in ≈ dolly ≈ zoom）：不告警；
    - 提示词命中运镜、motion 是不同族：warning；
    - 提示词没写运镜、motion 是运动族：info（仅提示，不记违规）。

    Returns:
        ``(level, message)``，level 为 ``warning`` / ``info``；无需提示返回 None
    """
    declared = _normalize_motion(motion)
    if declared is None:
        return None

    detected, keyword = detect_motion_from_text(text)
    lowered = (text or "").lower()
    if detected is None:
        if declared == CameraMotion.STATIC:
            return None
        static_hits = [marker for marker in _STATIC_PROMPT_MARKERS if marker in lowered]
        if static_hits:
            return (
                "warning",
                f"camera.motion={declared.value} 但提示词明确写为静止镜头"
                f"（{'/'.join(static_hits)}）",
            )
        return (
            "info",
            f"camera.motion={declared.value} 但提示词未出现运镜表述",
        )

    if declared == CameraMotion.STATIC:
        return (
            "warning",
            f"camera.motion=static 但提示词含运镜表述「{keyword}」",
        )
    if _MOTION_FAMILIES.get(declared) == _MOTION_FAMILIES.get(detected):
        return None
    return (
        "warning",
        f"camera.motion={declared.value} 与提示词运镜「{keyword}」"
        f"（{detected.value}）不一致",
    )


def build_camera_control(
    description: str, shot_type: Optional[str] = None
) -> CameraControl:
    """构建片段的结构化相机控制参数"""
    normalized, source_normalized, source_raw = _normalize_shot_type(
        shot_type, description
    )
    motion, intensity = _detect_motion(description)
    return CameraControl(
        shot_type=normalized,
        source_shot_type=source_normalized,
        shot_type_raw=source_raw,
        motion=motion,
        intensity=intensity,
        rack_focus=normalized == ShotType.CLOSE_UP.value,
        fps=24,
        shutter_angle=180.0,
    )
