"""M2 风格题材规范化与证据优先级的回归测试。

覆盖 0.4.4 Spec FR-020/021/023/024/027/028/029 与
AC-020/021/024/025/026/027/028/029：
- 规范题材表与六维模型，旧 GENRE_STYLE_MAP 键保持兼容；
- 显式元数据只接受规范题材/精确别名，非规范值进入 genre_rejected；
- 题材证据按 显式元数据 > 标题 > 场景 > 连续性要点 > 音频氛围 决议；
- 音频氛围为弱证据，移除后不得残留 genre；
- mood 维度以显式音频氛围为准，优先于场景一阶扫描；
- provenance 输出来源、候选与决议依据，无信号时不补默认题材；
- 渲染器按固定维度顺序输出、每维一值，并消解互斥打光。
"""

import json
from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    ATMOSPHERE_DIMENSIONS,
    ATMOSPHERE_KEYWORDS,
    ATMOSPHERE_STYLE_MAP,
    GENRE_DIMENSIONS,
    GENRE_STYLE_MAP,
    STYLE_DIMENSIONS,
    build_style_prefix,
    collect_genre_evidence,
    collect_mood_evidence,
    infer_style_anchor,
    infer_style_anchor_with_provenance,
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


# ---------------------------------------------------------------------------
# mood 采集（FR-023）
# ---------------------------------------------------------------------------


def test_explicit_atmosphere_mood_outranks_scene_scan():
    """AC-027：显式音频氛围决议 mood，场景“紧张”只作为候选保留"""
    parsed = _parsed_script(
        scenes=[("城市街角咖啡店外", "两人互动，气氛紧张")],
        atmosphere="整体氛围温暖浪漫",
    )

    evidence = collect_mood_evidence(parsed)

    assert evidence.mood == "romantic"
    assert evidence.source == "audio_atmosphere"
    assert evidence.keyword == "浪漫"
    assert evidence.resolved_by == "explicit_audio_atmosphere"
    assert {
        "field": "scene",
        "mood": "tense",
        "keyword": "紧张",
    } in evidence.candidates
    assert infer_style_anchor(parsed)["description"] == (
        "soft warm lighting, intimate framing"
    )


def test_mood_falls_back_to_scene_scan_without_explicit_atmosphere():
    """无显式氛围时，场景关键词仍可决议 mood"""
    parsed = _parsed_script(scenes=[("雨夜街道", "气氛紧张")])

    evidence = collect_mood_evidence(parsed)

    assert evidence.mood == "tense"
    assert evidence.source == "scene"
    assert evidence.keyword == "紧张"
    assert evidence.resolved_by == "keyword_scan"


def test_mood_keywords_cover_spec_words():
    """FR-023：样本出现的中文氛围词均有映射，且能映射到英文风格"""
    expected = {
        "清新": "fresh",
        "治愈": "healing",
        "温暖": "happy",
        "浪漫": "romantic",
        "压抑": "sad",
        "紧张": "tense",
    }
    for word, mood in expected.items():
        assert word in ATMOSPHERE_KEYWORDS[mood]
        evidence = collect_mood_evidence(_parsed_script(atmosphere=word))
        assert evidence.mood == mood, word
        assert ATMOSPHERE_STYLE_MAP[mood]


def test_mood_priority_avoids_conflicting_lighting():
    """显式氛围优先后，样本描述不再与题材风格打光冲突"""
    parsed = _parsed_script(
        title="雨中的约定",
        scenes=[("城市街角咖啡店外", "两人互动，气氛由紧张转为温馨幽默")],
        atmosphere="整体氛围清新治愈，营造温暖浪漫的收尾",
    )

    prefix = build_style_prefix(infer_style_anchor(parsed))

    assert "soft warm lighting" in prefix
    assert "high contrast lighting" not in prefix


# ---------------------------------------------------------------------------
# provenance（FR-029）
# ---------------------------------------------------------------------------


def test_with_provenance_reports_genre_and_mood_sources():
    """AC-027：溯源含题材/氛围来源、候选与决议依据，且可 JSON 序列化"""
    parsed = _parsed_script(
        title="雨中的约定",
        scenes=[("城市街角咖啡店外", "两人互动，气氛由紧张转为温馨幽默")],
        atmosphere="整体氛围清新治愈，营造温暖浪漫的收尾",
    )

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert anchor["genre"] == "romance"
    assert anchor["lighting"] == "soft warm lighting"
    assert anchor["mood"] == "romantic"
    assert provenance["genre_source"] == "audio_atmosphere"
    assert provenance["genre_keyword"] == "浪漫"
    assert provenance["confidence"] == "low"
    assert provenance["mood_source"] == "audio_atmosphere"
    assert "tense" in provenance["mood_candidates"]
    assert provenance["resolved_by"]
    assert provenance["genre_rejected"] == []
    assert provenance["discarded"] == []
    assert json.loads(json.dumps(provenance, ensure_ascii=False)) == provenance


