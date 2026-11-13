"""
M0.4.6 T-013 回归测试：氛围证据扩展与 provenance.source 枚举。

覆盖：
- 场景 `audio_context.env_sounds[].description` 与场景文本打光词进入氛围证据；
- 扩展证据命中时 `MoodEvidence.resolved_by=extracted`，并记录来源字段与原始词；
- `provenance.source` 只取固定枚举，多来源命中时按固定优先级决议。
"""

from types import SimpleNamespace

import pytest

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    EVIDENCE_SOURCES,
    LIGHTING_KEYWORDS,
    build_style_prefix,
    collect_lighting_evidence,
    collect_mood_evidence,
    infer_style_anchor_with_provenance,
)
from penshot.neopen.agent.script_parser.script_parser_models import (
    EnvironmentSound,
    SceneAudioContext,
)


def _scene(location="", description="", env_sounds=None):
    """构造场景：env_sounds 为 (sound_type, description) 列表"""
    audio_context = None
    if env_sounds is not None:
        audio_context = SceneAudioContext(
            scene_type="indoor",
            env_sounds=[
                EnvironmentSound(sound_type=sound_type, description=text)
                for sound_type, text in env_sounds
            ],
        )
    return SimpleNamespace(
        location=location,
        description=description,
        audio_context=audio_context,
    )


def _parsed_script(
    *, title="", scenes=None, atmosphere="neutral", notes="", metadata=None
):
    """构造最小剧本解析结果"""
    return SimpleNamespace(
        title=title,
        metadata=metadata or {},
        scenes=scenes or [],
        global_metadata=SimpleNamespace(
            continuity_notes=notes, audio_atmosphere=atmosphere
        ),
    )


# ---------------------------------------------------------------------------
# 扩展证据采集
# ---------------------------------------------------------------------------


def test_env_sound_evidence_marks_extracted():
    """FR-091：环境音描述命中氛围词时记为扩展证据并可追溯"""
    parsed = _parsed_script(
        scenes=[
            _scene(
                "城市地铁站台",
                "深夜空旷的地铁站台",
                env_sounds=[("silence", "深夜站台的寂静与空旷感")],
            )
        ]
    )

    evidence = collect_mood_evidence(parsed)

    assert evidence.mood == "calm"
    assert evidence.source == "env_sounds"
    assert evidence.keyword == "寂静"
    assert evidence.resolved_by == "extracted"

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert provenance["resolved_by"] == "extracted"
    assert provenance["source"] == "env_sound"
    assert provenance["mood_source"] == "env_sounds"
    assert provenance["mood_keyword"] == "寂静"
    assert provenance["lighting_source"] == "env_sound"
    assert provenance["lighting_keyword"] == "寂静"
    assert provenance["defaults_applied"] == []
    for dimension in ("lighting", "palette", "mood", "description"):
        assert anchor.get(dimension), dimension


def test_lighting_keyword_evidence_marks_extracted():
    """FR-091：场景文本打光词命中时记为扩展证据"""
    parsed = _parsed_script(scenes=[_scene("地下室走廊", "冷白色灯光笼罩着空荡的走廊")])

    evidence = collect_mood_evidence(parsed)

    assert evidence.mood == "sad"
    assert evidence.source == "lighting"
    assert evidence.keyword == "冷白"
    assert evidence.resolved_by == "extracted"

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert provenance["resolved_by"] == "extracted"
    assert provenance["source"] == "lighting_keyword"
    assert provenance["mood_source"] == "lighting"
    assert provenance["mood_keyword"] == "冷白"
    assert provenance["lighting_source"] == "lighting_keyword"
    assert provenance["lighting_keyword"] == "冷白"
    assert provenance["defaults_applied"] == []
    assert anchor["lighting"] == "diffused lighting"
    assert anchor["palette"] == "muted colors"


@pytest.mark.parametrize("word,mood", sorted(LIGHTING_KEYWORDS.items()))
def test_lighting_keywords_map_to_atmosphere(word, mood):
    """FR-091：六个打光词均有氛围映射，可单独构成证据"""
    parsed = _parsed_script(scenes=[_scene("街角", f"场景中出现{word}的画面")])

    evidence = collect_lighting_evidence(parsed)

    assert evidence.mood == mood
    assert evidence.source == "lighting"
    assert evidence.keyword == word
    assert evidence.resolved_by == "extracted"


def test_extended_candidates_record_field_and_keyword():
    """扩展证据的候选保留来源字段与原始词"""
    parsed = _parsed_script(
        scenes=[
            _scene(
                "站台",
                "冷白色灯光笼罩",
                env_sounds=[("silence", "站台的寂静")],
            )
        ]
    )

    evidence = collect_mood_evidence(parsed)

    assert {"field": "env_sounds", "mood": "calm", "keyword": "寂静"} in (
        evidence.candidates
    )
    assert {"field": "lighting", "mood": "sad", "keyword": "冷白"} in (
        evidence.candidates
    )


# ---------------------------------------------------------------------------
# 来源优先级
# ---------------------------------------------------------------------------


