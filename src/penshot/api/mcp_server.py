"""
@FileName: mcp_server.py
@Description: MCP (Model Context Protocol) Server，支持 Claude、Cursor 等 MCP 兼容智能体调用
@Author: HiPeng
@Time: 2026/3/23 18:39
"""

import asyncio
import json
import sys
from typing import Dict, Any

from penshot.api.function_calls import create_penshot_agent, PenshotFunction
from penshot.logger import info, error, log_with_context
from penshot.neopen.shot_language import Language
from penshot.neopen.task.task_models import TaskStatus


class PenshotMCPServer:
    """
    Penshot MCP Server

    使用 PenshotFunction（基于 TaskFactory）进行任务管理
    支持 MCP 协议的工具调用
    """

    def __init__(
            self,
            max_concurrent: int = 10,
            queue_size: int = 1000
    ):
        """
        初始化 MCP Server

        Args:
            max_concurrent: 最大并发数
            queue_size: 队列大小
        """
        # 使用统一的 PenshotFunction（内部使用 TaskFactory）
        self.penshot: PenshotFunction = create_penshot_agent(
            max_concurrent=max_concurrent,
            queue_size=queue_size,
            language=Language.ZH
        )

        # 保持兼容性
        self.task_manager = self.penshot.task_manager
        self._tools: Dict[str, Dict] = {}
        self._register_tools()

        info(f"Penshot MCP Server 初始化完成，最大并发: {max_concurrent}")

    def _register_tools(self):
        """注册 MCP 工具"""

        self._tools["breakdown_script"] = {
            "description": "将剧本拆分为分镜序列。提交剧本后立即返回任务ID，可后续查询状态和结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "剧本文本内容，支持自然语言描述"
                    },
                    "language": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "输出语言，默认为中文",
                        "default": "zh"
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "是否等待完成（同步模式），默认为false",
                        "default": False
                    },
                    "timeout": {
                        "type": "number",
                        "description": "等待超时时间（秒），仅在wait=true时生效",
                        "default": 300
                    }
                },
                "required": ["script"]
            },
            "handler": self._handle_breakdown_script
        }

        self._tools["get_task_status"] = {
            "description": "获取分镜生成任务的状态，包括进度、阶段等信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID，由 breakdown_script 返回"
                    }
                },
                "required": ["task_id"]
            },
            "handler": self._handle_get_task_status
        }

        self._tools["get_task_result"] = {
            "description": "获取任务的结果，包括分镜序列、镜头信息等",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            },
            "handler": self._handle_get_task_result
        }

        self._tools["cancel_task"] = {
            "description": "取消正在执行或等待中的任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            },
            "handler": self._handle_cancel_task
        }

        self._tools["list_tasks"] = {
            "description": "列出所有任务的状态摘要",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["pending", "processing", "completed", "failed"],
                        "description": "按状态筛选，可选"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制",
                        "default": 20
                    }
                }
            },
            "handler": self._handle_list_tasks
        }

        self._tools["get_queue_status"] = {
            "description": "获取任务队列状态，包括队列长度、活跃任务数等",
            "parameters": {
                "type": "object",
                "properties": {}
            },
            "handler": self._handle_get_queue_status
        }

        self._tools["get_stats"] = {
            "description": "获取服务器统计信息，包括总提交数、完成数、失败数等",
            "parameters": {
                "type": "object",
                "properties": {}
            },
            "handler": self._handle_get_stats
        }

    def get_tools_list(self) -> list:
        """获取工具列表（MCP协议要求）"""
        return [
            {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
            for name, tool in self._tools.items()
        ]

    async def call_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        """调用工具（MCP协议要求）"""
        if tool_name not in self._tools:
            return {
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self._tools.keys())
            }

        tool = self._tools[tool_name]
        try:
            result = await tool["handler"](arguments)
            return {"success": True, "result": result}
        except Exception as e:
            error(f"工具调用失败: {tool_name}, 错误: {str(e)}")
            return {"success": False, "error": str(e)}

    # ==================== 工具处理器 ====================

    async def _handle_breakdown_script(self, arguments: Dict) -> Dict:
        """处理剧本分镜拆分"""
        script = arguments.get("script")
        language = arguments.get("language", "zh")
        wait = arguments.get("wait", False)
        timeout = arguments.get("timeout", 300)

        if not script:
            raise ValueError("script is required")

        lang = Language.ZH if language == "zh" else Language.EN

        if wait:
            # 同步模式：等待完成
            result = self.penshot.breakdown_script(
                script_text=script,
                language=lang,
                wait_timeout=timeout
            )

            return {
                "task_id": result.task_id,
                "status": result.status,
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "processing_time_ms": result.processing_time_ms
            }
        else:
            # 异步模式：立即返回任务ID
            task_id = self.penshot.breakdown_script_async(
                script_text=script,
                language=lang
            )

            return {
                "task_id": task_id,
                "status": TaskStatus.PENDING,
                "message": "任务已提交，请使用 get_task_status 查询进度，使用 get_task_result 获取结果"
            }

    async def _handle_get_task_status(self, arguments: Dict) -> Dict:
        """获取任务状态"""
        task_id = arguments.get("task_id")

        if not task_id:
            raise ValueError("task_id is required")

        status = self.penshot.get_task_status(task_id)

        if not status:
            return {
                "task_id": task_id,
                "status": TaskStatus.NOT_FOUND,
                "message": f"任务不存在: {task_id}"
            }

        return {
            "task_id": task_id,
            "status": status.get("status"),
            "stage": status.get("stage"),
            "progress": status.get("progress"),
            "created_at": status.get("created_at"),
            "updated_at": status.get("updated_at"),
            "error_message": status.get("error")
        }

    async def _handle_get_task_result(self, arguments: Dict) -> Dict:
        """获取任务结果"""
        task_id = arguments.get("task_id")

        if not task_id:
            raise ValueError("task_id is required")

        result = self.penshot.get_task_result(task_id)

        if not result:
            return {
                "task_id": task_id,
                "status": TaskStatus.NOT_FOUND,
                "message": f"任务不存在: {task_id}"
            }

        # 任务还在处理中
        if result.status in ["pending", "processing"]:
            return {
                "task_id": result.task_id,
                "status": result.status,
                "message": f"任务仍在处理中，请稍后再试",
                "processing_time_ms": result.processing_time_ms
            }

        return {
            "task_id": result.task_id,
            "success": result.success,
            "status": result.status,
            "data": result.data,
            "error": result.error,
            "processing_time_ms": result.processing_time_ms
        }

    async def _handle_cancel_task(self, arguments: Dict) -> Dict:
        """取消任务"""
        task_id = arguments.get("task_id")

        if not task_id:
            raise ValueError("task_id is required")

        # 先检查任务状态
        status = self.penshot.get_task_status(task_id)
        if not status:
            return {
                "task_id": task_id,
                "cancelled": False,
                "message": f"任务不存在: {task_id}"
            }

        if status.get("status").is_completed():
            return {
                "task_id": task_id,
                "cancelled": False,
                "message": f"任务已结束，无法取消: {status.get('status')}"
            }

        success = self.penshot.cancel_task(task_id)

        return {
            "task_id": task_id,
            "cancelled": success,
            "message": "任务已取消" if success else "取消失败"
        }

    async def _handle_list_tasks(self, arguments: Dict) -> Dict:
        """列出任务列表"""
        status_filter = arguments.get("status_filter")
        limit = arguments.get("limit", 20)

        # 获取任务列表（从 TaskManager 获取）
        task_ids = self.task_manager.list_tasks() if hasattr(self.task_manager, 'list_tasks') else []

        tasks = []
        for task_id in task_ids[:limit]:
            status = self.penshot.get_task_status(task_id)
            if status:
                if status_filter and status.get("status") != status_filter:
                    continue
                tasks.append({
                    "task_id": task_id,
                    "status": status.get("status"),
                    "stage": status.get("stage"),
                    "progress": status.get("progress"),
                    "created_at": status.get("created_at")
                })

        return {
            "total": len(tasks),
            "limit": limit,
            "tasks": tasks
        }

    async def _handle_get_queue_status(self, arguments: Dict) -> Dict:
        """获取队列状态"""
        return self.penshot.get_queue_status()

    async def _handle_get_stats(self, arguments: Dict) -> Dict:
        """获取统计信息"""
        return self.penshot.get_stats()

    # ==================== 服务器启动 ====================

    def create_stdio_server(self):
        """创建标准输入输出服务器（用于 Claude Desktop 等）"""

        async def handle_request(request: Dict) -> Dict:
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            log_with_context("DEBUG", f"MCP请求", {"method": method, "id": request_id})

            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": self.get_tools_list()
                    }
                }
                return response

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await self.call_tool(tool_name, arguments)

                if result.get("success"):
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result.get("result", {}), ensure_ascii=False, indent=2)
                                }
                            ]
                        }
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32000,
                            "message": result.get("error", "Unknown error")
                        }
                    }
                return response

            elif method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "0.1.0",
                        "serverInfo": {
                            "name": "penshot-mcp-server",
                            "version": "0.1.0"
                        },
                        "capabilities": {
                            "tools": {}
                        }
                    }
                }
                return response

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

        async def main():
            info("Penshot MCP Server 启动，等待连接...")

            while True:
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line)
                    response = await handle_request(request)
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                except json.JSONDecodeError as e:
                    error(f"JSON解析错误: {str(e)}")
                    sys.stderr.write(f"Error: Invalid JSON: {str(e)}\n")
                except Exception as e:
                    error(f"处理请求错误: {str(e)}")
                    sys.stderr.write(f"Error: {str(e)}\n")

        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            info("MCP Server 已停止")
        finally:
            self._cleanup()

    def _cleanup(self):
        """清理资源"""
        try:
            self.penshot.shutdown()
        except Exception as e:
            error(f"清理资源时发生错误: {str(e)}")


def run_mcp_server(
        max_concurrent: int = 10,
        queue_size: int = 1000
):
    """
    启动 MCP 服务器（命令行入口）

    Args:
        max_concurrent: 最大并发数
        queue_size: 队列大小
    """
    server = PenshotMCPServer(
        max_concurrent=max_concurrent,
        queue_size=queue_size
    )
    server.create_stdio_server()


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Penshot MCP Server")
    parser.add_argument("--max-concurrent", type=int, default=10, help="最大并发数")
    parser.add_argument("--queue-size", type=int, default=1000, help="队列大小")

    args = parser.parse_args()

    run_mcp_server(
        max_concurrent=args.max_concurrent,
        queue_size=args.queue_size
    )
