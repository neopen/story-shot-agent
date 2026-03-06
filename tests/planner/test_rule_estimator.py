"""
@FileName: test_temporal_scene_planner.py
@Description: 规则基础时序规划器演示
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/13 16:12
"""
import json

from hengshot.hengline.agent.script_parser2.script_parser_models import UnifiedScript
from hengshot.hengline.agent.shot_generator_bak.local_temporal_planner import LocalRuleTemporalPlanner
from hengshot.utils.obj_utils import dict_to_obj


def test_rule_based_planner():
    """演示规则基础时序规划器"""

    print("=== 规则基础时序规划器演示 ===\n")

    # 1. 准备测试数据（基于你提供的剧本）
    script_data = {
        "meta": {
            "schema_version": "1.1",
            "time_unit": "seconds",
            "source_type": "screenplay_snippet",
            "target_use": "text-to-video prompt generation"
        },
        "scenes": [
            {
                "scene_id": "scene_1",
                "order": 1,
                "location": "城市公寓客厅",
                "time_of_day": "夜晚",
                "time_exact": "23:00",
                "weather": "大雨滂沱",
                "mood": "孤独紧张",
                "summary": "林然深夜独处时接到一个神秘来电，情绪剧烈波动。",
                "description": "深夜，窗外雨势猛烈。客厅昏暗，电视播放着无声的黑白老电影，光影在墙上晃动。林然蜷缩在沙发上，裹着旧羊毛毯，茶几上放着半杯凉茶和一本摊开的旧相册。气氛静谧而压抑。",
                "key_visuals": [
                    "电视静音播放黑白电影",
                    "凝出水雾的玻璃杯",
                    "摊开的旧相册",
                    "亮起的手机屏幕",
                    "滑落的羊毛毯"
                ],
                "character_refs": ["林然", "陈默"],
                "start_time": 0.0,
                "end_time": 60.0,
                "duration": 60.0
            }
        ],
        "characters": [
            {
                "name": "林然",
                "gender": "女",
                "role": "主角",
                "appearance": "裹着旧羊毛毯，蜷坐在沙发上，神情警觉而脆弱",
                "personality": "敏感、内敛、情感丰富"
            },
            {
                "name": "陈默",
                "gender": "男",
                "role": "配角",
                "personality": "神秘、低沉、隐忍"
            }
        ],
        "dialogues": [
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
                "dialogue_id": "dial_4",
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
            }
        ],
        "actions": [
            {
                "action_id": "act_1",
                "scene_ref": "scene_1",
                "actor": "林然",
                "target": "",
                "type": "posture",
                "description": "裹着旧羊毛毯蜷在沙发里",
                "time_offset": 0.0,
                "duration": 10.0
            },
            {
                "action_id": "act_2",
                "scene_ref": "scene_1",
                "actor": "手机",
                "target": "",
                "type": "device_alert",
                "description": "突然震动，屏幕亮起显示‘未知号码’",
                "time_offset": 10.0,
                "duration": 2.0
            },
            {
                "action_id": "act_3",
                "scene_ref": "scene_1",
                "actor": "林然",
                "target": "手机",
                "type": "gaze",
                "description": "盯着手机看了三秒，指尖悬停在接听键上方",
                "time_offset": 10.0,
                "duration": 3.0
            },
            {
                "action_id": "act_5",
                "scene_ref": "scene_1",
                "actor": "林然",
                "target": "手机",
                "type": "interaction",
                "description": "按下接听键，将手机贴到耳边",
                "time_offset": 14.0,
                "duration": 1.0
            },
            {
                "action_id": "act_6",
                "scene_ref": "scene_1",
                "actor": "林然",
                "target": "",
                "type": "gesture",
                "description": "手指瞬间收紧，指节泛白",
                "time_offset": 16.0,
                "duration": 2.0
            },
            {
                "action_id": "act_8",
                "scene_ref": "scene_1",
                "actor": "林然",
                "target": "",
                "type": "posture",
                "description": "猛地坐直身体",
                "time_offset": 28.0,
                "duration": 1.0
            }
        ]
    }

    # 2. 创建统一剧本对象
    # unified_script = dict_to_obj(script_data)
    unified_script = UnifiedScript.model_validate_json(json.dumps(script_data))

    # 3. 初始化规划器
    planner = LocalRuleTemporalPlanner()

    # 4. 加载剧本
    planner.load_unified_script(unified_script)
    print("剧本加载完成")
    print(f"场景: {len(unified_script.scenes)}个")
    print(f"对话: {len(unified_script.dialogues)}个")
    print(f"动作: {len(unified_script.actions)}个")
    print()

    # 5. 创建时序规划
    print("创建时序规划...")
    timeline_plan = planner.plan_timeline(unified_script)

    # 6. 显示结果概览
    print(f"\n时序规划创建完成:")
    print(f"  总时长: {timeline_plan.total_duration:.1f}秒")
    print(f"  片段数量: {timeline_plan.segments_count}")
    print(f"  主导情感: {timeline_plan.dominant_emotion}")
    print(f"  视觉风格: {timeline_plan.global_visual_style}")
    print(f"  关键转折点: {len(timeline_plan.key_transition_points)}个")
    print()

    # 7. 显示片段详情
    print("片段详情:")
    for i, segment in enumerate(timeline_plan.timeline_segments[:3]):  # 只显示前3个
        print(f"  [{segment.segment_id}] {segment.time_range[0]:.1f}-{segment.time_range[1]:.1f}秒")
        print(f"    内容: {segment.visual_summary}")
        print(f"    元素: {len(segment.contained_elements)}个")
        if segment.shot_type_suggestion:
            print(f"    镜头建议: {segment.shot_type_suggestion}")
        print()

    # 8. 显示估算统计
    print("估算统计:")
    scene_count = sum(1 for est in timeline_plan.duration_estimations.values()
                      if est.element_type.value == "scene")
    dialogue_count = sum(1 for est in timeline_plan.duration_estimations.values()
                         if est.element_type.value == "dialogue")
    action_count = sum(1 for est in timeline_plan.duration_estimations.values()
                       if est.element_type.value == "action")

    print(f"  场景估算: {scene_count}个")
    print(f"  对话估算: {dialogue_count}个")
    print(f"  动作估算: {action_count}个")

    # 计算平均置信度
    if timeline_plan.duration_estimations:
        avg_confidence = sum(est.confidence for est in timeline_plan.duration_estimations.values()) / len(timeline_plan.duration_estimations)
        print(f"  平均置信度: {avg_confidence:.2f}")

    # 9. 显示节奏分析
    print(f"\n节奏分析:")
    pacing_stats = timeline_plan.pacing_analysis.statistics
    print(f"  平均强度: {pacing_stats.get('avg_intensity', 0):.2f}")
    print(f"  最大强度: {pacing_stats.get('max_intensity', 0):.2f}")
    print(f"  最小强度: {pacing_stats.get('min_intensity', 0):.2f}")

    # 显示建议
    recommendations = timeline_plan.pacing_analysis.recommendations
    if recommendations:
        print(f"  建议: {recommendations[0]}")

    # 10. 显示性能统计
    stats = planner.performance_stats
    print(f"\n性能统计:")
    print(f"  估算元素: {stats.get('estimated_elements', 0)}/{stats.get('total_elements', 0)}")
    print(f"  总耗时: {stats.get('estimation_time_seconds', 0):.2f}秒")
    print(f"  平均每个元素: {stats.get('avg_time_per_element', 0):.3f}秒")

    return timeline_plan


