"""0.4.7 T-101：计划场景优先的场景权威测试。

覆盖 ``resolve_scene_anchor`` 的判定矩阵与路由阶段接线：计划场景存在且契约
有对应资产时，提示词里的其他地点不得驱动首帧替换；仅计划场景缺失或无对应
资产时才允许替换，并记录 ``scene_anchor_source`` 与降级告警。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter import (
    AdaptedPromptPackage,
    apply_image_to_video_routing,
)
from penshot.neopen.agent.model_adapter.first_frame_builder import (
    resolve_scene_anchor,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)


def _contract(*, with_corridor_asset: bool = True) -> GlobalConsistencyContract:
    """教室 + 走廊两个场景；可选是否登记走廊资产"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("张晨", 1, "他穿着蓝白相间棉质校服")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="教室",
            time_of_day="afternoon",
            characters_in_scene=["张晨"],
        )
    )
    contract.register_scene(
        SceneContract(
            scene_num=2,
            location="走廊/班级记忆墙",
            time_of_day="dusk",
            characters_in_scene=["张晨"],
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="教室",
            asset_ref="/tmp/assets/scene_001.png",
            image_prompt="establishing shot of 教室",
            status="generated",
        )
    )
    if with_corridor_asset:
        contract.register_asset(
            AssetContract(
                asset_id="scene_002",
                asset_type="scene",
                owner_name="走廊/班级记忆墙",
                asset_ref="/tmp/assets/scene_002.png",
                image_prompt="establishing shot of 走廊/班级记忆墙",
                status="generated",
            )
        )
    return contract


def _prompt(fragment_id: str = "frag_010") -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id=fragment_id,
        prompt=(
            "medium shot, Zhang Chen stands in a high school classroom, "
            "rows of desks and a blackboard behind him"
        ),
        duration=3.0,
        main_character="张晨",
    )


def _package(fragment_id: str = "frag_010") -> AdaptedPromptPackage:
    return AdaptedPromptPackage(
        fragment_id=fragment_id,
        target_model="runway_gen4",
        prompt="adapted",
        duration=3.0,
    )


def test_resolve_scene_anchor_plan_asset_blocks_replacement():
    """计划场景有资产时返回 None，提示词地点冲突不驱动替换（FR-097）"""
    resolution = resolve_scene_anchor(
        _prompt(),
        _contract(),
        fragment=SimpleNamespace(id="frag_010", description=""),
        first_frame_asset_id="scene_002",
        plan_scene_asset_id="scene_002",
    )

    assert resolution is None


def test_resolve_scene_anchor_plan_missing_allows_replacement():
    """计划场景无资产时保留旧替换能力并标记 plan_missing（FR-099）"""
    prompt = AIVideoPrompt(
        fragment_id="frag_010",
        prompt="medium shot, Zhang Chen walks down the hallway next to the memory wall",
        duration=3.0,
        main_character="张晨",
    )

    resolution = resolve_scene_anchor(
        prompt,
        _contract(),
        fragment=SimpleNamespace(id="frag_010", description=""),
        first_frame_asset_id="scene_001",
        plan_scene_asset_id="",
    )

    assert resolution is not None
    assert resolution.reason == "auto_replace"
    assert resolution.target_asset_id == "scene_002"
    assert resolution.scene_anchor_source == "plan_missing"
    assert "计划场景缺失或无对应资产" in resolution.message


def test_resolve_scene_anchor_invalid_plan_asset_id_treated_as_missing():
    """计划资产 ID 不在契约中时按计划缺失处理，不得静默放行"""
    prompt = AIVideoPrompt(
        fragment_id="frag_010",
        prompt="medium shot, Zhang Chen walks down the hallway next to the memory wall",
        duration=3.0,
        main_character="张晨",
    )

    resolution = resolve_scene_anchor(
        prompt,
        _contract(),
        fragment=SimpleNamespace(id="frag_010", description=""),
        first_frame_asset_id="scene_001",
        plan_scene_asset_id="scene_404",
    )

    assert resolution is not None
    assert resolution.reason == "auto_replace"
    assert resolution.scene_anchor_source == "plan_missing"


