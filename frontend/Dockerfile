# =====================================================
# paper-translate — Frontend Dockerfile (multi-stage)
# =====================================================
# Stage 1: 用 node:20-alpine 构建 Vite 静态资源
# Stage 2: 用 nginx:alpine 托管 dist/
# =====================================================

# ===========================================
# Stage 1 — Builder
# ===========================================
FROM node:20-alpine AS builder

# 安装 pnpm（可选，默认使用 npm）
# RUN npm install -g pnpm

WORKDIR /app

# ---- 缓存层 1: 仅复制 package.json / lock 文件 ----
COPY package.json package-lock.json* ./
# 如果使用 pnpm：
# COPY package.json pnpm-lock.yaml ./

# 安装依赖
RUN \
    if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund --prefer-offline; \
    else \
        npm install --no-audit --no-fund --prefer-offline; \
    fi
# pnpm:
# RUN pnpm install --frozen-lockfile --prefer-offline

# ---- 缓存层 2: 复制源码 ----
COPY . .

# ---- 构建 ----
# 传递构建期环境变量（API 基础 URL 等）
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_BASE_URL=/api/v1/ws
ARG VITE_SENTRY_DSN
ARG VITE_APP_VERSION=1.0.0

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_WS_BASE_URL=${VITE_WS_BASE_URL} \
    VITE_SENTRY_DSN=${VITE_SENTRY_DSN} \
    VITE_APP_VERSION=${VITE_APP_VERSION}

RUN npm run build

# ===========================================
# Stage 2 — Runtime (nginx)
# ===========================================
FROM nginx:1.27-alpine AS runtime

# 标签
LABEL maintainer="paper-translate contributors" \
      version="1.0.0" \
      description="Frontend for paper-translate (AGPL-3.0)" \
      license="AGPL-3.0"

# 删除默认 nginx 配置
RUN rm -rf /etc/nginx/conf.d/default.conf

# 复制自定义 nginx 配置（仅用于托管静态资源，不做反向代理）
# 反向代理由 docker-compose 中的 nginx 服务统一处理
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从 builder 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 健康检查端点
RUN echo "OK" > /usr/share/nginx/html/healthz

# nginx 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/healthz || exit 1

# 暴露端口
EXPOSE 80

# nginx 默认 CMD（前台运行）
CMD ["nginx", "-g", "daemon off;"]