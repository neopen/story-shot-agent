"""
@FileName: task_handler.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 16:42
"""
from typing import Dict

from hengshot.logger import error


class CallbackHandler:
    """回调处理器"""

    @staticmethod
    async def notify_callback(callback_url: str, task_data: Dict):
        """异步通知回调"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    callback_url,
                    json=task_data,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                return True
        except Exception as e:
            error(f"回调通知失败: {e}")
            return False