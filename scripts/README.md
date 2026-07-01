# Paper Translate — 部署与运维文档

## 目录

- [前置条件](#前置条件)
- [快速部署](#快速部署)
- [生产检查清单](#生产检查清单)
- [运维脚本清单](#运维脚本清单)
- [备份与恢复](#备份与恢复)
- [监控与告警](#监控与告警)
- [扩容指南](#扩容指南)
- [常见运维问题](#常见运维问题)
- [Windows 兼容性提示](#windows-兼容性提示)

---

## 前置条件

### 硬件要求

| 服务 | 最低配置 | 推荐配置 |
|------|---------|---------|
| API (FastAPI) | 1 CPU, 1GB RAM | 2 CPU, 2GB RAM |
| Worker (pdf2zh) | 2 CPU, 2GB RAM | 4 CPU, 4GB RAM |
| PostgreSQL | 1 CPU, 512MB RAM | 2 CPU, 1GB RAM |
| Redis | 1 CPU, 256MB RAM | 1 CPU, 512MB RAM |
| Nginx | 1 CPU, 128MB RAM | 1 CPU, 256MB RAM |
| **总计** | **2 CPU, 4GB RAM** | **4 CPU, 8GB RAM** |

### 软件要求

- **Docker** >= 24.0 + Docker Compose v2
- **Git** >= 2.30
- **域名**（生产必需）已备案并解析到服务器 IP
- **开放端口**：80 (HTTP), 443 (HTTPS), 9090 (Prometheus, 可选)

### 域名与备案（中国大陆）

如果面向中国大陆用户，需要：

1. **域名备案**：阿里云 / 腾讯云 / 华为云均可备案
   - 备案流程：购买域名 → 实名认证 → 提交备案申请 → 管局审核（约 7-20 个工作日）
   - 备案期间可用 IP 访问测试

2. **ICP 备案号**：在网站底部显示 "京ICP备xxxxx号"

3. **公安备案**：部分省市要求公安备案

4. **OSS 使用**：如果使用阿里云 OSS，需要 OSS 域名与网站域名同主体备案

### 对象存储（OSS）

- 推荐：阿里云 OSS 或腾讯云 COS
- 创建 Bucket（建议地域与服务器一致）
- 获取 AccessKey ID / Secret
- 配置自动生命周期规则：24h 自动清理

---

## 快速部署

### 一键部署

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/paper-translate.git
cd paper-translate

# 2. 配置环境变量
cp .env.prod.example .env
vim .env   # 填入所有 REQUIRED/CHANGE_ME 字段

# 3. 生成 SSL 证书（测试环境用自签，生产用 Let's Encrypt）
bash nginx/ssl/generate.sh selfsign yourdomain.com

# 4. 一键部署
bash scripts/deploy.sh
```

部署脚本会自动完成以下步骤：

1. `git pull` — 拉取最新代码
2. 检查 `.env` 是否存在，不存在则从 `.env.prod.example` 复制
3. `docker compose -f docker-compose.prod.yml pull` — 拉取镜像
4. `docker compose -f docker-compose.prod.yml up -d --force-recreate` — 启动所有服务
5. `docker system prune -f` — 清理无用资源
6. 打印服务状态
7. 健康检查 `http://localhost/api/v1/health`

### 手动分步部署

```bash
# 构建并启动所有服务
docker compose -f docker-compose.prod.yml up -d --build

# 查看服务状态
docker compose -f docker-compose.prod.yml ps

# 查看日志
docker compose -f docker-compose.prod.yml logs -f

# 仅启动核心服务（不启动监控）
docker compose -f docker-compose.prod.yml up -d

# 启动监控栈
bash scripts/monitoring.sh start
```

### 验证部署

```bash
# 运行完整健康检查
bash scripts/healthcheck.sh

# 手动验证 API
curl https://yourdomain.com/api/v1/health
# 预期: {"status":"ok","version":"1.0.0"}

# 验证 WebSocket
wscat -c wss://yourdomain.com/api/v1/ws/health
```

---

## 生产检查清单

### 安全检查

- [ ] 修改 JWT_SECRET_KEY 为 64 字符随机串
- [ ] 修改 POSTGRES_PASSWORD 为强密码
- [ ] 所有 API Key 已配置（DeepSeek / GLM / OSS / SMS）
- [ ] Nginx SSL 证书已配置（非自签）
- [ ] HSTS 已启用（nginx.conf 中已配置）
- [ ] `.env` 文件权限设置为 600
- [ ] 关闭 DEBUG 模式
- [ ] 确认 CORS_ORIGINS 仅包含可信域名
- [ ] 服务器防火墙配置：仅开放 80/443 端口

### 性能检查

- [ ] Worker memory_limit 已设为 4g（pdf2zh 需要较大内存）
- [ ] Redis maxmemory 已设为 512m
- [ ] API workers 数量 ≤ CPU 核数
- [ ] Nginx worker_processes 设为 auto
- [ ] 启用 Gzip 压缩（已配置）
- [ ] 静态资源缓存策略（已配置）

### 监控检查

- [ ] Sentry DSN 已配置
- [ ] UptimeRobot 已配置外部监控
- [ ] LLM 成本告警 Webhook 已配置
- [ ] 日志轮转已配置
- [ ] 数据库备份已配置（crontab）
- [ ] 磁盘监控已配置

---

## 运维脚本清单

| 脚本 | 功能 | 使用频率 |
|------|------|---------|
| `deploy.sh` | 一键部署更新 | 每次发布 |
| `rollback.sh` | 回滚到上一个版本 | 紧急回滚 |
| `backup.sh` | PostgreSQL 数据库备份 | 每日（crontab） |
| `restore.sh` | 从备份恢复数据库 | 灾难恢复 |
| `healthcheck.sh` | 完整健康检查 | 按需 / 监控 |
| `monitoring.sh` | 启动/停止监控栈 | 按需 |
| `init-quotas.sh` | 初始化用户配额 | 每月 1 日 |
| `nginx-log-rotate.sh` | Nginx 日志轮转 | 每日（crontab） |
| `setup-sentry.sh` | Sentry 配置指南 | 首次部署 |

### 一键部署

```bash
bash scripts/deploy.sh
```

### 回滚

```bash
bash scripts/rollback.sh
```

### 数据库备份

```bash
# 执行备份（使用 .env 中的配置）
bash scripts/backup.sh

# 干模式（只显示将要执行的操作）
bash scripts/backup.sh --dry-run
```

### 数据库恢复

```bash
# 列出可用备份
bash scripts/restore.sh --list

# 从备份文件恢复
bash scripts/restore.sh ../backups/paper_translate_20240101.sql.gz
```

### 健康检查

```bash
# 综合健康检查（容器状态 + API + Redis + PostgreSQL + 磁盘 + 内存）
bash scripts/healthcheck.sh
```

### 监控栈

```bash
# 启动 Prometheus + Node Exporter
bash scripts/monitoring.sh start

# 查看监控状态
bash scripts/monitoring.sh status

# 停止监控栈
bash scripts/monitoring.sh stop
```

### 配额初始化

```bash
# 为新用户初始化配额
bash scripts/init-quotas.sh

# 重置所有用户已用配额（每月 1 日执行）
bash scripts/init-quotas.sh --reset-all --force

# 自定义免费档页数
bash scripts/init-quotas.sh --daily-pages 10 --monthly-pages 50
```

### Nginx 日志轮转

```bash
# 默认轮转（保留 7 天）
bash scripts/nginx-log-rotate.sh

# 保留 14 天
bash scripts/nginx-log-rotate.sh -d 14

# 强制轮转（即使日志为空）
bash scripts/nginx-log-rotate.sh -f
```

### 配置 Crontab 自动运维

```bash
# 编辑 crontab
crontab -e

# 添加以下条目：
# 每日凌晨 2 点备份数据库
0 2 * * * cd /path/to/paper-translate && bash scripts/backup.sh

# 每日凌晨 3 点轮转 Nginx 日志
0 3 * * * cd /path/to/paper-translate && bash scripts/nginx-log-rotate.sh

# 每月 1 日凌晨 4 点重置配额
0 4 1 * * cd /path/to/paper-translate && bash scripts/init-quotas.sh --reset-all --force

# 每 5 分钟健康检查（可选，通知管理员）
*/5 * * * * cd /path/to/paper-translate && bash scripts/healthcheck.sh || curl -s "https://your-monitor-webhook.com/alert?service=paper-translate"
```

---

## 备份与恢复

### 备份策略

| 类型 | 频率 | 保留时间 | 存储位置 |
|------|------|---------|---------|
| 数据库全量备份 | 每日 | 30 天 | 本地 + OSS |
| 数据库全量备份 | 每周 | 90 天 | OSS 低频存储 |
| 配置文件备份 | Git 仓库 | 永久 | Git |

### 备份文件命名

```
backups/paper_translate_YYYYMMDD_HHMMSS.sql.gz
```

### 恢复流程

```bash
# 1. 列出可用备份
bash scripts/restore.sh --list

# 2. 确认要恢复的备份文件
# 3. 执行恢复（会提示确认破坏性操作）
bash scripts/restore.sh backups/paper_translate_20240101_120000.sql.gz
```

### 从 OSS 恢复

如果备份存储在 OSS 上：

```bash
# 1. 从 OSS 下载备份
ossutil cp oss://paper-translate-pdfs/db-backups/paper_translate_20240101.sql.gz ./backups/

# 2. 执行恢复
bash scripts/restore.sh backups/paper_translate_20240101.sql.gz
```

---

## 监控与告警

### 监控架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Node       │     │  API         │     │  Redis/Postgres│
│  Exporter   │     │  /metrics    │     │  Exporters   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └──────────┬─────────┴─────────┬──────────┘
                  │                   │
         ┌────────▼────────┐  ┌──────▼───────┐
         │   Prometheus    │  │   Sentry     │
         │   (端口 9090)   │  │ (错误监控)   │
         └────────┬────────┘  └──────────────┘
                  │
         ┌────────▼────────┐
         │   Grafana       │
         │   (端口 3000)   │
         └─────────────────┘
```

### 告警配置

#### 企业微信机器人

1. 在企业微信群中添加群机器人
2. 复制 Webhook URL
3. 配置环境变量：
   ```
   WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
   WECOM_WEBHOOK_MENTIONED_MOBILE=13800138000
   ```

#### LLM 成本告警

当每日 LLM 调用成本超过 `LLM_DAILY_COST_LIMIT_CNY`（默认 ¥50）时，系统会自动：

1. 发送企业微信告警
2. 发送邮件告警（如果 SMTP 已配置）
3. 记录告警日志

#### 外部监控（推荐）

推荐使用 UptimeRobot（免费）进行外部监控：

1. 注册 UptimeRobot
2. 添加 HTTP(s) 监控
3. URL: `https://yourdomain.com/api/v1/health`
4. 监控间隔: 5 分钟
5. 告警方式: 邮件 / 短信 / 企业微信

---

## 扩容指南

### 水平扩容（多实例）

当单个 API 或 Worker 实例不够用时：

```yaml
# docker-compose.prod.yml 中增加实例数
api:
  deploy:
    replicas: 2

worker:
  deploy:
    replicas: 2
```

### 垂直扩容（更大实例）

```yaml
worker:
  deploy:
    resources:
      limits:
        memory: 8g   # 从 4g 提升到 8g
        cpus: "8"     # 从 4 核提升到 8 核
```

### Redis 集群

当 Redis 内存不足时：

1. 在 docker-compose.prod.yml 中增加 maxmemory
2. 或使用 Redis Cluster（需要额外配置）

### PostgreSQL 优化

```yaml
postgres:
  deploy:
    resources:
      limits:
        memory: 4g   # 从 1g 提升
```

数据库参数优化（在 postgresql.conf 中）：

```
shared_buffers = 1GB           # 系统内存的 25%
effective_cache_size = 3GB     # 系统内存的 75%
work_mem = 64MB                # 排序和哈希操作
maintenance_work_mem = 256MB   # 维护操作
random_page_cost = 1.1         # SSD 优化
```

### 对象存储优化

如果 OSS 流量较大：

1. 启用 CDN 加速（阿里云 CDN / CloudFront）
2. 配置 OSS 传输加速
3. 考虑使用 OSS 内网 endpoint（同地域）

---

## 常见运维问题

### 1. Worker OOM（内存不足）

**症状**：Worker 容器被 kill，状态为 "exited (137)"

**解决方案**：

```bash
# 1. 检查当前内存使用
docker stats paper-translate-worker

# 2. 增加 Worker 内存限制（编辑 docker-compose.prod.yml）
#    memory_limit: 4g → 8g

# 3. 限制 Dramatiq 并发进程数
#    --processes 2 → --processes 1
```

### 2. Redis 连接拒绝

**症状**：API 日志显示 "Cannot connect to Redis"

**解决方案**：

```bash
# 1. 检查 Redis 是否运行
docker ps | grep redis

# 2. 检查 Redis 日志
docker logs paper-translate-redis

# 3. 重启 Redis
docker compose -f docker-compose.prod.yml restart redis
```

### 3. PostgreSQL 连接过多

**症状**：API 返回 500，日志显示 "too many connections"

**解决方案**：

```bash
# 1. 查看当前连接数
docker exec paper-translate-postgres \
    psql -U paper_translate -c "SELECT count(*) FROM pg_stat_activity;"

# 2. 增加最大连接数
docker exec paper-translate-postgres \
    psql -U paper_translate -c "ALTER SYSTEM SET max_connections = 200;"

# 3. 重启 PostgreSQL
docker compose -f docker-compose.prod.yml restart postgres
```

### 4. SSL 证书过期

**症状**：浏览器显示 "NET::ERR_CERT_DATE_INVALID"

**解决方案**：

```bash
# 1. 检查证书过期时间
openssl x509 -in nginx/certs/fullchain.pem -noout -dates

# 2. 手动更新 Let's Encrypt 证书
sudo certbot renew
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/certs/

# 3. 重载 Nginx
docker exec paper-translate-nginx nginx -s reload
```

### 5. 磁盘空间不足

**症状**：Docker 日志报 "no space left on device"

**解决方案**：

```bash
# 1. 清理 Docker 无用资源
docker system prune -a --volumes

# 2. 查看各目录占用
du -sh /var/lib/docker/*

# 3. 迁移 Docker 数据目录（如有更大磁盘）
# 编辑 /etc/docker/daemon.json
# { "data-root": "/data/docker" }
```

### 6. 翻译任务一直 Pending

**症状**：提交翻译任务后状态一直是 pending

**解决方案**：

```bash
# 1. 检查 Worker 是否运行
docker ps | grep worker

# 2. 检查 Worker 日志
docker logs paper-translate-worker --tail=50

# 3. 检查 Redis 队列
docker exec paper-translate-redis redis-cli LLEN dramatiq:default

# 4. 重启 Worker
docker compose -f docker-compose.prod.yml restart worker
```

---

## Windows 兼容性提示

这些部署脚本主要针对 **Linux 生产服务器**。如果需要在 Windows 上使用：

### 使用 Docker Desktop（推荐）

1. 安装 Docker Desktop for Windows（启用 WSL2 后端）
2. 直接使用 `docker compose -f docker-compose.prod.yml up -d`
3. Windows 上不需要运行 `.sh` 脚本，用 Docker Desktop 管理即可

### Windows 上的 Shell 脚本

- 脚本使用 Bash 语法，Windows 可用 Git Bash 或 WSL 运行
- 已配置 `set -euo pipefail` 确保安全

### 本地开发

```bash
# 使用开发版本（非生产）
docker compose up -d
```

---

## 服务架构

```
用户 → Nginx (443/80)
        ├── /api/* → API (FastAPI :8000)
        │               ├── PostgreSQL (业务数据)
        │               ├── Redis (缓存/队列)
        │               └── Worker (pdf2zh 翻译)
        └── /* → Frontend (Nginx 静态资源)
```

---

## 参考链接

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Dramatiq 文档](https://dramatiq.io/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Sentry](https://sentry.io/)
- [Prometheus](https://prometheus.io/)
- [阿里云 OSS](https://help.aliyun.com/product/31815.html)
- [企业微信机器人](https://developer.work.weixin.qq.com/document/path/91770)
