"""
@FileName: test_hybrid_estimator.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/15 19:10
"""
import json

from penshot.neopen.agent.script_parser2.script_parser_models import UnifiedScript
from penshot.neopen.agent.shot_generator_bak.estimator.estimator_factory import estimator_factory
from penshot.neopen.agent.shot_generator_bak.hybrid_temporal_planner import HybridTemporalPlanner
from penshot.neopen.client.client_factory import get_default_llm
from penshot.utils.obj_utils import dict_to_dataclass

"""
更新使用示例
"""


def test_demonstrate_refactored_planners():
    """演示重构后的时序规划器"""

    print("=== 重构时序规划器演示 ===\n")

    # 加载剧本数据
    with open("script_parser_result.json", "r", encoding="utf-8") as f:
        script_data_str = json.load(f)

    print(f"加载剧本数据: {len(script_data_str.get('scenes', []))}场景, "
          f"{len(script_data_str.get('dialogues', []))}对话, "
          f"{len(script_data_str.get('actions', []))}动作\n")

    # 1. 使用工厂方法创建规划器
    # 2. 使用工厂方法估算
    print("2. 使用工厂方法估算:")
    llm = get_default_llm()

    script_data = dict_to_dataclass(script_data_str, UnifiedScript)

    # LLM估算
    print("   LLM估算...")
    llm_estimations = estimator_factory.estimate_script_with_llm(llm, script_data)
    print(f"   完成: {len(llm_estimations)} 个元素")

    # 规则估算
    print("   规则估算...")
    rule_estimations = estimator_factory.estimate_script_with_rules(script_data)
    print(f"   完成: {len(rule_estimations)} 个元素")

    # 混合估算
    print("   混合估算...")
    hybrid_estimations = HybridTemporalPlanner(llm).plan_timeline(script_data)
    print(f"   完成: {len(hybrid_estimations)} 个元素\n")

    # 3. 对比结果
    print("3. 结果对比:")

    # 检查合并规则是否正确应用
    test_elements = list(hybrid_estimations.keys())[:3]

    for element_id in test_elements:
        hybrid_est = hybrid_estimations.get(element_id)
        llm_est = llm_estimations.get(element_id)
        rule_est = rule_estimations.get(element_id)

        if hybrid_est and llm_est and rule_est:
            print(f"  {element_id}:")
            print(f"    LLM: {llm_est.estimated_duration:.2f}s (置信度: {llm_est.confidence:.2f})")
            print(f"    规则: {rule_est.estimated_duration:.2f}s (置信度: {rule_est.confidence:.2f})")
            print(f"    混合: {hybrid_est.estimated_duration:.2f}s (来源: {hybrid_est.source.value})")

            # 检查合并规则
            if hybrid_est.llm_estimation and hybrid_est.rule_estimation:
                print(f"    合并方式: LLM {hybrid_est.llm_estimation:.2f}s + "
                      f"规则 {hybrid_est.rule_estimation:.2f}s")
            elif hybrid_est.llm_estimation:
                print("    合并方式: 使用LLM值（规则为0）")
            elif hybrid_est.rule_estimation:
                print("    合并方式: 使用规则值（LLM为0）")
            print()
