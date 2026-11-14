"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: quality_gate.py
@Description: Gate 1 结构与逻辑质量检查（P0-4）：发现问题回写 warnings，不再静默全绿
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

import re
from typing import Any, Dict, List, Optional, Sequence

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetPlanDocument,
    AssetType,
)
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    find_motion_clauses,
)
from penshot.neopen.agent.model_adapter.image_to_video import has_critical_text
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    RouteMode,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
)
from penshot.neopen.agent.prop_usage import mentions_prop

# 景别别名归一：结构化字段可能是 medium/medium_shot 等形式
_SHOT_ALIASES: Dict[str, str] = {
    "close": "close_up",
    "closeup": "close_up",
    "close_up": "close_up",
    "extreme_close": "extreme_close_up",
    "extreme_closeup": "extreme_close_up",
    "extreme_close_up": "extreme_close_up",
    "medium": "medium_shot",
    "medium_shot": "medium_shot",
    "medium_close": "medium_close_up",
    "medium_close_up": "medium_close_up",
    "wide": "wide_shot",
    "wide_shot": "wide_shot",
    "long_shot": "long_shot",
    "full_shot": "long_shot",
    "over_shoulder": "over_shoulder",
    "over_the_shoulder": "over_shoulder",
}

# 首帧需要“可读文字”证据的标记；只出现“纸条”不算可读地址
_READABLE_TEXT_MARKERS = (
    "text",
    "readable",
    "address",
    "handwriting",
    "subtitle",
    "文字",
    "字迹",
    "地址",
    "手写",
    "字幕",
    "招牌",
    "标牌",
    "海报",
    "书名",
    "报纸",
    "书信",
    "标题",
)

_EN_DIALOGUE_RE = re.compile(r"['\"][A-Za-z][^'\"]{8,}['\"]")
_ZH_DIALOGUE_RE = re.compile(r"[“\"][\u4e00-\u9fff][^”\"]{4,}[”\"]")

# 交付时长与镜头计划的容差：1s 或 10% 取大者，避免口径重算的正常差异误报
_DURATION_TOLERANCE_SECONDS = 1.0
_DURATION_TOLERANCE_RATIO = 0.1


def _canonical_shot(value: Any) -> str:
    """景别归一为可比对的标准值"""
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _SHOT_ALIASES.get(normalized, normalized)


def _plan_model(asset_plan: Any) -> Optional[AssetPlanDocument]:
    """把 dict/Pydantic 资产计划统一为模型；无法解析时返回 None"""
    if asset_plan is None:
        return None
    if isinstance(asset_plan, AssetPlanDocument):
        return asset_plan
    try:
        return AssetPlanDocument.model_validate(asset_plan)
    except Exception:
        return None


def _append(package: AdaptedPromptPackage, message: str) -> None:
    """追加告警并去重（Gate 可能被重复调用）"""
    if message and message not in package.warnings:
        package.warnings.append(message)


def _shot_type_warnings(prompt: Any) -> List[str]:
    """景别一致性：结构化景别与来源镜头景别不一致（P1-1 的检测口径）"""
    camera = getattr(prompt, "camera", None)
    shot = _canonical_shot(getattr(camera, "shot_type", ""))
    source = _canonical_shot(getattr(camera, "source_shot_type", ""))
    if shot and source and shot != source:
        return [f"景别不一致：结构化景别={shot}，来源镜头景别={source}"]
    return []


def _duration_warnings(package: AdaptedPromptPackage, prompt: Any) -> List[str]:
    """单片段时长口径：适配后时长被目标模型上限收敛时如实标注"""
    expected = float(getattr(prompt, "duration", 0.0) or 0.0)
    if expected and abs(package.duration - expected) > 0.05:
        return [f"时长被目标模型收敛：{expected:g}s -> {package.duration:g}s"]
    return []


def _first_frame_warnings(package: AdaptedPromptPackage) -> List[str]:
    """首帧静态性：image_prompt 不得混入动作序列（P0-2 验收）"""
    if package.mode != RouteMode.IMAGE_TO_VIDEO or not package.image_prompt:
        return []
    clauses = find_motion_clauses(package.image_prompt)
    if not clauses:
        return []
    return [f"首帧提示词包含动作序列：{'；'.join(clauses[:3])}"]


def _critical_text_warnings(package: AdaptedPromptPackage, prompt: Any) -> List[str]:
    """critical_text 路由证据：首帧必须要求呈现可读文字（P1-4）"""
    if package.mode != RouteMode.IMAGE_TO_VIDEO or not package.image_prompt:
        return []
    if not has_critical_text(getattr(prompt, "prompt", "")):
        return []
    lowered = package.image_prompt.lower()
    if any(marker in lowered for marker in _READABLE_TEXT_MARKERS):
        return []
    return ["critical_text 路由缺少首帧文字证据：image_prompt 未要求呈现可读文字"]


def _audio_language_warnings(prompt: Any) -> List[str]:
    """视频提示词对白语言与台词语言一致性（P1-3 的检测口径）"""
    audio = getattr(prompt, "audio", None)
    language = str(getattr(audio, "dialogue_language", "") or "")
    text = str(getattr(prompt, "prompt", "") or "")
    if language == "zh" and _EN_DIALOGUE_RE.search(text):
        return ["视频提示词含英文对白，与台词语言 zh 不一致"]
    if language == "en" and _ZH_DIALOGUE_RE.search(text):
        return ["视频提示词含中文对白，与台词语言 en 不一致"]
    return []


