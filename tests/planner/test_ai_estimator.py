"""
@FileName: test_ai_estimator.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/14 21:13
"""
from hengshot.hengline.agent.script_parser2.script_parser_models import UnifiedScript
from hengshot.hengline.agent.shot_generator_bak.estimator.ai_action_estimator import AIActionDurationEstimator
from hengshot.hengline.agent.shot_generator_bak.estimator.ai_dialogue_estimator import AIDialogueDurationEstimator
from hengshot.hengline.agent.shot_generator_bak.estimator.ai_scene_estimator import AISceneDurationEstimator
from hengshot.hengline.agent.shot_generator_bak.estimator.estimator_factory import estimator_factory
from hengshot.hengline.agent.shot_generator_bak.llm_temporal_planner import LLMTemporalPlanner
from hengshot.hengline.agent.temporal_planner.temporal_planner_model import ElementType
from hengshot.hengline.prompts.temporal_planner_prompt import PromptConfig
from hengshot.utils.obj_utils import dict_to_dataclass


def demonstrate_complete_system():
    """演示完整的系统"""

    print("=== AI时序规划系统演示 ===\n")

    # 1. 创建配置
    config = PromptConfig(
        enable_enhanced_analysis=True,
        include_visual_suggestions=True,
        include_continuity_hints=True
    )

    # 2. 创建测试数据
    test_script = {
        "scenes": [
            {
                "scene_id": "scene_1",
                "location": "城市公寓客厅",
                "time_of_day": "夜晚",
                "mood": "孤独紧张",
                "description": "深夜，窗外雨势猛烈。客厅昏暗，电视播放着无声的黑白老电影，光影在墙上晃动。林然蜷缩在沙发上，裹着旧羊毛毯，茶几上放着半杯凉茶和一本摊开的旧相册。气氛静谧而压抑。",
                "key_visuals": ["电视静音播放黑白电影", "凝出水雾的玻璃杯", "摊开的旧相册", "亮起的手机屏幕", "滑落的羊毛毯"]
            }
        ],
        "dialogues": [
            {
                "dialogue_id": "dial_1",
                "speaker": "林然",
                "content": "……陈默？你还好吗？",
                "emotion": "微颤",
                "voice_quality": "轻柔沙哑",
                "parenthetical": "声音微颤",
                "type": "speech"
            },
            {
                "dialogue_id": "dial_4",
                "speaker": "林然",
                "content": "",
                "emotion": "哽咽",
                "parenthetical": "张了张嘴，却发不出声音",
                "type": "silence"
            }
        ],
        "actions": [
            {
                "action_id": "act_3",
                "actor": "林然",
                "type": "gaze",
                "description": "盯着手机看了三秒，指尖悬停在接听键上方",
                "target": "手机"
            },
            {
                "action_id": "act_5",
                "actor": "林然",
                "type": "interaction",
                "description": "按下接听键，将手机贴到耳边",
                "target": "手机"
            }
        ]
    }

    # 3. 使用工厂类直接估算
    print("1. 使用工厂类直接估算元素:")

    script_data: UnifiedScript = dict_to_dataclass(test_script, UnifiedScript)

    # 估算场景
    scene_estimator = estimator_factory.get_llm_estimator(ElementType.SCENE, config)
    scene_result = scene_estimator.estimate(script_data.scenes[0])
    print(f"   场景时长: {scene_result.estimated_duration}秒 (置信度: {scene_result.confidence})")

    # 估算对话
    dialogue_estimator = estimator_factory.get_llm_estimator(ElementType.DIALOGUE, config)
    dialogue_result = dialogue_estimator.estimate(script_data.dialogues[0])
    print(f"   对话时长: {dialogue_result.estimated_duration}秒 (置信度: {dialogue_result.confidence})")

    # 估算动作
    action_estimator = estimator_factory.get_llm_estimator(ElementType.ACTION, config)
    action_result = action_estimator.estimate(script_data.actions[0])
    print(f"   动作时长: {action_result.estimated_duration}秒 (置信度: {action_result.confidence})")

    # 4. 使用工厂类估算整个剧本
    print("\n2. 估算整个剧本:")
    all_estimations = estimator_factory.estimate_script_with_llm(script_data)
    print(f"   总估算元素数: {len(all_estimations)}")

    # 显示估算结果摘要
    total_duration = sum(est.estimated_duration for est in all_estimations.values())
    avg_confidence = sum(est.confidence for est in all_estimations.values()) / len(all_estimations)
    print(f"   总估算时长: {total_duration:.1f}秒")
    print(f"   平均置信度: {avg_confidence:.2f}")

    # 5. 使用主规划器创建完整计划
    print("\n3. 创建完整时序规划:")
    planner = LLMTemporalPlanner()

    try:
        timeline_plan = planner.plan_timeline(script_data)

        print(f"   生成片段数: {timeline_plan.segments_count}")
        print(f"   总时长: {timeline_plan.total_duration:.1f}秒")
        print(f"   连续性锚点数: {len(timeline_plan.continuity_anchors)}")

        # 显示第一个片段
        if timeline_plan["segments"]:
            first_segment = timeline_plan.segments[0]
            print(f"\n   第一个片段: {first_segment['segment_id']}")
            print(f"   包含元素数: {len(first_segment['elements'])}")
            print(f"   时间范围: {first_segment['time_range'][0]:.1f}-{first_segment['time_range'][1]:.1f}秒")

    except Exception as e:
        print(f"   创建计划时出错: {str(e)}")

    # 6. 错误统计
    print("\n4. 错误统计:")
    error_summary = estimator_factory.get_error_summary()
    print(f"   总估算器数: {error_summary['total_estimators']}")
    print(f"   有错误的估算器: {error_summary['estimators_with_errors']}")

    if error_summary['estimators_with_errors'] > 0:
        for error_info in error_summary['errors_by_estimator']:
            print(f"     - {error_info['element_type']}: {error_info['total_errors']}个错误")

    # 7. 显示详细的估算结果
    print("\n5. 详细估算结果:")
    for element_id, estimation in list(all_estimations.items())[:3]:  # 显示前3个
        print(f"\n   [{estimation.element_type.value.upper()}] {element_id}")
        print(f"     时长: {estimation.estimated_duration}秒")
        print(f"     置信度: {estimation.confidence}")
        print(f"     关键因素: {', '.join(estimation.key_factors[:2])}")

        if estimation.visual_hints and "suggested_shot_types" in estimation.visual_hints:
            shots = estimation.visual_hints["suggested_shot_types"]
            if shots:
                print(f"     建议镜头: {shots[0]}")

    print("\n=== 演示完成 ===")


