"""人工编辑资产提示词测试。

覆盖编辑回写计划/契约、旧资产引用与回填绑定失效，以及 EDIT_ASSET 决策路由。
"""

from types import SimpleNamespace

from penshot.neopen.agent.asset_generator import (
    AssetBinding,
    AssetGeneratorAgent,
    AssetManifest,
    AssetStatus,
    AssetType,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _parsed_script() -> SimpleNamespace:
    """构造最小剧本解析结果"""
    return SimpleNamespace(
        characters=[
            SimpleNamespace(
                name="林然",
                description="瘦高个，眼神锐利",
                key_traits=["短发"],
            )
        ],
        scenes=[
            SimpleNamespace(
                location="霓虹街道",
                time_of_day="night",
                weather="rain",
                description="霓虹灯牌闪烁",
            )
        ],
        global_metadata=SimpleNamespace(
            key_props=[
                SimpleNamespace(
                    name="怀表",
                    description="金色怀表",
                    color="gold",
                    importance="high",
                )
            ],
            key_locations=[
                SimpleNamespace(name="霓虹街道", visual_cues=["neon signs", "wet asphalt"])
            ],
            character_outfits=[
                SimpleNamespace(
                    character="林然",
                    color="black",
                    style="suit",
                    material="wool",
                    description="修身",
                )
            ],
        ),
    )


def _contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("林然", 1, "他穿着黑色西装")
    contract.set_style_anchor("genre", "neo-noir")
    return contract


def _character_asset_id(agent: AssetGeneratorAgent, contract) -> str:
    plan = agent.plan_assets(_parsed_script(), contract, task_id="t1")
    return next(
        spec.asset_id
        for spec in plan.assets
        if spec.asset_type == AssetType.CHARACTER_SHEET
    )


def test_prompt_edit_updates_plan_and_contract():
    """人工编辑后的提示词应同时写回资产计划与全局契约"""
    agent = AssetGeneratorAgent()
    contract = _contract()
    plan = agent.plan_assets(_parsed_script(), contract, task_id="t1")
    asset_id = next(
        spec.asset_id for spec in plan.assets if spec.asset_type == AssetType.CHARACTER_SHEET
    )

    report = agent.generate_assets(
        _parsed_script(),
        contract,
        task_id="t1",
        plan=plan,
        prompt_edits=[
            {
                "asset_id": asset_id,
                "image_prompt": "character sheet of 林然 in a black suit, neon rim light",
                "negative_prompt": "extra limbs, blurry face",
                "revision_id": "human-1",
            }
        ],
    )

    spec = next(item for item in plan.assets if item.asset_id == asset_id)
    assert spec.image_prompt == "character sheet of 林然 in a black suit, neon rim light"
    assert spec.negative_prompt == "extra limbs, blurry face"
    assert spec.metadata["human_edited"] is True
    assert spec.metadata["edit_revision"] == "human-1"

    asset = contract.assets[asset_id]
    assert asset.image_prompt == spec.image_prompt
    assert asset.status == AssetStatus.PENDING.value
    assert report.total == len(plan.assets)


def test_edit_invalidates_old_asset_ref_and_manifest_binding():
    """编辑提示词后旧资产引用必须失效，相关回填绑定应被移除"""
    agent = AssetGeneratorAgent()
    contract = _contract()
    plan = agent.plan_assets(_parsed_script(), contract, task_id="t1")
    asset_id = next(
        spec.asset_id for spec in plan.assets if spec.asset_type == AssetType.CHARACTER_SHEET
    )

    spec = next(item for item in plan.assets if item.asset_id == asset_id)
    spec.status = AssetStatus.GENERATED
    spec.asset_ref = "/old/char.png"

    manifest = AssetManifest(
        task_id="t1",
        bindings=[
            AssetBinding(
                asset_id="ds_char_001",
                asset_ref="/old/char.png",
                source="downstream",
            )
        ],
        asset_id_map={asset_id: "ds_char_001"},
    )

    report = agent.generate_assets(
        _parsed_script(),
        contract,
        task_id="t1",
        plan=plan,
        manifest=manifest,
        prompt_edits=[
            {
                "asset_id": asset_id,
                "image_prompt": "character sheet of 林然, front side back views",
                "revision_id": "human-2",
            }
        ],
    )

    assert spec.status == AssetStatus.PENDING
    assert spec.asset_ref == ""
    assert report.manifest is not None
    assert report.manifest.bindings == []
    assert report.manifest.asset_id_map == {}


def test_edit_unknown_asset_is_ignored():
    """不存在的 asset_id 不应影响计划"""
    agent = AssetGeneratorAgent()
    contract = _contract()
    plan = agent.plan_assets(_parsed_script(), contract, task_id="t1")
    before = [spec.image_prompt for spec in plan.assets]

    changed = agent.apply_prompt_edits(
        plan,
        contract,
        [{"asset_id": "char_999", "image_prompt": "should be ignored"}],
    )

    assert changed == []
    assert [spec.image_prompt for spec in plan.assets] == before


def test_edit_asset_decision_requires_asset_rebuild():
    """EDIT_ASSET 应返回专用状态并路由到资产生成节点"""
    decision = PipelineDecision()
    state = WorkflowState.from_raw_script("测试剧本内容")
    state.execution.human_feedback = {"decision": "7"}
    state.execution.asset_prompt_edits = [
        {"asset_id": "char_001", "image_prompt": "new prompt"}
    ]
    state.execution.node_current_loops[PipelineNode.HUMAN_INTERVENTION] = 10

    result = decision.decide_after_human(state)

    assert result == PipelineState.NEEDS_ASSET_EDIT