def test_resolve_scene_anchor_ambiguous_with_missing_plan():
    """计划缺失时多个其他场景仍按 ambiguous 阻断"""
    contract = _contract(with_corridor_asset=False)
    for asset_id, owner_name in (("scene_003", "操场"), ("scene_004", "咖啡馆")):
        contract.register_asset(
            AssetContract(
                asset_id=asset_id,
                asset_type="scene",
                owner_name=owner_name,
                image_prompt=f"establishing shot of {owner_name}",
                status="generated",
            )
        )
    prompt = AIVideoPrompt(
        fragment_id="frag_010",
        prompt="Zhang Chen runs from the playground toward the cafe",
        duration=3.0,
        main_character="张晨",
    )

    resolution = resolve_scene_anchor(
        prompt,
        contract,
        fragment=SimpleNamespace(id="frag_010", description=""),
        first_frame_asset_id="scene_001",
        plan_scene_asset_id="",
    )

    assert resolution is not None
    assert resolution.reason == "ambiguous"
    assert resolution.scene_anchor_source == "plan_missing"


def test_resolve_scene_anchor_no_asset_with_missing_plan():
    """计划缺失且其他地点无资产时按 no_asset 阻断"""
    prompt = AIVideoPrompt(
        fragment_id="frag_011",
        prompt="a lonely figure crosses the playground",
        duration=3.0,
        main_character="张晨",
    )

    resolution = resolve_scene_anchor(
        prompt,
        _contract(with_corridor_asset=False),
        fragment=SimpleNamespace(id="frag_011", description=""),
        first_frame_asset_id="scene_001",
        plan_scene_asset_id="",
    )

    assert resolution is not None
    assert resolution.reason == "no_asset"
    assert resolution.scene_anchor_source == "plan_missing"


def test_apply_routing_keeps_plan_scene_asset():
    """路由阶段：计划场景有资产时首帧资产保持不变，且不产生替换告警"""
    packages = [_package()]
    apply_image_to_video_routing(
        packages,
        AIVideoInstructions(fragments=[_prompt()]),
        _contract(),
        fragments=[SimpleNamespace(id="frag_010", shot_id="shot_010", description="")],
        shots=[SimpleNamespace(id="shot_010", scene_id="scene_002")],
    )

    package = packages[0]
    first_frame = next(ref for ref in package.references if ref.role == "first_frame")
    assert first_frame.asset_id == "scene_002"
    assert package.warnings == []
    assert package.model_params["scene_anchor_source"] == "plan"
    assert "at 走廊/班级记忆墙" in package.image_prompt


def test_apply_routing_replaces_only_when_plan_asset_missing():
    """路由阶段：无镜头场景映射时才允许替换，并记录 plan_missing 与降级说明"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("张晨", 1, "他穿着蓝白相间棉质校服")
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="张晨",
            image_prompt="character reference sheet of 张晨",
            status="generated",
        )
    )
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="教室",
            time_of_day="afternoon",
            characters_in_scene=["张晨"],
        )
    )
    contract.register_scene(
        SceneContract(scene_num=2, location="走廊/班级记忆墙", time_of_day="dusk")
    )
    for asset_id, owner_name in (
        ("scene_001", "教室"),
        ("scene_002", "走廊/班级记忆墙"),
    ):
        contract.register_asset(
            AssetContract(
                asset_id=asset_id,
                asset_type="scene",
                owner_name=owner_name,
                asset_ref=f"/tmp/assets/{asset_id}.png",
                image_prompt=f"establishing shot of {owner_name}",
                status="generated",
            )
        )
    prompt = AIVideoPrompt(
        fragment_id="frag_010",
        prompt="medium shot, Zhang Chen walks down the hallway next to the memory wall",
        duration=3.0,
        main_character="张晨",
    )
    packages = [_package()]
    apply_image_to_video_routing(
        packages,
        AIVideoInstructions(fragments=[prompt]),
        contract,
    )

    package = packages[0]
    first_frame = next(ref for ref in package.references if ref.role == "first_frame")
    assert first_frame.asset_id == "scene_002"
    assert package.model_params["scene_anchor_source"] == "plan_missing"
    assert package.warnings
    assert "已自动替换" in package.warnings[0]
    assert "计划场景缺失或无对应资产" in package.warnings[0]
    assert "at 走廊/班级记忆墙" in package.image_prompt


def test_apply_routing_warns_when_plan_scene_missing():
    """无镜头场景映射时保持旧行为，但显式记录场景权威降级"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_character("张晨", 1, "他穿着蓝白相间棉质校服")
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="张晨",
            image_prompt="character reference sheet of 张晨",
            status="generated",
        )
    )
    packages = [_package("frag_012")]
    apply_image_to_video_routing(
        packages,
        AIVideoInstructions(
            fragments=[
                AIVideoPrompt(
                    fragment_id="frag_012",
                    prompt="medium shot of Zhang Chen standing still",
                    duration=3.0,
                    main_character="张晨",
                )
            ]
        ),
        contract,
    )

    package = packages[0]
    assert package.model_params["scene_anchor_source"] == "plan_missing"
    assert any("计划场景缺失，场景权威降级" in item for item in package.warnings)
