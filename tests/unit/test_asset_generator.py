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
    AssetSpec,
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


def test_character_sheet_resolves_ambiguous_clothing():
    """结构化服装自身含“A 或 B”时确定性消解，并标记人工复核"""
    parsed = _parsed_script()
    parsed.characters = [SimpleNamespace(name="林然", description="温和的女性教师")]
    parsed.global_metadata.character_outfits = [
        SimpleNamespace(
            character="林然",
            description="得体的浅色连衣裙或套装",
            color="米色/浅蓝",
            style="职业休闲",
            material="丝绸/棉麻",
        )
    ]
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert "或" not in spec.image_prompt
    assert "连衣裙" in spec.image_prompt
    assert spec.metadata["requires_special_attention"] is True
    assert spec.metadata["outfit_resolution"] in {
        "first_alternative",
        "garment_match",
    }
    assert set(spec.metadata["outfit_alternatives"]) == {
        "得体的浅色连衣裙",
        "套装",
    }


def test_character_sheet_resolves_free_text_ambiguity():
    """无结构化服装时，自由文本里的“或”同样被消解并标记"""
    parsed = _parsed_script()
    parsed.characters = [
        SimpleNamespace(name="林然", description="她身穿浅色连衣裙或套装，佩戴眼镜")
    ]
    parsed.global_metadata.character_outfits = []
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert "或" not in spec.image_prompt
    assert "连衣裙" in spec.image_prompt
    assert spec.metadata["requires_special_attention"] is True


def test_character_sheet_prefers_style_matched_alternative():
    """style 字段能唯一指向备选时，按 style 消解"""
    parsed = _parsed_script()
    parsed.global_metadata.character_outfits = [
        SimpleNamespace(
            character="林然",
            description="运动背心或短袖T恤，搭配运动短裤",
            color="灰色/黑色",
            style="运动背心",
            material="速干面料",
        )
    ]
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert spec.metadata["outfit_resolution"] == "style_match"
    assert "运动背心" in spec.image_prompt
    assert "短袖T恤" not in spec.image_prompt


def test_character_sheet_keeps_unambiguous_clothing():
    """无歧义且含服装名词时不产生审阅标记"""
    parsed = _parsed_script()
    parsed.global_metadata.character_outfits = [
        SimpleNamespace(
            character="林然",
            description="黑色羊毛西装",
            color="黑色",
            style="正装",
            material="羊毛",
        )
    ]
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert "requires_special_attention" not in spec.metadata
    assert "黑色羊毛西装" in spec.image_prompt


def test_default_agent_never_resolves_image_client(monkeypatch):
    """默认工作流只声明资产，不得惰性解析任何文生图客户端"""
    import penshot.neopen.agent.asset_generator.asset_generator_agent as module

    def _boom():
        raise AssertionError("默认路径不得解析文生图客户端")

    monkeypatch.setattr(module, "get_default_image_client", _boom)

    report = AssetGeneratorAgent().generate_assets(_parsed_script(), _contract())

    assert report.mode == "plan"
    assert report.enabled is False
    assert report.pending == 3


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


def test_plan_style_anchor_discards_conflicting_description_phrases():
    """资产计划的 style_anchor 必须与片段同源，不残留已丢弃的氛围短语"""
    contract = _contract()
    contract.set_style_anchor("palette", "fresh pastel palette")
    contract.set_style_anchor("mood", "hopeful")
    contract.set_style_anchor("description", "muted colors, melancholic tone")

    plan = AssetGeneratorAgent().plan_assets(_parsed_script(), contract)

    description = plan.style_anchor["description"]
    assert "muted colors" not in description
    assert "melancholic tone" not in description
    assert description == "neo-noir, fresh pastel palette, hopeful"
    # 只读契约，不得因生成计划而改写原始锚点
    assert contract.style_anchor["description"] == "muted colors, melancholic tone"


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


