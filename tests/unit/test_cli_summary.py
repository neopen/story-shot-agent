"""CLI 摘要在 workflow 输出结构上的回归测试。

覆盖 _extract_summary 对 shot_sequence / fragment_sequence / instructions 的
结构对齐与统计计算，防止字段名再次漂移导致 CLI 摘要空数据。
"""

from penshot.cli import _extract_summary


def test_extract_summary_from_shot_sequence():
    """从 shot_sequence.shots 提取镜头并计算统计"""
    data = {
        "shot_sequence": {
            "shots": [
                {
                    "id": "shot_001",
                    "duration": 3.0,
                    "shot_type": "wide_shot",
                    "description": "d1",
                },
                {
                    "id": "shot_002",
                    "duration": 4.5,
                    "shot_type": "close_up",
                    "description": "d2",
                },
            ]
        },
        "instructions": {"fragments": [], "route_plan": None},
    }
    shots, stats = _extract_summary(data)
    assert len(shots) == 2
    assert stats["shot_count"] == 2
    assert stats["total_duration"] == 7.5


def test_extract_summary_fallback_to_instructions_fragments():
    """镜头序列缺失时回退到 instructions.fragments"""
    data = {
        "instructions": {
            "fragments": [
                {"fragment_id": "frag_001", "duration": 2.0},
                {"fragment_id": "frag_002", "duration": 3.0},
            ]
        },
    }
    shots, stats = _extract_summary(data)
    assert stats["shot_count"] == 2
    assert stats["total_duration"] == 5.0


def test_extract_summary_fallback_to_fragment_sequence():
    """回退到 fragment_sequence.fragments"""
    data = {
        "fragment_sequence": {
            "fragments": [
                {"id": "frag_001", "duration": 1.5},
            ]
        },
    }
    shots, stats = _extract_summary(data)
    assert stats["shot_count"] == 1
    assert stats["total_duration"] == 1.5


def test_extract_summary_empty():
    """空数据返回空镜头列表与零统计"""
    shots, stats = _extract_summary({})
    assert shots == []
    assert stats["shot_count"] == 0
    assert stats["total_duration"] == 0
