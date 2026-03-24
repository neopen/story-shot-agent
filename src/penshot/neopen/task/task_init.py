"""
@FileName: task_init.py
@Description: 任务初始化
@Author: HiPeng
@Time: 2026/3/24 21:48
"""
from penshot.logger import info
from penshot.neopen.task.task_factory import TaskFactory, create_task_factory

# 使用 TaskFactory 替代原始的 TaskManager + TaskProcessor
task_factory: TaskFactory = None


def init_task_factory(max_concurrent: int = 10, queue_size: int = 1000):
    """初始化任务工厂（在应用启动时调用）"""
    global task_factory
    task_factory = create_task_factory(
        max_concurrent=max_concurrent,
        queue_size=queue_size
    )


def get_task_factory() -> TaskFactory:
    """获取任务工厂实例"""
    if task_factory is None:
        init_task_factory()
    return task_factory


# ============================================================================
# 应用启动/关闭钩子
# ============================================================================

async def startup_event():
    """应用启动时执行"""
    init_task_factory(max_concurrent=10, queue_size=1000)

    factory = get_task_factory()

    # 恢复未完成的任务（只恢复两小时内的）
    factory.recover_pending_tasks(max_age_hours=2)

    # 显示当前队列状态
    queue_status = factory.get_queue_status()
    info(f"队列状态: 队列长度={queue_status['queue_length']}, 活跃任务={queue_status['active_tasks']}")

    info("REST API 服务器启动完成")


async def startup_with_recovery():
    """带任务恢复的启动流程"""

    # 1. 初始化任务工厂
    init_task_factory(max_concurrent=10, queue_size=1000)
    factory = get_task_factory()

    # 2. 获取未完成的任务
    pending_tasks = factory.get_pending_tasks()

    if pending_tasks:
        info(f"发现 {len(pending_tasks)} 个未完成的任务")

        # 3. 显示任务信息
        for task in pending_tasks:
            info(f"  任务: {task.get('task_id')}, 状态: {task.get('status')}, 阶段: {task.get('stage')}")

        # 4. 恢复任务
        factory.recover_pending_tasks(max_age_hours=2)

    info("服务启动完成，队列状态:")
    info(f"  队列长度: {factory.get_queue_status()['queue_length']}")
    info(f"  活跃任务: {factory.get_queue_status()['active_tasks']}")


async def shutdown_event():
    """应用关闭时执行"""
    factory = get_task_factory()
    await factory.shutdown(wait_for_completion=True, timeout=30)
    info("REST API 服务器已关闭")
