"""
M0.4.6 T-015/T-016 回归测试：服装材质词表与回填来源优先级。

覆盖：
- “布料 / 面料 / 化纤 / 织物 / 制服布料”进入中文材质词表；
- `深蓝色制服布料标准地铁制服` 判定为类型、颜色、材质齐全；
- 既有材质词与“缺材质”判定不回归；
- 回填优先剧本材质，其次片段提示词，全部解决时清除复核标记；
- 未解决时写明“剧本与片段均未提供”。
"""

from types import SimpleNamespace

import pytest

from penshot.neopen.agent.asset_generator.asset_generator_agent import backfill_outfits
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetPlanDocument,
    AssetSpec,
    AssetType,
)
from penshot.neopen.agent.asset_generator.character_sheet_generator import (
    SCRIPT_MATERIAL_SOURCE,
    _missing_outfit_fields,
    backfill_character_outfits,
)
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    contains_keyword,
)
from penshot.neopen.constants.appearance import MATERIAL_KEYWORDS

NEW_MATERIAL_WORDS = ["布料", "面料", "化纤", "织物", "制服布料"]

EXISTING_MATERIAL_WORDS = ["棉质", "皮革", "羊毛", "针织", "涤纶"]


def test_sample_outfit_material_is_recognized():
    """FR-092：样本服装描述不再被判为缺少材质"""
    assert _missing_outfit_fields("深蓝色制服布料标准地铁制服") == []


@pytest.mark.parametrize("word", NEW_MATERIAL_WORDS)
def test_new_material_keywords_are_covered(word):
    """FR-092：新增材质词均可被关键词匹配识别"""
    assert word in MATERIAL_KEYWORDS
    assert contains_keyword(f"深蓝色制服{word}", MATERIAL_KEYWORDS)


@pytest.mark.parametrize("word", EXISTING_MATERIAL_WORDS)
def test_existing_material_keywords_still_recognized(word):
    """既有材质关键词不回归"""
    assert word in MATERIAL_KEYWORDS
    assert contains_keyword(f"深蓝色制服{word}", MATERIAL_KEYWORDS)


def test_outfit_without_material_still_missing():
    """只有类型与颜色时仍判定缺少材质"""
    assert _missing_outfit_fields("深蓝色制服") == ["材质"]


def _outfit_plan(
    outfit_text: str, reason: str = "服装描述缺少材质"
) -> AssetPlanDocument:
    """构造带缺失材质的角色三视图资产计划"""
    return AssetPlanDocument(
        assets=[
            AssetSpec(
                asset_id="char_002",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name="站台管理员",
                image_prompt=(
                    "character reference sheet of 站台管理员, front view, full body, "
                    f"{outfit_text}, highly detailed character design"
                ),
                metadata={
                    "role": "identity_anchor",
                    "outfit_text": outfit_text,
                    "outfit_missing_fields": ["材质"],
                    "requires_special_attention": True,
                    "attention_reason": reason,
                },
            )
        ]
    )


def test_script_material_takes_priority_over_fragment_prompts():
    """FR-093/FR-094：剧本材质优先，回填后清除缺失字段与复核标记"""
    plan = _outfit_plan("深蓝色标准地铁制服")

    changed = backfill_character_outfits(
        plan,
        {"站台管理员": [("frag_004", "wearing dark blue polyester uniform")]},
        {"站台管理员": "制服布料"},
    )

    spec = plan.assets[0]
    assert changed == ["char_002"]
    assert "制服布料" in spec.image_prompt
    assert "polyester" not in spec.image_prompt
    assert spec.metadata["outfit_backfill_source"] == SCRIPT_MATERIAL_SOURCE
    assert "outfit_missing_fields" not in spec.metadata
    assert "requires_special_attention" not in spec.metadata
    assert "attention_reason" not in spec.metadata


def test_fragment_prompt_used_when_script_material_absent():
    """FR-093：剧本未提供材质时退回片段提示词"""
    plan = _outfit_plan("深蓝色制服")

    changed = backfill_character_outfits(
        plan,
        {"站台管理员": [("frag_004", "wearing dark blue cotton uniform")]},
        {},
    )

    spec = plan.assets[0]
    assert changed == ["char_002"]
    assert "dark blue cotton uniform" in spec.image_prompt
    assert spec.metadata["outfit_backfill_source"] == "frag_004"
    assert "outfit_missing_fields" not in spec.metadata


def test_unresolved_outfit_reports_both_sources_absent():
    """FR-095：剧本与片段都未提供材质时保留标记并写明结论"""
    plan = _outfit_plan("深蓝色标准地铁制服")

    changed = backfill_character_outfits(
        plan,
        {"站台管理员": [("frag_004", "wearing dark blue uniform")]},
        {"站台管理员": "不详"},
    )

    spec = plan.assets[0]
    assert changed == []
    assert spec.metadata["outfit_missing_fields"] == ["材质"]
    assert spec.metadata["requires_special_attention"] is True
    assert "材质" in spec.metadata["attention_reason"]
    assert "剧本与片段均未提供" in spec.metadata["attention_reason"]
    assert "outfit_backfill_source" not in spec.metadata


def test_partial_backfill_keeps_remaining_missing_fields():
    """FR-094/FR-095：部分解决时只保留仍未解决的缺失项"""
    plan = _outfit_plan("制服", reason="服装描述缺少颜色和材质")

    changed = backfill_character_outfits(
        plan,
        {},
        {"站台管理员": "制服布料"},
    )

    spec = plan.assets[0]
    assert changed == ["char_002"]
    assert "制服布料" in spec.image_prompt
    assert spec.metadata["outfit_missing_fields"] == ["颜色"]
    assert spec.metadata["requires_special_attention"] is True
    assert "缺少颜色" in spec.metadata["attention_reason"]
    assert "剧本与片段均未提供" in spec.metadata["attention_reason"]


def test_wrapper_derives_script_materials_from_parsed_script():
    """asset_generator_agent 包装层从解析结果提取剧本材质"""
    plan = _outfit_plan("深蓝色标准地铁制服")
    parsed_script = SimpleNamespace(
        global_metadata=SimpleNamespace(
            character_outfits=[
                SimpleNamespace(character="站台管理员", material="制服布料")
            ]
        )
    )

    changed = backfill_outfits(plan, parsed_script=parsed_script)

    spec = plan.assets[0]
    assert changed == ["char_002"]
    assert "制服布料" in spec.image_prompt
    assert spec.metadata["outfit_backfill_source"] == SCRIPT_MATERIAL_SOURCE
