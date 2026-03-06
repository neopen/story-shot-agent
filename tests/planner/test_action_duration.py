"""
@FileName: action_duration_example_improved.py
@Description: 动作时长估算和分镜切分示例
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10/24 14:21
"""
from hengshot.hengline.tools.action_duration_tool import ActionDurationEstimatorTool
from typing import List, Dict, Any
import json


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