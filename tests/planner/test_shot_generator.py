"""
@FileName: test_shot_generator.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/17 23:22
"""

from penshot.neopen.agent.script_parser2.script_parser_models import UnifiedScript
from penshot.neopen.agent.shot_generator_bak.shot.shot_generator_manager import ShotGenerationManager
from penshot.utils.file_utils import save_to_json, load_from_obj


def test_example_usage():
    """使用示例"""

    # 1. 创建结构化脚本（模拟您已解析的数据）
    script = load_from_obj("script_parser_result.json", UnifiedScript)
    # 2. 创建生成管理器
    manager = ShotGenerationManager()

    # 3. 生成分镜头（混合模式）
    script_result = manager.generate_for_script(script)

    # 4. 输出结果
    print(f"剧本分镜生成完成")
    print(f"总镜头数: {script_result.total_shots}")
    print(f"总时长: {script_result.total_duration}秒")
    print(f"角色出场时间:")
    for char, time in script_result.global_character_screen_time.items():
        print(f"  {char}: {time:.1f}秒")

    print("\n场景分镜详情:")
    for scene_id, scene_result in script_result.scene_results.items():
        print(f"\n场景 {scene_id}: {scene_result.shot_count}镜头，{scene_result.total_duration}秒")
        for shot in scene_result.shots[:3]:  # 显示前3个镜头
            print(f"  {shot.sequence_number}. [{shot.shot_type.value}] {shot.description[:40]}...")

    # 5. 转换为JSON保存
    result_dict = script_result.to_dict()
    # 保存为JSON
    save_to_json(script_result, "timeline_shot_output")
    print(f"\nJSON格式已生成，包含{len(result_dict['scene_results'])}个场景的分镜")
