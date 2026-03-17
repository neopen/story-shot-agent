"""
@FileName: test_temporal_scene_planner.py
@Description: 对话估算器演示
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/13 16:12
"""
from penshot.neopen.agent.script_parser2.script_parser_models import Dialogue
from penshot.neopen.agent.shot_generator_bak.estimator.rule_base_estimator import EstimationContext
from penshot.neopen.agent.shot_generator_bak.estimator.rule_dialogue_estimator import RuleDialogueDurationEstimator
from penshot.utils.obj_utils import dict_to_obj, dict_to_dataclass


def test_demonstrate_dialogue_estimator():
    """演示对话时长估算器"""

    print("=== YAML配置的对话时长估算器演示 ===\n")

    # 1. 初始化配置管理器和估算器
    estimator = RuleDialogueDurationEstimator()

    # 2. 设置上下文
    context = EstimationContext(
        emotional_tone="tense",
        overall_pacing="normal"
    )
    estimator.set_context(context)

    # 3. 测试对话数据（基于你的剧本）
    test_dialogues = [
        {
            "dialogue_id": "dial_1",
            "scene_ref": "scene_1",
            "speaker": "林然",
            "content": "……陈默？你还好吗？",
            "target": "陈默",
            "emotion": "微颤",
            "voice_quality": "轻柔沙哑",
            "parenthetical": "声音微颤",
            "type": "speech",
            "time_offset": 18.0,
            "duration": 4.0
        },
        {
            "dialogue_id": "dial_2",
            "scene_ref": "scene_1",
            "speaker": "陈默",
            "content": "我回来了。",
            "target": "林然",
            "emotion": "低声",
            "voice_quality": "沙哑",
            "parenthetical": "",
            "type": "speech",
            "time_offset": 25.0,
            "duration": 3.0
        },
        {
            "dialogue_id": "dial_3",
            "scene_ref": "scene_1",
            "speaker": "林然",
            "content": "",
            "target": "",
            "emotion": "哽咽",
            "voice_quality": "",
            "parenthetical": "张了张嘴，却发不出声音",
            "type": "silence",
            "time_offset": 30.0,
            "duration": 3.0
        },
        {
            "dialogue_id": "dial_4",
            "scene_ref": "scene_1",
            "speaker": "路人甲",
            "content": "你好！今天天气真不错，你最近怎么样？工作还顺利吗？",
            "target": "",
            "emotion": "喜悦",
            "voice_quality": "明亮",
            "parenthetical": "热情地说",
            "type": "speech",
            "duration": 5.0
        }
    ]

    # 4. 估算每个对话
    for i, dialogue_data in enumerate(test_dialogues):
        print(f"\n{'=' * 50}")
        print(f"对话 {i + 1}: ID={dialogue_data['dialogue_id']}")
        print(f"说话者: {dialogue_data['speaker']}")
        print(f"内容: '{dialogue_data['content'][:30]}...'")
        print(f"情感: {dialogue_data['emotion']}")
        print(f"原始估算: {dialogue_data.get('duration', 'N/A')}秒")

        # 执行估算
        estimation = estimator.estimate(dict_to_dataclass(dialogue_data, Dialogue))

        # 显示结果
        print(f"\n规则估算结果:")
        print(f"  最终时长: {estimation.estimated_duration}秒")
        print(f"  置信度: {estimation.confidence}")
        print(f"  元素类型: {estimation.element_type.value}")
        print(f"  情感权重: {estimation.emotional_weight}")
        print(f"  视觉复杂度: {estimation.visual_complexity}")

        # 显示关键因素
        if estimation.key_factors:
            print(f"  关键因素: {', '.join(estimation.key_factors[:3])}")

        # 显示调整原因
        if estimation.adjustment_reason:
            print(f"  调整原因: {estimation.adjustment_reason}")

    # 5. 批量估算演示
    print(f"\n{'=' * 50}")
    print("批量估算演示:")

    batch_results = estimator.batch_estimate(test_dialogues)

    print(f"批量处理 {len(batch_results)} 个对话:")
    for dialogue_id, est in batch_results.items():
        print(f"  {dialogue_id}: {est.estimated_duration}秒 ({est.element_type.value}, 置信度: {est.confidence})")

    # 6. 不同类型对话对比
    print(f"\n{'=' * 50}")
    print("不同类型对话对比:")

    test_cases = [
        ("简短回应", {"content": "好", "emotion": "平静"}),
        ("情感对话", {"content": "我爱你", "emotion": "激动", "parenthetical": "深情地说"}),
        ("疑问句", {"content": "你真的这么想吗？", "emotion": "疑惑"}),
        ("长句", {"content": "在这个寂静的夜晚，我独自思考着人生的意义和未来的方向。", "emotion": "思考"})
    ]

    for case_name, dialogue_data in test_cases:
        test_data = {
            "dialogue_id": f"test_{case_name}",
            "duration": 0,
            "speaker": "测试角色",
            "content": dialogue_data["content"],
            "emotion": dialogue_data.get("emotion", "平静"),
            "parenthetical": dialogue_data.get("parenthetical", "")
        }

        estimation = estimator.estimate(dict_to_obj(test_data, Dialogue))
        print(f"\n{case_name}:")
        print(f"  内容: '{dialogue_data['content'][:20]}...'")
        print(f"  估算时长: {estimation.estimated_duration}秒")
        print(f"  主要调整: {estimation.adjustment_reason[:30]}...")

    return batch_results


def test_with_your_script_dialogues():
    """使用你的剧本对话数据测试"""

    print("\n=== 使用你的剧本对话数据测试 ===\n")

    # 你的剧本对话数据
    your_dialogues = [
        {
            "dialogue_id": "dial_1",
            "speaker": "林然",
            "content": "……陈默？你还好吗？",
            "emotion": "微颤",
            "parenthetical": "声音微颤",
            "type": "speech",
            "duration": 4.0
        },
        {
            "dialogue_id": "dial_2",
            "speaker": "陈默",
            "content": "我回来了。",
            "emotion": "低声",
            "parenthetical": "",
            "type": "speech",
            "duration": 3.0
        }
    ]

    # 初始化估算器
    estimator = RuleDialogueDurationEstimator()

    # 估算对话
    for dialogue_data in your_dialogues:
        print(f"\n对话: {dialogue_data['dialogue_id']}")
        print(f"说话者: {dialogue_data['speaker']}")
        print(f"内容: '{dialogue_data['content']}'")
        print(f"情感: {dialogue_data['emotion']}")
        print(f"原始解析器估算: {dialogue_data['duration']}秒")

        estimation = estimator.estimate(dict_to_obj(dialogue_data, Dialogue))

        print(f"规则估算结果: {estimation.estimated_duration}秒")
        print(f"置信度: {estimation.confidence}")
        print(f"差异: {estimation.estimated_duration - dialogue_data['duration']:.1f}秒 "
              f"({((estimation.estimated_duration - dialogue_data['duration']) / dialogue_data['duration'] * 100):.1f}%)")

        # 显示详细分析
        print(f"详细分析:")
        print(f"  情感权重: {estimation.emotional_weight}")
        print(f"  视觉复杂度: {estimation.visual_complexity}")

        if estimation.key_factors:
            print(f"  关键因素: {', '.join(estimation.key_factors)}")

        if estimation.visual_hints:
            print(f"  镜头建议: {estimation.visual_hints.get('suggested_shot_types', [])}")
