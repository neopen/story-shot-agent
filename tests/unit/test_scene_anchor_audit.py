"""计划场景 vs 首帧资产审计（0.4.7 T-103，FR-099a / AC-081）。

覆盖路由阶段「计划场景有资产但首帧引用漂移到其他场景」的违规收集、
审查报告不再判通过，以及非图生视频、无首帧引用、计划场景无资产、
首帧与计划资产一致时的无误报。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.model_adapter.image_to_video import (
    collect_plan_scene_violations,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    AuditStatus,
    SeverityLevel,
)
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import (
    RuleQualityAuditor,
)
from penshot.neopen.shot_config import ShotConfig

VIOLATION_CODE = "scene_anchor_mismatch"


def _contract() -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(scene_num=1, location="教室", time_of_day="day")
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="教室",
            image_prompt="establishing shot still of 教室",
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_002",
            asset_type="scene",
            owner_name="走廊",
            image_prompt="establishing shot still of 走廊",
        )
    )
    return contract


def _route_plan(
    first_frame_asset_id: str,
    *,
    mode: str = "image_to_video",
    fragment_id: str = "frag_001",
    first_frame_role: str = "first_frame",
):
    references = [
        {
            "asset_id": "char_001",
            "role": "identity_reference",
            "as_first_frame": False,
        }
    ]
    if first_frame_asset_id:
        references.append(
            {
                "asset_id": first_frame_asset_id,
                "role": first_frame_role,
                "as_first_frame": first_frame_role == "first_frame",
            }
        )
    return {
        "source_model": "runway_gen2",
        "decisions": [],
        "adapted_packages": [
            {
                "fragment_id": fragment_id,
                "target_model": "kling",
                "mode": mode,
                "references": references,
            }
        ],
    }


def _fragments(fragment_id: str = "frag_001"):
    return [SimpleNamespace(id=fragment_id, shot_id="shot_001", description="")]


def _shots():
    return [SimpleNamespace(id="shot_001", scene_id="scene_001")]


def test_mismatch_between_plan_scene_and_first_frame_is_collected():
    """FR-099a/AC-081：计划场景教室，首帧却用走廊资产 → 产生 MAJOR 违规"""
    violations = collect_plan_scene_violations(
        _route_plan("scene_002"), _fragments(), _shots(), _contract()
    )

    assert len(violations) == 1
    violation = violations[0]
    assert violation["type"] == VIOLATION_CODE
    assert violation["issue_code"] == VIOLATION_CODE
    assert violation["stage"] == "route_model"
    assert violation["fragment_id"] == "frag_001"
    assert violation["scene"] == "scene_001"
    assert violation["plan_location"] == "教室"
    assert violation["expected_asset_id"] == "scene_001"
    assert violation["actual_asset_id"] == "scene_002"
    assert "scene_002" in violation["message"]
    assert "scene_001" in violation["message"]


def test_audit_does_not_pass_when_scene_anchor_mismatches():
    """AC-081：违规项传入审查后状态不得为通过，并按 MAJOR 计入"""
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="medium shot, a boy stands in a classroom",
                duration=3.0,
            )
        ]
    )
    violations = collect_plan_scene_violations(
        _route_plan("scene_002"), _fragments(), _shots(), _contract()
    )

    report = RuleQualityAuditor(ShotConfig()).audit(
        instructions, contract=_contract(), contract_violations=violations
    )

    assert report.status != AuditStatus.PASSED
    matched = [v for v in report.violations if v.issue_code == VIOLATION_CODE]
    assert len(matched) == 1
    assert matched[0].severity == SeverityLevel.MAJOR
    assert matched[0].fragment_id == "frag_001"
    assert any(
        check["name"] == "契约一致性复核检查" and check["status"] == "failed"
        for check in report.checks
    )


def test_matching_first_frame_produces_no_violation():
    """首帧资产等于计划场景资产时不产生违规"""
    assert (
        collect_plan_scene_violations(
            _route_plan("scene_001"), _fragments(), _shots(), _contract()
        )
        == []
    )


def test_text_to_video_is_not_checked():
    """非图生视频包没有首帧语义，不参与锚点审计"""
    assert (
        collect_plan_scene_violations(
            _route_plan("scene_002", mode="text_to_video"),
            _fragments(),
            _shots(),
            _contract(),
        )
        == []
    )


def test_package_without_first_frame_reference_is_skipped():
    """只有身份引用、没有首帧引用的包不检查"""
    assert (
        collect_plan_scene_violations(
            _route_plan("scene_002", first_frame_role="identity_reference"),
            _fragments(),
            _shots(),
            _contract(),
        )
        == []
    )


def test_plan_scene_without_asset_is_not_checked():
    """计划场景在契约中无对应资产时无法给出期望资产，不误报"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(scene_num=2, location="走廊", time_of_day="dusk")
    )
    contract.register_asset(
        AssetContract(
            asset_id="scene_001",
            asset_type="scene",
            owner_name="教室",
            image_prompt="establishing shot still of 教室",
        )
    )
    shots = [SimpleNamespace(id="shot_001", scene_id="scene_002")]

    assert (
        collect_plan_scene_violations(
            _route_plan("scene_001"), _fragments(), shots, contract
        )
        == []
    )


def test_duplicate_packages_are_deduplicated():
    """同一片段重复出现同一首帧资产时只记一条（fragment_id + asset_id 去重）"""
    route_plan = _route_plan("scene_002")
    route_plan["adapted_packages"].append(dict(route_plan["adapted_packages"][0]))

    violations = collect_plan_scene_violations(
        route_plan, _fragments(), _shots(), _contract()
    )

    assert len(violations) == 1
