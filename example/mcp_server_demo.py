"""
@FileName: mcp_server_demo.py
@Description: MCP Server 使用示例
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 13:02
"""

import asyncio
import json
import subprocess
import sys
from typing import Dict, Optional


class MCPClient:
    """
    MCP 客户端 - 用于与 Penshot MCP Server 通信
    """

    def __init__(self, server_script: str = None):
        """
        初始化 MCP 客户端

        Args:
            server_script: MCP Server 脚本路径，默认使用当前模块
        """
        self.server_script = server_script or __file__.replace("_demo.py", "_server.py")
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    def start(self) -> None:
        """启动 MCP Server 进程"""
        self.process = subprocess.Popen(
            [sys.executable, self.server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        print(f"MCP Server 已启动，PID: {self.process.pid}")

    def _send_request(self, method: str, params: Dict = None) -> Dict:
        """发送 JSON-RPC 请求"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        # 发送请求
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        # 读取响应
        response_line = self.process.stdout.readline()
        if not response_line:
            raise Exception("Server 未响应")

        return json.loads(response_line)

    def get_tools(self) -> list:
        """获取可用工具列表"""
        response = self._send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """调用工具"""
        response = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if "error" in response:
            raise Exception(f"工具调用失败: {response['error']['message']}")

        # 解析结果
        content = response.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0].get("text", "{}"))
        return {}

    def stop(self) -> None:
        """停止 MCP Server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            print("MCP Server 已停止")


class MCPClientAsync:
    """
    异步 MCP 客户端 - 使用 asyncio 实现非阻塞通信
    """

    def __init__(self, server_script: str = None):
        self.server_script = server_script or __file__.replace("_demo.py", "_server.py")
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self._write_queue = asyncio.Queue()
        self._reader_task = None

    async def start(self) -> None:
        """启动 MCP Server 进程"""
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, self.server_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024  # 1MB buffer
        )
        print(f"MCP Server 已启动，PID: {self.process.pid}")

        # 启动响应读取任务
        self._reader_task = asyncio.create_task(self._read_responses())

    async def _read_responses(self) -> None:
        """读取服务器响应"""
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break

                response = json.loads(line.decode().strip())
                print(f"收到响应: {response.get('id')}")
        except Exception as e:
            print(f"读取响应出错: {e}")

    async def _send_request(self, method: str, params: Dict = None) -> Dict:
        """发送 JSON-RPC 请求"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        # 发送请求
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        await self.process.stdin.drain()

        # 等待响应（简化实现，实际需要匹配 request_id）
        # 这里使用轮询方式
        import time
        start = time.time()
        while time.time() - start < 30:
            line = await self.process.stdout.readline()
            if line:
                response = json.loads(line.decode().strip())
                if response.get("id") == self.request_id:
                    return response
            await asyncio.sleep(0.1)

        raise Exception("请求超时")

    async def get_tools(self) -> list:
        """获取可用工具列表"""
        response = await self._send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """调用工具"""
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if "error" in response:
            raise Exception(f"工具调用失败: {response['error']['message']}")

        content = response.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0].get("text", "{}"))
        return {}

    async def stop(self) -> None:
        """停止 MCP Server"""
        if self._reader_task:
            self._reader_task.cancel()
        if self.process:
            self.process.terminate()
            await self.process.wait()
            print("MCP Server 已停止")


# ==================== 示例函数 ====================

def example_basic_usage():
    """示例1: 基础使用 - 同步模式"""
    print("=" * 50)
    print("示例1: 基础使用 - 同步模式")
    print("=" * 50)

    # 注意：实际使用时需要先启动 MCP Server
    # 这里演示如何通过 MCP 协议调用

    script = """
    场景：咖啡店门口，雨天
    人物：林小雨（20岁，学生）
    动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
    """

    # 模拟 MCP 调用
    print(f"剧本内容: {script[:100]}...")
    print("\n通过 MCP 工具 breakdown_script 调用...")

    # 实际调用代码（需要 MCP 客户端）
    # client = MCPClient()
    # client.start()
    # result = client.call_tool("breakdown_script", {
    #     "script": script,
    #     "language": "zh",
    #     "wait": True,
    #     "timeout": 60
    # })
    # print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    # client.stop()

    print("\n[模拟] 任务已提交，返回结果:")
    print("""
    {
        "task_id": "TSK202603301200001234",
        "status": "success",
        "success": true,
        "data": {
            "instructions": {
                "project_info": {...},
                "fragments": [...]
            }
        }
    }
    """)


def example_async_usage():
    """示例2: 异步使用 - 提交后查询状态"""
    print("\n" + "=" * 50)
    print("示例2: 异步使用 - 提交后查询状态")
    print("=" * 50)

    script = """
    场景：城市街角，雨后初晴
    人物：陈阳（22岁，外卖员）
    动作：陈阳骑着电动车冲进雨幕，刹车太急差点撞上长椅
    """

    print(f"剧本内容: {script[:100]}...")
    print("\n步骤1: 异步提交任务")
    print("调用 breakdown_script (wait=false)")

    # 实际调用代码
    # client = MCPClient()
    # client.start()
    # result = client.call_tool("breakdown_script", {
    #     "script": script,
    #     "language": "zh",
    #     "wait": False
    # })
    # task_id = result.get("task_id")
    # print(f"任务已提交，task_id: {task_id}")
    #
    # print("\n步骤2: 轮询任务状态")
    # import time
    # while True:
    #     status = client.call_tool("get_task_status", {"task_id": task_id})
    #     print(f"状态: {status.get('status')}, 进度: {status.get('progress')}%")
    #     if status.get("status") in ["completed", "failed"]:
    #         break
    #     time.sleep(1)
    #
    # print("\n步骤3: 获取任务结果")
    # result = client.call_tool("get_task_result", {"task_id": task_id})
    # print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    # client.stop()

    print("\n[模拟] 异步流程:")
    print("""
    1. 任务已提交，task_id: TSK202603301200002345
    2. 轮询状态: processing (30%) -> processing (60%) -> completed (100%)
    3. 获取结果成功
    """)


def example_batch_processing():
    """示例3: 批量处理多个剧本"""
    print("\n" + "=" * 50)
    print("示例3: 批量处理多个剧本")
    print("=" * 50)

    scripts = [
        "场景1: 办公室，小李在写代码，突然接到电话",
        "场景2: 咖啡店，小雨在读书，阳光透过窗户",
        "场景3: 公园，老人在散步，夕阳西下"
    ]

    print(f"批量处理 {len(scripts)} 个剧本")
    print("\n方式1: 串行处理")
    print("for script in scripts:")
    print("    result = client.call_tool('breakdown_script', {'script': script, 'wait': True})")

    print("\n方式2: 并行处理（分别提交）")
    print("task_ids = []")
    print("for script in scripts:")
    print("    result = client.call_tool('breakdown_script', {'script': script, 'wait': False})")
    print("    task_ids.append(result['task_id'])")
    print("\n# 等待所有任务完成")
    print("for task_id in task_ids:")
    print("    while True:")
    print("        status = client.call_tool('get_task_status', {'task_id': task_id})")
    print("        if status['status'] in ['completed', 'failed']:")
    print("            break")
    print("        time.sleep(1)")


def example_task_management():
    """示例4: 任务管理"""
    print("\n" + "=" * 50)
    print("示例4: 任务管理")
    print("=" * 50)

    print("1. 列出所有任务:")
    print("   result = client.call_tool('list_tasks', {'limit': 10})")
    print("   for task in result['tasks']:")
    print("       print(f\"{task['task_id']}: {task['status']}\")")

    print("\n2. 按状态筛选:")
    print("   result = client.call_tool('list_tasks', {'status_filter': 'processing'})")

    print("\n3. 取消任务:")
    print("   result = client.call_tool('cancel_task', {'task_id': 'TSK123'})")
    print("   if result['cancelled']:")
    print("       print('任务已取消')")


def example_monitoring():
    """示例5: 监控队列状态"""
    print("\n" + "=" * 50)
    print("示例5: 监控队列状态")
    print("=" * 50)

    print("1. 获取队列状态:")
    print("   queue = client.call_tool('get_queue_status', {})")
    print("   print(f\"队列长度: {queue['queue_length']}\")")
    print("   print(f\"活跃任务: {queue['active_tasks']}\")")
    print("   print(f\"最大并发: {queue['max_concurrent']}\")")

    print("\n2. 获取统计信息:")
    print("   stats = client.call_tool('get_stats', {})")
    print("   print(f\"总提交: {stats['total_submitted']}\")")
    print("   print(f\"已完成: {stats['total_completed']}\")")
    print("   print(f\"失败数: {stats['total_failed']}\")")


def example_async_client():
    """示例6: 异步客户端使用"""
    print("\n" + "=" * 50)
    print("示例6: 异步客户端使用")
    print("=" * 50)

    async def demo():
        client = MCPClientAsync()
        await client.start()

        try:
            # 获取工具列表
            tools = await client.get_tools()
            print(f"可用工具: {[t['name'] for t in tools]}")

            # 提交任务
            script = "测试剧本：一个简单的场景"
            result = await client.call_tool("breakdown_script", {
                "script": script,
                "language": "zh",
                "wait": True,
                "timeout": 30
            })
            print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")

        finally:
            await client.stop()

    # 运行异步示例（注释掉，避免实际运行）
    # asyncio.run(demo())
    print("异步客户端示例已准备，使用 asyncio.run(demo()) 运行")


def example_claude_integration():
    """示例7: Claude Desktop 集成配置"""
    print("\n" + "=" * 50)
    print("示例7: Claude Desktop 集成配置")
    print("=" * 50)

    config = {
        "mcpServers": {
            "penshot": {
                "command": "python",
                "args": [
                    "-m",
                    "penshot.mcp_server",
                    "--max-concurrent",
                    "5",
                    "--queue-size",
                    "500"
                ]
            }
        }
    }

    print("将以下配置添加到 Claude Desktop 的配置文件中:")
    print("\n配置文件位置:")
    print("- Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    print("- macOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("- Linux: ~/.config/Claude/claude_desktop_config.json")

    print("\n配置内容:")
    print(json.dumps(config, ensure_ascii=False, indent=2))

    print("\n配置后，在 Claude 中可以直接使用:")
    print("- \"请帮我将这个剧本拆分为分镜：...\"")
    print("- \"查询任务状态：TSK202603301200001234\"")
    print("- \"获取任务结果：TSK202603301200001234\"")


def example_cursor_integration():
    """示例8: Cursor IDE 集成配置"""
    print("\n" + "=" * 50)
    print("示例8: Cursor IDE 集成配置")
    print("=" * 50)

    config = {
        "mcpServers": {
            "penshot": {
                "command": "python",
                "args": ["-m", "penshot.mcp_server"]
            }
        }
    }

    print("Cursor 配置文件位置: ~/.cursor/mcp.json")
    print("\n配置内容:")
    print(json.dumps(config, ensure_ascii=False, indent=2))

    print("\n配置后，在 Cursor 的 AI 对话中可以直接调用 Penshot 功能")


def example_workflow():
    """示例9: 完整工作流示例"""
    print("\n" + "=" * 50)
    print("示例9: 完整工作流示例")
    print("=" * 50)

    workflow = """
# 完整工作流示例

1. 提交剧本任务
   task_id = client.call_tool("breakdown_script", {
       "script": "长剧本内容...",
       "wait": False
   })["task_id"]

2. 获取任务状态
   while True:
       status = client.call_tool("get_task_status", {"task_id": task_id})
       if status["status"] == "completed":
           break
       elif status["status"] == "failed":
           print(f"任务失败: {status['error_message']}")
           return
       time.sleep(1)

3. 获取结果
   result = client.call_tool("get_task_result", {"task_id": task_id})
   
4. 处理结果
   instructions = result["data"]["instructions"]
   for fragment in instructions["fragments"]:
       print(f"片段 {fragment['fragment_id']}: {fragment['prompt'][:100]}...")
       print(f"音频: {fragment.get('audio_prompt', {}).get('prompt', '无')[:100]}...")
   
5. 监控队列
   queue = client.call_tool("get_queue_status", {})
   print(f"队列状态: 当前 {queue['queue_length']} 个任务等待中")
   
6. 清理
   # 可选：删除已完成的任务（需要实现）
   # client.call_tool("delete_task", {"task_id": task_id})
"""
    print(workflow)


# ==================== 主函数 ====================

def main():
    """主函数 - 运行所有示例"""
    print("\n" + "=" * 60)
    print("Penshot MCP Server 使用示例")
    print("=" * 60)

    # 运行所有示例
    example_basic_usage()
    example_async_usage()
    example_batch_processing()
    example_task_management()
    example_monitoring()
    example_async_client()
    example_claude_integration()
    example_cursor_integration()
    example_workflow()

    print("\n" + "=" * 60)
    print("示例运行完成")
    print("=" * 60)

    print("\n提示: 实际使用时需要先启动 MCP Server")
    print("启动命令: python -m penshot.mcp_server")
    print("或: penshot-mcp-server")
    print("\n然后在客户端中通过 MCP 协议调用工具")


if __name__ == "__main__":
    main()
