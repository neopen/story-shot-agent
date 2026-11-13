"""T-009 首帧提示词清洗与空镜兜底测试（FR-080~083、AC-073）。

覆盖中文镜头术语与 ``action:`` 标签剥离、音频/画外子句剔除、英文景别短语
保留在首位，以及纯广播片段按 FR-083 生成空镜描述。
"""

from types import SimpleNamespace

from penshot.neopen.agent.model_adapter.first_frame_builder import (
    EMPTY_SCENE_PROMPT,
    build_first_frame_prompt,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
    CameraControl,
)

SCENE = SimpleNamespace(location="城市地铁站台", time_of_day="深夜", weather="")


def _prompt(
    text: str = "",
    main_character: str = "林晚",
    shot_type: str = "wide_shot",
) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id="frag_001",
        prompt=text,
        duration=3.0,
        main_character=main_character,
        camera=CameraControl(shot_type=shot_type),
    )


def _first_frame(
    description: str,
    *,
    prompt: str = "",
    shot_type: str = "wide_shot",
    main_character: str = "林晚",
) -> str:
    fragment = SimpleNamespace(
        id="frag_001", shot_type=shot_type, description=description
    )
    return build_first_frame_prompt(
        _prompt(prompt, main_character, shot_type),
        scene=SCENE,
        fragment=fragment,
    )


def test_strips_chinese_shot_prefix_and_action_label():
    """FR-080：剥离“全景镜头：”与 action: 前缀，保留视觉内容"""
    first_frame = _first_frame("全景镜头：空旷的地铁站台，冷白灯光照在黄色安全线上。")

    assert first_frame.startswith("wide shot")
    assert "镜头" not in first_frame
    assert "action:" not in first_frame
    assert "空旷的地铁站台" in first_frame
    assert "黄色安全线" in first_frame


def test_strips_action_label_from_prompt_when_fragment_missing():
    """无片段描述时回退提示词正文，同样剥离 action: 并保留英文景别"""
    prompt = _prompt("action: wide shot, empty platform at night")

    first_frame = build_first_frame_prompt(prompt, scene=SCENE)

    assert first_frame.startswith("wide shot of 林晚")
    assert "action:" not in first_frame
    assert "empty platform at night" in first_frame


def test_drops_audio_only_sentences_and_uses_empty_scene():
    """FR-081/083：纯广播片段剔除音频句后按空镜兜底"""
    description = (
        "环境音/画外音：站台广播响起，机械而清晰的女声播报："
        "“开往南站的末班车即将进站。”声音在空旷的站台中回荡，打破寂静。"
    )

    first_frame = _first_frame(description)

    for forbidden in ("镜头", "广播", "画外音", "action:"):
        assert forbidden not in first_frame
    assert EMPTY_SCENE_PROMPT in first_frame
    assert "城市地铁站台" in first_frame
    assert "深夜 lighting" in first_frame


def test_keeps_visual_clauses_from_mixed_audio_fragment():
    """音频事件与视觉动作混排时只剔除音频子句"""
    description = "站台广播响起，林晚抬头看向漆黑的隧道口，神情犹豫。"

    first_frame = _first_frame(description)

    assert "广播" not in first_frame
    assert "林晚抬头看向漆黑的隧道口" in first_frame
    assert EMPTY_SCENE_PROMPT not in first_frame


def test_keeps_usable_empty_station_description():
    """纯广播片段里仍有空镜画面时保留该视觉描述，不退化为兜底"""
    description = (
        "全景/环境音镜头：站台广播响起，机械女声播报：“末班车即将进站。”"
        "画面保持静止，聚焦于空荡的站台和远处的隧道口。"
    )

    first_frame = _first_frame(description)

    assert "广播" not in first_frame
    assert "镜头" not in first_frame
    assert "空荡的站台" in first_frame
    assert "远处的隧道口" in first_frame
    assert EMPTY_SCENE_PROMPT not in first_frame


def test_strips_compound_prefix_and_keeps_quoted_dialogue_intact():
    """复合镜头前缀可剥离，引号内台词不被逗号切碎"""
    description = (
        "中景转全景：林晚最终迈步走上列车。"
        "管理员语气平淡地问道：“姑娘，末班车了，上不上？”"
    )

    first_frame = _first_frame(description, shot_type="medium_shot")

    assert first_frame.startswith("medium shot")
    assert "镜头" not in first_frame
    assert "林晚最终迈步走上列车" in first_frame
    assert "上不上？”" in first_frame


def test_camera_move_only_description_falls_back_to_empty_scene():
    """FR-083：只剩运镜描述时不能作为首帧内容"""
    first_frame = _first_frame("镜头拉远。")

    assert "镜头" not in first_frame
    assert EMPTY_SCENE_PROMPT in first_frame
