"""G 质量门禁四条新规则测试（0.4.4 T-601/T-602，FR-060..FR-064 / AC-060）。

覆盖外观锚点污染、景别与提示词不一致、互斥打光并存、资产使用范围缺失
四条规则各自的命中与定位字段（``fragment_id`` / ``asset_id``），并验证
干净输入不会新增误报。FR-063 的夹具按 M3 已回填的 ``asset_plan`` /
``route_plan`` 产物形状构造，不重复实现 usage 回填。
"""

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    CharacterContract,
    GlobalConsistencyContract,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
    CameraControl,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import SeverityLevel
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import (
    RuleQualityAuditor,
)
from penshot.neopen.shot_config import ShotConfig

NEW_RULE_CODES = {
    "appearance_anchor_polluted",
    "shot_type_prompt_mismatch",
    "style_lighting_conflict",
    "asset_usage_missing",
}

CLOSE_UP_PROMPT = (
    "close-up of a young man in a yellow raincoat standing by the cafe window at dusk"
)


def _auditor() -> RuleQualityAuditor:
    return RuleQualityAuditor(ShotConfig())


def _new_rule_violations(report):
    return [v for v in report.violations if v.issue_code in NEW_RULE_CODES]


def _character_sheet(asset_id: str = "char_001", owner: str = "林然") -> AssetContract:
    return AssetContract(
        asset_id=asset_id,
        asset_type="character_sheet",
        owner_name=owner,
        image_prompt="character reference sheet",
    )


def _contract(anchors=None) -> GlobalConsistencyContract:
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    character = CharacterContract(name="林然")
    character.appearance_anchors = (
        anchors
        if anchors is not None
        else {
            "age": "25岁",
            "gender": "男",
            "hair": "黑色短发",
            "clothing": "黄色连帽雨衣",
        }
    )
    contract.characters["林然"] = character
    contract.register_asset(_character_sheet())
    return contract


def _fragment(fragment_id: str = "frag_001", **overrides) -> AIVideoPrompt:
    payload = {
        "fragment_id": fragment_id,
        "prompt": CLOSE_UP_PROMPT,
        "duration": 3.0,
        "style": "cinematic, soft warm lighting, film grain",
        "camera": CameraControl(shot_type="close_up"),
    }
    payload.update(overrides)
    return AIVideoPrompt(**payload)


def _instructions(**overrides) -> AIVideoInstructions:
    payload = {"fragments": [_fragment()]}
    payload.update(overrides)
    return AIVideoInstructions(**payload)


def _route_plan(referenced_assets, fragment_id: str = "frag_001"):
    """构造 M3 形状的路由计划片段包（references 由模型适配产出）"""
    return {
        "source_model": "runway_gen2",
        "decisions": [],
        "adapted_packages": [
            {
                "fragment_id": fragment_id,
                "target_model": "kling",
                "mode": "image_to_video",
                "references": [
                    {
                        "asset_id": asset_id,
                        "role": "identity",
                        "view": "front",
                        "as_first_frame": False,
                        "required": True,
                    }
                    for asset_id in referenced_assets
                ],
            }
        ],
    }


def _asset_plan(usage_by_asset):
    """构造 M3 回填后的资产计划（usage.fragments 已由 backfill_usage 写入）"""
    return {
        "schema_version": "0.4.3",
        "task_id": "t1",
        "script_id": "s1",
        "assets": [
            {
                "asset_id": asset_id,
                "asset_type": "character_sheet",
                "owner_name": "林然",
                "image_prompt": "character reference sheet",
                "usage": {
                    "characters": ["林然"],
                    "scenes": [],
                    "fragments": list(fragments),
                },
            }
            for asset_id, fragments in usage_by_asset.items()
        ],
    }


def test_appearance_anchor_pollution_detected_with_asset_locator():
    """FR-060/FR-064：情绪表演词、半截词、语义域混入均命中并带 asset_id"""
    contract = _contract(
        anchors={
            "clothing": "焦急地握紧雨衣",
            "hair": "黑色短发，米色风衣",
            "accessories": "银色耳环和",
        }
    )

    report = _auditor().audit(_instructions(), contract=contract)
    violations = [
        v
        for v in _new_rule_violations(report)
        if v.issue_code == "appearance_anchor_polluted"
    ]

    assert len(violations) == 3
    assert {v.issue_value["field"] for v in violations} == {
        "clothing",
        "hair",
        "accessories",
    }
    for violation in violations:
        assert violation.severity == SeverityLevel.MAJOR
        assert violation.asset_id == "char_001"
        assert violation.issue_value["character"] == "林然"


def test_shot_type_prompt_mismatch_detected_with_fragment_id():
    """FR-061/FR-064：camera 景别与提示词景别表述冲突时命中并带 fragment_id"""
    fragment = _fragment(
        prompt="wide shot of the city street at dusk while rain falls softly",
        camera=CameraControl(shot_type="close_up"),
    )

    report = _auditor().audit(_instructions(fragments=[fragment]))
    violations = [
        v
        for v in _new_rule_violations(report)
        if v.issue_code == "shot_type_prompt_mismatch"
    ]

    assert len(violations) == 1
    violation = violations[0]
    assert violation.severity == SeverityLevel.MAJOR
    assert violation.fragment_id == "frag_001"
    assert violation.issue_value == {
        "camera_shot_type": "close_up",
        "prompt_shot_type": "wide_shot",
    }


def test_style_lighting_conflict_detected_once_per_style():
    """FR-062/FR-064：同一风格前缀互斥打光并存只报一次，带首个片段定位"""
    style = "cinematic, soft warm lighting, low-key shadows"
    fragments = [
        _fragment(fragment_id="frag_001", style=style),
        _fragment(fragment_id="frag_002", style=style),
    ]

    report = _auditor().audit(_instructions(fragments=fragments))
    violations = [
        v
        for v in _new_rule_violations(report)
        if v.issue_code == "style_lighting_conflict"
    ]

    assert len(violations) == 1
    violation = violations[0]
    assert violation.severity == SeverityLevel.WARNING
    assert violation.fragment_id == "frag_001"
    assert set(violation.issue_value["markers"]) == {"soft warm", "low-key"}


def test_asset_usage_missing_detected_with_fragment_and_asset_id():
    """FR-063/FR-064：路由引用资产在 usage.fragments 缺失时命中并双定位"""
    instructions = _instructions(
        route_plan=_route_plan(["char_001", "scene_001"]),
        asset_plan=_asset_plan({"char_001": ["frag_001"], "scene_001": []}),
    )

    report = _auditor().audit(instructions)
    violations = [
        v for v in _new_rule_violations(report) if v.issue_code == "asset_usage_missing"
    ]

    assert len(violations) == 1
    violation = violations[0]
    assert violation.severity == SeverityLevel.MAJOR
    assert violation.fragment_id == "frag_001"
    assert violation.asset_id == "scene_001"
    assert violation.issue_value["reason"] == "片段未出现在 usage.fragments 中"


def test_clean_inputs_produce_no_new_rule_violations():
    """干净契约/指令不得产生四条新规则的误报"""
    instructions = _instructions(
        route_plan=_route_plan(["char_001"]),
        asset_plan=_asset_plan({"char_001": ["frag_001"]}),
    )

    report = _auditor().audit(instructions, contract=_contract())

    assert _new_rule_violations(report) == []
