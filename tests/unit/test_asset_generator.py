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
from penshot.neopen.agent.asset_generator import (
    character_sheet_generator,
    prop_scene_asset_generator,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed
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
                SimpleNamespace(
                    name="霓虹街道", visual_cues=["neon signs", "wet asphalt"]
                )
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
    # FR-053：三视图不拼接剧情风格/氛围打光
    assert "neo-noir" not in char_specs[0].image_prompt
    assert "front view, side view and back view" in char_specs[0].image_prompt
    assert "neutral grey background" in char_specs[0].image_prompt
    assert "soft even studio lighting" in char_specs[0].image_prompt

    assert len(prop_specs) == 1
    assert prop_specs[0].asset_type == AssetType.PROP
    assert prop_specs[0].owner_name == "怀表"

    assert len(scene_specs) == 1
    assert scene_specs[0].asset_type == AssetType.SCENE
    assert scene_specs[0].owner_name == "霓虹街道"
    assert "neon signs" in scene_specs[0].image_prompt


def test_disabled_client_keeps_pending_assets():
    """文生图未启用时仅把 pending 资产与提示词挂到契约"""
    agent = AssetGeneratorAgent(
        image_client=_FakeImageClient(_config("", enabled=False))
    )
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


def _anchor_script() -> SimpleNamespace:
    """构造与 0.4.4 缺陷样本一致的三视图输入（含结构化服装）"""
    return SimpleNamespace(
        characters=[
            SimpleNamespace(
                name="林小雨",
                description=(
                    "20岁学生，神情焦急后转为惊喜，穿着素色外套（肩头微湿），"
                    "手持手帕和湿漉漉的诗集《飞鸟集》。"
                ),
                key_traits=["学生", "抱书", "带哭腔"],
            ),
            SimpleNamespace(
                name="陈阳",
                description=(
                    "22岁兼职外卖员，穿着黄色雨衣，骑着电动车，"
                    "动作匆忙但细心，从雨衣里掏出干毛巾。"
                ),
                key_traits=["外卖员", "黄色雨衣", "迟到"],
            ),
        ],
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="咖啡店外",
                time_of_day="day",
                elements=[
                    SimpleNamespace(character="林小雨"),
                    SimpleNamespace(character="陈阳"),
                ],
            )
        ],
        global_metadata=SimpleNamespace(
            character_outfits=[
                SimpleNamespace(
                    character="林小雨",
                    description="素色外套，肩头因雨水微湿，搭配学生气质的简约装扮。",
                    color="素色/浅灰",
                    style="休闲学生风",
                    material="棉质/混纺",
                ),
                SimpleNamespace(
                    character="陈阳",
                    description="亮黄色连帽雨衣，内搭深色T恤，下身深色长裤，脚穿防滑鞋。",
                    color="黄色",
                    style="功能性工装",
                    material="PVC/防水尼龙",
                ),
            ],
            key_props=[],
            key_locations=[],
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
        title="雨夜来电",
    )


def test_character_sheet_prompt_excludes_performance_and_duplicates():
    """AC-050/AC-051/AC-052：只有外观锚点，服装只出现一次，固定中性棚拍"""
    parsed = _anchor_script()
    contract = build_contract_from_parsed(parsed, script_id="s1")

    specs = build_character_sheet_specs(parsed, contract)
    prompt = next(s for s in specs if s.owner_name == "林小雨").image_prompt

    for banned in ("带哭腔", "神情", "手持", "骑着电动车", "湿漉"):
        assert banned not in prompt
    assert prompt.count("素色浅灰棉质外套") == 1
    assert prompt.count("肩头微湿") == 1
    assert "front view, side view and back view" in prompt
    assert "neutral grey background" in prompt
    assert "soft even studio lighting" in prompt


def test_character_sheet_prompt_dedupes_across_anchor_fields():
    """同一描述出现在多个白名单字段时只拼接一次"""
    parsed = _anchor_script()
    contract = build_contract_from_parsed(parsed, script_id="s1")
    anchors = contract.characters["林小雨"].appearance_anchors
    anchors.clear()
    anchors.update({"hair": "黑色短发", "clothing": "黑色短发"})

    prompt = build_character_sheet_specs(parsed, contract)[0].image_prompt

    assert prompt.count("黑色短发") == 1