def test_genre_dimensions_outrank_atmosphere_dimensions():
    """FR-022：题材维度优先，氛围只填补题材未声明的维度"""
    parsed = _parsed_script(metadata={"genre": "thriller"}, atmosphere="温暖浪漫")

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert anchor["lighting"] == "high contrast lighting"
    assert anchor["mood"] == "tense"
    assert anchor["framing"] == "shadowed framing"
    assert provenance["resolved_by"] == "field_priority"


def test_no_genre_signal_keeps_mood_and_lighting_without_default():
    """AC-029：无题材信号时 genre 为空，锚点仍由 mood/lighting 构成"""
    parsed = _parsed_script(atmosphere="tense")

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert "genre" not in anchor
    assert anchor["mood"] == "tense"
    assert anchor["lighting"] == "high contrast lighting"
    assert provenance["genre_source"] is None
    assert provenance["genre_candidates"] == []
    assert provenance["resolved_by"] == "mood_only"


def test_atmosphere_dimensions_cover_all_mood_keys():
    """氛围维度表覆盖所有可决议的氛围键"""
    assert set(ATMOSPHERE_DIMENSIONS) == set(ATMOSPHERE_STYLE_MAP)


def test_old_wrapper_matches_provenance_entry():
    """旧包装只返回锚点，内容与新入口的锚点一致"""
    parsed = _parsed_script(metadata={"genre": "romance"})

    anchor, _ = infer_style_anchor_with_provenance(parsed)

    assert infer_style_anchor(parsed) == anchor


# ---------------------------------------------------------------------------
# 渲染器（FR-021/024）
# ---------------------------------------------------------------------------


def test_prefix_renders_dimensions_in_fixed_order():
    """FR-021：六维按固定顺序渲染，每维只出现一个值"""
    anchor = {
        "grade": "soft pastel grade",
        "framing": "intimate framing",
        "mood": "romantic",
        "palette": "warm palette",
        "lighting": "soft warm lighting",
        "genre": "romance",
        "description": "soft warm lighting, warm palette",
    }

    assert build_style_prefix(anchor) == (
        "[Style: romance, soft warm lighting, warm palette, romantic, "
        "intimate framing, soft pastel grade]"
    )


def test_prefix_resolves_lighting_conflict_and_records_discard():
    """FR-024/AC-025：保留维度打光，冲突描述被丢弃并写入 provenance"""
    anchor = {
        "genre": "romance",
        "lighting": "soft warm lighting",
        "framing": "intimate framing",
        "description": "high contrast lighting, film grain",
    }
    provenance = {"discarded": []}

    prefix = build_style_prefix(anchor, provenance)

    assert "soft warm lighting" in prefix
    assert "high contrast lighting" not in prefix
    assert "film grain" in prefix
    assert provenance["discarded"] == [
        {
            "dimension": "lighting",
            "value": "high contrast lighting",
            "source": "description",
        }
    ]


def test_prefix_without_genre_is_built_from_mood_and_lighting():
    """AC-029：无题材信号时前缀仍由 mood/lighting 构成"""
    parsed = _parsed_script(atmosphere="tense")
    anchor, _ = infer_style_anchor_with_provenance(parsed)

    assert "genre" not in anchor
    assert build_style_prefix(anchor) == (
        "[Style: high contrast lighting, tense, shadowed framing]"
    )


def test_prefix_is_stable_for_same_anchor():
    """AC-021：同一契约输入重复渲染结果完全一致"""
    parsed = _parsed_script(atmosphere="温暖浪漫")
    anchor, _ = infer_style_anchor_with_provenance(parsed)

    prefixes = {build_style_prefix(dict(anchor)) for _ in range(11)}

    assert len(prefixes) == 1


def test_prefix_keeps_non_canonical_english_genre():
    """旧入参兼容：非规范英文题材原样保留"""
    assert build_style_prefix({"genre": "neo-noir"}) == "[Style: neo-noir]"
