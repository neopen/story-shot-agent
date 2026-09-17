"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: mcp_server_demo.py
@Description: MCP Server 端到端自测：自动拉起 mcp_server 并走完整流程
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:30
"""
import os
import sys
import time
from pathlib import Path

# 复用同目录 mcp_client.py 里的 stdio JSON-RPC 客户端（本示例不新增协议实现）。
# 直接运行：python examples/mcp/mcp_server_demo.py
try:  # 保证以任何方式启动都能在同目录找到 mcp_client 模块
    from mcp_client import MCPStdioClient, TERMINAL_STATUS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mcp_client import MCPStdioClient, TERMINAL_STATUS  # noqa: E402

# 前置：pip install -e . 使 penshot 可用（demo 会用当前解释器 spawn `python -m penshot.mcp_server`）。
# 未配置 LLM key 时任务无法真正完成，脚本会优雅结束并给出提示。


def llm_env_configured() -> bool:
    """检查是否已配置 LLM（环境变量或仓库根目录 .env）。"""
    if any(key.startswith("PENSHOT_LLM") for key in os.environ):
        return True
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.exists():
        for line in root_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("PENSHOT_LLM"):
                return True
    return False


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
    """本地拉起 mcp_server → initialize/tools/list → 异步提交 → 轮询 → 结果/队列/统计。"""
    client = MCPStdioClient(server_module="penshot.mcp_server")
    try:
        client.start()

        tools = client.list_tools()
        names = [t["name"] for t in tools]
        print("tools/list 返回工具:", names)
        assert "breakdown_script" in names, "服务端工具注册异常"

        # 队列/统计无需 LLM key，先验证监控类工具可用
        queue_status = client.get_queue_status()
        print("队列状态:", queue_status)
        stats = client.get_stats()
        print("统计:", {k: stats.get(k) for k in ("total_submitted", "total_completed", "total_failed")})

        script = "清晨的山间公路，一辆自行车沿着弯道下坡，朝阳从树缝里洒下来。"
        submit = client.breakdown_script(script, language="zh", wait=False)
        task_id = submit.get("task_id")
        print(f"异步提交任务: {task_id}, 初始状态: {submit.get('status')}")

        if not llm_env_configured():
            print("未配置 LLM key：任务将无法完成，本示例到此结束（仅验证链路与工具可达）。")
            return

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
            print(f"结果成功: 耗时 {result.get('processing_time_ms')}ms")
            print_instructions_summary(result)
        else:
            print(f"任务最终状态非成功: {result.get('status')}, error={result.get('error')}")
    except Exception as exc:  # noqa: BLE001 - 示例统一兜底
        print(f"自测失败: {exc}")
        sys.exit(1)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
