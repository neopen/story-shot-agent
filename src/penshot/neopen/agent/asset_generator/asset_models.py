"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: asset_models.py
@Description: 资产锚点数据模型（角色三视图 / 道具静帧 / 场景锚点，M0.4.2）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from penshot.neopen.agent.continuity_guardian.consistency_contract import AssetContract
from penshot.neopen.constants.schema import CONTRACT_SCHEMA_VERSION

# 资产计划/回填清单的契约版本号；下游升级字段时据此判断兼容性
ASSET_SCHEMA_VERSION = CONTRACT_SCHEMA_VERSION


class AssetType(str, Enum):
    """资产类型"""

    CHARACTER_SHEET = "character_sheet"  # 角色三视图
    PROP = "prop"  # 关键道具静帧
    SCENE = "scene"  # 场景锚点静帧


class AssetStatus(str, Enum):
    """资产生成状态"""

    PENDING = "pending"  # 待生成（未启用或等待真实调用）
    GENERATED = "generated"  # 已生成并落盘
    FAILED = "failed"  # 生成失败
    SKIPPED = "skipped"  # 已有可用资产，跳过重复生成


class AssetUsage(BaseModel):
    """资产使用范围声明；供下游按片段/场景按需生成，而非全量生成"""

    characters: List[str] = Field(default_factory=list, description="使用该角色的角色名")
    scenes: List[str] = Field(default_factory=list, description="使用该资产的场景地点")
    fragments: List[str] = Field(default_factory=list, description="使用该资产的片段ID")


class AssetConsistency(BaseModel):
    """资产的连续性约束，供下游执行器锁定角色身份"""

    identity_lock: bool = Field(default=True, description="是否锁定角色身份")
    preferred_view: str = Field(default="front", description="优先使用的视角")
    seed: Optional[int] = Field(default=None, description="建议的随机种子")


class AssetSpec(BaseModel):
    """单个资产的生成规格；生成后通过 asset_ref 挂回契约"""

    asset_id: str = Field(..., description="资产唯一标识，如 char_001")
    asset_type: AssetType = Field(..., description="资产类型")
    owner_name: str = Field(..., description="归属角色/道具/场景名")
    image_prompt: str = Field(..., min_length=1, description="文生图正向提示词")
    negative_prompt: str = Field(default="", description="文生图负向提示词")
    size: str = Field(default="1024x1024", description="输出尺寸")
    views: List[str] = Field(
        default_factory=list, description="视角列表（角色三视图使用）"
    )
    usage: AssetUsage = Field(
        default_factory=AssetUsage, description="资产使用范围（下游按需生成依据）"
    )
    consistency: AssetConsistency = Field(
        default_factory=AssetConsistency, description="连续性约束"
    )
    status: AssetStatus = Field(default=AssetStatus.PENDING, description="生成状态")
    asset_ref: str = Field(default="", description="落盘后的本地引用")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加信息")

    def to_contract(self) -> AssetContract:
        """转换为契约中的资产锚点"""
        return AssetContract(
            asset_id=self.asset_id,
            asset_type=self.asset_type.value,
            owner_name=self.owner_name,
            asset_ref=self.asset_ref,
            image_prompt=self.image_prompt,
            status=self.status.value,
        )


class AssetPromptEdit(BaseModel):
    """人工对资产提示词的编辑记录；仅允许修改提示词字段"""

    asset_id: str = Field(..., description="要编辑的资产ID")
    image_prompt: Optional[str] = Field(
        default=None, description="新的正向提示词；None 或空表示不修改"
    )
    negative_prompt: Optional[str] = Field(
        default=None, description="新的负向提示词；None 表示不修改"
    )
    source: str = Field(default="human_intervention", description="编辑来源")
    revision_id: str = Field(default="", description="编辑修订号，便于追溯")


