"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 02_async_submit_poll.py
@Description: REST 场景示例：异步提交 + 轮询状态 + 拉取结果
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:20
"""
import time

import httpx

# 先启动 REST 服务：
#   story-shot-agent serve-rest 或 python -m penshot.http_server
BASE_URL = "http://127.0.0.1:8000"

# REST 层序列化后的任务终态字符串
TERMINAL = {"success", "failed", "cancelled"}


def print_instructions(data: dict) -> None:
    """打印 data.instructions 摘要。"""
    if not data:
        return
    instructions = data.get("instructions", {})
    fragments = instructions.get("fragments", [])
    print(f"片段数: {len(fragments)}")
    print(f"总时长: {instructions.get('project_info', {}).get('total_duration', 0.0):.1f} 秒")
    for i, frag in enumerate(fragments[:3], 1):
        print(f"  [{i}] {frag.get('fragment_id')}: {str(frag.get('prompt', ''))[:80]}...")


def main():
    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(connect=5.0, read=20.0)) as client:
        # 1) 异步提交：立即返回 task_id
        payload = {
            "script": "办公室的午后，程序员小李正在修改代码，突然接到一通电话，神情惊讶。",
            "script_id": "rest-async-001",
            "language": "zh",
            "style": "cinematic",
        }
        resp = client.post("/api/v1/storyboard", json=payload)
        resp.raise_for_status()
        submit = resp.json()
        task_id = submit.get("task_id")
        print(f"已提交任务: {task_id}, 初始状态: {submit.get('status')}")

        # 2) 轮询状态（GET /api/v1/status/{task_id}）
        while True:
            status = client.get(f"/api/v1/status/{task_id}")
            status.raise_for_status()
            info = status.json()
            print(
                f"  状态: {info.get('status')}, 阶段: {info.get('stage_name') or info.get('stage')}, "
                f"进度: {info.get('progress')}%"
            )
            if info.get("status") in TERMINAL:
                break
            time.sleep(2)

        # 3) 拉取结果（GET /api/v1/result/{task_id}）
        result = client.get(f"/api/v1/result/{task_id}")
        result.raise_for_status()
        data = result.json()
        print(f"结果成功: {data.get('success')}, 处理耗时: {data.get('processing_time_ms')}ms")
        if data.get("success"):
            print_instructions(data.get("data") or {})
        else:
            print(f"错误: {data.get('message') or data.get('error')}")


if __name__ == "__main__":
    main()
