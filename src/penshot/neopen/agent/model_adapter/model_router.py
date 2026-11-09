"""模型路由规则引擎（M0.4.3）。

按 `settings.yaml` 的 routing 配置为每个片段选择目标模型与生成模式，输出可序列化、
可解释的 `RoutePlan`。规则命中失败或能力不满足时使用兜底策略，不影响既有输出。
"""

from typing import Any, List, Optional

from penshot.config.config import settings
from penshot.config.config_models import RoutingConditionConfig, RoutingRuleConfig
from penshot.neopen.agent.model_adapter.capability_registry import (
    all_capabilities,
    get_capability,
)
from penshot.neopen.agent.model_adapter.model_adapter_factory import get_adapter
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    RouteDecision,
    RouteFeatures,
    RouteMode,
    RoutePlan,
)
from penshot.neopen.agent.model_adapter.route_features import extract_route_features
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
)


def _condition_matches(
    conditions: RoutingConditionConfig, features: RouteFeatures
) -> bool:
    """判断单个片段特征是否满足规则条件"""
    if (
        conditions.has_critical_text is not None
        and conditions.has_critical_text != features.has_critical_text
    ):
        return False
    if (
        conditions.character_consistency_need is not None
        and conditions.character_consistency_need
        != features.character_consistency_need.value
    ):
        return False
    if (
        conditions.motion_complexity is not None
        and conditions.motion_complexity != features.motion_complexity.value
    ):
        return False
    if (
        conditions.style_bias is not None
        and conditions.style_bias != features.style_bias.value
    ):
        return False
    if (
        conditions.min_duration is not None
        and features.duration < conditions.min_duration
    ):
        return False
    if (
        conditions.max_duration is not None
        and features.duration > conditions.max_duration
    ):
        return False
    if (
        conditions.needs_first_last_frame is not None
        and conditions.needs_first_last_frame != features.needs_first_last_frame
    ):
        return False
    return True


def _select_rule(features: RouteFeatures) -> Optional[RoutingRuleConfig]:
    """按优先级选择第一条命中且模型已注册的规则"""
    rules = sorted(settings.routing.rules, key=lambda r: (-r.priority, r.name))
    for rule in rules:
        if get_capability(rule.model) is None:
            # 规则引用了未注册模型：跳过，避免产出下游无法消费的路由
            continue
        if _condition_matches(rule.conditions, features):
            return rule
    return None


def _apply_route_mode(
    package: AdaptedPromptPackage, prompt: Any, mode: RouteMode
) -> None:
    """按路由结果同步生成模式与两段式首帧字段"""
    package.mode = mode
    if mode == RouteMode.TEXT_TO_VIDEO:
        # 切换为文生视频时清理旧的两段式引用，避免下游拿到失效资产
        package.references = []
        package.asset_ref = ""
        package.image_prompt = ""
        package.first_frame_instruction = ""
        return
    if not package.first_frame_instruction:
        package.image_prompt = f"First frame still: {prompt.prompt}"
        package.first_frame_instruction = package.image_prompt


def _duration_fallback(
    target_model: str, duration: float, reason: str
) -> tuple[str, Any, str]:
    """目标模型时长不足时，选择可覆盖该时长且一致性最优的模型"""
    candidates = [
        capability
        for capability in all_capabilities().values()
        if capability.max_duration >= duration
    ]
    if not candidates:
        return target_model, get_capability(target_model), reason
    best = sorted(
        candidates,
        key=lambda c: (-c.character_consistency, c.max_duration),
    )[0]
    return best.model_name, best, f"{reason}+duration_fallback:{best.model_name}"


def build_route_plan(
    packages: List[AdaptedPromptPackage],
    instructions: AIVideoInstructions,
    contract: Any = None,
) -> RoutePlan:
    """按规则为每个片段生成路由决策"""
    prompts = {fragment.fragment_id: fragment for fragment in instructions.fragments}
    decisions: List[RouteDecision] = []

    for index, package in enumerate(packages):
        prompt = prompts.get(package.fragment_id)
        if prompt is None:
            continue

        features = extract_route_features(prompt, contract)
        rule = _select_rule(features) if settings.routing.enabled else None

        target_model = package.target_model
        mode = package.mode
        if rule is not None:
            target_model = rule.model
            mode = RouteMode(rule.mode)
            reason = rule.name
        elif get_capability(target_model) is None:
            target_model = settings.routing.default_model
            reason = "fallback_default_model"
        else:
            reason = "fallback_current_model"

        capability = get_capability(target_model)
        # 时长能力兜底按片段原始时长判断（package.duration 已被源模型收敛过）
        if capability is not None and features.duration > capability.max_duration:
            target_model, capability, reason = _duration_fallback(
                target_model, features.duration, reason
            )

        # 按最终目标模型重新适配，避免提示词包与所选模型不一致
        rebuilt = get_adapter(target_model).adapt(prompt)
        if mode == RouteMode.IMAGE_TO_VIDEO:
            rebuilt.asset_ref = package.asset_ref
            rebuilt.references = package.references
            rebuilt.image_prompt = package.image_prompt or rebuilt.image_prompt
            rebuilt.first_frame_instruction = (
                package.first_frame_instruction or rebuilt.first_frame_instruction
            )
        _apply_route_mode(rebuilt, prompt, mode)
        packages[index] = rebuilt

        decisions.append(
            RouteDecision(
                fragment_id=rebuilt.fragment_id,
                target_model=rebuilt.target_model,
                reason=reason,
                mode=rebuilt.mode,
                asset_ref=rebuilt.asset_ref,
                capability=capability,
            )
        )

    source_model = str(instructions.metadata.get("video_model", "") or "")
    return RoutePlan(source_model=source_model, decisions=decisions)
