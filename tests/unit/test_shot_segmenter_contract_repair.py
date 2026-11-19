"""
@FileName: test_shot_segmenter_contract_repair.py
@Description: 分镜修复器对契约违规项（unknown_character 字典）的确定性修复回归测试
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

from types import SimpleNamespace

from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
)
from penshot.neopen.agent.shot_segmenter_agent import ShotSegmenterAgent
from penshot.neopen.shot_config import ShotConfig


def _segmenter() -> ShotSegmenterAgent:
    return ShotSegmenterAgent(
        llm=None, config=ShotConfig(enable_llm=False, enable_enhance=False)
    )


def _shot(shot_id: str, main_character: str) -> ShotInfo:
    return ShotInfo(
        id=shot_id,
        scene_id="scene_001",
        description="门缝外有黑影晃动",
        duration=3.0,
        main_character=main_character,
    )


def _violation(shot_id: str, character: str) -> dict:
    return {
        "type": "unknown_character",
        "stage": "segment_shot",
        "shot_id": shot_id,
        "character": character,
        "message": f"镜头 {shot_id} 的角色 {character} 不在一致性契约中",
    }


def test_repair_shots_clears_hallucinated_main_character():
    """契约外角色不在剧本角色表时：清除主角色标注、保留画面描述"""
    shot_sequence = ShotSequence(shots=[_shot("shot_001", "神秘人")])
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="陈默")])

    repaired = _segmenter().repair_shots(
        shot_sequence, [_violation("shot_001", "神秘人")], structured_script
    )

    assert repaired.shots[0].main_character == ""
    assert "门缝外有黑影晃动" in repaired.shots[0].description
    assert repaired.metadata["repair_history"][-1]["fixed_issues"] == 1


def test_repair_shots_keeps_parsed_character_untouched():
    """剧本真实角色由契约补登记解决，不在镜头层改动"""
    shot_sequence = ShotSequence(shots=[_shot("shot_001", "门口黑影")])
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="门口黑影")])

    repaired = _segmenter().repair_shots(
        shot_sequence, [_violation("shot_001", "门口黑影")], structured_script
    )

    assert repaired.shots[0].main_character == "门口黑影"
    assert repaired.metadata["repair_history"][-1]["fixed_issues"] == 0


def test_repair_shots_tolerates_dict_and_basic_mixed_issues():
    """字典违规项与规则审查问题混合时不崩溃，且两者互不干扰"""
    shot_sequence = ShotSequence(shots=[_shot("shot_001", "神秘人")])
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="陈默")])
    basic = SimpleNamespace(
        issue_type="other",
        issue_code="unknown_rule",
        issue_desc="其他问题",
        fragment_id="shot_001",
    )

    repaired = _segmenter().repair_shots(
        shot_sequence, [_violation("shot_001", "神秘人"), basic], structured_script
    )

    assert repaired.shots[0].main_character == ""
    assert repaired.metadata["repair_history"][-1]["fixed_issues"] == 1


def test_real_character_violation_not_in_manual_list():
    """T-114：剧本真实角色补登记即收敛，不进入人工项"""
    shot_sequence = ShotSequence(shots=[_shot("shot_001", "门口黑影")])
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="门口黑影")])

    repaired = _segmenter().repair_shots(
        shot_sequence, [_violation("shot_001", "门口黑影")], structured_script
    )

    assert repaired.metadata["repair_status"] == "no_issues"
    assert "requires_manual_fix" not in repaired.metadata


def test_cleared_hallucination_not_in_manual_list():
    """T-114：已清除的幻觉角色不再计入人工项，未清除的仍保留人工项"""
    shot_sequence = ShotSequence(
        shots=[_shot("shot_001", "神秘人"), _shot("shot_002", "黑衣人")]
    )
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="陈默")])

    repaired = _segmenter().repair_shots(
        shot_sequence,
        [_violation("shot_001", "神秘人"), _violation("shot_002", "黑影甲")],
        structured_script,
    )

    assert repaired.shots[0].main_character == ""
    assert repaired.shots[1].main_character == "黑衣人"
    assert repaired.metadata["repair_status"] == "partial"
    assert len(repaired.metadata["requires_manual_fix"]) == 1


def test_basic_violation_wrapper_is_also_excluded_from_manual_list():
    """T-114：审计包装的同一违规项随清理结果一并从人工项剔除"""
    shot_sequence = ShotSequence(shots=[_shot("shot_001", "神秘人")])
    structured_script = SimpleNamespace(characters=[SimpleNamespace(name="陈默")])
    violation = _violation("shot_001", "神秘人")
    wrapper = SimpleNamespace(
        issue_type="continuity",
        issue_code="unknown_character",
        issue_desc=violation["message"],
        fragment_id="shot_001",
        issue_value=violation,
        suggestion="清除主角色标注",
    )

    repaired = _segmenter().repair_shots(shot_sequence, [wrapper], structured_script)

    assert repaired.shots[0].main_character == ""
    assert repaired.metadata["repair_status"] == "repaired"
    assert "requires_manual_fix" not in repaired.metadata