def demonstrate_individual_estimators():
    """演示各个估算器的独立使用"""

    print("\n=== 各估算器独立使用演示 ===\n")

    config = PromptConfig()

    # 创建各个估算器
    scene_estimator = AISceneDurationEstimator(config)
    dialogue_estimator = AIDialogueDurationEstimator(config)
    action_estimator = AIActionDurationEstimator(config)

    # 测试数据
    test_elements = {
        "scene": {
            "scene_id": "test_scene",
            "description": "简单的室内场景",
            "location": "客厅",
            "mood": "平静"
        },
        "dialogue": {
            "dialogue_id": "test_dialogue",
            "speaker": "测试角色",
            "content": "你好，世界！",
            "emotion": "平静"
        },
        "action": {
            "action_id": "test_action",
            "actor": "测试角色",
            "description": "简单的动作",
            "type": "gesture"
        }
    }

    # 分别估算
    print("分别估算不同类型元素:")

    scene_result = scene_estimator.estimate(test_elements["scene"])
    print(f"  场景: {scene_result.estimated_duration}秒")

    dialogue_result = dialogue_estimator.estimate(test_elements["dialogue"])
    print(f"  对话: {dialogue_result.estimated_duration}秒")

    action_result = action_estimator.estimate(test_elements["action"])
    print(f"  动作: {action_result.estimated_duration}秒")

    print("\n所有估算器均返回 DurationEstimation 对象")
    print(f"  场景对象类型: {type(scene_result).__name__}")
    print(f"  包含字段: {', '.join([f.name for f in scene_result.__dataclass_fields__.values()][:5])}...")


if __name__ == "__main__":
    demonstrate_complete_system()
    demonstrate_individual_estimators()
