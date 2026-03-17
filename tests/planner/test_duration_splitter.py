"""
@FileName: test_duration_splitter.py
@Description: 5秒分片模块使用示例
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/15 15:57
"""

from typing import Dict

from penshot.neopen.agent.script_parser2.script_parser_models import UnifiedScript
from penshot.neopen.agent.temporal_planner.splitter.five_second_splitter import FiveSecondSplitter
from penshot.neopen.agent.temporal_planner.splitter.splitter_config import SplitterConfig
from penshot.neopen.agent.video_assembler.splitter.splitter_validator import SplitterExporter, SegmentValidator, SegmentVisualizer
from penshot.neopen.agent.temporal_planner.temporal_planner_model import DurationEstimation, ElementType
from penshot.utils.obj_utils import dict_to_dataclass


def create_sample_estimations() -> Dict[str, DurationEstimation]:
    """创建示例的时长估算数据"""
    estimations = {}

    # 场景元素
    estimations["scene_1"] = DurationEstimation(
        element_id="scene_1",
        element_type=ElementType.SCENE,
        original_duration=8.5,
        estimated_duration=8.2,
        min_duration=6.0,
        max_duration=10.0,
        confidence=0.85,
        emotional_weight=1.2,
        visual_complexity=1.5,
        can_be_split=True,
        split_priority=5
    )

    # 对话元素
    estimations["dial_1"] = DurationEstimation(
        element_id="dial_1",
        element_type=ElementType.DIALOGUE,
        original_duration=3.2,
        estimated_duration=3.5,
        min_duration=2.8,
        max_duration=4.0,
        confidence=0.9,
        emotional_weight=1.8,
        pacing_factor=0.8,
        can_be_split=False,  # 对话通常不切割
        split_priority=2
    )

    # 沉默元素
    estimations["dial_4"] = DurationEstimation(
        element_id="dial_4",
        element_type=ElementType.SILENCE,
        original_duration=3.0,
        estimated_duration=3.2,
        min_duration=2.5,
        max_duration=3.8,
        confidence=0.88,
        emotional_weight=2.0,
        pacing_factor=0.6,
        can_be_split=False,  # 沉默不切割
        split_priority=1
    )

    # 动作元素
    estimations["act_1"] = DurationEstimation(
        element_id="act_1",
        element_type=ElementType.ACTION,
        original_duration=2.5,
        estimated_duration=2.3,
        min_duration=1.8,
        max_duration=3.0,
        confidence=0.8,
        visual_complexity=1.2,
        can_be_split=True,
        split_priority=4
    )

    estimations["act_2"] = DurationEstimation(
        element_id="act_2",
        element_type=ElementType.ACTION,
        original_duration=1.8,
        estimated_duration=1.6,
        min_duration=1.2,
        max_duration=2.2,
        confidence=0.85,
        visual_complexity=1.0,
        can_be_split=True,
        split_priority=4
    )

    estimations["act_3"] = DurationEstimation(
        element_id="act_3",
        element_type=ElementType.ACTION,
        original_duration=3.5,
        estimated_duration=3.7,
        min_duration=3.0,
        max_duration=4.5,
        confidence=0.75,
        emotional_weight=1.5,
        visual_complexity=1.8,
        can_be_split=True,
        split_priority=4
    )

    # 超长动作
    estimations["act_long"] = DurationEstimation(
        element_id="act_long",
        element_type=ElementType.ACTION,
        original_duration=12.0,
        estimated_duration=11.5,
        min_duration=10.0,
        max_duration=14.0,
        confidence=0.7,
        visual_complexity=2.5,
        can_be_split=True,  # 超长必须切割
        split_priority=6,
        key_moment_percentage=0.6
    )

    return estimations


def create_original_data() -> Dict[str, Dict]:
    """创建原始数据示例"""
    return {
        "scene_1": {
            "description": "深夜，窗外雨势猛烈。客厅昏暗，电视播放着无声的黑白老电影...",
            "location": "城市公寓客厅",
            "mood": "孤独紧张"
        },
        "dial_1": {
            "content": "……陈默？你还好吗？",
            "speaker": "林然",
            "emotion": "微颤"
        },
        "dial_4": {
            "content": "",
            "speaker": "林然",
            "parenthetical": "张了张嘴，却发不出声音",
            "type": "silence"
        },
        "act_1": {
            "description": "裹着旧羊毛毯蜷在沙发里",
            "actor": "林然",
            "type": "posture"
        },
        "act_2": {
            "description": "突然震动，屏幕亮起显示‘未知号码’",
            "actor": "手机",
            "type": "device_alert"
        },
        "act_3": {
            "description": "盯着手机看了三秒，指尖悬停在接听键上方",
            "actor": "林然",
            "type": "gaze"
        },
        "act_long": {
            "description": "从沙发上缓缓站起，走到窗边，看着窗外的雨，然后转身拿起电话",
            "actor": "林然",
            "type": "complex_sequence"
        }
    }


