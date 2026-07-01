# paper-translate — Backend

FastAPI 后端骨架，面向科研论文 PDF 翻译 SaaS。

## 技术栈

- Python 3.12
- FastAPI 0.115
- SQLAlchemy 2.0 async（SQLite / PostgreSQL 双数据库支持）
- Pydantic v2 + pydantic-settings
- python-jose（JWT） + passlib（bcrypt）
- redis-py 5.x（Dramatiq broker）
- dramatiq 1.17（异步任务队列）
- structlog（结构化日志）

## 目录结构

```
backend/
├── app/
│   ├── api/
│   │   └── v1/                 # 路由层（v1 聚合）
│   ├── core/                   # 配置 / 数据库 / Redis / 安全 / 日志
│   ├── models/                 # SQLAlchemy 模型
│   ├── schemas/                # Pydantic 请求 / 响应模型
│   ├── services/               # 业务服务层
│   ├── workers/                # Dramatiq 任务定义
│   └── main.py                 # FastAPI 入口
├── pyproject.toml
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## 启动

### 1. 准备环境

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动依赖（开发）

```bash
docker compose up -d redis postgres
# 或者直接使用本地安装的 redis / postgres
```

### 3. 启动 API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/api/v1/health
```

OpenAPI 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc:      http://localhost:8000/redoc

### 4. 启动 Worker

```bash
dramatiq app.workers.tasks -Q translation notifications maintenance
```

## 路由占位

T2 阶段所有业务端点返回 HTTP 501（`{"detail": "Not implemented yet", ...}`），但接口签名、请求 / 响应模型已完整定义，便于 T3-T5 增量实现。

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/auth/register` | POST | 注册（占位） |
| `/api/v1/auth/login` | POST | 登录（占位） |
| `/api/v1/auth/send-code` | POST | 发送验证码（占位） |
| `/api/v1/users/me` | GET | 当前用户（占位） |
| `/api/v1/quotas` | GET | 当前配额（占位） |
| `/api/v1/tasks` | POST / GET | 提交 / 列表任务（占位） |
| `/api/v1/tasks/{id}` | GET | 任务详情（占位） |
| `/api/v1/tasks/{id}/download` | GET | 下载结果（占位） |
| `/api/v1/tasks/{id}/ws` | WebSocket | 进度推送（占位） |
| `/api/v1/glossaries` | POST / GET | 术语库（占位） |
| `/api/v1/glossaries/{id}` | DELETE | 删除术语库（占位） |
| `/api/v1/orders` | POST / GET | 订单（占位） |
| `/api/v1/orders/callback` | POST | 支付回调（占位） |

## 测试

```bash
pytest -q
```

## 数据库切换

- 开发：默认使用 SQLite，路径 `./paper_translate.db`
- 生产：在 `.env` 中设置 `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db`

`app/core/database.py` 会自动把 `postgresql://` 转换为 `postgresql+asyncpg://`，`sqlite://` 转换为 `sqlite+aiosqlite://`。

## 协议

AGPL-3.0（与根目录 LICENSE 保持一致）。
