"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 01_sync_storyboard.py
@Description: REST 场景示例：同步分镜拆分（POST /api/v1/storyboard/sync）
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:20
"""
from pathlib import Path

import httpx

# 先启动 REST 服务，再运行本脚本：
#   story-shot-agent serve-rest --host 127.0.0.1 --port 8000
#   或 python -m penshot.http_server --host 127.0.0.1 --port 8000
BASE_URL = "http://127.0.0.1:8000"

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "scripts"


def load_sample_script(name: str = "natural_language_script.txt") -> str:
    """读取内置样例剧本，便于演示较长的剧本输入。"""
    path = SCRIPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else "剧本内容示例。"


def print_instructions(data: dict) -> None:
    """打印结果中的 data.instructions 摘要。"""
    if not data:
        return
    instructions = data.get("instructions", {})
    fragments = instructions.get("fragments", [])
    project_info = instructions.get("project_info", {})
    print(f"片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"总时长: {project_info.get('total_duration', 0.0):.1f} 秒")
    for i, frag in enumerate(fragments[:3], 1):
        print(f"  [{i}] {frag.get('fragment_id')}: {str(frag.get('prompt', ''))[:80]}...")


def main():
    """调用同步接口，等待任务完成后直接返回结果。"""
    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(connect=5.0, read=30.0)) as client:
        payload = {
            "script": load_sample_script(),
            "script_id": "rest-sync-001",
            "language": "zh",
            "timeout": 600,
        }
        resp = client.post("/api/v1/storyboard/sync", json=payload)

        if resp.status_code != 200:
            # 同步接口在业务失败时返回 HTTP 400，detail 携带错误信息
            detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise SystemExit(f"同步分镜失败(HTTP {resp.status_code}): {detail}")

        result = resp.json()
        print(f"任务ID: {result.get('task_id')}")
        print(f"状态: {result.get('status')}, 成功: {result.get('success')}")
        if result.get("success"):
            print_instructions(result.get("data") or {})
        else:
            print(f"错误: {result.get('message') or result.get('error')}")


if __name__ == "__main__":
    main()
