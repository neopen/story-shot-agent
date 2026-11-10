"""结构化相机控制构建（M0.4.3 / 0.4.4 景别一致性）。

由来源镜头景别与片段描述推导相机参数，供支持运镜的目标模型直出。
景别探测顺序为「最终提示词文本 > 来源镜头景别 > 默认值」（FR-031），
别名表覆盖 ``ShotType`` 全部值并按长词优先匹配（FR-030）。
"""

from typing import Dict, List, Optional, Tuple

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
    CameraMotion.DOLLY: ("dolly", "推镜", "拉镜", "跟拍"),
    CameraMotion.ZOOM: ("zoom", "变焦", "推近", "拉远"),
    CameraMotion.HANDHELD: ("handheld", "手持", "晃动"),
    CameraMotion.CRANE: ("crane", "升降", "摇臂"),
    CameraMotion.ORBIT: ("orbit", "环绕", "绕拍"),
}


def _detect_from_text(text: Optional[str]) -> str:
    """从最终提示词文本探测景别；无法识别返回空串（FR-031/FR-032）"""
    lowered = str(text or "").lower()
    if not lowered:
        return ""
    for alias, normalized in _TEXT_ALIASES:
        if alias in lowered:
            return normalized
    return ""


def _normalize_source(shot_type: Optional[str]) -> str:
    """把来源景别归一化为精确匹配键（小写、空格/连字符转下划线）"""
    raw = str(shot_type or "").strip().lower()
    return raw.replace("-", "_").replace(" ", "_")


def _normalize_shot_type(shot_type: Optional[str], description: str) -> str:
    """按「提示词文本 > 来源景别 > 默认值」归一化景别（FR-031~033）

    来源景别为已知扩展值时原样输出；完全未知时保留原始值并告警，
    不静默降级为默认景别。
    """
    detected = _detect_from_text(description)
    if detected:
        return detected

    source = str(shot_type or "").strip()
    if not source:
        return DEFAULT_SHOT_TYPE

    normalized = _EXACT_ALIASES.get(_normalize_source(source))
    if normalized:
        return normalized

    warning(f"未知景别来源，保留原始值: {source}")
    return source


def _detect_motion(description: str) -> tuple[CameraMotion, float]:
    """从描述推断运镜方式与强度"""
    lowered = (description or "").lower()
    for motion, keywords in _MOTION_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            intensity = 0.6 if motion == CameraMotion.HANDHELD else 0.4
            return motion, intensity
    return CameraMotion.STATIC, 0.2


def build_camera_control(
    description: str, shot_type: Optional[str] = None
) -> CameraControl:
    """构建片段的结构化相机控制参数"""
    normalized_shot_type = _normalize_shot_type(shot_type, description)
    motion, intensity = _detect_motion(description)
    return CameraControl(
        shot_type=normalized_shot_type,
        motion=motion,
        intensity=intensity,
        rack_focus=normalized_shot_type == ShotType.CLOSE_UP.value,
        fps=24,
        shutter_angle=180.0,
    )
