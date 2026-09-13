"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: test_task_factory.py
@Description: 
@Author: NeoPen
@Time: 2026/3/24 12:19
"""
import asyncio

from penshot.neopen.task.task_factory import create_task_factory


# ==================== 使用示例 ====================
async def example_usage():
    """使用示例"""

    # 1. 创建工厂
    factory = create_task_factory(max_concurrent=5)

    # 2. 同步提交并等待结果
    print("=== 同步提交示例 ===")
    result = factory.submit_and_wait(
        script="一个男孩在公园里放风筝，天空很蓝...",
        timeout=60
    )
    print(f"任务结果: {result.success}, 状态: {result.status}")
    if result.data:
        shots = result.data.get("shots", [])
        print(f"生成镜头数: {len(shots)}")

    # 3. 异步提交
    print("\n=== 异步提交示例 ===")
    task_id = factory.submit(
        script="一个女孩在咖啡馆读书...",
        callback=lambda r: print(f"回调: 任务完成 - {r.task_id}")
    )
    print(f"任务已提交: {task_id}")

    # 4. 查询状态
    status = factory.get_status(task_id)
    print(f"任务状态: {status.status if status else 'unknown'}")

    # 5. 等待结果
    result = factory.wait_for_result(task_id)
    print(f"最终结果: {result.success}")

    # 6. 批量处理
    print("\n=== 批量处理示例 ===")
    scripts = [
        "场景1: 海边日出...",
        "场景2: 城市夜景...",
        "场景3: 森林探险..."
    ]
    results = factory.batch(scripts, timeout=120)
    for i, r in enumerate(results):
        print(f"任务{i + 1}: 成功={r.success}")

    # 7. 异步批量处理
    print("\n=== 异步批量处理示例 ===")
    async_results = await factory.batch_async(scripts, max_concurrent=2)
    for i, r in enumerate(async_results):
        print(f"任务{i + 1}: 成功={r.success}")

    # 8. 查看队列状态
    queue_status = factory.get_queue_status()
    print(f"\n队列状态: {queue_status}")

    # 9. 查看统计
    stats = factory.get_stats()
    print(f"统计信息: {stats}")

    # 10. 关闭工厂
    await factory.shutdown(wait_for_completion=True)


# 同步版本（不需要 asyncio）
def example_sync_usage():
    """同步使用示例（不需要asyncio）"""

    factory = create_task_factory(max_concurrent=5)

    # 提交任务并等待
    result = factory.submit_and_wait(
        script="测试剧本内容...",
        timeout=60
    )

    if result.success:
        print("任务成功！")
        print(f"数据: {result.data}")
    else:
        print(f"任务失败: {result.error}")

    # 批量处理
    results = factory.batch(["剧本1", "剧本2", "剧本3"])

    # 查看队列状态
    print(f"队列状态: {factory.get_queue_status()}")


if __name__ == "__main__":
    # 运行异步示例
    asyncio.run(example_usage())
