"""
@FileName: direct_usage.py
@Description: 作为Python库直接使用
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/2/10 19:46
"""
import asyncio

from pydantic import SecretStr

from penshot import ShotLanguage, ShotConfig
from penshot.api import PenshotFunction
from penshot.config import EmbeddingBaseConfig, LLMBaseConfig


async def basic_usage():
    """基础用法示例"""
    print("=== 基础用法示例 ===")

    # 创建智能体实例（可配置并发数）
    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)

    script = """
    场景：现代办公室
    时间：下午3点
    人物：小李（程序员）
    动作：小李正在写代码，突然接到电话，表情惊讶
    """

    # 同步调用（等待完成）
    result = agent.breakdown_script(script, script_id="ddd123456")

    print(f"任务ID: {result.task_id}")
    print(f"成功: {result.success}, 状态: {result.status}")
    print(result)

    if result.success:
        data = result.data or {}
        instructions = data.get("instructions", {})
        shots = instructions.get("fragments", [])
        project_info = instructions.get("project_info", {})

        print(f"镜头数量: {project_info.get('total_fragments', len(shots))}")
        print(f"总时长: {project_info.get('total_duration', 0):.1f}秒")

        # 显示前3个镜头
        for i, shot in enumerate(shots[:3], 1):
            print(f" 片段提示词 {i}: {shot.get('prompt')[:50]}...")

    return result


async def async_usage():
    """异步用法示例"""
    print("\n=== 异步用法示例 ===")

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)

    script = """
    早晨，一个女孩在咖啡馆读书，阳光透过窗户...
    """

    # 异步提交任务
    task_id = agent.breakdown_script_async(
        script,
        callback=lambda r: print(f"回调: 任务 {r.task_id} 完成")
    )

    print(f"任务已提交: {task_id}")

    # 查询状态
    status = agent.get_task_status(task_id)
    print(f"初始状态: {status.get('status')}")

    # 等待结果
    result = await agent.wait_for_result_async(task_id)

    print(f"最终结果: 成功={result.success}, 状态={result.status}")
    print(f"result={result}")

    return result


async def batch_processing():
    """批量处理示例"""
    print("\n=== 批量处理示例 ===")

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)

    scripts = [
        "一个男人在海边跑步，日出时分...",
        "两个孩子在游乐场玩耍，欢声笑语...",
        "老人在公园下棋，专注沉思..."
    ]

    # 同步批量处理
    results = agent.batch_breakdown(scripts)

    for i, result in enumerate(results, 1):
        if result.success:
            data = result.data or {}
            shots = data.get("instructions", [])
            print(f"任务 {i}: 成功, {len(shots)}个镜头")
        else:
            print(f"任务 {i}: 失败 - {result.error}")

    return results


async def async_batch_processing():
    """异步批量处理示例"""
    print("\n=== 异步批量处理示例 ===")

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)

    scripts = [
        "科幻场景：太空站内部，宇航员发现异常信号...",
        "古装场景：侠客在竹林中对决...",
        "动画场景：小动物在森林里探险..."
    ]

    # 异步批量处理
    results = await agent.batch_breakdown_async(scripts, max_concurrent=2)

    for i, result in enumerate(results, 1):
        if result.success:
            data = result.data or {}
            stats = data.get("stats", {})
            print(f"任务 {i}: 成功, {stats.get('shot_count', 0)}个镜头, {result.processing_time_ms}ms")
        else:
            print(f"任务 {i}: 失败 - {result.error}")

    return results


async def with_custom_config():
    """使用自定义配置"""
    print("\n=== 自定义配置示例 ===")

    # 创建自定义配置
    custom_config = ShotConfig(
        llm=LLMBaseConfig(
            base_url="https://api.deepseek.com",
            model_name="gpt-4",
            api_key=SecretStr("xxxxxxxxxxxx"),
            temperature=0.3,
            timeout=60,
            max_tokens=3000
        ),
        embed=EmbeddingBaseConfig(
            base_url="http://localhost:11434",
            model_name="text-embedding-3-small",
            api_key=SecretStr("xxxxxxxxxxx"),
            timeout=60,
        ),
        max_fragment_duration=10,
        video_model="sora-2-2025-12-08",
    )

    agent = PenshotFunction(
        config=custom_config,
        language=ShotLanguage.ZH,
        max_concurrent=5
    )

    script = "科幻场景：太空站内部，宇航员发现异常信号..."

    result = agent.breakdown_script(script)

    print(f"使用自定义配置: 成功={result.success}")

    return result


async def with_queue_control():
    """队列控制示例"""
    print("\n=== 队列控制示例 ===")

    # 创建低并发数的智能体
    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=2)

    # 查看队列状态
    queue_status = agent.get_queue_status()
    print(f"初始队列状态: {queue_status}")

    # 提交多个任务
    scripts = ["剧本1", "剧本2", "剧本3", "剧本4", "剧本5"]
    task_ids = []

    for script in scripts:
        task_id = agent.breakdown_script_async(script)
        task_ids.append(task_id)
        print(f"提交任务: {task_id}")

    # 查看队列状态
    queue_status = agent.get_queue_status()
    print(f"提交后队列状态: {queue_status}")

    # 等待所有任务完成
    results = []
    for task_id in task_ids:
        result = agent.wait_for_result(task_id)
        results.append(result)

    # 查看统计信息
    stats = agent.get_stats()
    print(f"处理统计: {stats}")

    return results


def main():
    """主函数演示各种用法"""

    # 基本用法（同步）
    result = asyncio.run(basic_usage())

    # 异步用法
    async_result = asyncio.run(async_usage())

    # 批量处理
    batch_results = asyncio.run(batch_processing())

    # 异步批量处理
    async_batch_results = asyncio.run(async_batch_processing())

    # 自定义配置
    custom_result = asyncio.run(with_custom_config())

    # 队列控制
    queue_results = asyncio.run(with_queue_control())


if __name__ == "__main__":

    # main()
    asyncio.run(basic_usage())