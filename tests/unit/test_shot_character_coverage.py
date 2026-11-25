"""分镜角色覆盖检测：画外音/仅声音角色不应被判为“角色未在镜头中出现”。"""

from types import SimpleNamespace

from penshot.neopen.agent.base_models import ElementType
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


def _shot(shot_id: str, element_ids, main_character: str = "林然") -> ShotInfo:
    return ShotInfo(
        id=shot_id,
        scene_id="scene_001",
        description="林然握着手机，神情紧张",
        duration=3.0,
        main_character=main_character,
        element_ids=element_ids,
    )


def _script(elements, characters):
    return SimpleNamespace(
        scenes=[SimpleNamespace(id="scene_001", elements=elements)],
        characters=[SimpleNamespace(name=name) for name in characters],
    )


def test_voice_only_character_covered_by_dialogue_shot():
    """画外音角色只出现在台词元素中，镜头主体是听者，不应判为角色缺席"""
    dialogue = SimpleNamespace(
        id="elem_001", character="陈默", type=ElementType.DIALOGUE
    )
    action = SimpleNamespace(id="elem_002", character="林然", type=ElementType.ACTION)
    script = _script([dialogue, action], ["林然", "陈默"])
    shots = ShotSequence(
        shots=[
            _shot("shot_001", ["elem_001"]),
            _shot("shot_002", ["elem_002"]),
        ]
    )

    issues = _segmenter().detect_shot_issues(shots, script)

    assert not [
        issue for issue in issues if issue.issue_code == "character_not_in_shots"
    ]


def test_character_without_any_shot_is_still_reported():
    """未被任何镜头引用的角色仍需如实报告缺失"""
    action = SimpleNamespace(id="elem_001", character="林然", type=ElementType.ACTION)
    script = _script([action], ["林然", "陈默"])
    shots = ShotSequence(shots=[_shot("shot_001", ["elem_001"])])

    issues = _segmenter().detect_shot_issues(shots, script)

    missing = [
        issue for issue in issues if issue.issue_code == "character_not_in_shots"
    ]
    assert missing
    assert "陈默" in missing[0].issue_value