class AssetPlanDocument(BaseModel):
    """资产计划文档：PenShot 产出的声明式生图指令，默认不触发任何外部调用"""

    schema_version: str = Field(
        default=ASSET_SCHEMA_VERSION, description="资产计划契约版本"
    )
    task_id: str = Field(default="", description="任务ID")
    script_id: str = Field(default="", description="剧本ID")
    style_anchor: Dict[str, Any] = Field(
        default_factory=dict, description="全局风格锚点，供下游保持风格一致"
    )
    assets: List[AssetSpec] = Field(default_factory=list, description="资产规格列表")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="计划生成时间"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示（JSON 可序列化）"""
        return self.model_dump(mode="json")


class AssetBinding(BaseModel):
    """下游回填的单个资产绑定；asset_ref 与 asset_id 的映射保持可追溯"""

    asset_id: str = Field(..., description="资产唯一标识（可为下游实际ID）")
    view: str = Field(default="", description="实际生成的视角")
    asset_ref: str = Field(default="", description="下游生成后的资产引用")
    model: str = Field(default="", description="下游使用的生成模型")
    seed: Optional[int] = Field(default=None, description="下游使用的随机种子")
    checksum: str = Field(default="", description="资产内容校验值")
    source: str = Field(default="", description="产出该绑定的执行器标识")
    generated_at: str = Field(default="", description="下游产出的时间戳")
    revision: int = Field(default=0, description="绑定修订号")
    error: str = Field(default="", description="生成失败原因（空表示无错误）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump(mode="json")


class AssetManifest(BaseModel):
    """下游资产回填清单：把声明式 asset_id 绑定到真实资产引用"""

    schema_version: str = Field(
        default=ASSET_SCHEMA_VERSION, description="资产回填契约版本"
    )
    task_id: str = Field(default="", description="任务ID")
    script_id: str = Field(default="", description="剧本ID（可选，便于回溯）")
    generated_at: str = Field(default="", description="清单产出时间（可选）")
    bindings: List[AssetBinding] = Field(
        default_factory=list, description="资产绑定列表"
    )
    asset_id_map: Dict[str, str] = Field(
        default_factory=dict,
        description="下游改名映射：PenShot 规范 asset_id -> 下游实际 asset_id",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_assets_alias(cls, data: Any) -> Any:
        """兼容下游直接写 ``assets`` 的清单格式（0.4.5 任务 1）"""
        if isinstance(data, dict) and not data.get("bindings") and data.get("assets"):
            data = dict(data)
            data["bindings"] = data.pop("assets")
        return data

    def get_binding(self, asset_id: str) -> Optional[AssetBinding]:
        """按规范 asset_id 查找绑定；优先使用显式改名映射"""
        if not asset_id:
            return None
        alias = self.asset_id_map.get(asset_id, asset_id)
        # 先查下游实际ID，再回退到规范ID，兼容未改名与已改名的回填
        for binding in self.bindings:
            if binding.asset_id == alias:
                return binding
        for binding in self.bindings:
            if binding.asset_id == asset_id:
                return binding
        return None

    def resolve_ref(self, asset_id: str) -> str:
        """解析资产引用；未回填或失败时返回空字符串"""
        binding = self.get_binding(asset_id)
        return binding.asset_ref if binding is not None else ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump(mode="json")


class AssetGenerationReport(BaseModel):
    """一次资产生成的汇总报告（可序列化，供工作流输出与审计）"""

    schema_version: str = Field(
        default=ASSET_SCHEMA_VERSION, description="报告契约版本"
    )
    mode: str = Field(
        default="plan",
        description="处理模式：plan（仅声明计划）/ manifest（消费下游回填）/ generated（本地执行生成）",
    )
    enabled: bool = Field(default=False, description="是否启用了真实文生图调用")
    provider: str = Field(default="", description="实际使用的文生图供应商")
    total: int = Field(default=0, description="资产总数")
    generated: int = Field(default=0, description="成功生成数")
    failed: int = Field(default=0, description="失败数")
    pending: int = Field(default=0, description="待生成数")
    skipped: int = Field(default=0, description="跳过数")
    manifest_applied: int = Field(default=0, description="从回填清单应用的绑定数")
    plan: Optional[AssetPlanDocument] = Field(
        default=None, description="本次产出的资产计划文档"
    )
    manifest: Optional[AssetManifest] = Field(
        default=None, description="本次消费或产出的资产回填清单"
    )
    assets: List[AssetSpec] = Field(default_factory=list, description="资产规格列表")
    errors: List[str] = Field(default_factory=list, description="失败原因")

    @classmethod
    def from_specs(
        cls,
        specs: List[AssetSpec],
        enabled: bool,
        provider: str = "",
        errors: Optional[List[str]] = None,
        mode: str = "plan",
        plan: Optional[AssetPlanDocument] = None,
        manifest: Optional[AssetManifest] = None,
        manifest_applied: int = 0,
    ) -> "AssetGenerationReport":
        """按资产状态汇总统计"""
        return cls(
            mode=mode,
            enabled=enabled,
            provider=provider,
            total=len(specs),
            generated=sum(1 for s in specs if s.status == AssetStatus.GENERATED),
            failed=sum(1 for s in specs if s.status == AssetStatus.FAILED),
            pending=sum(1 for s in specs if s.status == AssetStatus.PENDING),
            skipped=sum(1 for s in specs if s.status == AssetStatus.SKIPPED),
            manifest_applied=manifest_applied,
            plan=plan,
            manifest=manifest,
            assets=specs,
            errors=errors or [],
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump(mode="json")
