"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 03_batch_processing.py
@Description: SDK 直调示例：批量分镜处理（同步/异步）
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from penshot import ShotLanguage
from penshot.api import PenshotFunction, PenshotResult

SCRIPTS = [
    "一个男人在海边慢跑，日出时分，浪花拍打着沙滩。",
    "两个孩子在游乐场里玩耍，笑声不断，阳光明媚。",
    "老人在公园长椅上下棋，神色专注，午后时光安静悠长。",
]


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


def print_batch(results: List[PenshotResult]) -> None:
    """批量打印结果，读取每条的 data.instructions 片段信息。"""
    for i, result in enumerate(results, 1):
        if not result:
            print(f"任务{i}: 无结果")
            continue
        if result.success:
            instructions = (result.data or {}).get("instructions", {})
            fragments = instructions.get("fragments", [])
            project_info = instructions.get("project_info", {})
            print(
                f"任务{i}: 成功, 片段数={len(fragments)}, "
                f"总时长={project_info.get('total_duration', 0.0):.1f}s, "
                f"耗时={result.processing_time_ms}ms"
            )
        else:
            print(f"任务{i}: 失败 - {result.error}")


def demo_sync_batch(agent: PenshotFunction) -> None:
    """同步批量：阻塞等待全部完成。"""
    print("=== 同步批量 batch_breakdown ===")
    results = agent.batch_breakdown(SCRIPTS, wait_timeout=600.0)
    print_batch(results)


async def demo_async_batch(agent: PenshotFunction) -> None:
    """异步批量：控制并发数（batch_breakdown_async 为协程）。"""
    print("\n=== 异步批量 batch_breakdown_async ===")
    results = await agent.batch_breakdown_async(SCRIPTS, max_concurrent=2)
    print_batch(results)


def main():
    """演示同步与异步批量处理。"""
    if not llm_env_configured():
        print("尚未配置 LLM：请先复制 .env.example 为 .env 并填写 LLM 相关环境变量。")
        sys.exit(0)

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)
    try:
        demo_sync_batch(agent)
        asyncio.run(demo_async_batch(agent))
    except Exception as exc:  # noqa: BLE001 - 示例中统一兜底打印
        print(f"批量调用失败: {exc}")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
