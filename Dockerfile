# ==========================================
# 1. 构建阶段 (Builder)
# ==========================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 安装底层 C/C++ 编译依赖（满足 Pillow, numpy, cffi 等包的编译依赖）
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential libffi-dev libssl-dev git curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖声明文件与项目源码
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 🎯 核心修改：在 '.' 后面加上 '[docker]'，强行构建 pyproject.toml 中 docker 组的所有依赖包
RUN python -m pip install --upgrade pip setuptools build \
    && pip wheel --no-cache-dir --wheel-dir /app/wheels .[docker]


# ==========================================
# 2. 运行阶段 (Runner)
# ==========================================
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PENSHOT_API__HOST=0.0.0.0 \
    PENSHOT_API__PORT=8000

WORKDIR /app

# 安装运行基础工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制预编译好的全量依赖包并安装
COPY --from=builder /app/wheels /wheels
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# 安全配置：创建 appuser 非 root 专属用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 拷贝全量代码
COPY --chown=appuser:appuser . .

EXPOSE 8000

# 容器健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 使用脚本入口启动服务
ENTRYPOINT ["python", "-m", "scripts.entrypoint"]
CMD ["start"]