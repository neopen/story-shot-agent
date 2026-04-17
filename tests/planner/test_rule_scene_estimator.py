"""
@FileName: test_temporal_scene_planner.py
@Description: 演示使用YAML配置的场景估算器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/13 16:12
"""
from penshot.neopen.agent.script_parser2.script_parser_models import Scene
from penshot.neopen.agent.shot_generator_bak.estimator.rule_base_estimator import EstimationContext
from penshot.neopen.agent.shot_generator_bak.estimator.rule_scene_estimator import RuleSceneDurationEstimator
from penshot.neopen.config.keyword_config import get_keyword_config
from penshot.neopen.config.temporal_planner_config import get_planner_config
from penshot.utils.obj_utils import dict_to_obj


def demonstrate_yaml_config():
    """演示YAML配置的场景估算器"""

    print("=== YAML配置的场景时长估算器演示 ===\n")

    # 1. 初始化配置管理器
    config_manager = get_planner_config()

    # 2. 初始化估算器
    estimator = RuleSceneDurationEstimator()

    # 3. 测试数据
    test_scenes = [
        {
            "scene_id": "scene_1",
            "location": "城市公寓客厅",
            "time_of_day": "夜晚",
            "weather": "大雨滂沱",
            "mood": "孤独紧张",
            "description": "深夜，窗外雨势猛烈。客厅昏暗，电视播放着无声的黑白老电影，光影在墙上晃动。林然蜷缩在沙发上，裹着旧羊毛毯，茶几上放着半杯凉茶和一本摊开的旧相册。气氛静谧而压抑。",
            "key_visuals": [
                "电视静音播放黑白电影",
                "凝出水雾的玻璃杯",
                "摊开的旧相册",
                "亮起的手机屏幕",
                "滑落的羊毛毯"
            ],
            "duration": 60.0
        }
    ]

    # 4. 设置上下文
    context = EstimationContext(
        scene_type="indoor",
        emotional_tone="tense",
        character_count=2,
        time_of_day="night",
        weather="rain",
        overall_pacing="normal"
    )
    estimator.set_context(context)

    # 5. 估算场景
    scene_data = test_scenes[0]
    print(f"场景: {scene_data['location']}")
    print(f"氛围: {scene_data['mood']}")
    print(f"时间: {scene_data['time_of_day']}, 天气: {scene_data['weather']}")
    print(f"原始估算: {scene_data['duration']}秒")
    print()

    estimation = estimator.estimate(dict_to_obj(scene_data, Scene))

    # 显示结果
    print(f"规则估算结果:")
    print(f"  最终时长: {estimation.estimated_duration}秒")
    print(f"  置信度: {estimation.confidence}")
    # print(f"  时长范围: {estimation.min_duration}-{estimation.max_duration}秒")
    print()

    # 显示调整因子
    print("应用的调整因子:")
    for factor, value in estimation.visual_hints.items():
        change = "增加" if value > 1.0 else "减少"
        percent = abs(value - 1.0) * 100
        print(f"  - {factor}: {value:.2f} ({change}{percent:.0f}%)")

    # 显示时长分解
    if estimation.reasoning_breakdown:
        print("\n时长分解:")
        total = sum(estimation.reasoning_breakdown.values())
        for component, duration in estimation.reasoning_breakdown.items():
            percent = (duration / total * 100) if total > 0 else 0
            print(f"  - {component}: {duration:.1f}秒 ({percent:.1f}%)")

    # 显示应用的规则
    print(f"\n应用的规则: {', '.join(estimation.rule_based_estimate[:5])}")

    return estimation


def test_config_loading():
    """测试配置加载"""
    print("\n=== 测试配置加载 ===\n")

    config_manager = get_planner_config()
    keyword_config = get_keyword_config()

    # 测试获取各种配置
    print("1. 基础配置:")
    print(f"   最小置信度: {config_manager.get_base_config('min_confidence')}")
    print(f"   最大置信度: {config_manager.get_base_config('max_confidence')}")

    print("\n2. 场景配置:")
    scene_config = config_manager.scene_estimator
    print(f"   场景类型数量: {len(scene_config.get('scene_type_baselines', {}))}")
    print(f"   氛围调整类型: {len(scene_config.get('mood_adjustments', {}))}")

    print("\n3. 关键词配置:")
    keywords = keyword_config.get_scene_keywords().get("scene_type")
    print(f"   场景类型关键词: {list(keywords.keys())}")

    print("\n4. 获取特定值:")
    value = config_manager.get_value("scene_estimator.config.min_scene_duration")
    print(f"   最小场景时长: {value}")

    print("\n配置加载测试完成!")



if __name__ == "__main__":
    # 演示YAML配置的场景估算器
    demonstrate_yaml_config()

    # 测试配置加载
    test_config_loading()

