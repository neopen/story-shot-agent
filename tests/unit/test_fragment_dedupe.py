"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_fragment_dedupe.py
@Description: 片段疑似重复检测与合并单测（0.4.6 FR-070~FR-074）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/13
"""

from typing import List, Optional, Tuple

from penshot.neopen.agent.shot_segmenter.estimator.action_nodes import (
    extract_action_nodes,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
    ShotType,
)
from penshot.neopen.agent.video_splitter.fragment_dedupe import (
    ACTION_RESPLIT,
    ACTION_TRUNCATE,
    CRITERIA_CHARACTER,
    CRITERIA_SHOT_TYPE,
    DENSITY_WARNING,
    MATCHED_BY_STRUCTURED,
    MATCHED_BY_TEXT_SIMILARITY,
    REASON_DENSITY,
    REASON_NO_BOUNDARY,
    compute_text_similarity,
    find_duplicate_candidates,
    lookup_fragment_origin,
    merge_fragments,
    normalize_text_for_similarity,
    resplit_duplicate_pair,
    split_text_units,
)
from penshot.neopen.agent.video_splitter.rule_video_splitter import RuleVideoSplitter
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.shot_config import ShotConfig

PLATFORM_DESCRIPTION = (
    "全景镜头：深夜11点47分，空旷的地铁站台笼罩在冷白色灯光中。"
    "远处隧道口漆黑一片，只有信号灯微弱闪烁，黄色安全线清晰可见，整体氛围孤寂冷清。"
)
CHARACTER_DESCRIPTION = (
    "林晚身穿深灰色长款大衣，颈部围着洗得发白的红围巾，独自站在黄色安全线后。"
    "她手里攥着一张皱巴巴的白色纸条，身体静止，融入孤寂背景中。"
)


def make_fragment(
    fragment_id: str,
    shot_id: str,
    description: str,
    *,
    duration: float = 3.0,
    shot_type: Optional[str] = "wide_shot",
    element_ids: Optional[List[str]] = None,
    continuity_notes: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> VideoFragment:
    """构造测试用片段"""
    return VideoFragment(
        id=fragment_id,
        shot_id=shot_id,
        description=description,
        duration=duration,
        shot_type=shot_type,
        element_ids=element_ids or ["elem_001"],
        continuity_notes=continuity_notes or {"continuity_check": "passed"},
        metadata=metadata or {},
    )


def make_shot(
    shot_id: str,
    scene_id: str,
    *,
    main_character: Optional[str] = "林晚",
    shot_type: ShotType = ShotType.WIDE_SHOT,
    description: str = "测试镜头",
) -> ShotInfo:
    """构造测试用镜头"""
    return ShotInfo(
        id=shot_id,
        scene_id=scene_id,
        description=description,
        shot_type=shot_type,
        main_character=main_character,
        duration=6.0,
    )


def test_sample_frag_001_frag_002_detected_as_duplicate():
    """样本 frag_001/frag_002 同属 shot_001，应命中结构化重复"""
    fragments = [
        make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION),
        make_fragment("frag_002", "shot_001", CHARACTER_DESCRIPTION),
    ]
    shots = [make_shot("shot_001", "scene_001")]

    candidates = find_duplicate_candidates(fragments, shots)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate.prev_index, candidate.index) == (0, 1)
    assert candidate.matched_by == MATCHED_BY_STRUCTURED
    assert CRITERIA_SHOT_TYPE in candidate.criteria
    assert CRITERIA_CHARACTER in candidate.criteria


def test_cross_scene_high_similarity_not_candidate():
    """跨场景的近似文本不得判为疑似重复"""
    fragments = [
        make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION),
        make_fragment("frag_002", "shot_002", PLATFORM_DESCRIPTION),
    ]
    shots = [
        make_shot("shot_001", "scene_001"),
        make_shot("shot_002", "scene_002"),
    ]

    assert find_duplicate_candidates(fragments, shots) == []


def test_text_similarity_fallback_without_shots():
    """缺少镜头上下文时，相邻片段文本相似度兜底仍生效"""
    fragments = [
        make_fragment(
            "frag_001",
            "shot_001",
            "Wide shot: a woman waits alone on the empty platform.",
            shot_type=None,
        ),
        make_fragment(
            "frag_002",
            "shot_001",
            "Medium shot: a woman waits alone on the empty platform.",
            shot_type=None,
        ),
    ]

    candidates = find_duplicate_candidates(fragments, shots=None)

    assert len(candidates) == 1
    assert candidates[0].matched_by == MATCHED_BY_TEXT_SIMILARITY
    assert candidates[0].similarity == 1.0


def test_text_similarity_fallback_rejects_dissimilar_text():
    """文本差异明显时兜底不命中"""
    fragments = [
        make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION, shot_type=None),
        make_fragment(
            "frag_002",
            "shot_002",
            "她转身跑向出口，脚步声在走廊里回荡。",
            shot_type=None,
        ),
    ]

    assert find_duplicate_candidates(fragments, shots=None) == []


def test_non_adjacent_similar_fragments_ignored():
    """相似度只对相邻片段生效"""
    fragments = [
        make_fragment(
            "frag_001",
            "shot_001",
            "A woman waits alone on the platform.",
            shot_type=None,
        ),
        make_fragment(
            "frag_002",
            "shot_002",
            "A train arrives with a loud screech.",
            shot_type=None,
        ),
        make_fragment(
            "frag_003",
            "shot_003",
            "A woman waits alone on the platform.",
            shot_type=None,
        ),
    ]

    assert find_duplicate_candidates(fragments, shots=None) == []


def test_normalization_strips_camera_lead_and_motion():
    """归一化应剥离景别前缀与运镜短语"""
    first = "中景镜头：slow push-in 她抬头望向隧道深处。"
    second = "特写镜头：她抬头望向隧道深处。"

    assert normalize_text_for_similarity(first) == normalize_text_for_similarity(second)
    assert compute_text_similarity(first, second) == 1.0


def test_candidate_to_dict_serializable():
    """候选结果可序列化为报告字典"""
    fragments = [
        make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION),
        make_fragment("frag_002", "shot_001", CHARACTER_DESCRIPTION),
    ]
    candidates = find_duplicate_candidates(
        fragments, [make_shot("shot_001", "scene_001")]
    )

    report = candidates[0].to_dict()

    assert report["matched_by"] == MATCHED_BY_STRUCTURED
    assert report["prev_index"] == 0
    assert report["index"] == 1
    assert isinstance(report["criteria"], list)


def test_merge_within_limit_sums_duration():
    """两段之和不超过 5 秒时合并，时长等于两者之和"""
    previous = make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION, duration=3.0)
    current = make_fragment(
        "frag_002",
        "shot_001",
        CHARACTER_DESCRIPTION,
        duration=2.0,
        shot_type=None,
    )

    merged = merge_fragments(previous, current)

    assert merged is not None
    assert merged.id == "frag_001"
    assert merged.start_time == previous.start_time
    assert merged.duration == 5.0
    assert merged.shot_type == "wide_shot"


def test_merge_over_limit_returns_none():
    """两段之和超过 5 秒时不合并，交给重切逻辑"""
    previous = make_fragment("frag_001", "shot_001", PLATFORM_DESCRIPTION, duration=3.0)
    current = make_fragment("frag_002", "shot_001", CHARACTER_DESCRIPTION, duration=2.5)

    assert merge_fragments(previous, current) is None


def test_merge_preserves_camera_phrase():
    """第二段的运镜描述必须并入合并结果（FR-071）"""
    previous = make_fragment("frag_001", "shot_001", "她站在站台边缘。", duration=2.0)
    current = make_fragment(
        "frag_002",
        "shot_001",
        "中景镜头：slow push-in 她低头看向纸条。",
        duration=2.0,
    )

    merged = merge_fragments(previous, current)

    assert merged is not None
    assert "slow push-in" in merged.description


def test_merge_unions_element_ids_without_duplicates():
    """合并后 element_ids 取并集且不重复"""
    previous = make_fragment(
        "frag_001",
        "shot_001",
        "她站在站台边缘。",
        duration=2.0,
        element_ids=["elem_001", "elem_002"],
    )
    current = make_fragment(
        "frag_002",
        "shot_001",
        "她低头看向纸条。",
        duration=2.0,
        element_ids=["elem_002", "elem_003"],
    )

    merged = merge_fragments(previous, current)

    assert merged is not None
    assert merged.element_ids == ["elem_001", "elem_002", "elem_003"]


def test_merge_keeps_dialogue_intact():
    """台词被拆到两段时，合并后原文完整且不重复（FR-074）"""
    previous = make_fragment(
        "frag_001",
        "shot_001",
        "她抬起头，轻声说：“我不",
        duration=2.0,
    )
    current = make_fragment(
        "frag_002",
        "shot_001",
        "想去。”随后转身离开。",
        duration=2.0,
    )

    merged = merge_fragments(previous, current)

    assert merged is not None
    assert "“我不想去。”" in merged.description
    assert merged.description.count("我不想去") == 1


def test_merge_records_source_metadata():
    """合并结果记录来源片段，便于回溯"""
    previous = make_fragment("frag_001", "shot_001", "她站在站台边缘。", duration=2.0)
    current = make_fragment("frag_002", "shot_001", "她低头看向纸条。", duration=2.0)

    merged = merge_fragments(previous, current)

    assert merged is not None
    assert merged.metadata["merged_from"] == ["frag_001", "frag_002"]
    assert merged.metadata["merge_total_duration"] == 4.0


EIGHT_NODE_TEXT = "林晚低头，抬头，转身，迈步，攥紧纸条，叹气，凝视窗外，微笑。"


def make_pair(
    text: str, *, duration: float = 3.0
) -> Tuple[VideoFragment, VideoFragment, ShotInfo]:
    """构造同镜头的一对疑似重复片段"""
    previous = make_fragment("frag_001", "shot_001", text, duration=duration)
    current = make_fragment("frag_002", "shot_001", text, duration=duration)
    shot = make_shot("shot_001", "scene_001", description=text)
    return previous, current, shot


def test_split_text_units_keeps_quoted_delimiters():
    """引号内的逗号与句号不参与切分（FR-074）"""
    text = "林晚低头，轻声说：“我，真的不想去。”，迈步。"

    units = split_text_units(text)

    assert len(units) == 3
    assert units[1] == "轻声说：“我，真的不想去。”，"
    assert "".join(units) == text


def test_resplit_eight_node_shot_within_bounds():
    """8 动作节点镜头重切后每段都在 [2.5, 5.0] 秒内（AC-073a）"""
    previous, current, shot = make_pair(EIGHT_NODE_TEXT)

    outcome = resplit_duplicate_pair(previous, current, shot=shot)

    assert outcome.action == ACTION_RESPLIT
    assert outcome.reason == "action_boundary"
    assert len(outcome.fragments) >= 2
    for fragment in outcome.fragments:
        assert 2.5 <= fragment.duration <= 5.0

    assert (
        "".join(fragment.description for fragment in outcome.fragments)
        == EIGHT_NODE_TEXT
    )
    assert outcome.to_dict()["action"] == ACTION_RESPLIT


def test_resplit_adjacent_core_actions_differ():
    """重切后相邻子段的核心动作不同（FR-072）"""
    previous, current, shot = make_pair(EIGHT_NODE_TEXT)

    fragments = resplit_duplicate_pair(previous, current, shot=shot).fragments

    for left, right in zip(fragments, fragments[1:]):
        left_actions = extract_action_nodes(left.description)
        right_actions = extract_action_nodes(right.description)
        assert left_actions and right_actions
        assert left_actions[-1] != right_actions[0]


def test_resplit_static_text_truncates_with_warning():
    """无可识别动作边界时截断为 5 秒并说明时长短差（FR-073）"""
    text = (
        "全景镜头：深夜的地铁站台笼罩在冷白色灯光中，空旷而寂静，"
        "隧道口只有信号灯微弱闪烁。"
    )
    previous, current, shot = make_pair(text)

    outcome = resplit_duplicate_pair(previous, current, shot=shot)

    assert outcome.action == ACTION_TRUNCATE
    assert outcome.reason == REASON_NO_BOUNDARY
    assert len(outcome.fragments) == 1
    assert outcome.fragments[0].duration == 5.0
    assert outcome.dropped_duration == 1.0
    assert "截断" in outcome.warnings[0]
    assert "丢弃1.0秒" in outcome.warnings[0]


def test_resplit_keeps_dialogue_intact():
    """重切不得拆分或重复引号内台词（FR-074）"""
    text = (
        "林晚低头，抬头，转身，轻声说：“我，真的不想去。”随后，迈步，凝视窗外，微笑。"
    )
    previous, current, shot = make_pair(text)

    outcome = resplit_duplicate_pair(previous, current, shot=shot)

    assert outcome.action == ACTION_RESPLIT
    descriptions = [fragment.description for fragment in outcome.fragments]
    assert "".join(descriptions) == text
    assert (
        sum(description.count("“我，真的不想去。”") for description in descriptions)
        == 1
    )
    for description in descriptions:
        assert description.count("“") == description.count("”")


def test_resplit_density_fallback_truncates():
    """子段 <2.5 秒且无法合并时回退截断并写密度告警（FR-073a）"""
    text = "林晚低头，抬头，转身，迈步，凝视，微笑，她轻声说：“好。”"
    previous, current, shot = make_pair(text)

    outcome = resplit_duplicate_pair(previous, current, shot=shot)

    assert outcome.action == ACTION_TRUNCATE
    assert outcome.reason == REASON_DENSITY
    assert len(outcome.fragments) == 1
    assert outcome.fragments[0].duration == 5.0
    assert outcome.dropped_duration == 1.0
    assert DENSITY_WARNING in outcome.warnings[0]
    assert "截断为5.0秒" in outcome.warnings[0]
    assert "“好。”" in outcome.fragments[0].description


SPLITTER = RuleVideoSplitter(ShotConfig())


def make_sequence(
    fragments: List[VideoFragment],
    shot_count: int,
) -> FragmentSequence:
    """构造片段序列"""
    return FragmentSequence(
        source_info={
            "shot_count": shot_count,
            "original_duration": 0.0,
            "title": "",
        },
        fragments=fragments,
        metadata={},
    )


def test_post_process_merges_same_shot_pair_and_renumbers():
    """同镜头重复对合并后重编号，映射可反查"""
    fragments = [
        make_fragment(
            "frag_001",
            "shot_001",
            "空旷的站台。",
            duration=1.0,
            metadata={"original_shot": "shot_001"},
        ),
        make_fragment(
            "frag_002",
            "shot_001",
            "昏黄的灯光。",
            duration=1.0,
            metadata={"original_shot": "shot_001"},
        ),
        make_fragment(
            "frag_003",
            "shot_002",
            "列车进站。",
            duration=1.0,
            metadata={"original_shot": "shot_002"},
        ),
    ]
    shots = [
        make_shot("shot_001", "scene_001"),
        make_shot("shot_002", "scene_001"),
    ]

    result = SPLITTER.post_process(
        make_sequence(fragments, shot_count=2), ShotSequence(shots=shots)
    )

    assert len(result.fragments) == 2
    assert [f.duration for f in result.fragments] == [5.0, 2.5]
    assert [f.start_time for f in result.fragments] == [0.0, 5.0]
    assert result.fragments[1].description == "列车进站。"

    report = result.metadata["dedupe_report"]
    assert report["summary"]["merged"] == 1
    assert report["summary"]["skipped_cross_shot"] == 1
    assert report["operations"][0]["action"] == "merge"

    origin = lookup_fragment_origin(result, "frag_001")
    assert origin == {
        "shot_id": "shot_001",
        "fragment_id": "frag_001",
        "source_fragment_ids": ["frag_001", "frag_002"],
    }
    assert lookup_fragment_origin(result, "frag_002")["fragment_id"] == "frag_003"
    assert result.stats["fragments_split"] == 0


def test_post_process_resplits_same_shot_pair_and_tracks_split_stats():
    """同镜头超长重复对重切后，fragments_split 与操作报告一致"""
    fragments = [
        make_fragment(
            "frag_001",
            "shot_001",
            EIGHT_NODE_TEXT,
            duration=1.0,
            metadata={"original_shot": "shot_001"},
        ),
        make_fragment(
            "frag_002",
            "shot_001",
            EIGHT_NODE_TEXT,
            duration=1.0,
            metadata={"original_shot": "shot_001"},
        ),
    ]
    shots = [make_shot("shot_001", "scene_001", description=EIGHT_NODE_TEXT)]

    result = SPLITTER.post_process(
        make_sequence(fragments, shot_count=1), ShotSequence(shots=shots)
    )

    assert len(result.fragments) >= 2
    assert all(2.5 <= fragment.duration <= 5.0 for fragment in result.fragments)
    assert "".join(f.description for f in result.fragments) == EIGHT_NODE_TEXT

    report = result.metadata["dedupe_report"]
    assert report["summary"]["resplit"] == 1
    assert report["summary"]["split_shots"] == 1
    assert result.stats["fragments_split"] == 1
    assert result.stats["split_ratio"] == 1.0

    for fragment in result.fragments:
        origin = lookup_fragment_origin(result, fragment.id)
        assert origin is not None
        assert origin["shot_id"] == "shot_001"
        assert origin["source_fragment_ids"] == ["frag_001", "frag_002"]


def test_post_process_skips_cross_shot_candidates():
    """跨镜头候选只记录不处理，原片段内容保持不变"""
    fragments = [
        make_fragment(
            "frag_001",
            "shot_001",
            "林晚低头看着纸条。",
            duration=1.0,
            metadata={"original_shot": "shot_001"},
        ),
        make_fragment(
            "frag_002",
            "shot_002",
            "林晚转身迈步离开。",
            duration=1.0,
            metadata={"original_shot": "shot_002"},
        ),
    ]
    shots = [
        make_shot("shot_001", "scene_001"),
        make_shot("shot_002", "scene_001"),
    ]

    result = SPLITTER.post_process(
        make_sequence(fragments, shot_count=2), ShotSequence(shots=shots)
    )

    assert [f.description for f in result.fragments] == [
        "林晚低头看着纸条。",
        "林晚转身迈步离开。",
    ]
    assert [f.element_ids for f in result.fragments] == [["elem_001"], ["elem_001"]]
    assert all(2.5 <= f.duration <= 5.0 for f in result.fragments)

    report = result.metadata["dedupe_report"]
    assert report["operations"] == []
    assert report["summary"]["skipped_cross_shot"] == 1
    assert result.stats["fragments_split"] == 0


def test_post_process_normalizes_durations_without_shot_sequence():
    """无镜头序列时仍按动作复杂度统一时长，且不改写内容"""
    fragment = make_fragment(
        "frag_001",
        "shot_001",
        "林晚低头看着纸条。",
        duration=9.0,
    )

    result = SPLITTER.post_process(make_sequence([fragment], shot_count=1))

    assert result.fragments[0].duration == 2.7
    assert result.fragments[0].description == "林晚低头看着纸条。"
    assert result.metadata["dedupe_applied"] is False
    assert "dedupe_report" not in result.metadata