def test_character_sheet_prompt_truncates_at_clause_boundary(monkeypatch):
    """FR-055：超限时只裁掉整段子句，不产生半截词"""
    parsed = _anchor_script()
    contract = build_contract_from_parsed(parsed, script_id="s1")
    anchors = contract.characters["林小雨"].appearance_anchors
    anchors.clear()
    anchors["clothing"] = (
        "素色浅灰棉质外套，肩头微湿，袖口有补丁，"
        "内搭深色T恤，下身深色长裤，脚穿防滑鞋，配饰是一枚旧胸针"
    )
    monkeypatch.setattr(
        character_sheet_generator, "CHARACTER_SHEET_MAX_PROMPT_LENGTH", 230
    )

    prompt = build_character_sheet_specs(parsed, contract)[0].image_prompt

    assert len(prompt) <= 230
    assert "素色浅灰棉质外套，肩头微湿，袖口有补丁" in prompt
    assert "内搭" not in prompt
    assert "旧胸针" not in prompt


def _styled_script() -> SimpleNamespace:
    """构造道具/场景提示词样本（含可重复的视觉线索）"""
    return SimpleNamespace(
        characters=[],
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="咖啡店外",
                time_of_day="dusk",
                weather="rain",
                description="雨棚下亮着暖黄灯",
            )
        ],
        global_metadata=SimpleNamespace(
            key_props=[
                SimpleNamespace(
                    name="《飞鸟集》",
                    description="蓝色封面的诗集",
                    color="蓝色",
                    importance="high",
                )
            ],
            key_locations=[
                SimpleNamespace(
                    name="咖啡店外", visual_cues=["rainy street", "warm awning light"]
                )
            ],
        ),
    )


def _style_contract(genre: str = "romance") -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.set_style_anchor("genre", genre)
    return contract


def test_prop_and_scene_prompts_use_dimension_style_not_bare_genre():
    """AC-053/FR-054：资产提示词取维度风格，不拼裸 genre 标签"""
    parsed = _styled_script()
    contract = _style_contract("romance")

    prop_prompt = build_prop_specs(parsed, contract)[0].image_prompt
    scene_prompt = build_scene_specs(parsed, contract)[0].image_prompt

    for prompt in (prop_prompt, scene_prompt):
        tokens = [part.strip().lower() for part in prompt.split(",")]
        assert "romance" not in tokens
        assert "soft warm lighting" in tokens
        assert "warm palette" in tokens

    # 颜色已包含在描述中，不再重复拼接（FR-052）
    assert "color: 蓝色" not in prop_prompt
    assert prop_prompt.count("蓝色") == 1


def test_scene_prompt_dedupes_cue_already_in_description():
    """FR-052：同一语义内容只拼接一次"""
    parsed = _styled_script()
    parsed.scenes[0].description = "neon signs lit over wet asphalt"
    parsed.global_metadata.key_locations[0].visual_cues = [
        "neon signs",
        "wet asphalt",
    ]
    contract = _style_contract("romance")

    prompt = build_scene_specs(parsed, contract)[0].image_prompt

    assert prompt.count("neon signs") == 1
    assert prompt.count("wet asphalt") == 1


def test_scene_prompt_truncates_at_clause_boundary(monkeypatch):
    """FR-055：超限时只裁掉整段子句，不产生半截词"""
    parsed = _styled_script()
    parsed.scenes[0].description = (
        "雨棚下亮着暖黄灯，地面积水映出灯光，行人撑伞匆匆走过，"
        "咖啡店招牌微微发光，长椅空着"
    )
    contract = _style_contract("romance")
    monkeypatch.setattr(prop_scene_asset_generator, "SCENE_MAX_PROMPT_LENGTH", 130)

    prompt = build_scene_specs(parsed, contract)[0].image_prompt

    assert len(prompt) <= 130
    assert "雨棚下亮着暖黄灯，地面积水映出灯光，行人撑伞匆匆走过" in prompt
    assert "咖啡店招牌" not in prompt
    assert "长椅空着" not in prompt
