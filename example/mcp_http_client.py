"""
@FileName: mcp_http_client.py
@Description: HTTP MCP 客户端测试
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30 17:19
"""

import time

import requests


class HTTPMCPClient:
    """HTTP MCP 客户端"""

    def __init__(self, base_url: str = "http://127.0.0.1:8888"):
        self.base_url = base_url

    def get_tools(self) -> list:
        """获取工具列表"""
        resp = requests.get(f"{self.base_url}/tools")
        return resp.json().get("tools", [])

    def breakdown_script(self, script: str, language: str = "zh", wait: bool = False, timeout: int = 300) -> dict:
        """拆分剧本"""
        resp = requests.post(
            f"{self.base_url}/tools/breakdown_script",
            json={
                "script": script,
                "language": language,
                "wait": wait,
                "timeout": timeout
            }
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        resp = requests.post(
            f"{self.base_url}/tools/get_task_status",
            json={"task_id": task_id}
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_result(self, task_id: str) -> dict:
        """获取任务结果"""
        resp = requests.post(
            f"{self.base_url}/tools/get_task_result",
            json={"task_id": task_id}
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_task(self, task_id: str) -> dict:
        """取消任务"""
        resp = requests.post(
            f"{self.base_url}/tools/cancel_task",
            json={"task_id": task_id}
        )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, status_filter: str = None, limit: int = 20) -> dict:
        """列出任务"""
        resp = requests.post(
            f"{self.base_url}/tools/list_tasks",
            json={"status_filter": status_filter, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    def get_queue_status(self) -> dict:
        """获取队列状态"""
        resp = requests.get(f"{self.base_url}/tools/queue_status")
        resp.raise_for_status()
        return resp.json()

    def get_stats(self) -> dict:
        """获取统计信息"""
        resp = requests.get(f"{self.base_url}/tools/stats")
        resp.raise_for_status()
        return resp.json()


def main():
    """测试主函数"""
    script = """
    场景：咖啡店门口，雨天
    人物：林小雨（20岁，学生）
    动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
    """

    print("=" * 60)
    print("HTTP MCP 客户端测试")
    print("=" * 60)

    client = HTTPMCPClient()

    try:
        # 1. 获取工具列表
        print("\n1. 获取工具列表...")
        tools = client.get_tools()
        print(f"   可用工具: {[t['name'] for t in tools]}")

        # 2. 提交任务
        print("\n2. 提交任务...")
        result = client.breakdown_script(script, wait=False)
        task_id = result["task_id"]
        print(f"   任务ID: {task_id}")
        print(f"   状态: {result['status']}")

        # 3. 轮询状态
        print("\n3. 等待任务完成...")
        while True:
            status = client.get_task_status(task_id)
            print(f"   状态: {status['status']}, 进度: {status.get('progress', 0)}%")
            if status["status"] in ["completed", "failed", "success"]:
                break
            time.sleep(2)

        # 4. 获取结果
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
            print(f"\n   片段预览:")
            for i, frag in enumerate(fragments[:3], 1):
                prompt = frag.get("prompt", "")[:100]
                print(f"     {i}. {prompt}...")
        else:
            print(f"   ✗ 失败: {result.get('error')}")

        # 5. 获取队列状态
        print("\n5. 获取队列状态...")
        queue = client.get_queue_status()
        print(f"   队列长度: {queue.get('queue_length', 0)}")
        print(f"   活跃任务: {queue.get('active_tasks', 0)}")
        print(f"   最大并发: {queue.get('max_concurrent', 0)}")

        # 6. 获取统计信息
        print("\n6. 获取统计信息...")
        stats = client.get_stats()
        print(f"   总提交: {stats.get('total_submitted', 0)}")
        print(f"   已完成: {stats.get('total_completed', 0)}")
        print(f"   失败数: {stats.get('total_failed', 0)}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