def _prop_reference_warnings(
    packages: Sequence[AdaptedPromptPackage],
    plan: Optional[AssetPlanDocument],
    fragments: Optional[Sequence[Any]],
    prompts: Dict[str, Any],
) -> List[str]:
    """道具引用完整性：使用范围与包内引用必须互为子集（P0-1/P0-4）"""
    if plan is None:
        return []

    props = {
        spec.asset_id: spec for spec in plan.assets if spec.asset_type == AssetType.PROP
    }
    if not props:
        return []

    expected = {asset_id: set(spec.usage.fragments) for asset_id, spec in props.items()}
    global_warnings: List[str] = []

    for package in packages:
        if package.mode != RouteMode.IMAGE_TO_VIDEO:
            continue
        referenced = {
            reference.asset_id
            for reference in package.references
            if reference.role == "prop"
        }
        for asset_id, fragments_in_use in expected.items():
            if package.fragment_id in fragments_in_use and asset_id not in referenced:
                owner = props[asset_id].owner_name
                _append(
                    package,
                    f"缺少道具引用：{asset_id}（{owner}）应在本片段使用范围内",
                )
        for asset_id in referenced - set(expected):
            _append(package, f"道具引用不在使用范围：{asset_id}")

    # 使用范围为空但片段确实提及该道具：P0-1 根因（匹配键失效）的回归守卫
    if fragments:
        texts = []
        for fragment in fragments:
            fragment_id = str(getattr(fragment, "id", "") or "")
            prompt = prompts.get(fragment_id)
            description = str(getattr(fragment, "description", "") or "")
            text = f"{description} {getattr(prompt, 'prompt', '')}".strip()
            texts.append(text)
        for spec in props.values():
            if spec.usage.fragments:
                continue
            if any(mentions_prop(text, spec.owner_name) for text in texts):
                global_warnings.append(
                    f"道具使用范围为空：{spec.asset_id}（{spec.owner_name}）"
                    "在片段文本中被提及但未回填"
                )

    return global_warnings


def _global_warnings(instructions: AIVideoInstructions) -> List[str]:
    """跨片段口径告警：交付偏差、打光证据来源（P1-2/P1-5 的检测口径）

    三个时长字段语义不同（实际交付 / 镜头计划 / 元素推算），不能互相比对；
    只在交付总时长实质性偏离镜头计划时告警。
    """
    warnings: List[str] = []
    metadata = getattr(instructions, "metadata", None) or {}

    report = metadata.get("duration_report") or {}
    delivered = report.get("total_duration")
    planned = report.get("shot_duration")
    if isinstance(delivered, (int, float)) and isinstance(planned, (int, float)):
        tolerance = max(
            _DURATION_TOLERANCE_SECONDS, abs(float(planned)) * _DURATION_TOLERANCE_RATIO
        )
        if abs(float(delivered) - float(planned)) > tolerance:
            warnings.append(
                f"交付时长偏离镜头计划：计划={planned}s，实际={delivered}s，"
                f"偏差={float(delivered) - float(planned):+.1f}s"
            )

    provenance = metadata.get("style_anchor_provenance") or {}
    lighting_source = str(provenance.get("lighting_source") or "")
    if lighting_source and lighting_source != "lighting_keyword":
        keyword = provenance.get("lighting_keyword") or ""
        warnings.append(
            f"打光证据来源={lighting_source}（关键词={keyword}），未命中打光词表"
        )

    return warnings


def apply_quality_gate(
    packages: Sequence[AdaptedPromptPackage],
    instructions: AIVideoInstructions,
    asset_plan: Any = None,
    fragments: Optional[Sequence[Any]] = None,
) -> List[str]:
    """执行 Gate 1 结构/逻辑检查，把发现的问题回写到片段告警

    检查项：首帧静态性、景别一致性、道具引用完整性、单片段时长收敛、
    critical_text 首帧文字证据、视频提示词与台词语言一致性；跨片段检查
    交付时长偏差与打光证据来源。片段级告警写入 ``package.warnings`` 并置位
    ``requires_special_attention``，跨片段告警作为返回值写入 ``RoutePlan``。

    Returns:
        跨片段告警列表（片段级告警已在 ``package`` 原地回写）
    """
    prompts = {fragment.fragment_id: fragment for fragment in instructions.fragments}
    plan = _plan_model(asset_plan)

    for package in packages:
        prompt = prompts.get(package.fragment_id)
        if prompt is None:
            continue
        for message in (
            *_first_frame_warnings(package),
            *_shot_type_warnings(prompt),
            *_duration_warnings(package, prompt),
            *_critical_text_warnings(package, prompt),
            *_audio_language_warnings(prompt),
        ):
            _append(package, message)
        prompt.requires_special_attention = bool(package.warnings)

    return [
        *_global_warnings(instructions),
        *_prop_reference_warnings(packages, plan, fragments, prompts),
    ]
