"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: mcp_http_client.py
@Description: MCP HTTP 客户端示例：直连 penshot.mcp_http_server 的 /tools 路由
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:30
"""
import os
import time
from typing import Optional

import httpx

# 先启动 MCP HTTP 服务（默认 127.0.0.1:8000，与 REST 服务不同，二者不要同时占用同一端口）：
#   python -m penshot.mcp_http_server
#   story-shot-agent --help 查看有无对应子命令；若无请用上方模块方式启动
BASE_URL = os.getenv("PENSHOT_MCP_HTTP", "http://127.0.0.1:8000")

# MCP HTTP 层反序列化后的任务终态字符串
TERMINAL_STATUS = {"success", "failed", "cancelled"}


class HTTPMCPClient:
    """封装 penshot.mcp_http_server 暴露的 HTTP 工具路由（httpx 客户端）。"""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=timeout),
        )

    # ---- 工具元信息 ----
    def list_tools(self) -> dict:
        """GET /tools：工具列表（HTTP 版带 parameters 描述）。"""
        resp = self._client.get("/tools")
        resp.raise_for_status()
        return resp.json()

    # ---- 任务工具（POST /tools/{name}）----
    def breakdown_script(self, script: str, language: str = "zh", wait: bool = False, timeout: int = 300) -> dict:
        """拆分剧本；wait=False 立即返回 task_id。"""
        resp = self._client.post(
            "/tools/breakdown_script",
            json={"script": script, "language": language, "wait": wait, "timeout": timeout},
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> dict:
        """查询任务状态（含当前阶段与各阶段进度）。"""
        resp = self._client.post("/tools/get_task_status", json={"task_id": task_id})
        resp.raise_for_status()
        return resp.json()

    def get_task_result(self, task_id: str) -> dict:
        """拉取任务结果（data.instructions 结构）。"""
        resp = self._client.post("/tools/get_task_result", json={"task_id": task_id})
        resp.raise_for_status()
        return resp.json()

    def cancel_task(self, task_id: str) -> dict:
        """取消任务，返回 {"cancelled": bool}。"""
        resp = self._client.post("/tools/cancel_task", json={"task_id": task_id})
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, status_filter: Optional[str] = None, limit: int = 20) -> dict:
        """列出近期任务摘要，可按状态筛选。"""
        resp = self._client.post("/tools/list_tasks", json={"status_filter": status_filter, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    # ---- 监控工具（GET /tools/...）----
    def get_queue_status(self) -> dict:
        """GET /tools/queue_status：队列状态。"""
        resp = self._client.get("/tools/queue_status")
        resp.raise_for_status()
        return resp.json()

    def get_stats(self) -> dict:
        """GET /tools/stats：统计信息。"""
        resp = self._client.get("/tools/stats")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


def print_instructions_summary(result: dict) -> None:
    """按 data.instructions 契约打印结果摘要。"""
    data = result.get("data") or {}
    instructions = data.get("instructions", {})
    project_info = instructions.get("project_info", {})
    fragments = instructions.get("fragments", [])
    print(f"  片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"  总时长: {project_info.get('total_duration', 0.0):.1f} 秒")
    for i, frag in enumerate(fragments[:3], 1):
        print(f"  [{i}] {frag.get('fragment_id')}: {str(frag.get('prompt', ''))[:70]}...")


def main():
    """演示：工具列表 → 异步提交 → 轮询 → 结果 → 队列/统计。"""
    client = HTTPMCPClient()
    try:
        tools = client.list_tools()
        print("可用工具:", [t["name"] for t in tools.get("tools", [])])

        script = "雨夜街角，一位撑伞的老人停下脚步，抬头望向亮着灯的便利店。"
        submit = client.breakdown_script(script, language="zh", wait=False)
        task_id = submit.get("task_id")
        print(f"已提交任务: {task_id}, 初始状态: {submit.get('status')}")

        for _ in range(15):
            status = client.get_task_status(task_id)
            state = status.get("status")
            print(f"  状态: {state}, 阶段: {status.get('stage_name') or status.get('current_stage')}, "
                  f"进度: {status.get('progress')}%")
            if state in TERMINAL_STATUS:
                break
            time.sleep(2)

        result = client.get_task_result(task_id)
        if result.get("success"):
            print(f"结果成功: {result.get('success')}, 处理耗时: {result.get('processing_time_ms')}ms")
            print_instructions_summary(result)
        else:
            print("任务未成功完成：若已配置 LLM key，请提高轮询次数。")

        queue_status = client.get_queue_status()
        print(f"队列: 长度={queue_status.get('queue_length')}, "
              f"活跃={queue_status.get('active_tasks')}, 最大并发={queue_status.get('max_concurrent')}")
        stats = client.get_stats()
        print(f"统计: 提交={stats.get('total_submitted')}, "
              f"完成={stats.get('total_completed')}, 失败={stats.get('total_failed')}")
    except Exception as exc:  # noqa: BLE001 - 示例统一兜底
        print(f"调用失败: {exc}")
        print("请确认已先启动服务：python -m penshot.mcp_http_server")
    finally:
        client.close()


if __name__ == "__main__":
    main()
