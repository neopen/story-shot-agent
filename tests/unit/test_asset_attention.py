"""P0-6 服装关键信息不足的角色资产：引用片段必须降级为剪影/背影。

覆盖：``apply_asset_attention_constraints`` 只对 requires_special_attention
且缺失类型/颜色/材质的角色资产生效，约束写入包告警并落为结构化指令。
"""

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetPlanDocument,
    AssetSpec,
    AssetType,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AdaptedPromptPackage,
    PromptReference,
)
from penshot.neopen.agent.model_adapter.quality_gate import (
    SILHOUETTE_CONSTRAINT,
    apply_asset_attention_constraints,
)


def _asset_plan(metadata: dict, asset_type: AssetType = AssetType.CHARACTER_SHEET):
    return AssetPlanDocument(
        assets=[
            AssetSpec(
                asset_id="char_002",
                asset_type=asset_type,
                owner_name="沙发人影",
                image_prompt="a looming human silhouette in an armchair",
                metadata=metadata,
            )
        ]
    ).to_dict()


def _package(fragment_id: str = "frag_005", asset_id: str = "char_002"):
    return AdaptedPromptPackage(
        fragment_id=fragment_id,
        target_model="runway_gen4",
        prompt="adapted",
        duration=3.0,
        references=[
            PromptReference(
                asset_id=asset_id,
                role="identity_reference",
                as_first_frame=False,
            )
        ],
    )


def test_missing_key_outfit_fields_add_silhouette_constraint():
    plan = _asset_plan(
        {
            "requires_special_attention": True,
            "outfit_missing_fields": ["类型", "颜色", "材质"],
            "attention_reason": "剧本与片段均未提供",
        }
    )
    package = _package()

    global_warnings, degraded = apply_asset_attention_constraints([package], plan)

    assert package.warnings
    message = package.warnings[0]
    assert "沙发人影" in message
    assert "类型、颜色、材质" in message
    assert "剪影/背影" in message
    assert SILHOUETTE_CONSTRAINT in message
    assert degraded["frag_005"][0]["asset_id"] == "char_002"
    assert degraded["frag_005"][0]["constraint"] == SILHOUETTE_CONSTRAINT
    assert global_warnings and "frag_005" in global_warnings[0]


def test_no_constraint_when_asset_only_missing_non_key_field():
    """只缺非关键字段（如款式）时不强制降级"""
    plan = _asset_plan(
        {"requires_special_attention": True, "outfit_missing_fields": ["款式"]}
    )
    package = _package()

    global_warnings, degraded = apply_asset_attention_constraints([package], plan)

    assert package.warnings == []
    assert degraded == {}
    assert global_warnings == []


def test_no_constraint_when_asset_not_referenced():
    plan = _asset_plan(
        {"requires_special_attention": True, "outfit_missing_fields": ["颜色"]}
    )
    package = _package(asset_id="char_001")

    global_warnings, degraded = apply_asset_attention_constraints([package], plan)

    assert package.warnings == []
    assert degraded == {}
    assert global_warnings == []


def test_non_character_asset_is_ignored():
    plan = _asset_plan(
        {"requires_special_attention": True, "outfit_missing_fields": ["颜色"]},
        asset_type=AssetType.PROP,
    )
    package = _package()

    global_warnings, degraded = apply_asset_attention_constraints([package], plan)

    assert package.warnings == []
    assert degraded == {}