def test_character_sheet_prompt_keeps_outfit_accessories():
    """char_002 缺陷回归：结构化服装里的“佩戴眼镜”必须进入三视图提示词"""
    parsed = SimpleNamespace(
        characters=[SimpleNamespace(name="语文老师", description="", key_traits=[])],
        scenes=[SimpleNamespace(id="scene_001", location="教室", elements=[])],
        global_metadata=SimpleNamespace(
            character_outfits=[
                SimpleNamespace(
                    character="语文老师",
                    description="得体的浅色连衣裙或套装，佩戴眼镜，气质温婉。",
                    color="浅色",
                    style="知性教师风",
                    material="棉质",
                )
            ],
            key_props=[],
            key_locations=[],
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
        title="走廊",
    )
    contract = build_contract_from_parsed(parsed, script_id="s1")

    prompt = build_character_sheet_specs(parsed, contract)[0].image_prompt

    assert "佩戴眼镜" in prompt
    assert "连衣裙" in prompt
    assert "气质温婉" not in prompt


def test_character_sheet_prompt_supports_english_script():
    """英文剧本：结构化服装与配饰进入三视图提示词，情绪/动作子句不混入"""
    parsed = SimpleNamespace(
        characters=[
            SimpleNamespace(
                name="Ethan",
                description=(
                    "25-year-old male, short black hair, wearing a yellow raincoat, "
                    "holding a wet notebook, smiling nervously."
                ),
                key_traits=[],
            )
        ],
        scenes=[SimpleNamespace(id="scene_001", location="Corridor", elements=[])],
        global_metadata=SimpleNamespace(
            character_outfits=[
                SimpleNamespace(
                    character="Ethan",
                    description=(
                        "A yellow hooded raincoat with dark trousers, wearing glasses, "
                        "a kind expression."
                    ),
                    color="yellow",
                    style="functional workwear",
                    material="PVC",
                )
            ],
            key_props=[],
            key_locations=[],
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
        title="The Memory Wall",
    )
    contract = build_contract_from_parsed(parsed, script_id="s1")

    prompt = build_character_sheet_specs(parsed, contract)[0].image_prompt

    assert "yellow hooded raincoat with dark trousers" in prompt
    assert "glasses" in prompt
    for banned in ("holding", "smiling", "kind expression"):
        assert banned not in prompt


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


# ======================== 0.4.5 任务 2：服装完整性 ========================


def _outfit_script(clothing: str) -> SimpleNamespace:
    """构造只有单一服装描述的最小解析结果"""
    return SimpleNamespace(
        characters=[SimpleNamespace(name="张晨", description="高中生")],
        scenes=[],
        global_metadata=SimpleNamespace(
            character_outfits=[SimpleNamespace(character="张晨", description=clothing)],
            key_props=[],
            key_locations=[],
        ),
    )


def test_incomplete_outfit_is_flagged_with_missing_fields():
    """只有服装类型、缺颜色与材质时标记人工复核并写明缺口"""
    parsed = _outfit_script("高中校服")
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert spec.metadata["requires_special_attention"] is True
    assert spec.metadata["outfit_missing_fields"] == ["颜色", "材质"]
    assert "缺少颜色和材质" in spec.metadata["attention_reason"]
    assert spec.metadata["outfit_text"] == "高中校服"


def test_complete_outfit_has_no_missing_flag():
    """类型+颜色+材质齐全时不产生信息不足标记"""
    parsed = _outfit_script("蓝白相间棉质高中校服")
    contract = build_contract_from_parsed(parsed, script_id="s1")

    spec = build_character_sheet_specs(parsed, contract)[0]

    assert "requires_special_attention" not in spec.metadata
    assert "outfit_missing_fields" not in spec.metadata


def test_backfill_character_outfits_from_fragment_prompts():
    """路由阶段用片段提示词补全颜色/材质，保留复核标记与缺失说明"""
    plan = AssetPlanDocument(
        assets=[
            AssetSpec(
                asset_id="char_001",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name="张晨",
                image_prompt=(
                    "character reference sheet of 张晨, front view, full body, "
                    "高中校服, highly detailed character design"
                ),
                metadata={
                    "role": "identity_anchor",
                    "outfit_text": "高中校服",
                    "requires_special_attention": True,
                    "attention_reason": "服装描述缺少颜色和材质",
                },
            )
        ]
    )

    changed = character_sheet_generator.backfill_character_outfits(
        plan,
        {
            "张晨": [
                (
                    "frag_011",
                    "Zhang Chen wearing slightly disheveled blue and white cotton "
                    "school uniform, sweat drops on forehead",
                )
            ]
        },
    )

    spec = plan.assets[0]
    assert changed == ["char_001"]
    assert "blue and white cotton school uniform" in spec.image_prompt
    assert "高中校服" not in spec.image_prompt
    assert spec.metadata["outfit_backfill_source"] == "frag_011"
    assert spec.metadata["requires_special_attention"] is True
    assert "缺少颜色和材质" in spec.metadata["attention_reason"]
    assert "已从片段提示词" in spec.metadata["attention_reason"]


def test_backfill_skips_complete_or_generated_assets():
    """已完整、已生成或人工编辑过的资产不回填"""
    complete = AssetSpec(
        asset_id="char_001",
        asset_type=AssetType.CHARACTER_SHEET,
        owner_name="甲",
        image_prompt="character reference sheet of 甲, 黑色羊毛西装",
        metadata={"outfit_text": "黑色羊毛西装"},
    )
    generated = AssetSpec(
        asset_id="char_002",
        asset_type=AssetType.CHARACTER_SHEET,
        owner_name="乙",
        image_prompt="character reference sheet of 乙, 高中校服",
        asset_ref="/downstream/char_002.png",
        status=AssetStatus.GENERATED,
        metadata={"outfit_text": "高中校服"},
    )
    edited = AssetSpec(
        asset_id="char_003",
        asset_type=AssetType.CHARACTER_SHEET,
        owner_name="丙",
        image_prompt="character reference sheet of 丙, 高中校服",
        metadata={"outfit_text": "高中校服", "human_edited": True},
    )
    plan = AssetPlanDocument(assets=[complete, generated, edited])

    changed = character_sheet_generator.backfill_character_outfits(
        plan, {"甲": [("f1", "wearing blue cotton coat")]}
    )

    assert changed == []
    assert generated.status == AssetStatus.GENERATED
    assert edited.metadata["outfit_text"] == "高中校服"


def test_manifest_missing_file_uri_keeps_pending(tmp_path):
    """显式 file:// 指向的文件不存在时保持 pending，并记录明确错误"""
    contract = _contract()
    agent = AssetGeneratorAgent()
    manifest = AssetManifest(
        task_id="t1",
        bindings=[
            AssetBinding(
                asset_id="char_001",
                asset_ref=(tmp_path / "missing.png").as_uri(),
                source="external",
            )
        ],
    )

    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert report.manifest_applied == 0
    assert any(
        "char_001" in message and "不存在" in message for message in report.errors
    )
    assert contract.assets["char_001"].status == AssetStatus.PENDING.value


def test_manifest_checksum_mismatch_keeps_pending(tmp_path):
    """校验和不匹配时拒绝回填，避免挂上错误图片"""
    image = tmp_path / "char_001.png"
    image.write_bytes(b"real-image")
    contract = _contract()
    agent = AssetGeneratorAgent()
    manifest = AssetManifest(
        task_id="t1",
        bindings=[
            AssetBinding(
                asset_id="char_001",
                asset_ref=image.as_uri(),
                checksum="sha256:" + "0" * 64,
            )
        ],
    )

    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert report.manifest_applied == 0
    assert any("校验和不匹配" in message for message in report.errors)
    assert contract.assets["char_001"].status == AssetStatus.PENDING.value


def test_manifest_accepts_v3_assets_alias(tmp_path):
    """兼容 v3 清单的 assets 字段、script_id 与 generated_at"""
    image = tmp_path / "char_001.png"
    image.write_bytes(b"real-image")
    contract = _contract()
    agent = AssetGeneratorAgent()
    manifest = AssetManifest.model_validate(
        {
            "task_id": "t1",
            "script_id": "s1",
            "generated_at": "2026-11-12T15:00:00Z",
            "assets": [
                {
                    "asset_id": "char_001",
                    "asset_ref": image.as_uri(),
                    "generated_at": "2026-11-12T15:00:00Z",
                    "source": "external",
                }
            ],
        }
    )

    assert manifest.script_id == "s1"
    assert manifest.generated_at == "2026-11-12T15:00:00Z"
    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert report.manifest_applied == 1
    assert report.errors == []
    spec = next(item for item in report.assets if item.asset_id == "char_001")
    assert spec.metadata["generated_at"] == "2026-11-12T15:00:00Z"


def test_manifest_unknown_asset_id_is_reported():
    """清单里出现计划外的 asset_id 时给出明确错误"""
    contract = _contract()
    agent = AssetGeneratorAgent()
    manifest = AssetManifest(
        task_id="t1",
        bindings=[AssetBinding(asset_id="char_999", asset_ref="/cdn/char_999.png")],
    )

    report = agent.generate_assets(_parsed_script(), contract, manifest=manifest)

    assert report.manifest_applied == 0
    assert any(
        "char_999" in message and "不在资产计划中" in message
        for message in report.errors
    )
