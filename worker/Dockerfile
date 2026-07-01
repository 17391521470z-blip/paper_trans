# =====================================================
# paper-translate — Worker Dockerfile
# =====================================================
# 复用 backend 镜像作为基础（共享 pdf2zh_next / babeldoc 等大依赖）
# 仅安装 Dramatiq 特有的运行时
# =====================================================
# syntax=docker/dockerfile:1.7
FROM paper-translate/backend:latest AS base

# =====================
# 工作目录
# =====================
WORKDIR /app

# =====================
# Worker 特有的依赖（如果与 backend 不同）
# =====================
# 这里可以加 worker 独有的 Python 包：
# 例如：dramatiq[rabbitmq] / dramatiq-brokers / prometheus-dramatiq 等
# 当前 backend 镜像已包含 dramatiq，无需重复安装
# RUN pip install --no-cache-dir \
#         prometheus-dramatiq==0.1.0

# =====================
# 复制 worker 应用代码
# =====================
COPY app/ ./app/

# =====================
# 确保目录存在
# =====================
RUN mkdir -p /app/uploads /app/downloads /app/logs /tmp/pdf-work

# =====================
# 健康检查（Dramatiq 进程存在）
# =====================
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD pgrep -f "dramatiq" > /dev/null || exit 1

# =====================
# 启动 Dramatiq worker
# =====================
# --processes: worker 进程数（建议 ≤ CPU 核数）
# --threads: 每个进程的线程数
# --queues: 监听的队列列表
# --watch: 监视 .py 文件改动自动重载（生产环境请去掉）
# =====================
CMD ["dramatiq", \
     "app.workers.tasks", \
     "--processes", "2", \
     "--threads", "4", \
     "--queues", "default,translation,glossary,notification"]