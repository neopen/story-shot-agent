"""
@FileName: test_time_annotation.py
@Description: 测试动作时长估算器对时间标注的处理
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18
"""

from hengshot.hengline.agent.shot_generator.estimator.rule_action_estimator import RuleActionDurationEstimator


def test_time_annotations():
    """测试不同类型的时间标注处理"""
    # 使用正确的配置文件路径（中文）
    estimator = RuleActionDurationEstimator()
    
    test_cases = [
        # 动作中的时间标注
        ("盯着看了三秒", False, "平静", "default", 3.0),
        ("沉默两秒", False, "平静", "default", 2.0),
        ("等待五秒", False, "平静", "default", 5.0),
        ("停顿了10秒", False, "平静", "default", 10.0),
        ("思考了1分钟", False, "平静", "default", 60.0),
        
        # 对话中的时间标注
        ("说：'等一下'，沉默三秒", True, "平静", "default", 3.0),
        ("电话那头沉默两秒", True, "平静", "default", 2.0),
        ("思考片刻，说：'好的'（停顿4秒）", True, "平静", "default", 4.0),
        ("沉默了3秒后开口", True, "平静", "default", 3.0),
        
        # 没有时间标注的情况（应返回常规估算）
        ("说：'你好'", True, "平静", "default", 0.7),  # 2个字 × 0.35秒/字
        ("快速跑开", False, "平静", "default", 1.05),  # 跑(1.5) × 快速(0.7)
    ]
    
    print("测试时间标注处理功能...")
    print("=" * 60)
    
    for i, (text, is_dialogue, emotion, char_type, expected) in enumerate(test_cases):
        # 构建适合估算器的输入文本
        if is_dialogue:
            input_text = text
        else:
            input_text = text
        
        duration = estimator.estimate(input_text)
        
        # 检查结果
        passed = abs(duration - expected) < 0.1
        status = "✓ PASS" if passed else "✗ FAIL"
        
        print(f"测试 {i+1}: {status}")
        print(f"  输入: {input_text}")
        print(f"  预期: {expected:.2f}秒")
        print(f"  实际: {duration:.2f}秒")
        if not passed:
            print(f"  误差: {abs(duration - expected):.2f}秒")
        print()
    
    print("=" * 60)
    print("测试完成！")

if __name__ == "__main__":
    test_time_annotations()