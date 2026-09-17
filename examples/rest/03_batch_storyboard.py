"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 03_batch_storyboard.py
@Description: REST 场景示例：批量分镜（同步/异步 + 批量状态/结果）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:20
"""
import argparse
import time

import httpx

# 先启动 REST 服务：
#   story-shot-agent serve-rest 或 python -m penshot.http_server
BASE_URL = "http://127.0.0.1:8000"

SCRIPTS = [
    "一个男人在海边慢跑，日出时分，浪花拍打沙滩。",
    "两个孩子放学后在操场追逐，笑声不断。",
    "老人在公园石桌旁下棋，夕阳将影子拉得很长。",
]

TERMINAL = {"success", "failed", "cancelled"}


def print_single_result(result: dict) -> None:
    """打印单个 ProcessResult。"""
    print(f"  任务 {result.get('task_id')}: status={result.get('status')}, success={result.get('success')}")
    if result.get("success"):
        instructions = (result.get("data") or {}).get("instructions", {})
        fragments = instructions.get("fragments", [])
        print(f"    片段数: {len(fragments)}")
    else:
        print(f"    错误: {result.get('message') or result.get('error')}")


def demo_sync_batch(client: httpx.Client) -> None:
    """同步批量：POST /api/v1/storyboard/batch/sync（返回结果数组）。"""
    print("=== 同步批量 /storyboard/batch/sync ===")
    resp = client.post("/api/v1/storyboard/batch/sync", json={"scripts": SCRIPTS, "language": "zh"})
    resp.raise_for_status()
    for result in resp.json():
        print_single_result(result)


def demo_async_batch(client: httpx.Client) -> None:
    """异步批量：POST /storyboard/batch 后通过 batch/status 与 batch/result 查询。"""
    print("\n=== 异步批量 /storyboard/batch ===")
    resp = client.post("/api/v1/storyboard/batch", json={"scripts": SCRIPTS, "language": "zh"})
    resp.raise_for_status()
    batch = resp.json()
    batch_id = batch.get("batch_id")
    print(f"batch_id: {batch_id}, 任务数: {batch.get('total_tasks')}")

    while True:
        info = client.get(f"/api/v1/batch/status/{batch_id}")
        info.raise_for_status()
        state = info.json()
        done = state.get("success") + state.get("failed") + state.get("cancelled")
        print(f"  完成: {done}/{state.get('total_tasks')} (success={state.get('success')}, failed={state.get('failed')})")
        if done >= state.get("total_tasks"):
            break
        time.sleep(2)

    detail = client.get(f"/api/v1/batch/result/{batch_id}")
    detail.raise_for_status()
    for item in detail.json().get("results", []):
        print(f"  任务 {item.get('task_id')}: success={item.get('success')}, status={item.get('status')}")


def main():
    parser = argparse.ArgumentParser(description="REST 批量分镜示例")
    parser.add_argument("--mode", choices=["sync", "async"], default="sync", help="同步或异步批量")
    args = parser.parse_args()

    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(connect=5.0, read=30.0)) as client:
        if args.mode == "sync":
            demo_sync_batch(client)
        else:
            demo_async_batch(client)


if __name__ == "__main__":
    main()
