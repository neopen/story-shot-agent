"""
@FileName: middleware_constant.py
@Description: 上下文变量
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/17 22:51
"""
import contextvars
from fastapi import Request
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

# 定义一个 request 级别的上下文变量，默认值为 None
task_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default=None)
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default=None)
session_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default=None)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 例如从 header 获取 user_id，或生成 request_id
        task_id = str(uuid.uuid4())
        user_id = request.headers.get("X-User-ID", "anonymous")

        # 设置上下文变量
        r_token = task_id_ctx.set(task_id)
        u_token = user_id_ctx.set(user_id)

        try:
            response = await call_next(request)
            return response
        finally:
            # 可选：清理（通常不必要，因为 context 自动销毁）
            task_id_ctx.reset(r_token)
            user_id_ctx.reset(u_token)