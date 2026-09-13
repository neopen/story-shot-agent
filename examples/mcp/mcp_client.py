"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: mcp_client.py
@Description: MCP stdio 客户端示例：JSON-RPC 2.0 over stdio，自动拉起 mcp_server
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:30
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# 前置：先 pip install -e .（本文件 import 仅依赖标准库，跨平台可用）。
# mcp_server 的所有日志走 stderr，stdout 只输出逐行 JSON-RPC，因此可直接用管道通信。
# 本类同时被 mcp_server_demo.py import 复用做端到端自测。

# MCP 层反序列化后的任务终态字符串（TaskStatus 经 json 序列化为字面量，成功为 "success"）
TERMINAL_STATUS = {"success", "failed", "cancelled"}


def llm_env_configured() -> bool:
    """检查是否已配置 LLM（PENSHOT_LLM__* 环境变量或仓库根目录 .env）。"""
    if any(key.startswith("PENSHOT_LLM") for key in os.environ):
        return True
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.exists():
        for line in root_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("PENSHOT_LLM"):
                return True
    return False


class MCPStdioClient:
    """与 `python -m penshot.mcp_server` 通信的 stdio JSON-RPC 客户端。

    后台线程持续读取 stdout 并把 JSON 响应放入队列；请求按自增 id 匹配响应，
    避免阻塞式 readline 在 Windows 上的兼容问题。
    """

    def __init__(self, python: Optional[str] = None, server_module: str = "penshot.mcp_server"):
        self.python = python or sys.executable
        self.server_module = server_module
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._responses: "queue.Queue[dict]" = queue.Queue()
        self._stderr_lines: list = []
        self._stderr_lock = threading.Lock()

    def start(self) -> "MCPStdioClient":
        """启动 server 子进程，开启 stdout/stderr 读取线程并完成 initialize 握手。"""
        self.process = subprocess.Popen(
            [self.python, "-m", self.server_module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._call("initialize", {})  # MCP 握手
        print(f"已启动 {self.server_module} (pid={self.process.pid})")
        return self

    def _read_stdout(self) -> None:
        """逐行读取 stdout，把 JSON 消息放入响应队列（跳过空行与日志噪音）。"""
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._responses.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _drain_stderr(self) -> None:
        """排空 stderr，避免管道写满阻塞 server；保留最近 50 行供报错展示。"""
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            with self._stderr_lock:
                self._stderr_lines.append(line.rstrip())
                del self._stderr_lines[:-50]

    def stderr_tail(self) -> str:
        """返回最近若干行 server 日志，便于排查启动/调用失败。"""
        with self._stderr_lock:
            return "\n".join(self._stderr_lines)

    def _call(self, method: str, params: Optional[dict] = None, timeout: float = 120.0) -> dict:
        """发送一次 JSON-RPC 请求，等待与自增 id 匹配的响应。"""
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError(f"server 未在运行：\n{self.stderr_tail()}")

        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"请求 {method} 超时（{timeout}s）：\n{self.stderr_tail()}")
            try:
                message = self._responses.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("id") != self._request_id:
                continue  # 丢弃通知或迟到的旧响应
            if "error" in message:
                err = message["error"]
                raise RuntimeError(f"MCP 错误 {err.get('code')}: {err.get('message')}")
            return message.get("result", {})

    def list_tools(self) -> list:
        """tools/list。注意：当前 mcp_server 对每个工具声明的是空 parameters（见源码）。"""
        result = self._call("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        """tools/call：server 把 handler 返回的 dict 序列化在 content[0].text 中。"""
        result = self._call("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content") or []
        if content and content[0].get("type") == "text":
            text = content[0].get("text", "{}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"_raw_text": text}
        return {}

    # ---- 对 7 个内置工具的语义化封装 ----
    def breakdown_script(self, script: str, language: str = "zh", wait: bool = False, timeout: int = 300) -> dict:
        """拆分剧本；wait=False 立即返回 task_id，wait=True 同步等待结果。"""
        return self.call_tool(
            "breakdown_script",
            {"script": script, "language": language, "wait": wait, "timeout": timeout},
        )

    def get_task_status(self, task_id: str) -> dict:
        """查询任务状态（含当前阶段与各阶段进度）。"""
        return self.call_tool("get_task_status", {"task_id": task_id})

    def get_task_result(self, task_id: str) -> dict:
        """拉取任务结果（data.instructions 结构）。"""
        return self.call_tool("get_task_result", {"task_id": task_id})

    def cancel_task(self, task_id: str) -> dict:
        """取消任务，返回 {"cancelled": bool}。"""
        return self.call_tool("cancel_task", {"task_id": task_id})

    def list_tasks(self, limit: int = 20) -> dict:
        """列出近期任务摘要。"""
        return self.call_tool("list_tasks", {"limit": limit})

    def get_queue_status(self) -> dict:
        """队列状态：queue_length / active_tasks / max_concurrent。"""
        return self.call_tool("get_queue_status", {})

    def get_stats(self) -> dict:
        """统计信息：total_submitted / total_completed / total_failed。"""
        return self.call_tool("get_stats", {})

    def stop(self) -> None:
        """终止 server 子进程。"""
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


def print_instructions_summary(result: dict) -> None:
    """按 data.instructions 契约打印结果摘要（与 SDK/REST 结果结构一致）。"""
    data = result.get("data") or {}
    instructions = data.get("instructions", {})
    project_info = instructions.get("project_info", {})
    fragments = instructions.get("fragments", [])
    print(f"  片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"  总时长: {project_info.get('total_duration', 0.0):.1f} 秒")
    for i, frag in enumerate(fragments[:3], 1):
        print(f"  [{i}] {frag.get('fragment_id')}: {str(frag.get('prompt', ''))[:70]}...")


def main():
    """本地拉起 mcp_server 并演示：握手 → tools/list → 异步提交 → 轮询 → 结果。"""
    if not llm_env_configured():
        print("未配置 LLM API key：任务无法真正完成。设置 PENSHOT_LLM__DEFAULT__API_KEY 后再试。")

    client = MCPStdioClient()
    try:
        client.start()

        tools = client.list_tools()
        print("可用工具:", [t["name"] for t in tools])

        script = "海边日落，一个男人牵着狗沿着沙滩慢慢散步，浪花轻轻拍打脚踝。"
        submit = client.breakdown_script(script, language="zh", wait=False)
        task_id = submit.get("task_id")
        print(f"已提交任务: {task_id}, 初始状态: {submit.get('status')}")

        for _ in range(15):
            status = client.get_task_status(task_id)
            state = status.get("status")
            print(f"  状态: {state}, 阶段: {status.get('stage_name') or status.get('current_stage')}, "
                  f"进度: {status.get('progress')}%")
            if state in TERMINAL_STATUS or state == "not_found":
                break
            time.sleep(2)

        if state in {"success", "not_found"} and client.get_task_result(task_id).get("success"):
            result = client.get_task_result(task_id)
            print(f"结果成功: {result.get('success')}, 处理耗时: {result.get('processing_time_ms')}ms")
            print_instructions_summary(result)
        else:
            print("任务未成功完成：若已配置 key，请提高轮询次数或检查 server 日志。")
    except Exception as exc:  # noqa: BLE001 - 示例统一兜底
        print(f"调用失败: {exc}")
    finally:
        client.stop()


if __name__ == "__main__":
    main()
