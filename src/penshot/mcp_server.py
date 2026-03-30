"""
@FileName: mcp_server.py
@Description: MCP Server - 所有日志输出到 stderr
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/23 18:39
"""

import json
import logging
import sys

def setLog():
    # 重定向所有日志到 stderr
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 禁用其他模块的日志输出
    logging.getLogger("PenShot").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class PenshotMCPServer:
    """Penshot MCP Server"""

    def __init__(self, max_concurrent: int = 10, queue_size: int = 1000):
        # 延迟导入
        from penshot.api.function_calls import create_penshot_agent
        from penshot.neopen.shot_language import Language

        setLog()

        # 所有初始化日志输出到 stderr
        sys.stderr.write(f"Penshot MCP Server initializing...\n")
        sys.stderr.flush()

        self.penshot = create_penshot_agent(
            max_concurrent=max_concurrent,
            queue_size=queue_size,
            language=Language.ZH
        )
        self.task_manager = self.penshot.task_manager
        self._tools: dict = {}
        self._register_tools()

        sys.stderr.write(f"Penshot MCP Server ready\n")
        sys.stderr.flush()

    def _register_tools(self):
        """注册 MCP 工具"""
        self._tools = {
            "breakdown_script": {
                "description": "将剧本拆分为分镜序列",
                "handler": self._handle_breakdown_script
            },
            "get_task_status": {
                "description": "获取任务状态",
                "handler": self._handle_get_task_status
            },
            "get_task_result": {
                "description": "获取任务结果",
                "handler": self._handle_get_task_result
            },
            "cancel_task": {
                "description": "取消任务",
                "handler": self._handle_cancel_task
            },
            "list_tasks": {
                "description": "列出任务",
                "handler": self._handle_list_tasks
            },
            "get_queue_status": {
                "description": "获取队列状态",
                "handler": self._handle_get_queue_status
            },
            "get_stats": {
                "description": "获取统计信息",
                "handler": self._handle_get_stats
            }
        }

    def get_tools_list(self) -> list:
        return [
            {
                "name": name,
                "description": tool["description"],
                "parameters": {"type": "object", "properties": {}}
            }
            for name, tool in self._tools.items()
        ]

    def _handle_breakdown_script(self, arguments: dict) -> dict:
        from penshot.neopen.shot_language import Language
        from penshot.neopen.task.task_models import TaskStatus

        script = arguments.get("script")
        if not script:
            raise ValueError("script is required")

        language = arguments.get("language", "zh")
        wait = arguments.get("wait", False)
        timeout = arguments.get("timeout", 300)
        lang = Language.ZH if language == "zh" else Language.EN

        if wait:
            result = self.penshot.breakdown_script(script, lang, wait_timeout=timeout)
            return {
                "task_id": result.task_id,
                "status": result.status,
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "processing_time_ms": result.processing_time_ms
            }
        else:
            task_id = self.penshot.breakdown_script_async(script, lang)
            return {
                "task_id": task_id,
                "status": TaskStatus.PENDING,
                "message": "任务已提交"
            }

    def _handle_get_task_status(self, arguments: dict) -> dict:
        """获取任务状态"""
        task_id = arguments.get("task_id")
        if not task_id:
            raise ValueError("task_id is required")

        status = self.penshot.get_task_status(task_id)
        if not status:
            return {"task_id": task_id, "status": "not_found"}

        # 转换 datetime 对象为字符串
        result = {}
        for key, value in status.items():
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    def _handle_get_task_result(self, arguments: dict) -> dict:
        """获取任务结果"""
        task_id = arguments.get("task_id")
        if not task_id:
            raise ValueError("task_id is required")

        result = self.penshot.get_task_result(task_id)
        if not result:
            return {"task_id": task_id, "status": "not_found"}

        # 转换 datetime 对象为字符串
        def convert_datetime(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return obj

        result_dict = {
            "task_id": result.task_id,
            "success": result.success,
            "status": result.status,
            "data": result.data,
            "error": result.error,
            "processing_time_ms": result.processing_time_ms
        }

        # 处理可能存在的 datetime
        if hasattr(result, 'created_at') and result.created_at:
            result_dict["created_at"] = convert_datetime(result.created_at)
        if hasattr(result, 'completed_at') and result.completed_at:
            result_dict["completed_at"] = convert_datetime(result.completed_at)

        return result_dict

    def _handle_cancel_task(self, arguments: dict) -> dict:
        task_id = arguments.get("task_id")
        if not task_id:
            raise ValueError("task_id is required")

        success = self.penshot.cancel_task(task_id)
        return {"task_id": task_id, "cancelled": success}

    def _handle_list_tasks(self, arguments: dict) -> dict:
        limit = arguments.get("limit", 20)
        task_ids = self.task_manager.list_tasks() if hasattr(self.task_manager, 'list_tasks') else []
        tasks = []
        for task_id in task_ids[:limit]:
            status = self.penshot.get_task_status(task_id)
            if status:
                tasks.append({
                    "task_id": task_id,
                    "status": status.get("status"),
                    "stage": status.get("stage"),
                    "progress": status.get("progress"),
                    "created_at": status.get("created_at")
                })
        return {"total": len(tasks), "limit": limit, "tasks": tasks}

    def _handle_get_queue_status(self, arguments: dict) -> dict:
        return self.penshot.get_queue_status()

    def _handle_get_stats(self, arguments: dict) -> dict:
        return self.penshot.get_stats()

    def run(self):
        """运行服务器"""
        while True:
            try:
                # 读取请求
                line = sys.stdin.buffer.readline()
                if not line:
                    break

                request = json.loads(line.decode('utf-8'))
                request_id = request.get("id")
                method = request.get("method")
                params = request.get("params", {})

                # 处理请求
                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": self.get_tools_list()}
                    }
                elif method == "tools/call":
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    tool = self._tools.get(tool_name)

                    if tool:
                        try:
                            handler_result = tool["handler"](arguments)
                            response = {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "result": {
                                    "content": [{
                                        "type": "text",
                                        "text": json.dumps(handler_result, ensure_ascii=False)
                                    }]
                                }
                            }
                        except Exception as e:
                            response = {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "error": {"code": -32000, "message": str(e)}
                            }
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
                        }
                elif method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "0.1.0",
                            "serverInfo": {"name": "penshot-mcp-server", "version": "1.0.0"},
                            "capabilities": {"tools": {}}
                        }
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}
                    }

                # 只输出 JSON 到 stdout
                sys.stdout.buffer.write((json.dumps(response) + "\n").encode('utf-8'))
                sys.stdout.buffer.flush()

            except json.JSONDecodeError as e:
                sys.stderr.write(f"JSON decode error: {e}\n")
                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.stderr.flush()


def run_mcp_server(max_concurrent: int = 10, queue_size: int = 1000):
    """启动 MCP 服务器"""
    server = PenshotMCPServer(max_concurrent=max_concurrent, queue_size=queue_size)
    server.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Penshot MCP Server")
    parser.add_argument("--max-concurrent", type=int, default=10)
    parser.add_argument("--queue-size", type=int, default=1000)
    args = parser.parse_args()
    run_mcp_server(max_concurrent=args.max_concurrent, queue_size=args.queue_size)
