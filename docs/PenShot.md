# PenShot - 剧本分镜智能体

一个基于多智能体协作的剧本分镜系统，能够将任意格式剧本自动拆分为AI可生成的短视频脚本单元。

## 概述

PenShot 是一个智能剧本分镜工具，能够将用户提供的原始自然语言剧本，自动拆分为多个**n秒长度的短视频片段脚本**，并确保**画面连贯性、角色一致性、动作延续性**，适用于主流 AI 视频生成模型（如 Runway、Pika、Sora、Wan、Stable Video等）。

### 核心挑战

当前 AI 视频模型仅支持生成 5-10 秒的视频，要生成完整视频只能通过拼接多个片段实现。PenShot 解决了这个问题的第一步：**智能拆分剧本，确保每个片段符合模型时长限制，同时保持视觉和叙事的连贯性**。

### 主要特性

- **智能剧本解析**：自动识别场景、对话和动作指令
- **精准时序规划**：按镜头粒度智能切分内容，分配合理时长
- **连续性守护**：确保相邻分镜间角色状态、场景和情节的一致性
- **高质量分镜生成**：生成详细的中文画面描述和英文 AI 视频提示词
- **音频提示词支持**：为每个分镜生成对应的环境音和声音设计提示词
- **多模型支持**：兼容 OpenAI、Qwen、DeepSeek、Ollama 等多种 AI 提供商
- **多种集成方式**：支持 Python 库、REST API、MCP、LangGraph 节点、A2A 系统

## 快速开始

### 安装

```sh
pip install penshot
```

如需使用特定 LLM 提供商，安装对应依赖：

```python
# OpenAI / DeepSeek
pip install langchain-openai

# 通义千问
pip install dashscope
```

### 环境配置

创建 `.env` 文件配置 LLM：

```properties
########################## LLM CONFIG #########################
# Supported providers (openai, qwen, deepseek, ollama).
LLM__DEFAULT__BASE_URL=https://api.openai.com/v1
LLM__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM__DEFAULT__MODEL_NAME=gpt-4

# ================ Embedding config ================
# Supported providers（openai, qwen, HuggingFace, ollama）
EMBED__DEFAULT__BASE_URL=https://api.openai.com/v1
EMBED__DEFAULT__API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EMBED__DEFAULT__MODEL_NAME=text-embedding-v4
```

## 使用方式

### 1. Python 库直接调用

最简单的使用方式，直接作为 Python 库调用：

```python
from penshot.api import create_penshot_agent

async def async_usage():
    """异步用法示例"""
    penshot = create_penshot_agent(max_concurrent=5)

    script = """
    早晨，一个女孩在咖啡馆读书，阳光透过窗户...
    """

    # 异步提交任务
    task_id = penshot.breakdown_script_async(
        script,
        callback=lambda r: print(f"回调: 任务 {r.task_id} 完成")
    )

    # 查询状态
    status = penshot.get_task_status(task_id)
    print(f"初始状态: {status.get('status')}")

    # 等待结果
    result = await penshot.wait_for_result_async(task_id)

    print(f"最终结果: 成功={result.success}, 状态={result.status}")
```

### 2. REST API 服务

启动 API 服务：

```python
python -m penshot.http_server
```

提交任务：

```sh
curl -X POST http://localhost:8000/api/v1/storyboard \
  -H "Content-Type: application/json" \
  -d '{"script": "你的剧本内容..."}'
```

查询状态：

```sh
curl http://localhost:8000/api/v1/status/{task_id}
```

获取结果：

```sh
curl http://localhost:8000/api/v1/result/{task_id}
```



### 3. MCP 协议支持

Penshot 支持 MCP (Model Context Protocol)，可与 Claude Desktop、Cursor 等 MCP 兼容客户端集成。

启动 MCP Server：

```sh
python -m penshot.mcp_server
# or
python -m penshot.mcp_server --max-concurrent 5 --queue-size 500
```



