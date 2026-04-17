"""
@FileName: application.py
@Description: 应用程序主模块 - 负责初始化和配置整个应用
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10/6
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback


#
# 导入模型API路由器
from penshot.api.index_api import router as index_router
from penshot.api.rest_api import router as rest_router
from penshot.config.config import settings
from penshot.logger import error
from penshot.neopen.shot_context import RequestContextMiddleware
from .proxy import router as proxy_router
from ..neopen.task.task_init import startup_with_recovery
from ..utils.path_utils import PathResolver


async def app_startup():
    """
    应用启动时的初始化操作
    """
    # 在这里添加任何需要在应用启动时执行的初始化代码
    data_paths = settings.get_data_paths()
    output_dir = os.path.join(PathResolver.get_project_root(), data_paths["data_output"])
    os.makedirs(output_dir, exist_ok=True)
    memory_dir = os.path.join(PathResolver.get_project_root(), data_paths["data_memory"])
    os.makedirs(memory_dir, exist_ok=True)
    embedding_dir = os.path.join(PathResolver.get_project_root(), data_paths["data_embedding"])
    os.makedirs(embedding_dir, exist_ok=True)

    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
    await startup_with_recovery()
    yield


# 创建FastAPI应用
app = FastAPI(
    title="剧本分镜智能体服务",
    description="一个能够将剧本智能拆分为短视频脚本单元的API服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 生产环境应限制为特定域名
cors_config = os.environ.get("APP_CORS", "")
if cors_config != "":
    if cors_config == "1":
        cors_config = ["http://localhost:8000", "*"]
    else:
        cors_config = cors_config.split(";")
else:
    cors_config = ["*"]

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 添加请求上下文中间件
app.add_middleware(RequestContextMiddleware)


# ========== 中间件和配置 ==========
@app.middleware("http")
async def add_cache_control_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    """添加处理时间头"""
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["Cache-Control"] = "max-age=0"
    return response


# ========== 错误处理器 ==========
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """全局 HTTP 异常处理器"""
    error(f"[ERROR] HTTPException: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    error(f"[ERROR] Unhandled exception: {str(exc)}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "path": request.url.path
        }
    )

# =====================router======================
app.include_router(proxy_router)
app.include_router(rest_router)
app.include_router(index_router)
