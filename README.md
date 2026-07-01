# Paper Translate — 学术论文 PDF 翻译 SaaS

> 面向科研用户的 ToC（透明 + 准确）学术论文翻译服务。在开源 [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 与 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 之上构建。

## 项目简介

`paper-translate` 是一个面向**科研工作者**的 PDF 论文翻译 SaaS 平台。我们解决了通用翻译工具在学术场景下的痛点：

- **公式与符号保留**：LaTeX 公式 / 数字 / 上下标不被破坏
- **术语准确**：支持自定义学术术语库（CS / AI / 物理 / 生物医学等）
- **参考文献跳过**：自动识别 References 章节并保留原文（DOI / 作者 / 年份不被破坏）
- **多格式输出**：双语 PDF + 纯译文 PDF + Markdown（方便笔记软件二次编辑）
- **章节结构识别**：自动识别 Abstract / Introduction / Methods / Experiments 等章节

## AGPL-3.0 协议声明

本项目以 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源发布。这意味着：

1. **你可以自由使用、修改、分发本项目源码**
2. **如果你修改了本项目并在网络服务器上提供对外服务，你必须将修改后的完整源码以 AGPL-3.0 协议公开**
3. **完整协议文本见 [LICENSE](./LICENSE) 文件**

### 上游依赖

- [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) — AGPL-3.0（pip 安装，本项目不修改其源码）
- [BabelDOC](https://github.com/funstory-ai/BabelDOC) — AGPL-3.0（pip 安装，本项目不修改其源码）

我们通过 `import pdf2zh_next` / `import babeldoc` 调用上游包，属于 AGPL 兼容的"聚合"行为，不要求 PDFMathTranslate-next 的修改一并开源。但**本项目自身所有代码必须以 AGPL-3.0 开源**。

## 源码链接

**GitHub 仓库**：<https://github.com/yourname/paper-translate>

> 该链接为本项目的占位符，请在你 fork / clone 后替换为实际仓库地址。AGPL-3.0 协议要求我们公开源码，因此线上运行的版本必须能映射到一个公开仓库。

## 功能特性

### 核心功能

| 功能 | 描述 |
|---|---|
| 双语 PDF 翻译 | 原文与译文左右对照，保留原始排版 |
| 纯译文 PDF | 仅译文版本，适合直接阅读 |
| Markdown 导出 | 通过 pypandoc 后处理，方便 Notion / Obsidian 二次编辑 |
| 自定义术语库 | CSV 上传 / 下载 / 编辑，支持 `term`、`translation`、`context_optional` 三列 |
| 章节结构识别 | LLM 一次小成本调用识别 Abstract / Introduction / Methods / References 等 |
| 参考文献跳过 | 自动识别 References 章节，DOI / 作者 / 年份保留原样 |
| 实时进度推送 | WebSocket 推送翻译进度（0-100%） |
| 24h 文件清理 | OSS 生命周期 + 后端定时任务双重保障 |

### 运营能力

| 功能 | 描述 |
|---|---|
| 用户账号 | 手机号 / 邮箱注册，JWT 鉴权 |
| 翻译配额 | 免费档 5 页/天、30 页/月；标准档 ¥29 月卡 200 页；Pro 档 ¥69 月卡 800 页 |
| 支付 | 微信支付 Native + 支付宝当面付 |
| LLM 成本监控 | 每日成本 > ¥50 触发企业微信 / 邮件告警 |
| 文件下载签名 | OSS 签名 URL，24h 自动过期 |

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui |
| 后端 | FastAPI + uvicorn + SQLAlchemy 2.0 |
| 任务队列 | Dramatiq + Redis |
| 数据库 | PostgreSQL 16 |
| 翻译核心 | pdf2zh_next（pip）+ babeldoc（pip） |
| LLM | DeepSeek-V3（主）/ GLM-4-Flash（备） |
| 容器化 | Docker + Docker Compose |
| 反向代理 | Nginx |

## 部署指南

### 前置依赖

- Docker 24+ 与 Docker Compose v2
- 4C8G 以上云服务器
- 阿里云 OSS / 腾讯云 COS Bucket（用于存储 PDF）
- LLM API Key（DeepSeek / GLM-4 / OpenAI 等）
- 域名（生产环境需要 SSL 证书）

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/yourname/paper-translate.git
cd paper-translate

# 2. 复制环境变量模板
cp .env.example .env

# 3. 修改 .env，填入 DB / Redis / OSS / LLM API Key 等实际配置
vim .env

# 4. 启动所有服务
docker compose up -d

# 5. 查看启动日志
docker compose logs -f

# 6. 访问网站
open http://localhost
```

### 服务清单

| 服务 | 端口 | 描述 |
|---|---|---|
| `frontend` | 80 | Nginx 托管 Vite 静态资源 |
| `api` | 8000 | FastAPI 后端（uvicorn） |
| `worker` | — | Dramatiq 消费者，调用 pdf2zh_next / babeldoc |
| `redis` | 6379 | Dramatiq broker + 缓存 |
| `postgres` | 5432 | 业务数据 |
| `nginx` | 443 | 反向代理 + SSL 终止（生产环境） |

### 生产环境部署

1. **域名与备案**：购买域名并完成 ICP 备案
2. **SSL 证书**：使用 Let's Encrypt 自动签发（certbot + cron）
3. **Nginx 配置**：启用 HTTPS（`nginx/nginx.conf` 中替换自签证书为正式证书）
4. **OSS 生命周期**：在 Bucket 控制台配置 24h 自动删除规则
5. **监控告警**：配置 Sentry（错误）+ UptimeRobot（健康检查）+ 企业微信机器人（成本告警）
6. **数据库备份**：每日 `pg_dump` 上传到 OSS

详细部署文档见 [docs/deployment.md](./docs/deployment.md)（TODO）。

## 开发指南

### 本地开发（不使用 Docker）

```bash
# 后端
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Worker（另一个终端）
cd worker
dramatiq app.workers.tasks --processes 2

# 前端（第三个终端）
cd frontend
npm install
npm run dev
```

### 目录结构

```
paper-translate/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/         # 路由
│   │   ├── core/           # 配置 / 数据库
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── services/       # 业务服务层
│   │   └── workers/        # Dramatiq 任务
│   ├── Dockerfile
│   └── requirements.txt
├── worker/                 # 独立的 Worker 容器（也可与 backend 合并）
│   ├── app/
│   └── Dockerfile
├── frontend/               # React 前端
│   ├── src/
│   │   ├── pages/          # 页面
│   │   ├── components/     # 组件
│   │   ├── lib/            # API 客户端 / 工具
│   │   └── stores/         # Zustand store
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── nginx/                  # 反向代理
│   └── nginx.conf
├── docker-compose.yml      # 一键编排
├── .env.example            # 环境变量模板
├── LICENSE                 # AGPL-3.0 全文
└── README.md               # 本文件
```

## 测试

### 环境要求

- Python 3.12+（后端测试）
- Node.js 20+（前端与 E2E 测试）
- Redis（部分测试需要，但大多数单元测试使用 mock）
- 开发模式验证码（`.env` 中 `APP_ENV=development` 或 `APP_ENV=test` 时，验证码统一为 `123456`）

### 运行所有测试

```bash
make test
```

### 后端单元测试（pytest）

```bash
# 运行所有后端测试
make test-backend

# 或直接
cd backend && python -m pytest tests/ -v --tb=short
```

覆盖范围：

| 文件 | 覆盖内容 |
|------|------|
| `tests/test_auth.py` | 注册/登录/改密/验证码/配额查询 |
| `tests/test_tasks.py` | 任务创建/列表/详情/缓存/下载/配额超限 |
| `tests/test_glossary.py` | CSV 解析/校验/CRUD/导出/配额检查/Prompt 生成 |
| `tests/test_services.py` | 存储/Llm/结构/Markdown/成本监控/Task 服务/配额服务 |
| `tests/test_api_health.py` | 健康检查/OpenAPI 白名单 |

### 前端检查

```bash
make test-frontend
# 或
cd frontend && npm run typecheck && npm run lint
```

### E2E 测试（Playwright）

```bash
make test-e2e
# 或
npx playwright test --project=chromium
```

E2E 测试位于 `e2e/` 目录：

| 文件 | 场景 |
|------|------|
| `e2e/auth.spec.ts` | 首页→登录跳转、注册、登录一致性 |
| `e2e/translate.spec.ts` | 上传 PDF→选语言→翻译→下载 |
| `e2e/glossary.spec.ts` | CSV 术语库上传/列表/导出 |
| `e2e/billing.spec.ts` | 订阅页查看/选择套餐/支付跳转 |

运行前需要：

1. 启动后端服务：`docker compose up -d` 或 `cd backend && uvicorn app.main:app --port 8000`
2. 启动前端开发服务器：`cd frontend && npm run dev`
3. E2E Fixtures 文件位于 `e2e/fixtures/`

### 压测脚本

```bash
# 安装 locust
pip install locust

# 启动压测（假设 API 运行在 localhost:8000）
locust -f locustfile.py --host http://localhost:8000 --users 100 --spawn-rate 10 --run-time 1m
```

### CI/CD

GitHub Actions 配置见 `.github/workflows/ci.yml`，包含：

1. **lint-and-typecheck** — 后端 ruff + mypy
2. **frontend-check** — 前端 TypeScript 类型检查 + ESLint
3. **test** — pytest + Playwright（依赖 Redis/PostgreSQL 服务容器）

## 贡献指南

欢迎 PR 与 Issue。由于 AGPL-3.0 协议要求所有衍生作品同样以 AGPL-3.0 开源，提交 PR 即代表你同意以 AGPL-3.0 协议授权你的贡献。

## 致谢

- [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) — 翻译核心
- [BabelDOC](https://github.com/funstory-ai/BabelDOC) — 高质量 PDF 翻译引擎
- [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO) — 版面分析模型

## 联系方式

- Issue 区：<https://github.com/yourname/paper-translate/issues>
- 邮箱：<your-email@example.com>

---

**Copyright (C) 2026 paper-translate contributors**

**Licensed under GNU Affero General Public License v3.0**