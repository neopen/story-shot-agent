"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: action_duration_example_improved.py
@Description: 动作时长估算和分镜切分示例
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10/24 14:21
"""
from penshot.neopen.tools.action_duration_tool import ActionDurationEstimatorTool
from types import SimpleNamespace
from typing import Any, Dict, List
import json

import penshot.neopen.agent.shot_segmenter.estimator.estimator_factory as estimator_factory_module
import penshot.neopen.agent.workflow.workflow_nodes as workflow_nodes_module
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.estimator_factory import (
    DurationEstimatorFactory,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
    ShotType,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes


def extract_verbs_from_script(script: str) -> List[Dict[str, Any]]:
    """
    从剧本中提取动词和动作
    
    Args:
        script: 剧本文本
        
    Returns:
        提取的动作列表，包含角色、动作、情绪和对话
    """
    # 示例剧本解析
    # 实际应用中应该使用更复杂的NLP解析
    sample_actions = [
        {
            "character": "小明",
            "action": "走进房间",
            "emotion": "平静"
        },
        {
            "character": "小明",
            "action": "环顾四周",
            "emotion": "好奇"
        },
        {
            "character": "小明",
            "action": "坐在沙发上",
            "emotion": "放松"
        },
        {
            "character": "小明",
            "action": "拿起手机",
            "emotion": "平静"
        },
        {
            "character": "小明",
            "action": "查看消息",
            "emotion": "惊讶",
            "dialogue": "哇，太棒了！"
        },
        {
            "character": "小明",
            "action": "站起来",
            "emotion": "激动"
        },
        {
            "character": "小明",
            "action": "来回踱步",
            "emotion": "兴奋"
        },
        {
            "character": "小明",
            "action": "拿起外套",
            "emotion": "急切"
        },
        {
            "character": "小明",
            "action": "走向门口",
            "emotion": "期待"
        },
        {
            "character": "小明",
            "action": "打开门",
            "emotion": "兴奋"
        },
        {
            "character": "小明",
            "action": "离开房间",
            "emotion": "喜悦"
        }
    ]
    return sample_actions


def split_into_segments(actions: List[Dict[str, Any]], estimator: ActionDurationEstimatorTool, target_duration: float = 5.0, max_deviation: float = 0.5) -> List[Dict[str, Any]]:
    """
    将动作列表切分为5秒粒度的分段
    
    Args:
        actions: 动作列表
        estimator: 动作时长估算器
        target_duration: 目标分段时长
        max_deviation: 最大时长偏差
        
    Returns:
        分段列表
    """
    segments = []
    current_segment = {
        "id": 1,
        "actions": [],
        "est_duration": 0.0,
        "scene_id": 0
    }
    
    for action in actions:
        # 估算动作时长
        action_text = action["action"]
        emotion = action.get("emotion", "")
        character_type = "default"  # 可以根据角色类型调整
        
        duration = estimator.estimate(action_text, emotion=emotion, character_type=character_type)
        
        # 如果有对话，额外估算对话时长
        if "dialogue" in action:
            dialogue_duration = estimator.estimate(f"说：'{action['dialogue']}'", emotion=emotion)
            duration = max(duration, dialogue_duration)
        
        # 记录动作时长
        action["estimated_duration"] = duration
        
        # 检查是否需要分段
        if current_segment["est_duration"] + duration > target_duration + max_deviation:
            # 保存当前分段
            segments.append(current_segment)
            
            # 开始新分段
            current_segment = {
                "id": len(segments) + 1,
                "actions": [],
                "est_duration": 0.0,
                "scene_id": 0
            }
        
        # 添加动作到当前分段
        current_segment["actions"].append(action)
        current_segment["est_duration"] += duration
    
    # 添加最后一个分段
    if current_segment["actions"]:
        segments.append(current_segment)
    
    return segments


def generate_storyboard_segments(script: str, min_shots: int = 5, max_shots: int = 6) -> List[Dict[str, Any]]:
    """
    生成分镜分段，确保分段数量在指定范围内
    
    Args:
        script: 剧本文本
        min_shots: 最小分镜数量
        max_shots: 最大分镜数量
        
    Returns:
        优化后的分段列表
    """
    # 初始化估算器
    estimator = ActionDurationEstimatorTool()
    estimator.clear_cache()
    
    # 提取动作
    actions = extract_verbs_from_script(script)
    print(f"从剧本中提取了 {len(actions)} 个动作")
    
    # 第一次切分
    segments = split_into_segments(actions, estimator)
    print(f"第一次切分生成了 {len(segments)} 个分段")
    
    # 如果分段数量少于最小值，尝试更细粒度的切分
    if len(segments) < min_shots:
        print(f"分段数量不足，尝试更细粒度切分...")
        # 可以通过调整目标时长来增加分段数量
        adjusted_target = 5.0 * len(segments) / min_shots
        segments = split_into_segments(actions, estimator, target_duration=adjusted_target)
        print(f"调整后生成了 {len(segments)} 个分段")
    
    # 如果分段数量仍然不足，可以尝试将长动作拆分为多个短动作
    if len(segments) < min_shots:
        print("尝试将长动作拆分为多个短动作...")
        # 这里是简化的实现，实际应用中需要更智能的动作拆分
        expanded_actions = []
        for action in actions:
            # 检查动作是否可能较长
            if any(long_verb in action["action"] for long_verb in ["走", "移动", "等待", "思考"]):
                # 拆分为开始和结束两个动作
                expanded_actions.append({**action, "action": f"开始{action['action']}"})
                expanded_actions.append({**action, "action": f"继续{action['action']}"})
            else:
                expanded_actions.append(action)
        
        # 重新切分
        segments = split_into_segments(expanded_actions, estimator)
        print(f"动作拆分后生成了 {len(segments)} 个分段")
    
    # 确保分段数量不超过最大值
    if len(segments) > max_shots:
        print(f"分段数量过多，尝试合并部分分段...")
        # 简单的合并策略：从后往前合并
        while len(segments) > max_shots and len(segments) >= 2:
            # 合并最后两个分段
            last_segment = segments.pop()
            segments[-1]["actions"].extend(last_segment["actions"])
            segments[-1]["est_duration"] += last_segment["est_duration"]
        
        print(f"合并后生成了 {len(segments)} 个分段")
    
    return segments


if __name__ == '__main__':
    # 示例剧本
    sample_script = """
    小明走进房间，环顾四周，然后坐在沙发上。他拿起手机查看消息，表情变得惊讶。
    "哇，太棒了！"他兴奋地说道。
    他站起来来回踱步，显得非常激动。随后他拿起外套，走向门口，打开门离开了房间。
    """
    
    print("=== 动作时长估算和分镜切分示例 ===")
    
    # 初始化估算器（单例推荐）
    estimator = ActionDurationEstimatorTool()
    estimator.clear_cache()
    
    # 演示基础用法
    print("\n--- 基础动作时长估算 ---")
    actions = [
        "缓缓走向窗边",
        "轻声说：'你好。'",
        "快速转身",
        "惊讶地看着",
        "坐下并思考"
    ]
    
    for action in actions:
        duration = estimator.estimate(action)
        print(f"动作: '{action}' → 估算时长: {duration}秒")
    
    # 演示带有情绪的动作时长估算
    print("\n--- 带情绪的动作时长估算 ---")
    emotion_actions = [
        ("说：'我不敢相信！'", "惊讶"),
        ("走过去", "紧张"),
        ("坐下", "放松"),
        ("等待", "焦虑")
    ]
    
    for action, emotion in emotion_actions:
        duration = estimator.estimate(action, emotion=emotion)
        print(f"动作: '{action}' (情绪: {emotion}) → 估算时长: {duration}秒")
    
    # 演示分镜切分
    print("\n--- 分镜切分演示 ---")
    segments = generate_storyboard_segments(sample_script, min_shots=5, max_shots=6)
    
    print(f"\n最终生成了 {len(segments)} 个分镜：")
    for i, segment in enumerate(segments, 1):
        print(f"\n分镜 {i}: 估计时长 = {segment['est_duration']:.2f}秒")
        print(f"包含 {len(segment['actions'])} 个动作：")
        for action in segment['actions']:
            action_text = action['action']
            duration = action.get('estimated_duration', 'N/A')
            character = action['character']
            emotion = action.get('emotion', '无')
            dialogue = action.get('dialogue', '')
            
            action_desc = f"  - {character}({emotion}): {action_text}"
            if dialogue:
                action_desc += f" '{dialogue}'"
            action_desc += f" [{duration}秒]"
            
            print(action_desc)
    
    # 生成最终的分镜JSON输出
    storyboard_output = {
        "title": "示例剧本分镜",
        "total_shots": len(segments),
        "segments": segments
    }
    
    print("\n--- 分镜JSON输出 ---")
    print(json.dumps(storyboard_output, ensure_ascii=False, indent=2))
    
    print("\n=== 演示完成 ===")


# ==================== 0.4.5 T-007：estimator 接入与总时长统计 ====================


def _make_sequence(descriptions: List[str]) -> ShotSequence:
    """按描述构造中等景别镜头序列"""
    return ShotSequence(
        shots=[
            ShotInfo(
                id=f"shot_{index:03d}",
                scene_id="scene_001",
                description=text,
                shot_type=ShotType.MEDIUM_SHOT,
            )
            for index, text in enumerate(descriptions, start=1)
        ]
    )


def _capture_warnings(monkeypatch) -> List[str]:
    """替换 estimator_factory 的 warning，收集告警文案"""
    messages: List[str] = []
    monkeypatch.setattr(estimator_factory_module, "warning", messages.append)
    return messages


def test_estimate_sequence_uses_action_nodes_duration(monkeypatch):
    """有描述时使用动作节点公式，元素估算只进报告不改写时长"""
    _capture_warnings(monkeypatch)
    sequence = _make_sequence(["她低头，随后抬头。"])

    result = DurationEstimatorFactory.estimate_sequence(sequence, ParsedScript())

    assert result.shots[0].duration == 2.7  # 1.5 + 0.6 * 2
    assert result.stats["duration_source"] == "action_nodes"
    assert result.stats["element_duration"] > 0
    assert result.stats["target_duration"] is None
    assert result.stats["duration_delta"] is None


def test_estimate_sequence_total_equals_shot_sum(monkeypatch):
    """总时长等于全部镜头时长之和"""
    _capture_warnings(monkeypatch)
    sequence = _make_sequence(
        ["她低头，随后抬头。", "窗外的雨渐渐停了。", "他转身离开。"]
    )

    result = DurationEstimatorFactory.estimate_sequence(sequence, ParsedScript())

    assert [shot.duration for shot in result.shots] == [2.7, 2.5, 2.5]
    assert result.stats["total_duration"] == round(
        sum(shot.duration for shot in result.shots), 2
    )
    assert result.stats["total_duration"] == 7.7


def test_no_target_duration_has_no_shortage_warning(monkeypatch):
    """未声明目标时长时不产生“总时长不足”告警"""
    messages = _capture_warnings(monkeypatch)
    sequence = _make_sequence(["她低头，随后抬头。"])

    DurationEstimatorFactory.estimate_sequence(sequence, ParsedScript())

    assert not any("总时长不足" in message for message in messages)


def test_target_duration_records_delta_and_warning(monkeypatch):
    """显式目标时长记录差值，差额为正时给出“总时长不足”告警"""
    messages = _capture_warnings(monkeypatch)
    sequence = _make_sequence(["她低头，随后抬头。"])
    script = ParsedScript(metadata={"target_duration": 10.0})

    result = DurationEstimatorFactory.estimate_sequence(sequence, script)

    assert result.stats["target_duration"] == 10.0
    assert result.stats["duration_delta"] == 7.3
    assert any("总时长不足" in message and "7.3" in message for message in messages)


def test_blank_description_falls_back_to_element_estimator(monkeypatch):
    """缺少描述时回退到元素估算器，并标记来源"""
    messages = _capture_warnings(monkeypatch)
    sequence = _make_sequence(["   "])

    result = DurationEstimatorFactory.estimate_sequence(sequence, ParsedScript())

    shot = result.shots[0]
    assert shot.duration >= 2.0
    assert result.stats["duration_source"] == "fallback_estimator"
    assert result.stats["element_duration"] == shot.duration
    assert any("缺少描述" in message for message in messages)


def test_invalid_target_duration_is_ignored(monkeypatch):
    """非法目标时长被忽略并告警，不写负数差值"""
    messages = _capture_warnings(monkeypatch)
    sequence = _make_sequence(["她低头，随后抬头。"])
    script = ParsedScript(metadata={"target_duration": "abc"})

    result = DurationEstimatorFactory.estimate_sequence(sequence, script)

    assert result.stats["target_duration"] is None
    assert result.stats["duration_delta"] is None
    assert any("非法目标时长" in message for message in messages)


# ==================== 0.4.5 T-008：总时长报告落盘 ====================


def _make_prompt_nodes(instructions: AIVideoInstructions) -> WorkflowNodes:
    """构造只打桩外部依赖的提示词节点"""
    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes._recall_patterns_by_anchors = lambda state: ([], {})
    nodes.workflow_memory = SimpleNamespace(
        get_memory_dict=lambda *args, **kwargs: {},
        get_memory_list=lambda *args, **kwargs: [],
        after_stage_completion=lambda *args, **kwargs: None,
    )
    nodes.prompt_converter = SimpleNamespace(
        apply_historical_context=lambda *args, **kwargs: None,
        apply_repair_params=lambda *args, **kwargs: None,
        process=lambda *args, **kwargs: instructions,
        detect_issues=lambda *args, **kwargs: [],
        clear_repair_params=lambda *args, **kwargs: None,
        clear_historical_context=lambda *args, **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)
    return nodes


def _make_prompt_state(
    fragment_durations: List[float], shot_stats: Dict[str, Any]
) -> WorkflowState:
    """构造含片段与镜头统计的最小状态"""
    state = WorkflowState.from_raw_script("剧本内容")
    state.domain.contract = None
    state.domain.shot_sequence = ShotSequence(
        shots=[
            ShotInfo(
                id="shot_001",
                scene_id="scene_001",
                description="她低头，随后抬头。",
            )
        ],
        stats=shot_stats,
    )
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[
            VideoFragment(
                id=f"frag_{index:03d}",
                shot_id="shot_001",
                duration=duration,
                description="她低头，随后抬头。",
            )
            for index, duration in enumerate(fragment_durations, start=1)
        ]
    )
    return state


def test_generate_prompts_writes_duration_report(monkeypatch):
    """节点把片段总时长与解析元素推算值写入 metadata.duration_report"""
    messages: List[str] = []
    monkeypatch.setattr(workflow_nodes_module, "warning", messages.append)

    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="a woman waits", duration=3.0)
        ]
    )
    nodes = _make_prompt_nodes(instructions)
    state = _make_prompt_state(
        [2.5, 3.0],
        {
            "total_duration": 5.0,
            "element_duration": 9.9,
            "target_duration": 12.0,
            "duration_delta": 7.0,
            "duration_source": "action_nodes",
        },
    )

    nodes.generate_prompts_node(state)

    assert instructions.metadata["duration_report"] == {
        "total_duration": 5.5,
        "shot_duration": 5.0,
        "element_duration": 9.9,
        "target_duration": 12.0,
        "duration_delta": 6.5,
        "delivery_deviation": 0.5,
        "duration_source": "action_nodes",
        "semantics": {
            "total_duration": "实际交付：片段时长求和（切片器按文本重算）",
            "shot_duration": "切分前的镜头计划总时长",
            "element_duration": "切分前的解析元素推算总时长",
            "target_duration": "剧本声明的目标总时长",
            "duration_delta": "目标总时长 - 实际交付总时长",
            "delivery_deviation": "实际交付总时长 - 镜头计划总时长",
        },
    }
    assert any("总时长不足" in message and "6.5" in message for message in messages)


def test_duration_report_without_target_has_no_shortage_warning(monkeypatch):
    """无目标时长时报告为 None，且不产生“总时长不足”告警"""
    messages: List[str] = []
    monkeypatch.setattr(workflow_nodes_module, "warning", messages.append)

    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="a woman waits", duration=3.0)
        ]
    )
    nodes = _make_prompt_nodes(instructions)
    state = _make_prompt_state(
        [2.5],
        {
            "total_duration": 2.5,
            "element_duration": 3.1,
            "target_duration": None,
            "duration_delta": None,
            "duration_source": "action_nodes",
        },
    )

    nodes.generate_prompts_node(state)

    report = instructions.metadata["duration_report"]
    assert report["total_duration"] == 2.5
    assert report["target_duration"] is None
    assert report["duration_delta"] is None
    assert not any("总时长不足" in message for message in messages)
