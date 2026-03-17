"""
@FileName: langchain_memory_test.py
@Description: 测试LangChainMemoryTool的功能
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/11
"""
import time

from penshot.neopen.tools.langchain_memory_tool import LangChainMemoryTool


def test_langchain_memory():
    """
    测试LangChainMemoryTool的基本功能
    """
    try:
        # 初始化LangChainMemoryTool
        memory_tool = LangChainMemoryTool()
        print("\n=== LangChainMemoryTool 初始化完成 ===")
        print(f"运行模式: {'内存模式' if memory_tool.use_memory_mode else '向量存储模式'}")
        if memory_tool.use_memory_mode:
            print("注意: 当前使用内存模式进行测试，无需API密钥和外部依赖")
        else:
            print("注意: 当前使用向量存储模式，需要相关依赖和配置")
        
        # 测试状态存储
        print("\n=== 测试状态存储功能 ===")
        
        # 创建三个测试状态
        state1 = {
            "action": "站立",
            "emotion": "平静",
            "position": {"x": 100, "y": 200, "z": 0},
            "timestamp": time.time()  # 添加时间戳
        }
        
        state2 = {
            "action": "行走", 
            "emotion": "愉悦",
            "position": {"x": 110, "y": 210, "z": 0},
            "timestamp": time.time()
        }
        
        state3 = {
            "action": "坐下",
            "emotion": "放松",
            "position": {"x": 120, "y": 220, "z": 0},
            "timestamp": time.time()
        }
        
        # 存储状态
        result1 = memory_tool.store_state(state1, context="在花园中")
        result2 = memory_tool.store_state(state2, context="走向长椅")
        result3 = memory_tool.store_state(state3, context="坐在长椅上休息")
        
        print(f"状态1存储: {'成功' if result1 else '失败'}")
        print(f"状态2存储: {'成功' if result2 else '失败'}")
        print(f"状态3存储: {'成功' if result3 else '失败'}")
        
        # 测试相似状态检索
        print("\n=== 测试相似状态检索功能 ===")
        
        # 检索与站立相关的状态
        standing_results = memory_tool.retrieve_similar_states("站立", k=2)
        print(f"\n查询'站立'相关状态 ({len(standing_results)}个):")
        for i, result in enumerate(standing_results):
            # 截断显示内容
            content = result['content'][:100] + '...' if len(result['content']) > 100 else result['content']
            metadata = result.get('metadata', {})
            print(f"  结果{i+1}:\n    内容: {content}\n    元数据: {metadata}")
        
        # 检索与情绪相关的状态
        emotion_results = memory_tool.retrieve_similar_states("愉悦")
        print(f"\n查询'愉悦'相关状态 ({len(emotion_results)}个):")
        for i, result in enumerate(emotion_results):
            content = result['content'][:100] + '...' if len(result['content']) > 100 else result['content']
            print(f"  结果{i+1}: {content}")
        
        # 测试状态转换建议
        print("\n=== 测试状态转换建议功能 ===")
        
        # 从站立状态获取转换建议
        transition_suggestions = memory_tool.get_state_transition_suggestions(state1)
        print(f"\n从'站立'状态转换建议 ({len(transition_suggestions)}个):")
        for i, suggestion in enumerate(transition_suggestions[:3]):  # 只显示前3个
            state = suggestion['state']
            score = suggestion.get('score', 0)
            print(f"  建议{i+1} (分数: {score:.2f}):")
            print(f"    动作: {state.get('action')}")
            print(f"    情绪: {state.get('emotion')}")
        
        # 测试持久化记忆
        print("\n=== 测试记忆持久化功能 ===")
        persist_result = memory_tool.persist_memory()
        print(f"记忆持久化: {'成功' if persist_result else '失败'}")
        
        # 测试清空记忆
        print("\n=== 测试清空记忆功能 ===")
        clear_result = memory_tool.clear_memory()
        print(f"记忆清空: {'成功' if clear_result else '失败'}")
        
        # 验证清空效果
        after_clear_results = memory_tool.retrieve_similar_states("站立")
        print(f"清空后检索结果数量: {len(after_clear_results)}")
        
        print("\n=== 测试完成 ===")
        return True
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        print("\n注意: 请确保配置正确，特别是在使用向量存储模式时需要相关依赖")
        return False


if __name__ == "__main__":
    test_langchain_memory()