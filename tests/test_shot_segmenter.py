"""
@FileName: test_shot_splitter.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 22:11
"""
import logging

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.script_parser_models import BaseElement, SceneInfo, CharacterInfo, ParsedScript
from penshot.neopen.agent.shot_segmenter.rule_shot_segmenter import RuleShotSegmenter


# 使用示例
def main():
    # 初始化日志
    logging.basicConfig(level=logging.INFO)

    # 创建测试剧本（使用之前解析的结果）
    parsed_script = ParsedScript(
        title="深夜对话",
        characters=[
            CharacterInfo(name="张三", gender="男", role="主角", description="中年男性"),
            CharacterInfo(name="李四", gender="女", role="主角", description="年轻女性")
        ],
        scenes=[
            SceneInfo(
                id="scene_001",
                location="客厅",
                description="昏暗的客厅",
                time_of_day="night",
                elements=[
                    BaseElement(
                        id="elem_001",
                        type=ElementType.ACTION,
                        sequence=1,
                        content="张三紧张地环顾四周",
                        character="张三",
                        duration=3.0
                    ),
                    BaseElement(
                        id="elem_002",
                        type=ElementType.DIALOGUE,
                        sequence=2,
                        content="你听到了吗？",
                        character="张三",
                        duration=2.0
                    )
                ]
            )
        ],
        stats={
            "total_elements": 2,
            "total_duration": 5.0
        }
    )

    # 使用规则拆分器（MVP推荐）
    print("=== 使用规则拆分器 ===")
    rule_splitter = RuleShotSegmenter()
    rule_sequence = rule_splitter.split(parsed_script)

    print(f"生成镜头数: {len(rule_sequence.shots)}")
    for shot in rule_sequence.shots:
        print(f"  {shot.id}: {shot.description} ({shot.shot_type}, {shot.duration}秒)")

    print(f"\n统计数据: {rule_sequence.stats}")

    # 转换为JSON输出
    print("\n=== JSON输出示例 ===")
    json_output = rule_sequence.model_dump_json(indent=2)
    print(json_output[:500] + "...")  # 只显示前500字符


if __name__ == "__main__":
    main()
