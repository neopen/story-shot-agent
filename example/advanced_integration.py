"""
@FileName: advanced_integration.py
@Description: 高级集成示例（结合其他功能）
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:47
"""
import asyncio
import json
from datetime import datetime
from typing import Dict

from example.direct_usage import basic_usage
from penshot.neopen import generate_storyboard


class StoryboardManager:
    """分镜管理器，提供更高级的功能"""

    def __init__(self, storage_path: str = "storyboards/"):
        self.storage_path = storage_path

    async def generate_and_save(self, script: str, project_name: str) -> Dict:
        """
        生成分镜并保存到文件
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = f"{project_name}_{timestamp}"

        # 生成分镜
        result = await generate_storyboard(
            script_text=script,
            task_id=task_id
        )

        # 保存结果
        filename = f"{self.storage_path}{task_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        result['saved_path'] = filename
        return result

    async def compare_versions(self, task_id1: str, task_id2: str):
        """
        比较两个版本的分镜结果
        """
        # 这里可以实现版本比较逻辑
        pass


# 使用示例
async def advanced_demo():
    manager = StoryboardManager(storage_path="./data/output/")

    script = """
    电影开场：
    1. 外景，城市夜景，高楼林立
    2. 内景，主角房间，台灯下看书
    3. 特写，时钟指向午夜12点
    """

    result = await manager.generate_and_save(
        script=script,
        project_name="my_movie"
    )

    print(f"分镜已保存到: {result['saved_path']}")
    return result


# 运行所有示例
if __name__ == "__main__":
    print("运行基础示例...")
    asyncio.run(basic_usage())

    print("\n运行高级示例...")
    asyncio.run(advanced_demo())
