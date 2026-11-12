"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: model_models.py
@Description: 目标模型适配层数据模型（M0.4.0）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from penshot.neopen.agent.prompt_converter.prompt_converter_models import CameraControl
from penshot.neopen.constants.schema import CONTRACT_SCHEMA_VERSION

# 提示词适配/路由契约版本号；下游据此判断字段兼容性
PROMPT_SCHEMA_VERSION = CONTRACT_SCHEMA_VERSION


class AestheticBias(str, Enum):
    """模型美学偏好枚举（用于路由与适配时的风格兜底）"""

    CINEMATIC = "cinematic"  # 电影感
    ANIME = "anime"  # 二次元/动画
    REALISTIC = "realistic"  # 写实


class MotionComplexity(str, Enum):
    """动作复杂度（路由特征）"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConsistencyNeed(str, Enum):
    """人物一致性需求（路由特征）"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RouteFeatures(BaseModel):
    """片段路由特征；由确定性规则抽取，供 model_router 匹配"""

    has_critical_text: bool = Field(default=False, description="是否含关键文字")
    motion_complexity: MotionComplexity = Field(
        default=MotionComplexity.MEDIUM, description="动作复杂度"
    )
    character_consistency_need: ConsistencyNeed = Field(
        default=ConsistencyNeed.MEDIUM, description="人物一致性需求"
    )
    style_bias: AestheticBias = Field(
        default=AestheticBias.CINEMATIC, description="风格倾向"
    )
    duration: float = Field(default=5.0, ge=0.5, description="片段时长（秒）")
    needs_first_last_frame: bool = Field(
        default=False, description="是否需要首尾帧控制"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class RouteMode(str, Enum):
    """片段生成模式（M0.4.2 图生视频优先）"""

    TEXT_TO_VIDEO = "text_to_video"  # 单段文生视频
    IMAGE_TO_VIDEO = "image_to_video"  # 文生图 -> 图生视频两段式


class ModelCapability(BaseModel):
    """视频模型能力声明；是路由匹配与提示词适配的共同依据"""

    model_name: str = Field(..., description="模型唯一标识，如 runway_gen4")
    max_duration: float = Field(..., gt=0, description="单次最大时长（秒）")
    supports_image_to_video: bool = Field(default=False, description="是否支持图生视频")
    supports_camera_control: bool = Field(
        default=False, description="是否支持结构化相机参数"
    )
    text_rendering_score: float = Field(
        ..., ge=0.0, le=1.0, description="文字渲染能力 0~1"
    )
    character_consistency: float = Field(
        ..., ge=0.0, le=1.0, description="人物一致性 0~1"
    )
    aesthetic_bias: AestheticBias = Field(
        default=AestheticBias.CINEMATIC, description="美学偏好"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示（便于路由与序列化消费）"""
        return self.model_dump()


class PromptReference(BaseModel):
    """片段对资产的声明式引用；下游据此按需生成/复用资产"""

    asset_id: str = Field(..., description="引用的资产ID（PenShot 规范ID）")
    role: str = Field(default="character", description="引用角色：character/prop/scene/first_frame")
    view: str = Field(default="front", description="希望使用的视角")
    as_first_frame: bool = Field(default=True, description="是否作为图生视频首帧")
    required: bool = Field(default=True, description="缺失时是否必须回退文生视频")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class PromptOverride(BaseModel):
    """下游对提示词的二次修改记录；只允许改提示词字段，不允许改资产身份"""

    target_id: str = Field(..., description="目标片段ID")
    target_type: str = Field(default="package", description="目标类型：package/fragment/asset")
    field: str = Field(..., description="被修改的字段名")
    value: str = Field(default="", description="修改后的值")
    source: str = Field(default="", description="修改来源（下游节点/人工/模型）")
    revision_id: str = Field(default="", description="本次修订ID")
    parent_id: str = Field(default="", description="父修订ID，用于追溯链")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class AdaptedPromptPackage(BaseModel):
    """单个片段经模型适配后产出的专属提示词包"""

    fragment_id: str = Field(..., description="片段ID")
    target_model: str = Field(..., description="目标模型名")
    prompt: str = Field(..., description="模型专属正向提示词")
    negative_prompt: str = Field(default="", description="模型专属负向提示词")
    duration: float = Field(..., gt=0, description="适配后的片段时长（秒）")
    style: Optional[str] = Field(
        default=None, description="风格描述（模型美学偏好兜底）"
    )
    camera: Optional[str] = Field(default=None, description="模型专属相机表述")
    camera_control: Optional[CameraControl] = Field(
        default=None, description="结构化相机控制参数（目标模型支持时直出）"
    )
    mode: RouteMode = Field(
        default=RouteMode.TEXT_TO_VIDEO, description="生成模式（文生视频/图生视频）"
    )
    asset_ref: str = Field(
        default="", description="图生视频使用的资产锚点（角色三视图/场景静帧落盘引用）"
    )
    image_prompt: str = Field(
        default="", description="两段式模式下的首帧文生图提示词"
    )
    first_frame_instruction: str = Field(
        default="", description="下游图生视频可直接消费的首帧指令"
    )
    references: List[PromptReference] = Field(
        default_factory=list,
        description="片段引用的资产列表（声明式，允许下游按需生成）",
    )
    revision_id: str = Field(default="", description="当前提示词修订ID")
    revision_source: str = Field(default="", description="当前修订来源")
    parent_id: str = Field(default="", description="父修订ID（追溯链）")
    revision: int = Field(default=0, description="修订序号")
    prompt_overrides: List[PromptOverride] = Field(
        default_factory=list, description="下游二次修改记录"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="构建期发现但不阻断的声明式告警（如场景锚定不一致）",
    )
    model_params: Dict[str, Any] = Field(
        default_factory=dict, description="模型专属生成参数"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class RouteDecision(BaseModel):
    """单个片段的路由决策（片段 -> 目标模型）"""

    fragment_id: str = Field(..., description="片段ID")
    target_model: str = Field(..., description="路由到的目标模型名")
    reason: str = Field(default="", description="路由原因")
    mode: RouteMode = Field(
        default=RouteMode.TEXT_TO_VIDEO, description="该片段采用的生成模式"
    )
    asset_ref: str = Field(
        default="", description="图生视频引用的资产锚点（无则为空）"
    )
    capability: Optional[ModelCapability] = Field(
        default=None, description="目标模型能力声明"
    )


class RoutePlan(BaseModel):
    """可序列化、下游可直接消费的模型路由计划指令包"""

    schema_version: str = Field(
        default=PROMPT_SCHEMA_VERSION, description="路由计划契约版本"
    )
    plan_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="计划唯一标识"
    )
    source_model: str = Field(default="", description="通用 prompt 中声明的原始模型名")
    decisions: List[RouteDecision] = Field(
        default_factory=list, description="路由决策列表"
    )
    adapted_packages: List[AdaptedPromptPackage] = Field(
        default_factory=list, description="适配后的提示词包列表"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示（JSON 可序列化）"""
        return self.model_dump()


# 允许下游覆盖的提示词字段白名单；asset_id/asset_ref/references 等身份字段不可改
OVERRIDABLE_FIELDS = {
    "prompt",
    "negative_prompt",
    "image_prompt",
    "first_frame_instruction",
    "style",
    "camera",
    # 下游可切换目标模型，但资产身份字段仍然不可改
    "target_model",
}


def apply_overrides(
    packages: List[AdaptedPromptPackage], overrides: List[PromptOverride]
) -> int:
    """应用下游提示词覆盖并保留完整 provenance

    设计约束：
    - 只允许修改提示词文本类字段，``asset_ref`` / ``references`` 中的
      ``asset_id`` 不允许被静默改名，资产映射必须走 ``AssetManifest.asset_id_map``；
    - 每次覆盖写入 ``revision_id`` / ``revision_source`` / ``parent_id``，
      形成可追溯的修订链。

    Returns:
        实际应用的覆盖条数
    """
    package_map = {package.fragment_id: package for package in packages}
    applied = 0
    for override in overrides:
        package = package_map.get(override.target_id)
        if package is None or override.field not in OVERRIDABLE_FIELDS:
            continue

        parent_id = override.parent_id or package.revision_id or package.fragment_id
        package.revision += 1
        package.revision_id = override.revision_id or str(uuid.uuid4())
        package.revision_source = override.source
        package.parent_id = parent_id
        package.prompt_overrides.append(
            PromptOverride(
                target_id=override.target_id,
                target_type=override.target_type,
                field=override.field,
                value=override.value,
                source=override.source,
                revision_id=package.revision_id,
                parent_id=parent_id,
            )
        )
        setattr(package, override.field, override.value)
        applied += 1

    return applied