#### Claude Desktop 配置

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "penshot": {
      "command": "python",
      "args": ["-m", "penshot.mcp_server"]
    }
  }
}
```

配置后，在 Claude 中直接使用自然语言调用：

```
请帮我将这个剧本拆分为分镜：
场景：咖啡店门口，雨天
人物：林小雨（20岁，学生）
动作：林小雨蹲在长椅旁，用手帕擦拭一本被雨水浸湿的诗集
```



#### Python MCP 客户端示例

```python
"""
@FileName: mcp_client.py
@Description: MCP Client 测试脚本 - Windows 兼容版
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
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
```

示例代码：[video-shot-agent/example/mcp_client.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/mcp_client.py)



### 4. LangGraph 节点集成

```python
from penshot.api import create_penshot_agent

class StoryboardWorkflowNodes:
    """分镜生成工作流节点"""

    def __init__(self):
        """
        初始化工作流节点

        Args:
            config: 全局配置
        """
        self.agent = create_penshot_agent()

    async def submit_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        提交任务节点

        提交分镜生成任务，获取 task_id
        """
        print(f"[节点] 提交任务: {state.script_text[:50]}...")

        # 创建临时智能体（或复用）
        task_id = self.agent.breakdown_script_async(
            script_text=state.script_text
        )

        return {
            "task_id_assigned": task_id,
            "stage": WorkflowStage.PARSING,
            "progress": 10.0
        }

    async def poll_task_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        轮询任务状态节点

        检查任务是否完成，更新进度
        """
        task_id = state.task_id_assigned or state.task_id

        if not task_id:
            return {
                "stage": WorkflowStage.FAILED,
                "error": "没有任务ID",
                "progress": 0
            }

        # 获取任务状态
        task = self.agent.get_task_status(task_id)

        if not task:
            return {
                "stage": WorkflowStage.FAILED,
                "error": f"任务不存在: {task_id}",
                "progress": 0
            }

        status = task.get("status")
        progress = task.get("progress", 0)

        print(f"[节点] 轮询任务: {task_id}, 状态={status}, 进度={progress}%")

        if status == "completed":
            # 获取结果
            result = self.agent.get_task_result(task_id)

            return {
                "stage": WorkflowStage.COMPLETED,
                "result": result,
                "progress": 100.0
            }

        elif status == "failed":
            return {
                "stage": WorkflowStage.FAILED,
                "error": task.get("error", "未知错误"),
                "progress": progress
            }

        else:
            # 仍在处理中
            return {
                "stage": WorkflowStage.GENERATING,
                "progress": progress
            }

    async def wait_for_result_node(self, state: StoryboardState) -> Dict[str, Any]:
        """
        等待结果节点

        阻塞等待任务完成
        """
        task_id = state.task_id_assigned or state.task_id

        if not task_id:
            return {
                "stage": WorkflowStage.FAILED,
                "error": "没有任务ID"
            }

        print(f"[节点] 等待结果: {task_id}")

        try:
            result = await self.agent.wait_for_result_async(task_id)

            if result.success:
                return {
                    "stage": WorkflowStage.COMPLETED,
                    "result": result,
                    "progress": 100.0
                }
            else:
                return {
                    "stage": WorkflowStage.FAILED,
                    "error": result.error,
                    "progress": 0
                }

        except Exception as e:
            return {
                "stage": WorkflowStage.FAILED,
                "error": str(e),
                "progress": 0
            }
```

示例代码：[video-shot-agent/example/langgraph_integration.py at main · neopen/video-shot-agent](https://github.com/neopen/video-shot-agent/blob/main/example/langgraph_integration.py)



## 输出示例

```json
{
  "task_id": "TSK202603291447329714",
  "success": true,
  "data": {
    "instructions": {
      "project_info": {
        "title": "AI视频项目",
        "total_fragments": 13,
        "total_duration": 48.0
      },
      "fragments": [
        {
          "fragment_id": "frag_001",
          "prompt": "Cinematic wide shot: overcast sky with low, heavy gray clouds; cold fine rain falling diagonally...",
          "duration": 4.0,
          "model": "runway_gen2",
          "style": "cinematic realism",
          "audio_prompt": {
            "audio_id": "audio_001",
            "prompt": "Natural rainfall as base layer — soft, steady drizzle with gentle spatial stereo spread...",
            "model_type": "AudioLDM_3"
          }
        }
      ]
    }
  },
  "processing_time_ms": 88988
}
```



## 配置参数

| 参数                    | 默认值 | 说明               |
| :---------------------- | :----- | :----------------- |
| `max_concurrent`        | 10     | 最大并发任务数     |
| `queue_size`            | 1000   | 任务队列大小       |
| `max_fragment_duration` | 5.0    | 片段最大时长（秒） |
| `min_fragment_duration` | 1.0    | 片段最小时长（秒） |
| `prompt_length_max`     | 200    | 提示词最大单词数   |
| `prompt_length_min`     | 20     | 提示词最单词数     |

## 系统要求

- Python 3.10 或更高版本
- 稳定的网络连接（用于调用 LLM API）
- 可选的 Redis（用于任务持久化）

## 相关链接

- [GitHub 仓库](https://github.com/neopen/video-shot-agent)
- [详细文档](https://pengline.cn/2026/02/7e6cd67dd5ee45248f2276ac145555f5/)
- [示例代码](https://github.com/neopen/video-shot-agent/tree/main/example)



