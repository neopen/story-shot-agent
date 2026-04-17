"""
@FileName: test_temporal_scene_planner.py
@Description: 演示使用YAML配置的场景估算器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/13 16:12
"""

from penshot.neopen.agent.script_parser2.script_parser_models import Action
from penshot.neopen.agent.shot_generator_bak.estimator.rule_action_estimator import RuleActionDurationEstimator
from penshot.neopen.agent.shot_generator_bak.estimator.rule_base_estimator import EstimationContext
from penshot.neopen.agent.temporal_planner.temporal_planner_model import DurationEstimation
from penshot.utils.obj_utils import batch_dict_to_dataclass, dict_to_dataclass


def test_demonstrate_action_estimator():
    """演示动作时长估算器"""

    print("=== 动作时长估算器演示 ===\n")

    # 1. 初始化配置管理器和估算器
    estimator = RuleActionDurationEstimator()

    # 2. 设置上下文
    context = EstimationContext(
        scene_type="indoor",
        emotional_tone="tense",
        character_count=2,
        time_of_day="night",
        weather="rain",
        overall_pacing="normal"
    )
    estimator.set_context(context)

    # 3. 测试动作数据（基于你的剧本）
    test_actions = [
        {
            "action_id": "act_1",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "type": "posture",
            "description": "裹着旧羊毛毯蜷在沙发里",
            "time_offset": 0.0,
            "duration": 10.0
        },
        {
            "action_id": "act_2",
            "actor": "手机",
            "target": "",
            "scene_ref": "",
            "type": "device_alert",
            "description": "突然震动，屏幕亮起显示'未知号码'",
            "time_offset": 10.0,
            "duration": 2.0
        },
        {
            "action_id": "act_3",
            "actor": "林然",
            "target": "手机",
            "scene_ref": "",
            "type": "gaze",
            "description": "盯着手机看了三秒，指尖悬停在接听键上方",
            "time_offset": 10.0,
            "duration": 3.0
        },
        {
            "action_id": "act_4",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "type": "physiological",
            "description": "喉头轻轻滚动",
            "time_offset": 13.0,
            "duration": 1.0
        },
        {
            "action_id": "act_5",
            "actor": "林然",
            "target": "手机",
            "scene_ref": "",
            "type": "interaction",
            "description": "按下接听键，将手机贴到耳边",
            "time_offset": 14.0,
            "duration": 1.0
        },
        {
            "action_id": "act_6",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "type": "gesture",
            "description": "手指瞬间收紧，指节泛白",
            "time_offset": 16.0,
            "duration": 2.0
        }
    ]

    # 4. 估算每个动作
    for i, action_data in enumerate(test_actions):
        print(f"\n{'=' * 60}")
        print(f"动作 {i + 1}: {action_data['description'][:40]}...")
        print(f"执行者: {action_data['actor']}, 类型: {action_data['type']}")
        print(f"原始估算: {action_data.get('duration', 'N/A')}秒")

        # 执行估算
        estimation = estimator.estimate(dict_to_dataclass(action_data, Action))

        # 显示结果
        print(f"\n规则估算结果:")
        print(f"  最终时长: {estimation.estimated_duration}秒")
        print(f"  置信度: {estimation.confidence}")
        print(f"  情感权重: {estimation.emotional_weight}")
        print(f"  视觉复杂度: {estimation.visual_complexity}")

        # 显示关键因素
        if estimation.key_factors:
            print(f"  关键因素: {', '.join(estimation.key_factors)}")

        # 显示状态变化
        if estimation.character_states:
            print(f"  角色状态变化: {estimation.character_states}")
        if estimation.prop_states:
            print(f"  道具状态变化: {estimation.prop_states}")

        # 显示调整原因
        if estimation.adjustment_reason:
            print(f"  调整原因: {estimation.adjustment_reason}")

    # 5. 批量估算演示
    print(f"\n{'=' * 60}")
    print("批量估算演示:")

    batch_results = estimator.batch_estimate(test_actions)

    print(f"批量处理 {len(batch_results)} 个动作:")
    total_duration = 0
    for action_id, est in batch_results.items():
        print(f"  {action_id}: {est.estimated_duration}秒 "
              f"(置信度: {est.confidence}, 原始: {est.original_duration}秒)")
        total_duration += est.estimated_duration

    print(f"\n总时长: {total_duration:.1f}秒")
    print(f"平均每个动作: {total_duration / len(batch_results):.1f}秒")

    # 6. 输出格式演示
    print(f"\n{'=' * 60}")
    print("输出格式演示（第一个动作的完整输出）:")

    first_estimation = batch_results["act_1"]
    estimation_dict = first_estimation.to_dict()

    print(f"元素ID: {estimation_dict['element_id']}")
    print(f"元素类型: {estimation_dict['element_type']}")
    print(f"规则估算: {estimation_dict['estimated_duration']}秒")
    print(f"规则基准: {estimation_dict['rule_based_estimate']}秒")
    print(f"原始时长: {estimation_dict['original_duration']}秒")
    print(f"置信度: {estimation_dict['confidence']}")

    print(f"\n数据结构验证:")
    print(f"  是否为 DurationEstimation 实例: {isinstance(first_estimation, DurationEstimation)}")
    print(f"  是否包含 rule_based_estimate 字段: {hasattr(first_estimation, 'rule_based_estimate')}")
    print(f"  是否包含 estimated_duration 字段: {hasattr(first_estimation, 'estimated_duration')}")

    return batch_results


