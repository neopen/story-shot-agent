"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_mcp.py
@Description: MCP 客户端测试脚本
@Author: NeoPen
@Time: 2026/3/30
"""

import asyncio
import json
import subprocess
import sys
import time


class SimpleMCPClient:
    """简单的 MCP 客户端，通过 stdio 与 Server 通信"""

    def __init__(self, server_script: str = None):
        self.server_script = server_script or "penshot.mcp_server"
        self.process = None
        self._request_id = 0

    def start(self):
        """启动 MCP Server 子进程"""
        self.process = subprocess.Popen(
            [sys.executable, "-m", self.server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        print(f"MCP Server 已启动，PID: {self.process.pid}")

    async def call(self, method: str, params: dict = None) -> dict:
        """调用 MCP 方法"""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        # 发送请求
        request_str = json.dumps(request)
        self.process.stdin.write(request_str)
        self.process.stdin.flush()

        # 读取响应
        line = self.process.stdout.readline()
        if not line:
            raise Exception("Server 无响应")

        return json.loads(line)

    async def get_tools(self) -> list:
        """获取工具列表"""
        result = await self.call("tools/list")
        return result.get("result", {}).get("tools", [])

    async def breakdown(self, script: str, language: str = "zh", wait: bool = True) -> dict:
        """拆分剧本"""
        result = await self.call("tools/call", {
            "name": "breakdown_script",
            "arguments": {
                "script": script,
                "language": language,
                "wait": wait,
                "timeout": 300
            }
        })

        if "error" in result:
            raise Exception(result["error"]["message"])

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return {}

    def stop(self):
        """停止 Server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            print("MCP Server 已停止")


async def main():
    """测试主函数"""
    script = """
    场景：咖啡店门口，雨天
    人物：林小雨（20岁，学生）
    动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
    """

    print("=" * 50)
    print("MCP 客户端测试")
    print("=" * 50)

    client = SimpleMCPClient()

    try:
        # 1. 启动 Server
        client.start()
        await asyncio.sleep(1)

        # 2. 获取工具列表
        print("\n获取工具列表...")
        tools = await client.get_tools()
        print(f"可用工具: {[t['name'] for t in tools]}")

        # 3. 提交任务
        print("\n提交任务...")
        result = await client.breakdown(script, wait=False)
        task_id = result.get("task_id")
        print(f"任务ID: {task_id}")

        # 4. 等待完成
        print("\n等待完成...")
        import time
        for i in range(30):
            status = await client.call("tools/call", {
                "name": "get_task_status",
                "arguments": {"task_id": task_id}
            })
            content = status.get("result", {}).get("content", [])
            if content:
                status_data = json.loads(content[0]["text"])
                print(f"  状态: {status_data.get('status')}, 进度: {status_data.get('progress')}%")
                if status_data.get("status") in ["completed", "failed"]:
                    break
            await asyncio.sleep(2)

        # 5. 获取结果
        print("\n获取结果...")
        result = await client.breakdown(script, wait=True)
        if result.get("success"):
            data = result.get("data", {})
            instructions = data.get("instructions", {})
            fragments = instructions.get("fragments", [])
            print(f"\n成功! 生成了 {len(fragments)} 个片段")
            for i, frag in enumerate(fragments[:2], 1):
                print(f"  片段{i}: {frag.get('prompt', '')[:80]}...")
        else:
            print(f"失败: {result.get('error')}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.stop()


def test_mcp_server():
    """测试 MCP Server"""

    print("启动 MCP Server...")
    process = subprocess.Popen(
        [sys.executable, "-m", "penshot.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0
    )
    print(f"PID: {process.pid}")
    time.sleep(2)

    def read_json_response():
        """读取 JSON 响应，跳过非 JSON 行"""
        while True:
            line = process.stdout.readline()
            if not line:
                return None
            line = line.decode('utf-8', errors='ignore').strip()
            if not line:
                continue
            if line.startswith('{'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    try:
        # 1. 获取工具列表
        print("\n1. 获取工具列表...")
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        process.stdin.write((json.dumps(request) + "\n").encode('utf-8'))
        process.stdin.flush()

        response = read_json_response()
        print(f"工具数量: {len(response.get('result', {}).get('tools', []))}")

        # 2. 提交剧本
        print("\n2. 提交剧本...")
        script = """
        场景：咖啡店门口，雨天
        人物：林小雨（20岁，学生）
        动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
        """
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "breakdown_script",
                "arguments": {
                    "script": script.strip(),
                    "language": "zh",
                    "wait": False
                }
            }
        }
        process.stdin.write((json.dumps(request) + "\n").encode('utf-8'))
        process.stdin.flush()

        response = read_json_response()
        content = response.get("result", {}).get("content", [])
        if content:
            result = json.loads(content[0]["text"])
            task_id = result.get("task_id")
            print(f"任务ID: {task_id}")

        # 3. 轮询状态
        print("\n3. 等待完成...")
        for i in range(30):
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_task_status",
                    "arguments": {"task_id": task_id}
                }
            }
            process.stdin.write((json.dumps(request) + "\n").encode('utf-8'))
            process.stdin.flush()

            response = read_json_response()
            content = response.get("result", {}).get("content", [])
            if content:
                status = json.loads(content[0]["text"])
                print(f"  状态: {status.get('status')}, 进度: {status.get('progress', 0)}%")
                if status.get("status") in ["completed", "failed", "success"]:
                    break
            time.sleep(2)

        # 4. 获取结果
        print("\n4. 获取结果...")
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_task_result",
                "arguments": {"task_id": task_id}
            }
        }
        process.stdin.write((json.dumps(request) + "\n").encode('utf-8'))
        process.stdin.flush()

        response = read_json_response()
        content = response.get("result", {}).get("content", [])
        if content:
            task_result = json.loads(content[0]["text"])
            if task_result.get("success"):
                fragments = task_result.get("data", {}).get("instructions", {}).get("fragments", [])
                print(f"\n✓ 成功! 生成 {len(fragments)} 个片段")
            else:
                print(f"✗ 失败: {task_result.get('error')}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        process.terminate()
        process.wait(timeout=5)
        print("\nMCP Server 已停止")


def test_mcp():
    asyncio.run(main())
