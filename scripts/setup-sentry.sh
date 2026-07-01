#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo " Sentry 错误监控配置指南"
echo "=========================================="
echo ""

usage() {
    cat <<EOF
Usage: $(basename "$0") [option]

Options:
  guide          Print Sentry setup guide (default)
  backend        Print backend Sentry integration instructions
  frontend       Print frontend Sentry integration instructions
  verify         Print verification instructions

Examples:
  ./$(basename "$0") guide
  ./$(basename "$0") backend
  ./$(basename "$0") frontend
EOF
    exit 0
}

MODE="${1:-guide}"

case "$MODE" in
    guide|full)
        cat << 'GUIDE'
===========================================
 Sentry 配置完整指南
===========================================

步骤 1：注册 Sentry 账号
  - 访问 https://sentry.io/signup/
  - 推荐使用 GitHub 账号登录
  - 选择 Team 计划（免费额度够用）

步骤 2：创建项目
  - 登录后点击 "Create Project"
  - Platform: Python (FastAPI) — 用于后端
  - 项目名称: paper-translate-backend
  - 点击 "Create Project"

  - 再次创建项目：
  - Platform: React — 用于前端
  - 项目名称: paper-translate-frontend
  - 点击 "Create Project"

步骤 3：获取 DSN
  - 在每个项目的 Settings → Client Keys (DSN) 中
  - 复制 DSN 字符串 (https://xxxxx@sentry.io/yyyyy)

步骤 4：配置环境变量
  - 编辑 .env 文件，设置：
    SENTRY_DSN=https://your-dsn@sentry.io/project-id
    SENTRY_ENVIRONMENT=production
    SENTRY_TRACES_SAMPLE_RATE=0.1

步骤 5：配置后端 (Python/FastAPI)
  - 运行以下命令查看后端配置详情：
    ./setup-sentry.sh backend

步骤 6：配置前端 (React)
  - 运行以下命令查看前端配置详情：
    ./setup-sentry.sh frontend

步骤 7：验证集成
  - 运行以下命令查看验证方法：
    ./setup-sentry.sh verify
GUIDE
        ;;

    backend)
        cat << 'BACKEND'
===========================================
 后端 Sentry 集成（Python/FastAPI）
===========================================

当前后端代码已包含 sentry_sdk 依赖。
确保 .env 中有正确的 SENTRY_DSN。

完整的 sentry_sdk.init 配置（在 backend/app/main.py 中已有占位）：

需要在 lifespan 函数的开始位置添加：

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.loguru import LoguruIntegration

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            sample_rate=1.0,
            max_breadcrumbs=50,
            debug=False,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                SqlalchemyIntegration(),
                RedisIntegration(),
            ],
            send_default_pii=False,
            release=f"paper-translate@{settings.app_version}",
        )

验证后端 Sentry：
  1. 启动服务后访问任意 API 端点
  2. 在 Sentry Dashboard 中查看 Issues
  3. 手动测试：访问 /docs 页面触发一个 500 错误
BACKEND
        ;;

    frontend)
        cat << 'FRONTEND'
===========================================
 前端 Sentry 集成（React）
===========================================

步骤 1：安装 @sentry/react

  cd frontend
  npm install @sentry/react @sentry/vite-plugin

  # 或使用 pnpm
  # pnpm add @sentry/react @sentry/vite-plugin

步骤 2：配置 Vite 插件（vite.config.ts）
  在 vite.config.ts 中添加 Sentry 插件：

  import { sentryVitePlugin } from "@sentry/vite-plugin";

  export default defineConfig({
    plugins: [
      react(),
      sentryVitePlugin({
        org: "your-sentry-org",
        project: "paper-translate-frontend",
        authToken: process.env.SENTRY_AUTH_TOKEN,
        telemetry: false,
      }),
      // ...
    ],
    build: {
      sourcemap: true,
    },
  });

步骤 3：在 main.tsx 中初始化 Sentry

  在文件顶部添加：

  import * as Sentry from "@sentry/react";

  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_APP_ENV || "production",
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    release: `paper-translate@${import.meta.env.VITE_APP_VERSION}`,
  });

步骤 4：添加 Sentry ErrorBoundary
  在 App.tsx 或路由配置中：

  import * as Sentry from "@sentry/react";

  // 替换现有的 ErrorBoundary：
  <Sentry.ErrorBoundary
    fallback={({ error }) => (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600">Something went wrong</h1>
          <p className="mt-2 text-gray-600">{error.message}</p>
        </div>
      </div>
    )}
  >
    <App />
  </Sentry.ErrorBoundary>

步骤 5：构建环境变量
  在 Dockerfile 构建时传入 VITE_SENTRY_DSN：

  docker build \\
    --build-arg VITE_SENTRY_DSN=https://your-dsn@sentry.io/project-id \\
    -t paper-translate/frontend:latest \\
    ./frontend

  或在 docker-compose.prod.yml 的 frontend build args 中配置：

  frontend:
    build:
      args:
        VITE_SENTRY_DSN: ${SENTRY_DSN}
FRONTEND
        ;;

    verify)
        cat << 'VERIFY'
===========================================
 Sentry 集成验证方法
===========================================

1. 后端验证
   手动触发一个错误测试：

   curl -X POST http://localhost/api/v1/test-sentry-error

   （如果后端有测试路由）或在代码中临时添加：

   @app.get("/api/v1/test-sentry")
   async def test_sentry():
       raise Exception("Sentry test error from paper-translate backend")

   访问该路由后，检查 Sentry Dashboard → Issues
   应该看到 test_sentry 的错误报告

2. 前端验证
   在浏览器控制台执行：

   import * as Sentry from "@sentry/react"
   Sentry.captureException(new Error("Sentry test error from frontend"))

   或临时在某个组件中添加：

   throw new Error("Sentry test error")

   检查 Sentry Dashboard → Issues
   应该看到前端的错误报告

3. 确认 .env 配置

   grep SENTRY_DSN .env

   输出应类似：
   SENTRY_DSN=https://xxxxxxxxxxxxxxxxxxxx@sentry.io/yyyyyy

4. 常见问题
   - 如果 Sentry 收不到错误，检查网络是否能访问 sentry.io
   - 自托管 Sentry 需要配置 outgoing 网络
   - traces_sample_rate 设为 0.1 即可（采样 10% 减少费用）
VERIFY
        ;;

    *)
        usage
        ;;
esac
