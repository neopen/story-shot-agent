"""路由特征抽取（M0.4.3）。

本模块只做确定性规则抽取，不调用 LLM，保证路由结果可复现、可解释。
"""

from typing import Any

from penshot.neopen.agent.model_adapter.image_to_video import (
    has_critical_text,
    should_use_image_to_video,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AestheticBias,
    ConsistencyNeed,
    MotionComplexity,
    RouteFeatures,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoPrompt

# 高复杂度动作关键词：命中任意一个即视为高复杂度
HIGH_MOTION_KEYWORDS = (
    "fight",
    "chase",
    "battle",
    "explosion",
    "dance",
    "run",
    "打斗",
    "追逐",
    "战斗",
    "爆炸",
    "舞蹈",
    "奔跑",
    "翻滚",
    "旋转",
    "飞跃",
)

# 中等复杂度动作关键词
MEDIUM_MOTION_KEYWORDS = (
    "walk",
    "turn",
    "push",
    "pick",
    "hug",
    "走",
    "转身",
    "推",
    "拿起",
    "拥抱",
    "挥手",
    "坐下",
)

# 风格关键词映射
STYLE_KEYWORDS = {
    "anime": AestheticBias.ANIME,
    "animation": AestheticBias.ANIME,
    "cartoon": AestheticBias.ANIME,
    "动画": AestheticBias.ANIME,
    "二次元": AestheticBias.ANIME,
    "realistic": AestheticBias.REALISTIC,
    "photorealistic": AestheticBias.REALISTIC,
    "写实": AestheticBias.REALISTIC,
    "cinematic": AestheticBias.CINEMATIC,
    "film": AestheticBias.CINEMATIC,
    "电影": AestheticBias.CINEMATIC,
    "电影感": AestheticBias.CINEMATIC,
}


def _character_has_anchors(prompt: AIVideoPrompt, contract: Any) -> bool:
    """角色是否在契约中登记了外观锚点"""
    if contract is None or not prompt.main_character:
        return False
    character = getattr(contract, "characters", {}).get(prompt.main_character)
    return bool(getattr(character, "appearance_anchors", None))


def _detect_motion_complexity(text: str) -> MotionComplexity:
    """按动作关键词判断动作复杂度"""
    lowered = (text or "").lower()
    if any(keyword in lowered for keyword in HIGH_MOTION_KEYWORDS):
        return MotionComplexity.HIGH
    matches = sum(1 for keyword in MEDIUM_MOTION_KEYWORDS if keyword in lowered)
    if matches >= 2:
        return MotionComplexity.MEDIUM
    if matches == 1:
        return MotionComplexity.MEDIUM
    return MotionComplexity.LOW


def _detect_style_bias(style: str | None, text: str) -> AestheticBias:
    """按风格声明与提示词关键词判断风格倾向"""
    lowered = f"{style or ''} {(text or '')}".lower()
    for keyword, bias in STYLE_KEYWORDS.items():
        if keyword in lowered:
            return bias
    return AestheticBias.CINEMATIC


def extract_route_features(
    prompt: AIVideoPrompt, contract: Any = None
) -> RouteFeatures:
    """从片段提示词与契约提取路由特征"""
    anchors = _character_has_anchors(prompt, contract)
    if anchors:
        consistency = ConsistencyNeed.HIGH
    elif prompt.main_character:
        consistency = ConsistencyNeed.MEDIUM
    else:
        consistency = ConsistencyNeed.LOW

    return RouteFeatures(
        has_critical_text=has_critical_text(prompt.prompt),
        motion_complexity=_detect_motion_complexity(prompt.prompt),
        character_consistency_need=consistency,
        style_bias=_detect_style_bias(prompt.style, prompt.prompt),
        duration=prompt.duration,
        needs_first_last_frame=should_use_image_to_video(prompt, contract),
    )
