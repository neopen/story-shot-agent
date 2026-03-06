
from hengshot.utils.file_utils import load_from_obj, save_to_json


def _call_llm(self, prompt: str) -> str:
    """
    调用LLM API的完整实现
    实际使用时需要替换为真实的API调用
    """
    # 这里模拟API调用，实际应使用真实的API
    print(f"[AI Estimator] 调用 {self.config.model_name.value} 模型")
    print(f"[提示词长度] {len(prompt)} 字符")

    # 根据提示词内容生成不同的模拟响应
    return self._generate_mock_response(prompt)


def _generate_mock_response(self, prompt: str) -> str:
    """生成模拟响应（更复杂的模拟逻辑）"""
    # 根据提示词内容判断元素类型
    if "场景时长估算" in prompt:
        return self._mock_scene_response(prompt)
    elif "对话时长估算" in prompt and "沉默" not in prompt:
        return self._mock_dialogue_response(prompt)
    elif "沉默时长估算" in prompt:
        return self._mock_silence_response(prompt)
    elif "动作时长估算" in prompt:
        return self._mock_action_response(prompt)
    elif "批量场景时长估算" in prompt:
        return self._mock_batch_scene_response(prompt)
    elif "批量对话时长估算" in prompt:
        return self._mock_batch_dialogue_response(prompt)
    elif "批量动作时长估算" in prompt:
        return self._mock_batch_action_response(prompt)
    else:
        return """{
               "estimated_duration": 2.0,
               "confidence": 0.7,
               "reasoning_breakdown": {"default": 2.0},
               "visual_hints": {"suggested_shot_types": ["medium_shot"]}
           }"""


def _mock_scene_response(self, prompt: str) -> str:
    """模拟场景响应"""
    return """{
           "estimated_duration": 8.5,
           "confidence": 0.85,
           "reasoning_breakdown": {
               "establishing_shot": 2.5,
               "mood_setting": 3.0,
               "detail_reveal": 2.0,
               "pacing_buffer": 1.0
           },
           "visual_hints": {
               "suggested_shot_types": ["slow_pan", "close_up_details", "atmosphere_shot"],
               "lighting_notes": "low_key_lighting with rim_light from TV",
               "focus_transitions": ["雨窗→电视光→角色面部→茶几细节"],
               "color_palette": "冷色调，蓝色和灰色为主"
           },
           "duration_breakdown": {
               "雨窗镜头": 1.2,
               "电视光影": 1.8,
               "林然蜷坐": 2.5,
               "茶几细节": 1.5,
               "氛围沉浸": 1.5
           },
           "key_factors": ["高情绪价值", "多视觉细节", "氛围建立重要", "孤独感传递"],
           "pacing_notes": "需要缓慢节奏建立孤独感，每个视觉元素要有足够展示时间",
           "continuity_requirements": ["光线方向一致", "雨势连贯", "角色姿势自然"],
           "shot_suggestions": ["开场用雨窗特写建立氛围", "缓慢摇到角色", "茶几细节特写过渡"]
       }"""


def _mock_dialogue_response(self, prompt: str) -> str:
    """模拟对话响应"""
    return """{
           "estimated_duration": 3.2,
           "confidence": 0.9,
           "reasoning_breakdown": {
               "words_delivery": 1.8,
               "emotional_pause": 1.0,
               "reaction_time": 0.4
           },
           "speech_characteristics": {
               "pace": "slow_emotional",
               "intonation": "rising_then_falling",
               "breath_pattern": "hesitant",
               "emphasis_points": ["陈默", "还好吗"]
           },
           "visual_hints": {
               "reaction_shot_needed": true,
               "focus_on": "micro_expressions",
               "suggested_angle": "medium_close_up",
               "eye_line_direction": "slightly_down",
               "lighting_change": "slight_brightening_on_face"
           },
           "duration_breakdown": {
               "前导停顿": 0.3,
               "说出名字": 0.8,
               "疑问语气": 1.1,
               "情绪延留": 1.0
           },
           "emotional_trajectory": [
               {"time": 0.0, "emotion": "apprehensive", "intensity": 7},
               {"time": 0.8, "emotion": "concerned", "intensity": 8},
               {"time": 2.0, "emotion": "vulnerable", "intensity": 9}
           ],
           "key_factors": ["情感密度高", "角色关系关键", "微表情重要"],
           "pacing_notes": "需要给观众时间理解角色关系的重量"
       }"""


def _mock_silence_response(self, prompt: str) -> str:
    """模拟沉默响应"""
    return """{
           "estimated_duration": 3.5,
           "confidence": 0.88,
           "reasoning_breakdown": {
               "shock_absorption": 1.5,
               "emotional_processing": 1.2,
               "visual_reaction": 0.8
           },
           "silence_type": "emotional_shock",
           "visual_hints": {
               "suggested_shot_types": ["extreme_close_up", "slow_zoom_out"],
               "focus_elements": ["eyes", "trembling_lips", "hands"],
               "time_stretching_technique": "slow_motion_micro_expressions"
           },
           "duration_breakdown": {
               "信息冲击": 1.0,
               "情感涌现": 1.2,
               "试图回应": 0.8,
               "放弃说话": 0.5
           },
           "emotional_trajectory": [
               {"time": 0.0, "emotion": "shocked", "intensity": 9},
               {"time": 1.5, "emotion": "overwhelmed", "intensity": 10},
               {"time": 2.5, "emotion": "resigned", "intensity": 8}
           ],
           "key_factors": ["戏剧高潮点", "非语言表演重要", "观众共鸣时刻"],
           "pacing_notes": "沉默时间要足够让观众感受到角色的内心冲击",
           "continuity_requirements": ["面部表情连贯演变", "身体语言渐进变化"]
       }"""


