# =====================================================
# paper-translate — Backend Dockerfile
# =====================================================
# FastAPI + uvicorn + pdf2zh_next + babeldoc + pypandoc
# =====================================================
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

# =====================
# 系统依赖
# =====================
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        libpq-dev \
        gcc \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        libpng-dev \
        zlib1g-dev \
        poppler-utils \
        texlive-xetex \
        texlive-latex-recommended \
        texlive-latex-extra \
        pandoc \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        chromium \
        chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# =====================
# pip 配置
# =====================
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore

# =====================
# 升级 pip 并安装基础工具
# =====================
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# =====================
# 工作目录
# =====================
WORKDIR /app

# =====================
# 先复制 requirements.txt 以利用 Docker 层缓存
# =====================
COPY requirements.txt ./

# =====================
# 安装 Python 依赖（按字母顺序，方便审阅）
# =====================
# Web 框架
# 数据库
# 鉴权
# 任务队列
# 翻译核心（AGPL-3.0 上游）
# LLM
# 文件处理
# 监控
# 工具
RUN pip install --no-cache-dir \
        fastapi==0.115.0 \
        uvicorn[standard]==0.32.0 \
        pydantic==2.9.2 \
        pydantic-settings==2.6.0 \
        python-multipart==0.0.12 \
        sqlalchemy==2.0.36 \
        asyncpg==0.30.0 \
        alembic==1.13.3 \
        python-jose[cryptography]==3.3.0 \
        passlib[bcrypt]==1.7.4 \
        bcrypt==4.2.0 \
        dramatiq==1.17.0 \
        redis==5.2.0 \
        pdf2zh_next==2.6.4 \
        babeldoc>=0.5.6 \
        pypandoc==1.13 \
        httpx==0.27.2 \
        openai==1.54.4 \
        oss2==2.18.5 \
        aiofiles==24.1.0 \
        pandas==2.2.3 \
        python-dotenv==1.0.1 \
        sentry-sdk[fastapi]==2.18.0 \
        structlog==24.4.0 \
        tenacity==9.0.0 \
        prometheus-client==0.21.0

# =====================
# 复制应用代码
# =====================
COPY app/ ./app/

# =====================
# 创建必要目录
# =====================
RUN mkdir -p /app/uploads /app/downloads /app/logs \
    && chmod -R 755 /app

# =====================
# 非 root 用户运行
# =====================
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# =====================
# 健康检查
# =====================
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# =====================
# 暴露端口
# =====================
EXPOSE 8000

# =====================
# 启动命令
# =====================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]