def test_compare_with_original():
    """与原始解析器估算比较"""
    print("\n=== 与原始解析器估算比较 ===\n")

    # 读取原始数据
    with open("script_parser_result.json", "r", encoding="utf-8") as f:
        script_data = json.load(f)

    # 计算原始总时长
    original_total = 0
    for scene in script_data["scenes"]:
        original_total += scene.get("duration", 0)

    print(f"原始解析器总时长: {original_total}秒")

    # 创建规划器并估算
    unified_script = dict_to_obj(script_data, UnifiedScript)
    # unified_script = UnifiedScript.model_validate_json(json.dumps(script_data))
    planner = LocalRuleTemporalPlanner()
    planner.load_unified_script(unified_script)

    # 只估算不创建完整规划
    estimations = planner.estimate_all_elements()

    # 计算规则估算总时长
    rule_based_total = sum(est.estimated_duration for est in estimations.values())

    print(f"规则估算总时长: {rule_based_total:.1f}秒")
    print(f"差异: {rule_based_total - original_total:.1f}秒 ({((rule_based_total - original_total) / original_total * 100):.1f}%)")

    # 显示主要差异
    print(f"\n主要元素差异:")

    # 场景差异
    for scene in script_data["scenes"]:
        scene_id = scene["scene_id"]
        if scene_id in estimations:
            est = estimations[scene_id]
            diff = est.estimated_duration - scene["duration"]
            if abs(diff) > 2.0:  # 只显示显著差异
                print(f"  {scene_id}: {scene['duration']}秒 → {est.estimated_duration:.1f}秒 ({diff:+.1f}秒)")

    # 对话差异
    for dialogue in script_data["dialogues"]:
        dialogue_id = dialogue["dialogue_id"]
        if dialogue_id in estimations:
            est = estimations[dialogue_id]
            diff = est.estimated_duration - dialogue["duration"]
            if abs(diff) > 0.5:  # 只显示显著差异
                print(f"  {dialogue_id}: {dialogue['duration']}秒 → {est.estimated_duration:.1f}秒 ({diff:+.1f}秒)")

    return estimations


if __name__ == "__main__":
    # 演示规则基础时序规划器
    timeline_plan = test_rule_based_planner()

    # 与原始解析器比较
    # compare_with_original()
