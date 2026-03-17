"""
@FileName: test_api_client.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 17:05
"""
import asyncio
from typing import Dict

import httpx


class APIClient:
    """API客户端封装"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        import httpx
        self.client = httpx.AsyncClient(base_url=self.base_url)

    async def process_script(self, script: str, config: Dict = None, callback_url: str = None):
        """处理剧本"""
        response = await self.client.post(
            "/api/v1/generate",
            json={
                "script": script,
                "config": config,
                "callback_url": callback_url
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_status(self, task_id: str):
        """获取任务状态"""
        response = await self.client.get(f"/api/v1/status/{task_id}")
        response.raise_for_status()
        return response.json()

    async def get_result(self, task_id: str, wait_for_completion: bool = False, poll_interval: int = 2):
        """获取任务结果，可选择等待完成"""
        if wait_for_completion:
            while True:
                try:
                    result = await self.get_status(task_id)
                    if result["status"] in ["completed", "failed"]:
                        break
                    await asyncio.sleep(poll_interval)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 202:
                        raise

        response = await self.client.get(f"/api/v1/result/{task_id}")
        response.raise_for_status()
        return response.json()

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
