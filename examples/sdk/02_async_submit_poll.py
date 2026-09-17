"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 02_async_submit_poll.py
@Description: SDK 直调示例：异步提交 + 回调/轮询 + 异步等待
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional

from penshot import ShotLanguage
from penshot.api import PenshotFunction, PenshotResult
from penshot.neopen.task.task_models import TaskStatus

SCRIPT_A = "深夜的客厅里，张三紧张地环顾四周，桌上放着一封信，他犹豫着是否拆开。"
SCRIPT_B = "清晨的海边，一个女孩沿着沙滩奔跑，海鸥在头顶盘旋，远处日出正缓缓升起。"

TERMINAL_STATUS = {
    TaskStatus.SUCCESS.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


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


def demo_callback_and_poll(agent: PenshotFunction) -> Optional[PenshotResult]:
    """异步提交：任务完成时回调 + 主动轮询状态 + 等待最终结果。"""
    print("\n=== 异步提交（回调 + 轮询）===")

    # breakdown_script_async 是普通函数，不是协程：提交后立即返回 task_id（字符串）
    task_id = agent.breakdown_script_async(
        SCRIPT_A,
        script_id="sdk-async-001",
        language=ShotLanguage.ZH,
        callback=lambda r: print(
            f"[回调] 任务 {r.task_id} 完成, success={r.success}, status={r.status.value}"
        ),
    )
    print(f"任务已提交: {task_id}")

    # 轮询任务状态（get_task_status 返回的 status 是 TaskStatus 枚举，需用 .value 比较/打印）
    while True:
        status = agent.get_task_status(task_id)
        if not status:
            print("任务不存在")
            return None
        print(
            f"[轮询] {status['stage_name']} | status={status['status'].value} "
            f"| progress={status['progress']}%"
        )
        if status["status"].value in TERMINAL_STATUS:
            break
        time.sleep(2)

    # 等待最终结果（阻塞，最多 600 秒）
    result = agent.wait_for_result(task_id, timeout=600.0)
    print(f"最终结果: success={result.success}, status={result.status.value}")
    return result


async def demo_wait_async(agent: PenshotFunction) -> Optional[PenshotResult]:
    """在用户自己的 asyncio 事件循环中异步等待任务完成。"""
    print("\n=== 异步等待（wait_for_result_async）===")

    task_id = agent.breakdown_script_async(
        SCRIPT_B,
        script_id="sdk-async-002",
        language=ShotLanguage.ZH,
    )
    print(f"任务已提交: {task_id}")

    result = await agent.wait_for_result_async(task_id, timeout=600.0, poll_interval=1.0)
    print(f"最终结果: success={result.success}, status={result.status.value}")
    return result


def main():
    """演示异步提交与等待方式。"""
    if not llm_env_configured():
        print("尚未配置 LLM：请先复制 .env.example 为 .env 并填写 LLM 相关环境变量。")
        sys.exit(0)

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)
    try:
        demo_callback_and_poll(agent)
        asyncio.run(demo_wait_async(agent))
    except Exception as exc:  # noqa: BLE001 - 示例中统一兜底打印
        print(f"调用失败: {exc}")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
