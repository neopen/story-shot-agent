
"""
@FileName: application.py
@Description: 应用程序主模块 - 负责初始化和配置整个应用
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10/6
"""
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hengshot.api.index_api import app as index_api
#
# 导入模型API路由器
from hengshot.api.shot_api import app as shot_api
from hengshot.config.config import settings
from hengshot.hengline.context_var import RequestContextMiddleware
from hengshot.logger import error
from .proxy import router as proxy_router
from ..utils.path_utils import PathResolver


async def app_startup():
    """
    应用启动时的初始化操作
    """
    # 在这里添加任何需要在应用启动时执行的初始化代码
    data_paths = settings.get_data_paths()
    output_dir = os.path.join(PathResolver.get_project_root(), data_paths["data_output"])
    os.makedirs(output_dir, exist_ok=True)
    # os.makedirs(data_paths["data_input"], exist_ok=True)
    # os.makedirs(data_paths["model_cache"], exist_ok=True)
    # os.makedirs(data_paths["embedding_cache"], exist_ok=True)

    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
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

app.include_router(proxy_router)

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
async def http_exception_handler(request, exc):
    """HTTP异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理器"""
    error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "内部服务器错误",
            "message": str(exc),
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )


# =====================router======================

app.include_router(index_api, prefix="/api/v1")
app.include_router(shot_api, prefix="/api/v1")
