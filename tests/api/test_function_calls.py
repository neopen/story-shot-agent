"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: test_function_calls.py
@Description: 
@Author: NeoPen
@Time: 2026/3/24 12:23
"""
from penshot.api import PenshotResult
from penshot.api.function_calls import create_penshot_agent

# ==================== 使用示例 ====================

if __name__ == '__main__':
    # 创建智能体
    agent = create_penshot_agent(max_concurrent=5)

    # 示例1: 同步调用
    print("=== 同步调用示例 ===")
    result = agent.breakdown_script(
        "一个男孩在公园里放风筝，天空很蓝...",
        wait_timeout=60
    )
    print(f"任务ID: {result.task_id}")
    print(f"成功: {result.success}")
    if result.data:
        shots = result.data.get("shots", [])
        print(f"镜头数: {len(shots)}")

    # 示例2: 异步调用
    print("\n=== 异步调用示例 ===")
    def on_complete(r: PenshotResult):
        print(f"回调: 任务 {r.task_id} 完成, 成功={r.success}")

    task_id = agent.breakdown_script_async(
        "一个女孩在咖啡馆读书...",
        callback=on_complete
    )
    print(f"任务已提交: {task_id}")

    # 示例3: 等待结果
    result = agent.wait_for_result(task_id)
    print(f"等待结果: 成功={result.success}")

    # 示例4: 批量处理
    print("\n=== 批量处理示例 ===")
    scripts = [
        "场景1: 海边日出...",
        "场景2: 城市夜景...",
        "场景3: 森林探险..."
    ]
    results = agent.batch_breakdown(scripts)
    for i, r in enumerate(results):
        print(f"任务{i+1}: 成功={r.success}")

    # 示例5: 查看队列状态
    queue_status = agent.get_queue_status()
    print(f"\n队列状态: {queue_status}")

    # 示例6: 查看统计
    stats = agent.get_stats()
    print(f"统计信息: {stats}")

    # 关闭
    agent.shutdown()