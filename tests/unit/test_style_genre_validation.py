"""M2 风格题材规范化与证据优先级的回归测试。

覆盖 0.4.4 Spec FR-020/027/028 与 AC-026/028：
- 规范题材表与六维模型，旧 GENRE_STYLE_MAP 键保持兼容；
- 显式元数据只接受规范题材/精确别名，非规范值进入 genre_rejected；
- 题材证据按 显式元数据 > 标题 > 场景 > 连续性要点 > 音频氛围 决议；
- 音频氛围为弱证据，移除后不得残留 genre。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    GENRE_DIMENSIONS,
    GENRE_STYLE_MAP,
    STYLE_DIMENSIONS,
    collect_genre_evidence,
    infer_style_anchor,
    normalize_genre,
    resolve_genre_dimensions,
)

CANONICAL_GENRES = {
    "action",
    "thriller",
    "horror",
    "romance",
    "comedy",
    "sci-fi",
    "crime",
    "documentary",
    "youth",
    "drama",
}


def _parsed_script(
    title: str = "",
    metadata=None,
    scenes=None,
    notes: str = "",
    atmosphere: str = "neutral",
) -> SimpleNamespace:
    """构造最小剧本解析结果"""
    return SimpleNamespace(
        title=title,
        metadata=metadata or {},
        scenes=[
            SimpleNamespace(location=location, description=description)
            for location, description in (scenes or [])
        ],
        global_metadata=SimpleNamespace(
            continuity_notes=notes, audio_atmosphere=atmosphere
        ),
    )


def test_canonical_genre_table_and_dimensions():
    """规范题材表覆盖 10 个题材，旧映射键保持兼容"""
    assert set(GENRE_DIMENSIONS) == CANONICAL_GENRES
    assert set(GENRE_STYLE_MAP) == CANONICAL_GENRES
    assert STYLE_DIMENSIONS == (
        "genre",
        "lighting",
        "palette",
        "mood",
        "framing",
        "grade",
    )
    allowed = set(STYLE_DIMENSIONS) - {"genre"}
    for dimensions in GENRE_DIMENSIONS.values():
        assert set(dimensions) <= allowed


def test_resolve_genre_dimensions():
    """romance 解析出软暖光与私密构图，未知题材返回全空模型"""
    romance = resolve_genre_dimensions("romance")
    assert romance.genre == "romance"
    assert romance.lighting == "soft warm lighting"
    assert romance.framing == "intimate framing"
    assert set(romance.to_dict()) == set(STYLE_DIMENSIONS)
    assert romance.to_dict()["grade"] is None

    unknown = resolve_genre_dimensions("cinematic realism")
    assert unknown.to_dict() == {name: None for name in STYLE_DIMENSIONS}


def test_normalize_genre_accepts_canonical_and_alias():
    """只接受规范键或精确别名，非规范值返回空串"""
    assert normalize_genre("Romance") == "romance"
    assert normalize_genre("爱情") == "romance"
    assert normalize_genre("science fiction") == "sci-fi"
    assert normalize_genre("cinematic realism") == ""
    assert normalize_genre("neo-noir") == ""
    assert normalize_genre("") == ""


def test_explicit_canonical_genre_wins():
    """显式规范题材优先并记录来源字段与命中词"""
    parsed = _parsed_script(metadata={"genre": "romance"})

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == "romance"
    assert evidence.source == "metadata.genre"
    assert evidence.keyword == "romance"
    assert evidence.confidence == "high"
    assert infer_style_anchor(parsed).get("genre") == "romance"


def test_non_canonical_explicit_genre_is_rejected():
    """AC-026：非规范显式值不写入 genre，原始值进入 genre_rejected"""
    parsed = _parsed_script(metadata={"genre": "cinematic realism"})

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == ""
    assert evidence.rejected == [
        {"field": "metadata.genre", "value": "cinematic realism"}
    ]
    assert infer_style_anchor(parsed).get("genre") in (None, "")


def test_rejected_explicit_value_falls_back_to_title():
    """显式值被拒后仍可按标题证据决议，rejected 保留原始值"""
    parsed = _parsed_script(metadata={"genre": "neo-noir"}, title="雨夜悬疑")

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == "thriller"
    assert evidence.source == "title"
    assert evidence.keyword == "悬疑"
    assert evidence.confidence == "medium"
    assert any(item["value"] == "neo-noir" for item in evidence.rejected)
    assert infer_style_anchor(parsed).get("genre") == "thriller"


def test_evidence_priority_order():
    """证据按字段优先级排序：显式 > 标题 > 场景 > 连续性要点 > 音频氛围"""
    parsed = _parsed_script(
        metadata={"genre": "romance"},
        title="恐怖圣诞夜",
        scenes=[("教室", "放学后的空教室")],
        notes="整体氛围悬疑紧张",
        atmosphere="温暖浪漫",
    )

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == "romance"
    assert [item["field"] for item in evidence.candidates] == [
        "metadata.genre",
        "title",
        "scene",
        "continuity_notes",
        "audio_atmosphere",
    ]
    assert [item["confidence"] for item in evidence.candidates] == [
        "high",
        "medium",
        "medium",
        "medium",
        "low",
    ]


def test_scene_outranks_continuity_notes():
    """无显式/标题信号时，场景证据优先于连续性要点"""
    parsed = _parsed_script(
        scenes=[("教室", "放学后的空教室")], notes="整体氛围悬疑紧张"
    )

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == "youth"
    assert evidence.source == "scene"


def test_atmosphere_is_weak_evidence():
    """AC-028：音频氛围可作最后证据但标记 low，移除后不得残留 genre"""
    scenes = [("咖啡店外", "雨夜街道")]
    with_atmosphere = _parsed_script(scenes=scenes, atmosphere="温暖浪漫")

    evidence = collect_genre_evidence(with_atmosphere)

    assert evidence.genre == "romance"
    assert evidence.source == "audio_atmosphere"
    assert evidence.keyword == "浪漫"
    assert evidence.confidence == "low"
    assert infer_style_anchor(with_atmosphere).get("genre") == "romance"

    without_atmosphere = _parsed_script(scenes=scenes, atmosphere="neutral")
    assert collect_genre_evidence(without_atmosphere).genre == ""
    assert infer_style_anchor(without_atmosphere).get("genre") in (None, "")


def test_incidental_mood_word_in_scene_does_not_decide_genre():
    """AC-024：场景里的“幽默”属于氛围词，不抢占音频氛围的 romance 证据"""
    parsed = _parsed_script(
        title="雨中的约定",
        scenes=[("城市街角咖啡店外", "两人互动，气氛由紧张转为温馨幽默")],
        atmosphere="整体氛围清新治愈，营造温暖浪漫的收尾",
    )

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == "romance"
    assert evidence.source == "audio_atmosphere"
    assert evidence.keyword == "浪漫"
    assert evidence.confidence == "low"
    assert "scene" not in [item["field"] for item in evidence.candidates]


def test_no_signal_produces_empty_evidence():
    """无任何题材信号时不补默认题材"""
    parsed = _parsed_script()

    evidence = collect_genre_evidence(parsed)

    assert evidence.genre == ""
    assert evidence.source == ""
    assert evidence.confidence == ""
    assert evidence.candidates == []
    assert evidence.rejected == []
    assert infer_style_anchor(parsed) == {}