def test_demonstrate_splitter():
    """演示5秒分片器功能"""
    print("=== 5秒分片器演示 ===\n")

    # 1. 准备数据
    estimations = create_sample_estimations()
    original_data = create_original_data()

    # 元素顺序（模拟剧本顺序）
    element_order = [
        "scene_1",  # 场景建立
        "act_1",  # 初始动作
        "act_2",  # 手机震动
        "act_3",  # 凝视手机
        "dial_1",  # 对话
        "dial_4",  # 沉默
        "act_long"  # 超长动作
    ]

    print(f"处理 {len(element_order)} 个元素:")
    for elem_id in element_order:
        if elem_id in estimations:
            elem = estimations[elem_id]
            print(f"  {elem_id}: {elem.element_type.value} ({elem.estimated_duration:.1f}s)")

    # 2. 配置分片器
    config = SplitterConfig()
    config.target_segment_duration = 5.0
    config.min_segment_duration = 4.0
    config.max_segment_duration = 6.0

    splitter = FiveSecondSplitter(config)

    # 3. 执行分片
    print("\n开始分片处理...")
    result = splitter.split_into_segments(
        estimations=estimations,
        element_order=element_order,
        original_data=dict_to_dataclass(original_data, UnifiedScript)
    )

    # 4. 显示结果
    print(f"\n分片完成，生成 {len(result.segments)} 个片段:")
    print(f"总体质量评分: {result.overall_quality_score:.2f}/1.0")
    print(f"节奏一致性: {result.pacing_consistency_score:.2f}/1.0")
    print(f"连续性: {result.continuity_score:.2f}/1.0")

    # 5. 显示片段详情
    print(f"\n片段详情:")
    for i, segment in enumerate(result.segments):
        print(f"\n片段 {segment.segment_id}:")
        print(f"  时间范围: {segment.start_time:.1f}s - {segment.end_time:.1f}s ({segment.duration:.1f}s)")
        print(f"  类型: {segment.segment_type}, 节奏分: {segment.pacing_score:.1f}")
        print(f"  视觉摘要: {segment.visual_summary}")
        print(f"  包含元素: {len(segment.contained_elements)} 个")

        for elem in segment.contained_elements:
            partial = " (部分)" if elem.is_partial else ""
            print(f"    - {elem.element_id}: {elem.element_type.value}{partial}")
            if elem.is_partial:
                print(f"      类型: {elem.partial_type}, 偏移: {elem.start_offset:.1f}s, 时长: {elem.duration:.1f}s")

    # 6. 显示切割决策
    if result.split_decisions:
        print(f"\n切割决策 ({len(result.split_decisions)} 个):")
        for decision in result.split_decisions:
            print(f"  {decision.element_id}: 切割点 {decision.split_point:.2f}")
            print(f"    原因: {decision.reason}")
            print(f"    质量: {decision.quality_score:.2f}")

    # 7. 显示统计信息
    print(f"\n统计信息:")
    stats = result.statistics
    print(f"  总时长: {stats['total_duration']:.1f}秒")
    print(f"  总元素数: {stats['total_elements']} 个")
    print(f"  部分元素: {stats['partial_elements']} 个 ({stats['partial_ratio'] * 100:.1f}%)")

    duration_stats = stats['duration_stats']
    print(f"  时长统计: 平均 {duration_stats['average']:.2f}s, 最小 {duration_stats['min']:.2f}s, 最大 {duration_stats['max']:.2f}s")

    # 8. 可视化时间线
    print(f"\n时间线可视化:")
    print(SegmentVisualizer.generate_timeline_visualization(result.segments, width=60))

    # 9. 验证结果
    print(f"\n验证分片结果...")
    validation = SegmentValidator.validate_split_result(result)

    if validation["valid"]:
        print("✓ 分片结果验证通过")
    else:
        print("✗ 分片结果验证失败:")
        for error in validation["errors"][:5]:  # 只显示前5个错误
            print(f"  - {error}")

    if validation["warnings"]:
        print(f"警告 ({len(validation['warnings'])} 个):")
        for warning in validation["warnings"][:3]:  # 只显示前3个警告
            print(f"  - {warning}")

    # 10. 导出结果（可选）
    print(f"\n导出结果...")
    try:
        SplitterExporter.export_to_readable_format(result, "split_result.txt")
        print("✓ 结果已导出到 split_result.txt")
    except Exception as e:
        print(f"✗ 导出失败: {e}")

    print(f"\n=== 演示完成 ===")

    return result



