"""结构化相机控制构建（M0.4.3）。

由来源镜头景别与片段描述推导相机参数，供支持运镜的目标模型直出。
"""

from typing import Optional

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    CameraControl,
    CameraMotion,
)

_SHOT_TYPE_ALIASES = {
    "close_up": "close_up",
    "closeup": "close_up",
    "close": "close_up",
    "特写": "close_up",
    "wide_shot": "wide_shot",
    "wide": "wide_shot",
    "全景": "wide_shot",
    "long_shot": "long_shot",
    "远景": "long_shot",
    "medium_shot": "medium_shot",
    "medium": "medium_shot",
    "中景": "medium_shot",
}

_MOTION_KEYWORDS = {
    CameraMotion.PAN: ("pan", "摇镜", "横向移动"),
    CameraMotion.TILT: ("tilt", "俯仰", "上下移动"),
    CameraMotion.DOLLY: ("dolly", "推镜", "拉镜", "跟拍"),
    CameraMotion.ZOOM: ("zoom", "变焦", "推近", "拉远"),
    CameraMotion.HANDHELD: ("handheld", "手持", "晃动"),
    CameraMotion.CRANE: ("crane", "升降", "摇臂"),
    CameraMotion.ORBIT: ("orbit", "环绕", "绕拍"),
}


def _normalize_shot_type(shot_type: Optional[str], description: str) -> str:
    """归一化景别，优先使用来源镜头景别，缺失时从描述推断"""
    raw = (shot_type or "").lower()
    if raw in _SHOT_TYPE_ALIASES:
        return _SHOT_TYPE_ALIASES[raw]

    lowered = (description or "").lower()
    for alias, normalized in _SHOT_TYPE_ALIASES.items():
        if alias in lowered:
            return normalized
    return "medium_shot"


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
        rack_focus=normalized_shot_type == "close_up",
        fps=24,
        shutter_angle=180.0,
    )