def _mock_action_response(self, prompt: str) -> str:
    """模拟动作响应"""
    return """{
           "estimated_duration": 3.5,
           "confidence": 0.8,
           "reasoning_breakdown": {
               "decision_moment": 1.2,
               "physical_action": 0.8,
               "emotional_weight": 1.5
           },
           "action_components": [
               {"component": "gaze_fixation", "duration": 1.0, "visual_focus": "screen_reflection_in_eyes"},
               {"component": "hesitation_moment", "duration": 0.8, "keyframe": "finger_trembling"},
               {"component": "decision_click", "duration": 0.4, "sound_cue": "subtle_click"},
               {"component": "phone_to_ear", "duration": 0.6, "movement_arc": "slow_deliberate"},
               {"component": "listening_posture", "duration": 0.7, "body_tension": "increased"}
           ],
           "visual_hints": {
               "keyframe_suggestions": ["悬停手指特写", "面部紧张特写", "接听动作中景"],
               "movement_pacing": "slow_deliberate",
               "camera_movement": "slight_push_in_on_face",
               "focus_rack": "from_finger_to_face"
           },
           "duration_breakdown": {
               "察觉震动": 0.3,
               "目光转移": 0.7,
               "识别来电": 0.8,
               "决策过程": 1.2,
               "执行动作": 0.5
           },
           "key_factors": ["决策时刻", "情感转折点", "精细动作"],
           "pacing_notes": "动作要慢到能看清决策的挣扎，但不要拖沓",
           "continuity_requirements": ["手部位置连贯", "视线方向自然", "身体姿势流畅"]
       }"""


def _mock_batch_scene_response(self, prompt: str) -> str:
    """模拟批量场景响应"""
    return """{
           "results": [
               {
                   "scene_id": "scene_1",
                   "estimated_duration": 8.5,
                   "confidence": 0.85,
                   "pacing_category": "slow",
                   "key_visual_emphasis": ["雨窗", "电视光", "蜷坐姿势"]
               }
           ],
           "comparison_notes": "这是开篇场景，需要较长时间建立氛围和情绪",
           "pacing_arc": "从缓慢建立逐渐加速",
           "visual_continuity": ["雨的元素贯穿", "冷暖色调对比", "封闭空间感"]
       }"""


def _mock_batch_dialogue_response(self, prompt: str) -> str:
    """模拟批量对话响应"""
    return """{
           "results": [
               {
                   "dialogue_id": "dial_1",
                   "estimated_duration": 3.2,
                   "confidence": 0.9,
                   "pacing_category": "medium_slow",
                   "emotional_weight": "high"
               },
               {
                   "dialogue_id": "dial_2", 
                   "estimated_duration": 2.8,
                   "confidence": 0.85,
                   "pacing_category": "medium",
                   "emotional_weight": "medium"
               },
               {
                   "dialogue_id": "dial_3",
                   "estimated_duration": 1.5,
                   "confidence": 0.9,
                   "pacing_category": "medium",
                   "emotional_weight": "high"
               }
           ],
           "comparison_notes": "对话节奏逐渐加快，情感强度有起伏",
           "conversation_flow": "从试探到确认再到情感冲击",
           "silence_distribution": "对话间应有自然停顿"
       }"""


def _mock_batch_action_response(self, prompt: str) -> str:
    """模拟批量动作响应"""
    return """{
           "results": [
               {
                   "action_id": "act_1",
                   "estimated_duration": 10.0,
                   "confidence": 0.8,
                   "pacing_category": "very_slow",
                   "action_complexity": "static_posture"
               },
               {
                   "action_id": "act_2",
                   "estimated_duration": 2.0,
                   "confidence": 0.9,
                   "pacing_category": "fast",
                   "action_complexity": "device_alert"
               },
               {
                   "action_id": "act_3",
                   "estimated_duration": 3.0,
                   "confidence": 0.85,
                   "pacing_category": "medium_slow",
                   "action_complexity": "gaze_with_decision"
               }
           ],
           "comparison_notes": "动作从静态到突然变化，再到缓慢决策",
           "movement_progression": "静止→突发→凝视→行动",
           "tension_build": "通过动作节奏变化构建紧张感"
       }"""


def test_main():
    # 初始化智能体
    # planner = TemporalPlannerAgent(get_default_llm())
    planner = TemporalPlannerAgent(None)

    # 加载数据
    script_data = load_from_obj("script_parser_result.json", UnifiedScript)

    # 创建时间线规划
    timeline_plan = planner.plan_process(
        script_data, True
    )

    # 输出结果
    print("\n" + "=" * 50)
    print("时间线规划结果")
    print("=" * 50)

    for segment in timeline_plan.timeline_segments:
        print(f"\n{segment.segment_id}: {segment.time_range}")
        print(f"  内容: {segment.visual_content}")
        print(f"  元素: {segment.element_coverage}")

    print(f"\n节奏类型: {timeline_plan.pacing_analysis.pace_type}")
    print(f"连贯性锚点: {len(timeline_plan.continuity_anchors)}个")

    # 验证结果
    if timeline_plan.validation_report.get("is_valid"):
        print("\n规划验证通过！")
    else:
        print(f"\n规划存在问题: {timeline_plan.validation_report['critical_issues']}个关键问题")

    # 保存为JSON
    save_to_json(timeline_plan, "timeline_plan_output")

    print("\n结果已保存到 timeline_plan_output.json")
