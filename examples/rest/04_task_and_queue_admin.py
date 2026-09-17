"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 04_task_and_queue_admin.py
@Description: REST 场景示例：任务/队列/配置/健康等管理接口
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:20
"""
import argparse

import httpx

# 先启动 REST 服务：
#   story-shot-agent serve-rest 或 python -m penshot.http_server
BASE_URL = "http://127.0.0.1:8000"


def main():
    parser = argparse.ArgumentParser(description="REST 任务/队列管理接口示例")
    parser.add_argument("--task", help="需要查询状态的 task_id")
    args = parser.parse_args()

    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(connect=5.0, read=20.0)) as client:
        # 服务信息 / 健康
        health = client.get("/api/v1/health")
        health.raise_for_status()
        print("健康:", health.json())

        # 支持的语言与默认配置
        langs = client.get("/api/v1/languages")
        langs.raise_for_status()
        print("语言:", langs.json())
        config = client.get("/api/v1/config")
        config.raise_for_status()
        cfg = config.json()
        print("默认视频模型:", cfg.get("video_model"), "| 最大片段时长:", cfg.get("max_fragment_duration"))

        # 队列与统计
        queue = client.get("/api/v1/queue/status")
        queue.raise_for_status()
        print("队列:", queue.json())
        stats = client.get("/api/v1/stats")
        stats.raise_for_status()
        s = stats.json()
        print("统计:", {k: s.get(k) for k in ("total_submitted", "total_completed", "total_failed")})

        # 按需查询单个任务状态 / 结果
        if args.task:
            status = client.get(f"/api/v1/status/{args.task}")
            print(f"任务 {args.task} 状态码: {status.status_code}")
            if status.status_code == 200:
                print("任务状态:", status.json())
                result = client.get(f"/api/v1/result/{args.task}")
                if result.status_code == 200:
                    print("任务结果 success:", result.json().get("success"))

        # 取消不存在的任务：预期 404，用于演示取消接口
        cancel = client.delete("/api/v1/task/not-exist-task")
        print("取消未知任务 HTTP:", cancel.status_code, "| body:", cancel.json())


if __name__ == "__main__":
    main()
