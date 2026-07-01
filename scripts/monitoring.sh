#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
MONITORING_DIR="$PROJECT_DIR/monitoring"

ensure_prometheus_config() {
    mkdir -p "$MONITORING_DIR"
    if [ ! -f "$MONITORING_DIR/prometheus.yml" ]; then
        cat > "$MONITORING_DIR/prometheus.yml" << 'PROMEOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s

alerting:
  alertmanagers:
    - static_configs:
        - targets: []

rule_files:

scrape_configs:
  - job_name: node
    static_configs:
      - targets:
        - node_exporter:9100
        labels:
          service: paper-translate
          env: production

  - job_name: api
    static_configs:
      - targets:
        - api:8000
        labels:
          service: paper-translate-api
          env: production
    metrics_path: /metrics

  - job_name: redis
    static_configs:
      - targets:
        - redis:6379
        labels:
          service: paper-translate-redis
          env: production

  - job_name: postgres
    static_configs:
      - targets:
        - postgres:5432
        labels:
          service: paper-translate-postgres
          env: production
PROMEOF
        echo "[OK] Prometheus config created: $MONITORING_DIR/prometheus.yml"
    else
        echo "[INFO] Prometheus config already exists."
    fi
}

case "${1:-start}" in
    start)
        echo "=========================================="
        echo " Monitoring Stack Startup"
        echo "=========================================="

        ensure_prometheus_config

        echo "[INFO] Starting Prometheus and Node Exporter..."
        docker compose -f "$COMPOSE_FILE" --profile monitoring up -d prometheus node_exporter

        echo "[INFO] Waiting for services to be ready..."
        sleep 5

        echo ""
        echo "=========================================="
        echo " Monitoring Stack is running!"
        echo "=========================================="
        echo ""
        echo " Prometheus:  http://localhost:9090"
        echo " Node Exporter: http://localhost:9100/metrics"
        echo ""

        cat << 'EOF'
告警配置指南
==============

1. 企业微信机器人告警（推荐）
   - 在企业微信群中添加机器人，获取 Webhook URL
   - 设置环境变量：
     WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
     WECOM_WEBHOOK_MENTIONED_MOBILE=13800138000

2. 邮件告警
   - 配置 SMTP 环境变量（见 .env）
   - LLM 成本超限时将自动发送邮件

3. UptimeRobot（外部监控）
   - 注册 UptimeRobot（免费）
   - 添加监控：HTTP(s) → https://yourdomain.com/api/v1/health
   - 监控间隔：5 分钟
   - 告警方式：邮件 / 短信 / 企业微信

4. Prometheus Alertmanager（高级）
   - 参考文档：https://prometheus.io/docs/alerting/latest/alertmanager/
EOF
        ;;

    stop)
        echo "[INFO] Stopping monitoring stack..."
        docker compose -f "$COMPOSE_FILE" --profile monitoring stop prometheus node_exporter
        echo "[OK] Monitoring stack stopped."
        ;;

    restart)
        echo "[INFO] Restarting monitoring stack..."
        docker compose -f "$COMPOSE_FILE" --profile monitoring restart prometheus node_exporter
        echo "[OK] Monitoring stack restarted."
        ;;

    status)
        echo "Monitoring Stack Status:"
        echo "========================"
        docker compose -f "$COMPOSE_FILE" --profile monitoring ps prometheus node_exporter --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
        ;;

    logs)
        echo "Monitoring Stack Logs:"
        echo "======================"
        docker compose -f "$COMPOSE_FILE" --profile monitoring logs --tail=50 prometheus node_exporter
        ;;

    *)
        echo "Usage: $(basename "$0") {start|stop|restart|status|logs}"
        echo ""
        echo "  start    Start Prometheus + Node Exporter"
        echo "  stop     Stop monitoring services"
        echo "  restart  Restart monitoring services"
        echo "  status   Show service status"
        echo "  logs     Show recent logs"
        exit 0
        ;;
esac
