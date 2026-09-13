"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 04_queue_and_task_mgmt.py
@Description: SDK 直调示例：任务管理 / 队列监控 / 并发调整
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import os
import time
from pathlib import Path

from penshot import ShotLanguage
from penshot.api import PenshotFunction


def llm_env_configured() -> bool:
    """粗略判断 LLM 是否已配置（直接环境变量或仓库根目录 .env）。"""
    if any(k.startswith("PENSHOT_LLM") for k in os.environ):
        return True
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("PENSHOT_LLM") and not line.strip().endswith("="):
                return True
    return False


def demo_queue_and_stats(agent: PenshotFunction) -> None:
    """演示队列状态、统计信息与并发调整（无需调用 LLM）。"""
    print("=== 队列 / 统计 / 并发控制 ===")

    # 队列状态：get_queue_status()
    queue = agent.get_queue_status()
    print(
        f"队列: length={queue.get('queue_length', 0)}, "
        f"waiting={queue.get('queue_waiting', 0)}, "
        f"active={queue.get('active_tasks', 0)}, "
        f"max_concurrent={queue.get('max_concurrent')}, "
        f"queue_max={queue.get('queue_max_size')}"
    )

    # 统计信息：get_stats()
    stats = agent.get_stats()
    print(
        f"统计: submitted={stats.get('total_submitted', 0)}, "
        f"completed={stats.get('total_completed', 0)}, "
        f"failed={stats.get('total_failed', 0)}"
    )

    # 动态调整并发
    agent.set_max_concurrent(3)
    queue = agent.get_queue_status()
    print(f"调整后 max_concurrent = {queue.get('max_concurrent')}")

    # 取消不存在的任务返回 False
    print(f"取消未知任务: {agent.cancel_task('not-exist-task')}")


def demo_submit_and_cancel(agent: PenshotFunction) -> None:
    """配置了 LLM 时，演示提交任务并尽量在排入队列期间取消其中一个。"""
    print("\n=== 提交与取消 ===")
    task_ids = []
    for i in range(3):
        tid = agent.breakdown_script_async(
            f"第{i + 1}段：一个街头艺人正在黄昏的城市广场演奏，周围行人驻足聆听。",
            language=ShotLanguage.ZH,
        )
        task_ids.append(tid)
        print(f"提交任务: {tid}")

    # 尝试取消（任务可能已进入处理，成功与否取决于时序）
    cancelled = agent.cancel_task(task_ids[0])
    print(f"取消 {task_ids[0]} -> {cancelled}")

    # 简单轮询等待剩余任务结束
    deadline = time.time() + 60
    while time.time() < deadline:
        stats = agent.get_stats()
        if stats.get("total_completed", 0) + stats.get("total_failed", 0) >= len(task_ids):
            break
        time.sleep(2)
    stats = agent.get_stats()
    print(f"任务结束后统计: submitted={stats.get('total_submitted', 0)}, "
          f"completed={stats.get('total_completed', 0)}, failed={stats.get('total_failed', 0)}")


def main():
    """演示任务队列监控与任务管理接口。"""
    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=2)
    try:
        demo_queue_and_stats(agent)
        if llm_env_configured():
            demo_submit_and_cancel(agent)
        else:
            print("\n（未配置 LLM，跳过真实任务提交演示；队列/统计接口无需 LLM 也可调用）")
    except Exception as exc:  # noqa: BLE001 - 示例中统一兜底打印
        print(f"调用失败: {exc}")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
