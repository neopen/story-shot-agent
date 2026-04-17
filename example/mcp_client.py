"""
@FileName: mcp_client.py
@Description: MCP Client 测试脚本 - Windows 兼容版
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30
"""

import json
import re
import subprocess
import sys
import time
from typing import Optional


class MCPClient:
    """MCP 客户端 - 同步版本，Windows 兼容"""

    def __init__(self, server_module: str = "penshot.mcp_server"):
        self.server_module = server_module
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

    def start(self):
        """启动 MCP Server 子进程"""
        cmd = [sys.executable, "-m", self.server_module]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        print(f"MCP Server 已启动，PID: {self.process.pid}")
        time.sleep(2)

    def _clean_ansi(self, text: str) -> str:
        """清理 ANSI 转义码"""
        return self._ansi_escape.sub('', text)

    def read_json_response(self, timeout: float = 30) -> Optional[dict]:
        """读取 JSON 响应，跳过非 JSON 行并清理 ANSI 转义码"""

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 检查是否有数据可读（非阻塞）
                import msvcrt
                if msvcrt.kbhit():
                    pass
            except:
                pass

            # 使用非阻塞方式读取
            try:
                # Windows 上不能直接 select 管道，使用轮询方式
                line = self.process.stdout.readline()
                if line:
                    cleaned_line = self._clean_ansi(line).strip()
                    if cleaned_line and cleaned_line.startswith('{'):
                        try:
                            return json.loads(cleaned_line)
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

            # 短暂休眠，避免 CPU 占用过高
            time.sleep(0.05)

        return None

    def _call(self, method: str, params: dict = None) -> dict:
        """调用 MCP 方法"""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        # 发送请求
        request_str = json.dumps(request, ensure_ascii=False)
        try:
            self.process.stdin.write(request_str + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            raise Exception("Server 进程已断开")

        # 读取响应
        response = self.read_json_response()
        if response is None:
            stderr = self.process.stderr.read()
            raise Exception(f"Server 无响应: {stderr}")

        return response

    def get_tools(self) -> list:
        """获取工具列表"""
        result = self._call("tools/list")
        return result.get("result", {}).get("tools", [])

    def breakdown_script(self, script: str, language: str = "zh", wait: bool = False, timeout: int = 300) -> dict:
        """拆分剧本"""
        result = self._call("tools/call", {
            "name": "breakdown_script",
            "arguments": {
                "script": script.strip(),
                "language": language,
                "wait": wait,
                "timeout": timeout
            }
        })

        print(f"   [DEBUG] 原始响应: {result}")

        if "error" in result:
            raise Exception(result["error"]["message"])

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            text_content = content[0]["text"]
            try:
                parsed = json.loads(text_content)
                print(f"   [DEBUG] 解析后: {parsed}")
                return parsed
            except json.JSONDecodeError:
                print(f"   [DEBUG] JSON解析失败，原始文本: {text_content}")
                return {}
        return {}

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        result = self._call("tools/call", {
            "name": "get_task_status",
            "arguments": {"task_id": task_id}
        })

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return {}

    def get_task_result(self, task_id: str) -> dict:
        """获取任务结果"""
        result = self._call("tools/call", {
            "name": "get_task_result",
            "arguments": {"task_id": task_id}
        })

        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return {}

    def stop(self):
        """停止 Server"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print("MCP Server 已停止")


def main():
    """测试主函数"""
    script = """
    场景：咖啡店门口，雨天
    人物：林小雨（20岁，学生）
    动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
    """

    print("=" * 50)
    print("MCP 客户端测试")
    print("=" * 50)

    client = MCPClient()

    try:
        client.start()

        # 获取工具列表
        print("\n1. 获取工具列表...")
        tools = client.get_tools()
        print(f"   可用工具: {[t['name'] for t in tools]}")

        # 提交任务
        print("\n2. 提交任务...")
        result = client.breakdown_script(script, wait=False)
        print(f"   返回结果: {result}")
        task_id = result.get("task_id")

        # 轮询状态
        print("\n3. 等待任务完成...")
        max_attempts = 60
        for i in range(max_attempts):
            try:
                status = client.get_task_status(task_id)
                state = status.get("status")
                progress = status.get("progress", 0)
                print(f"   状态: {state}, 进度: {progress}%")
                if state in ["completed", "failed", "success"]:
                    break
            except Exception as e:
                print(f"   获取状态出错: {e}")
            time.sleep(2)

        # 获取结果
        print("\n4. 获取结果...")
        result = client.get_task_result(task_id)

        if result.get("success"):
            data = result.get("data", {})
            instructions = data.get("instructions", {})
            fragments = instructions.get("fragments", [])

            print(f"\n   ✓ 拆分完成!")
            print(f"   片段数: {len(fragments)}")
            print(f"   总时长: {instructions.get('project_info', {}).get('total_duration', 0)} 秒")
            print(f"   处理时间: {result.get('processing_time_ms', 0)} ms")
            if fragments:
                print(f"\n   片段预览:")
                for i, frag in enumerate(fragments[:3], 1):
                    prompt = frag.get("prompt", "")[:100]
                    print(f"     {i}. {prompt}...")
        else:
            print(f"   ✗ 失败: {result.get('error')}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.stop()


if __name__ == "__main__":
    main()
