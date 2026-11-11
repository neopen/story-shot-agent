"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: model_adapter.py
@Description: 目标模型提示词适配器（通用 AIVideoPrompt -> 模型专属提示词包）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    ModelCapability,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
    CameraControl,
)

# 镜头类型关键词 -> 结构化景别（用于从通用 prompt 文本探测相机表述）
_SHOT_TYPE_KEYWORDS: Dict[str, str] = {
    "extreme close-up": "extreme_close_up",
    "extreme close up": "extreme_close_up",
    "close-up": "close_up",
    "close up": "close_up",
    "medium close-up": "medium_close_up",
    "medium shot": "medium",
    "wide shot": "wide",
    "extreme wide": "extreme_wide",
    "establishing shot": "wide",
}

# 运镜关键词 -> 结构化运镜方式
_MOTION_KEYWORDS: Dict[str, str] = {
    "tracking shot": "dolly",
    "dolly": "dolly",
    "handheld": "handheld",
    "zoom": "zoom",
    "tilt": "tilt",
    "pan": "pan",
}


def _detect_camera(prompt: str) -> Optional[Dict[str, str]]:
    """从通用提示词文本中探测镜头类型与运镜方式；无法识别时返回 None"""
    lowered = prompt.lower()
    shot_type: Optional[str] = None
    motion: str = "static"

    for keyword, value in _SHOT_TYPE_KEYWORDS.items():
        if keyword in lowered:
            shot_type = value
            break

    for keyword, value in _MOTION_KEYWORDS.items():
        if keyword in lowered:
            motion = value
            break

    if shot_type is None and motion == "static":
        return None
    return {"shot_type": shot_type or "medium", "motion": motion}


class BaseModelAdapter(ABC):
    """模型适配器抽象基类：把通用片段提示词转换为目标模型专属提示词包"""

    def __init__(self, capability: ModelCapability):
        self.capability = capability

    @property
    def model_name(self) -> str:
        """返回目标模型名"""
        return self.capability.model_name

    def adapt(self, prompt: AIVideoPrompt) -> AdaptedPromptPackage:
        """适配单个片段（模板方法）；各子类通过覆写钩子产生结构差异

        相机参数优先消费提示词阶段产出的结构化 ``camera``：目标模型支持结构化
        相机控制时直接透传，不支持时降级为模型惯用的文字描述。
        """
        camera_control: Optional[CameraControl] = None
        if prompt.camera is not None and self.capability.supports_camera_control:
            camera_control = prompt.camera
            camera_text = None
        else:
            camera_text = self.format_camera(_detect_camera(prompt.prompt))

        return AdaptedPromptPackage(
            fragment_id=prompt.fragment_id,
            target_model=self.model_name,
            prompt=self.build_positive_prompt(prompt),
            negative_prompt=self.build_negative_prompt(prompt),
            duration=self._clamp_duration(prompt.duration),
            style=self._resolve_style(prompt),
            camera=camera_text,
            camera_control=camera_control,
            model_params=self.build_model_config(prompt),
        )

    def _clamp_duration(self, duration: float) -> float:
        """将片段时长收敛到模型支持范围（不超过 max_duration）"""
        return min(duration, self.capability.max_duration)

    def _resolve_style(self, prompt: AIVideoPrompt) -> Optional[str]:
        """解析风格：优先取片段内风格，否则用模型美学偏好兜底"""
        return prompt.style or self.capability.aesthetic_bias.value

    @abstractmethod
    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        """构建模型专属正向提示词"""

    @abstractmethod
    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        """构建模型专属负向提示词"""

    @abstractmethod
    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        """按模型习惯格式化相机表述"""

    @abstractmethod
    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        """构建模型专属生成参数"""


class RunwayGen4Adapter(BaseModelAdapter):
    """Runway Gen-4：电影感、自然语言、简洁负向提示词"""

    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        text = prompt.prompt.strip()
        if not text.lower().startswith("cinematic"):
            text = f"cinematic film still, {text}"
        return text

    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        base = (prompt.negative_prompt or "").strip()
        return ", ".join(filter(None, [base, "blurry, low quality, jitter"]))

    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        if camera is None:
            return None
        return f"camera: {camera['shot_type']}, {camera['motion']}"

    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        return {"aspect_ratio": "16:9", "motion_scale": 1.0, "seed": None}


class Kling3Adapter(BaseModelAdapter):
    """Kling 3：详细描述、强化人物一致性、正向负向均为句式"""

    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        parts = [prompt.prompt.strip()]
        if prompt.main_character:
            parts.append(f"main character: {prompt.main_character}")
        parts.append("high detail, cinematic lighting, 8k")
        return ", ".join(parts)

    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        base = (prompt.negative_prompt or "blurry, distorted").strip()
        return f"avoid: {base}"

    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        if camera is None:
            return None
        return f"shot: {camera['shot_type']}, movement: {camera['motion']}"

    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        return {
            "mode": "std",
            "aspect_ratio": "16:9",
            "negative_prompt": True,
            "camera_control": True,
        }


class LumaDreamAdapter(BaseModelAdapter):
    """Luma Dream Machine：关键词风格、中括号标注相机、简洁负向"""

    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        return prompt.prompt.strip()

    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        return (prompt.negative_prompt or "").strip()

    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        if camera is None:
            return None
        return f"[{camera['shot_type']}] [{camera['motion']}]"

    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        return {"resolution": "720p", "aspect_ratio": "16:9", "loop": False}


class Sora2Adapter(BaseModelAdapter):
    """Sora 2：叙述式长文本、不使用负向提示词、强调文字渲染"""

    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        return f"A cinematic scene: {prompt.prompt.strip()}"

    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        # Sora 走自然语言，不依赖负向提示词
        return ""

    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        if camera is None:
            return None
        return f"Shot type: {camera['shot_type']}. Camera movement: {camera['motion']}."

    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        return {"resolution": "1080p", "text_rendering": True, "negative_prompt": False}


class Pika2Adapter(BaseModelAdapter):
    """Pika 2：动画/风格化、参数式相机、显式负向前缀"""

    def build_positive_prompt(self, prompt: AIVideoPrompt) -> str:
        return f"{prompt.prompt.strip()}, anime style, smooth motion, vibrant colors"

    def build_negative_prompt(self, prompt: AIVideoPrompt) -> str:
        base = (prompt.negative_prompt or "blurry, low quality").strip()
        return f"negative_prompt: {base}"

    def format_camera(self, camera: Optional[Dict[str, str]]) -> Optional[str]:
        if camera is None:
            return None
        return f"-camera {camera['motion']} {camera['shot_type']}"

    def build_model_config(self, prompt: AIVideoPrompt) -> Dict[str, Any]:
        return {
            "motion": 1,
            "guidance_scale": 12,
            "negative_prompt": True,
            "frame_rate": 24,
        }