def test_explicit_atmosphere_outranks_extended_evidence():
    """固定优先级：全局音频氛围高于环境音与打光词"""
    parsed = _parsed_script(
        atmosphere="tense",
        scenes=[
            _scene(
                "站台",
                "冷白色灯光笼罩",
                env_sounds=[("silence", "站台的寂静")],
            )
        ],
    )

    evidence = collect_mood_evidence(parsed)
    _, provenance = infer_style_anchor_with_provenance(parsed)

    assert evidence.mood == "tense"
    assert evidence.source == "audio_atmosphere"
    assert evidence.resolved_by == "extracted"
    assert provenance["source"] == "audio_atmosphere"
    assert provenance["resolved_by"] == "extracted"
    assert provenance["lighting_source"] == "audio_atmosphere"
    assert provenance["lighting_keyword"] == "tense"
    assert provenance["defaults_applied"] == ["palette"]


def test_env_sound_outranks_lighting_keyword():
    """固定优先级：环境音高于场景文本打光词"""
    parsed = _parsed_script(
        scenes=[
            _scene(
                "站台",
                "冷白色灯光笼罩",
                env_sounds=[("silence", "站台的寂静")],
            )
        ]
    )

    evidence = collect_mood_evidence(parsed)
    _, provenance = infer_style_anchor_with_provenance(parsed)

    assert evidence.mood == "calm"
    assert evidence.source == "env_sounds"
    assert provenance["source"] == "env_sound"
    assert provenance["lighting_source"] == "env_sound"
    assert provenance["lighting_keyword"] == "寂静"


def test_lighting_keyword_outranks_keyword_scan():
    """固定优先级：打光词高于标题/场景/连续性关键词扫描"""
    parsed = _parsed_script(
        notes="整体气氛紧张",
        scenes=[_scene("站台", "冷白色灯光笼罩")],
    )

    evidence = collect_mood_evidence(parsed)
    _, provenance = infer_style_anchor_with_provenance(parsed)

    assert evidence.mood == "sad"
    assert evidence.source == "lighting"
    assert provenance["source"] == "lighting_keyword"
    assert provenance["resolved_by"] == "extracted"
    assert provenance["lighting_source"] == "lighting_keyword"
    assert provenance["lighting_keyword"] == "冷白"
    assert "tense" in provenance["mood_candidates"]


def test_provenance_source_only_uses_fixed_enum():
    """provenance.source 只出现固定枚举值，且按固定优先级取值"""
    cases = [
        (
            _parsed_script(metadata={"genre": "thriller"}, atmosphere="sad"),
            "field_priority",
        ),
        (_parsed_script(atmosphere="tense"), "audio_atmosphere"),
        (
            _parsed_script(
                scenes=[_scene("站台", "", env_sounds=[("silence", "站台的寂静")])]
            ),
            "env_sound",
        ),
        (_parsed_script(scenes=[_scene("站台", "冷白色灯光笼罩")]), "lighting_keyword"),
        (_parsed_script(notes="安静的小镇"), "keyword_scan"),
    ]

    for parsed, expected in cases:
        _, provenance = infer_style_anchor_with_provenance(parsed)
        assert provenance["source"] == expected
        assert provenance["source"] in EVIDENCE_SOURCES
        assert provenance["resolved_by"] == "extracted"
        assert provenance["lighting_source"] in EVIDENCE_SOURCES

    assert EVIDENCE_SOURCES == (
        "field_priority",
        "audio_atmosphere",
        "env_sound",
        "lighting_keyword",
        "keyword_scan",
    )


def test_all_evidence_missing_applies_default_dimensions():
    """FR-088/FR-089：全部证据缺失时兜底三维并标记 default_fallback"""
    anchor, provenance = infer_style_anchor_with_provenance(_parsed_script())

    assert anchor == {
        "lighting": "natural lighting",
        "palette": "muted colors",
        "mood": "neutral",
    }
    assert "genre" not in anchor
    assert provenance["resolved_by"] == "default_fallback"
    assert provenance["source"] is None
    assert provenance["mood_source"] is None
    assert provenance["defaults_applied"] == ["lighting", "palette", "mood"]
    assert provenance["lighting_source"] == "default_fallback"
    assert provenance["lighting_keyword"] is None


def test_defaults_only_fill_missing_dimensions():
    """FR-088：默认值只填空缺，不覆盖已有证据维度"""
    parsed = _parsed_script(atmosphere="tense")

    anchor, provenance = infer_style_anchor_with_provenance(parsed)

    assert anchor["lighting"] == "high contrast lighting"
    assert anchor["mood"] == "tense"
    assert anchor["palette"] == "muted colors"
    assert provenance["defaults_applied"] == ["palette"]
    assert provenance["resolved_by"] == "extracted"
    assert provenance["source"] == "audio_atmosphere"
    assert provenance["lighting_source"] == "audio_atmosphere"


def test_default_fallback_renders_non_empty_prefix():
    """FR-088：兜底三维仍可渲染出非空风格前缀"""
    anchor, _ = infer_style_anchor_with_provenance(_parsed_script())

    assert build_style_prefix(anchor) == (
        "[Style: natural lighting, muted colors, neutral]"
    )
