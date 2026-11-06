"""M0.4.2 资产锚点生成智能体测试。

覆盖角色三视图/道具/场景资产规格生成、未启用时仅保留 pending、
启用时真实落盘并挂回契约，以及重复执行跳过已生成资产。
"""

import base64
from types import SimpleNamespace

from penshot.config.config_models import ImageBaseConfig
from penshot.neopen.agent.asset_generator import (
    ASSET_SCHEMA_VERSION,
    AssetBinding,
    AssetGeneratorAgent,
    AssetManifest,
    AssetPlanDocument,
    AssetStatus,
    AssetType,
    build_character_sheet_specs,
    build_prop_specs,
    build_scene_specs,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.client.image_generation import (
    BaseImageGenerationClient,
    ImageGenerationRequest,
    ImagePayload,
)


class _FakeImageClient(BaseImageGenerationClient):
    """以 base64 回包模拟供应商"""

    def _request_image(self, request: ImageGenerationRequest) -> ImagePayload:
        return ImagePayload(b64_data=base64.b64encode(b"fake-png").decode())


def _config(tmp_path, enabled=True) -> ImageBaseConfig:
    return ImageBaseConfig(
        provider="flux",
        base_url="https://example.com/v1",
        api_key="test-key",
        model_name="flux-1.1-pro",
        max_retries=0,
        output_dir=str(tmp_path),
        enabled=enabled,
    )


def _parsed_script() -> SimpleNamespace:
    """构造最小剧本解析结果（仅覆盖资产生成所需字段）"""
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


def test_build_specs_cover_character_prop_scene():
    """三类资产规格齐全，且提示词带上风格与外观锚点"""
    parsed = _parsed_script()
    contract = _contract()

    char_specs = build_character_sheet_specs(parsed, contract)
    prop_specs = build_prop_specs(parsed, contract)
    scene_specs = build_scene_specs(parsed, contract)

    assert len(char_specs) == 1
    assert char_specs[0].asset_type == AssetType.CHARACTER_SHEET
    assert char_specs[0].owner_name == "林然"
    assert char_specs[0].views == ["front", "side", "back"]
    assert "neo-noir" in char_specs[0].image_prompt

    assert len(prop_specs) == 1
    assert prop_specs[0].asset_type == AssetType.PROP
    assert prop_specs[0].owner_name == "怀表"

    assert len(scene_specs) == 1
    assert scene_specs[0].asset_type == AssetType.SCENE
    assert scene_specs[0].owner_name == "霓虹街道"
    assert "neon signs" in scene_specs[0].image_prompt


def test_disabled_client_keeps_pending_assets():
    """文生图未启用时仅把 pending 资产与提示词挂到契约"""
    agent = AssetGeneratorAgent(image_client=_FakeImageClient(_config("", enabled=False)))
    report = agent.generate_assets(_parsed_script(), _contract())

    assert report.enabled is False
    assert report.total == 3
    assert report.pending == 3
    assert report.generated == 0

    contract = _contract()
    agent.generate_assets(_parsed_script(), contract)
    assert len(contract.assets) == 3
    assert all(a.status == AssetStatus.PENDING.value for a in contract.assets.values())
    assert all(a.image_prompt for a in contract.assets.values())


def test_enabled_client_generates_and_attaches_asset_ref(tmp_path):
    """启用后资产真实落盘，asset_ref 与 generated 状态写回契约"""
    contract = _contract()
    agent = AssetGeneratorAgent(image_client=_FakeImageClient(_config(tmp_path)))
    report = agent.generate_assets(_parsed_script(), contract)

    assert report.enabled is True
    assert report.generated == report.total == 3
    assert all(spec.asset_ref for spec in report.assets)
    assert all((tmp_path / f"{spec.asset_id}.png").exists() for spec in report.assets)

    char_asset = next(
        a for a in contract.assets.values() if a.asset_type == "character_sheet"
    )
    assert char_asset.status == AssetStatus.GENERATED.value
    assert char_asset.asset_ref.endswith("char_001.png")


def test_rerun_skips_generated_assets(tmp_path):
    """重复执行时已生成且文件存在的资产被跳过而非重建"""
    contract = _contract()
    client = _FakeImageClient(_config(tmp_path))
    agent = AssetGeneratorAgent(image_client=client)

    first = agent.generate_assets(_parsed_script(), contract)
    assert first.generated == 3

    second = agent.generate_assets(_parsed_script(), contract)
    assert second.skipped == 3
    assert second.generated == 0
    assert second.pending == 0


def test_plan_assets_always_produces_declarative_plan():
    """即使未启用生成，也始终产出带 schema_version 的声明式资产计划"""
    agent = AssetGeneratorAgent(
        image_client=_FakeImageClient(_config("", enabled=False))
    )
    plan = agent.plan_assets(
        _parsed_script(), _contract(), task_id="t1", script_id="s1"
    )

    assert isinstance(plan, AssetPlanDocument)
    assert plan.schema_version == ASSET_SCHEMA_VERSION
    assert plan.task_id == "t1"
    assert plan.script_id == "s1"
    assert plan.style_anchor["genre"] == "neo-noir"
    assert len(plan.assets) == 3
    assert all(spec.status == AssetStatus.PENDING for spec in plan.assets)

    char = next(s for s in plan.assets if s.asset_type == AssetType.CHARACTER_SHEET)
    assert char.usage.characters == ["林然"]
    assert char.consistency.identity_lock is True
    assert char.consistency.preferred_view == "front"


class _CountingImageClient(_FakeImageClient):
    """记录真实调用次数，用于验证回填清单不会触发生成"""

    def __init__(self, config):
        super().__init__(config)
        self.calls = 0

    def _request_image(self, request: ImageGenerationRequest) -> ImagePayload:
        self.calls += 1
        return super()._request_image(request)


def test_manifest_bindings_apply_without_calling_api(tmp_path):
    """提供下游回填清单时直接复用 asset_ref，不调用文生图接口"""
    contract = _contract()
    client = _CountingImageClient(_config(tmp_path))
    agent = AssetGeneratorAgent(image_client=client)

    manifest = AssetManifest(
        task_id="t1",
        bindings=[
            AssetBinding(
                asset_id="char_001",
                view="front",
                asset_ref=str(tmp_path / "downstream_char.png"),
                model="flux",
                source="downstream",
                revision=1,
            )
        ],
    )
    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert client.calls == 0
    assert report.mode == "manifest"
    assert report.manifest_applied == 1
    assert report.manifest is not None

    char_asset = contract.assets["char_001"]
    assert char_asset.status == AssetStatus.GENERATED.value
    assert char_asset.asset_ref.endswith("downstream_char.png")


def test_manifest_asset_id_map_supports_downstream_renaming(tmp_path):
    """下游改名时通过显式 asset_id_map 映射，asset_id 不被静默改写"""
    contract = _contract()
    agent = AssetGeneratorAgent(
        image_client=_FakeImageClient(_config("", enabled=False))
    )

    manifest = AssetManifest(
        task_id="t1",
        asset_id_map={"char_001": "downstream_char_001"},
        bindings=[
            AssetBinding(
                asset_id="downstream_char_001",
                asset_ref=str(tmp_path / "renamed.png"),
                source="downstream",
            )
        ],
    )
    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert report.manifest_applied == 1
    assert "char_001" in contract.assets
    assert contract.assets["char_001"].asset_ref.endswith("renamed.png")