def test_with_your_script():
    """使用你的剧本数据进行测试"""

    print("\n=== 使用你的剧本完整动作数据测试 ===\n")

    # 加载完整的动作数据
    your_actions = [
        {
            "action_id": "act_1",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "posture",
            "description": "裹着旧羊毛毯蜷在沙发里",
            "duration": 10.0
        },
        {
            "action_id": "act_2",
            "actor": "手机",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "device_alert",
            "description": "突然震动，屏幕亮起显示'未知号码'",
            "duration": 2.0
        },
        {
            "action_id": "act_3",
            "actor": "林然",
            "type": "gaze",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "description": "盯着手机看了三秒，指尖悬停在接听键上方",
            "duration": 3.0
        },
        {
            "action_id": "act_4",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "physiological",
            "description": "喉头轻轻滚动",
            "duration": 1.0
        },
        {
            "action_id": "act_5",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "interaction",
            "description": "按下接听键，将手机贴到耳边",
            "duration": 1.0
        },
        {
            "action_id": "act_6",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "gesture",
            "description": "手指瞬间收紧，指节泛白",
            "duration": 2.0
        },
        {
            "action_id": "act_7",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "physiological",
            "description": "呼吸停滞了一瞬",
            "duration": 1.0
        },
        {
            "action_id": "act_8",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "posture",
            "description": "猛地坐直身体",
            "duration": 1.0
        },
        {
            "action_id": "act_9",
            "actor": "林然",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "facial",
            "description": "瞳孔收缩，泪水在眼眶中打转",
            "duration": 1.0
        },
        {
            "action_id": "act_10",
            "actor": "旧羊毛毯",
            "target": "",
            "scene_ref": "",
            "time_offset": 0.0,
            "type": "prop_fall",
            "description": "从林然肩头滑落",
            "duration": 1.0
        }
    ]

    # 初始化估算器
    estimator = RuleActionDurationEstimator()

    # 设置上下文
    context = EstimationContext(
        emotional_tone="tense",
        time_of_day="night",
        weather="rain"
    )
    estimator.set_context(context)

    # 批量估算
    results = estimator.batch_estimate(batch_dict_to_dataclass(your_actions, Action))

    # 分析结果
    print(f"动作数量: {len(results)}")

    # 统计信息
    total_original = sum(action["duration"] for action in your_actions)
    total_estimated = sum(est.estimated_duration for est in results.values())
    avg_confidence = sum(est.confidence for est in results.values()) / len(results)

    print(f"\n统计信息:")
    print(f"  原始总时长: {total_original}秒")
    print(f"  估算总时长: {total_estimated:.1f}秒")
    print(f"  差异: {total_estimated - total_original:.1f}秒 "
          f"({((total_estimated - total_original) / total_original * 100):.1f}%)")
    print(f"  平均置信度: {avg_confidence:.2f}")

    # 显示每个动作的详细对比
    print(f"\n详细对比:")
    print(f"{'动作ID':<10} {'原始时长':<10} {'估算时长':<10} {'差异':<10} {'置信度':<10} {'关键因素'}")
    print("-" * 70)

    for action_id, estimation in results.items():
        original = next((a["duration"] for a in your_actions if a["action_id"] == action_id), 0)
        difference = estimation.estimated_duration - original
        factors = ", ".join(estimation.key_factors[:2]) if estimation.key_factors else "无"

        print(f"{action_id:<10} {original:<10.1f} {estimation.estimated_duration:<10.1f} "
              f"{difference:<10.1f} {estimation.confidence:<10.2f} {factors}")

    return results
