"""
@FileName: test_shot_segmenter_element_ids.py
@Description: 校验 LLM 分镜输出的 element_ids 与剧本解析的全局元素ID对齐
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

import json
from typing import List

import pytest

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    GlobalMetadata,
    SceneInfo,
)
from penshot.neopen.agent.shot_segmenter.llm_shot_segmenter import LLMShotSegmenter
from penshot.neopen.shot_config import ShotConfig


def _element(element_id: str, sequence: int, content: str) -> BaseElement:
    return BaseElement(
        id=element_id,
        type=ElementType.ACTION,
        sequence=sequence,
        content=content,
        duration=3.0,
    )


@pytest.fixture
def scene_002() -> SceneInfo:
    """第二场景元素ID从 elem_005 起（与真实样本 SN4445005582174366474090 一致）"""
    return SceneInfo(
        id="scene_002",
        location="走廊",
        description="贴满记忆的走廊",
        elements=[
            _element("elem_005", 5, "记忆墙上的便利贴"),
            _element("elem_006", 6, "李明想起往事"),
            _element("elem_007", 7, "张晨抱着篮球走来"),
        ],
    )


@pytest.fixture
def segmenter() -> LLMShotSegmenter:
    return LLMShotSegmenter(llm_client=None, config=ShotConfig())


def _shots_json(shots: List[dict]) -> str:
    return json.dumps(shots, ensure_ascii=False)


def test_scene_restarted_ids_are_remapped(segmenter, scene_002):
    """LLM 按场景从 elem_001 重新编号时，按场景序号映射回全局ID"""
    payload = _shots_json(
        [
            {
                "description": "记忆墙特写",
                "duration": 3.0,
                "shot_type": "close_up",
                "element_ids": ["elem_001"],
            },
            {
                "description": "两个动作合成一镜",
                "duration": 4.0,
                "shot_type": "medium_shot",
                "element_ids": ["elem_002", "elem_003"],
            },
        ]
    )

    shots = segmenter._parse_ai_response(payload, scene_002, 0.0, 4)

    assert [shot.element_ids for shot in shots] == [
        ["elem_005"],
        ["elem_006", "elem_007"],
    ]


def test_local_numbering_that_collides_with_global_ids(segmenter):
    """场景内重编号恰好与全局ID重名时，仍按整批镜头判定为场景内编号"""
    scene = SceneInfo(
        id="scene_002",
        location="走廊",
        elements=[_element(f"elem_{i:03d}", i, f"元素{i}") for i in range(5, 12)],
    )
    payload = _shots_json(
        [
            {"description": "一", "duration": 2.0, "element_ids": ["elem_001"]},
            {"description": "二", "duration": 2.0, "element_ids": ["elem_002"]},
            {"description": "三", "duration": 2.0, "element_ids": ["elem_003"]},
            {"description": "四", "duration": 2.0, "element_ids": ["elem_004"]},
            {
                "description": "五、六",
                "duration": 3.0,
                "element_ids": ["elem_005", "elem_006"],
            },
            {"description": "七", "duration": 2.0, "element_ids": ["elem_007"]},
        ]
    )

    shots = segmenter._parse_ai_response(payload, scene, 0.0, 4)

    assert [shot.element_ids for shot in shots] == [
        ["elem_005"],
        ["elem_006"],
        ["elem_007"],
        ["elem_008"],
        ["elem_009", "elem_010"],
        ["elem_011"],
    ]


def test_valid_global_ids_are_kept(segmenter, scene_002):
    """LLM 直接给出真实全局ID时不做任何改写"""
    payload = _shots_json(
        [
            {
                "description": "张晨走来",
                "duration": 3.0,
                "shot_type": "medium_shot",
                "element_ids": ["elem_007", "elem_005"],
            }
        ]
    )

    shots = segmenter._parse_ai_response(payload, scene_002, 0.0, 0)

    assert shots[0].element_ids == ["elem_007", "elem_005"]


def test_duplicate_and_unknown_ids_are_cleaned(segmenter, scene_002):
    """重复ID去重，无法识别的ID丢弃"""
    payload = _shots_json(
        [
            {
                "description": "混合ID",
                "duration": 3.0,
                "shot_type": "medium_shot",
                "element_ids": ["elem_005", "elem_005", "elem_999", "not_an_id"],
            }
        ]
    )

    shots = segmenter._parse_ai_response(payload, scene_002, 0.0, 0)

    assert shots[0].element_ids == ["elem_005"]


def test_missing_element_ids_defaults_to_empty(segmenter, scene_002):
    """缺失或类型非法时返回空列表，不抛异常"""
    payload = _shots_json([{"description": "无ID", "duration": 2.0}])

    shots = segmenter._parse_ai_response(payload, scene_002, 0.0, 0)

    assert shots[0].element_ids == []


def test_scene_prompt_carries_real_element_ids(monkeypatch, segmenter, scene_002):
    """场景提示词必须携带真实元素ID，供LLM原样引用"""
    captured = {}

    def _fake_call(system_prompt: str, user_prompt: str, max_retries: int = 2) -> str:
        captured["user_prompt"] = user_prompt
        return _shots_json(
            [
                {
                    "description": "记忆墙特写",
                    "duration": 3.0,
                    "shot_type": "close_up",
                    "element_ids": ["elem_005"],
                }
            ]
        )

    monkeypatch.setattr(segmenter, "_call_llm_chat_with_retry", _fake_call)
    monkeypatch.setattr(segmenter, "_format_global_metadata", lambda *a, **k: "")

    shots = segmenter._split_scene_with_llm(scene_002, 0.0, 0, GlobalMetadata())

    prompt = captured["user_prompt"]
    assert "[elem_005]" in prompt
    assert "[elem_006]" in prompt
    assert "[elem_007]" in prompt
    assert shots[0].element_ids == ["elem_005"]
