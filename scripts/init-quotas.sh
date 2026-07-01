#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] .env file not found at $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

QUOTA_FREE_DAILY=${QUOTA_FREE_DAILY_PAGES:-5}
QUOTA_FREE_MONTHLY=${QUOTA_FREE_MONTHLY_PAGES:-30}
QUOTA_STANDARD_MONTHLY=${QUOTA_STANDARD_MONTHLY_PAGES:-200}
QUOTA_PRO_MONTHLY=${QUOTA_PRO_MONTHLY_PAGES:-800}

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --daily-pages N    Override free daily pages (default: $QUOTA_FREE_DAILY)
  --monthly-pages N  Override free monthly pages (default: $QUOTA_FREE_MONTHLY)
  --reset-all        Reset all users' used quota to 0
  --force            Skip confirmation prompt
  -h, --help         Show this help message

Examples:
  ./$(basename "$0")                          # Reset with defaults
  ./$(basename "$0") --daily-pages 10         # Set free daily to 10 pages
  ./$(basename "$0") --reset-all --force      # Reset all without prompt
EOF
    exit 0
}

RESET_ALL=false
FORCE=false

while [ $# -gt 0 ]; do
    case "$1" in
        --daily-pages)
            QUOTA_FREE_DAILY="$2"
            shift 2
            ;;
        --monthly-pages)
            QUOTA_FREE_MONTHLY="$2"
            shift 2
            ;;
        --reset-all)
            RESET_ALL=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "[ERROR] Unknown option: $1"
            usage
            ;;
    esac
done

echo "=========================================="
echo " 配额初始化脚本"
echo "=========================================="
echo ""
echo " 免费档:  每日 $QUOTA_FREE_DAILY 页 / 每月 $QUOTA_FREE_MONTHLY 页"
echo " 标准档:  每月 $QUOTA_STANDARD_MONTHLY 页"
echo " Pro 档:  每月 $QUOTA_PRO_MONTHLY 页"
if [ "$RESET_ALL" = true ]; then
    echo " 模式:    重置所有用户已用配额为 0"
fi
echo ""

if [ "$FORCE" = false ]; then
    read -r -p "Continue? [y/N]: " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "[INFO] Cancelled."
        exit 0
    fi
fi

if ! docker ps --format '{{.Names}}' | grep -q "^paper-translate-postgres$"; then
    echo "[ERROR] PostgreSQL container is not running."
    echo "[ERROR] Start services first: docker compose -f $COMPOSE_FILE up -d postgres"
    exit 1
fi

echo "[INFO] PostgreSQL container found. Running quota initialization..."

if [ "$RESET_ALL" = true ]; then
    SQL="
    UPDATE quotas SET used_daily = 0, used_monthly = 0, updated_at = NOW();
    SELECT 'OK' AS result, COUNT(*) AS updated_users FROM quotas WHERE used_daily = 0 AND used_monthly = 0;
    "
    echo "[INFO] Resetting all users' used quotas to 0..."
    RESULT=$(docker exec paper-translate-postgres \
        psql -U "${POSTGRES_USER:-paper_translate}" \
        -d "${POSTGRES_DB:-paper_translate}" \
        -t -A -c "$SQL" 2>/dev/null)
    echo "[OK] $RESULT"
fi

SQL="
INSERT INTO quotas (user_id, plan, daily_limit, monthly_limit, used_daily, used_monthly, created_at, updated_at)
SELECT
    u.id,
    'free',
    $QUOTA_FREE_DAILY,
    $QUOTA_FREE_MONTHLY,
    0,
    0,
    NOW(),
    NOW()
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM quotas q WHERE q.user_id = u.id)
AND u.id NOT IN (SELECT user_id FROM quotas);
SELECT 'OK' AS result, COUNT(*) AS initialized_users FROM users u WHERE NOT EXISTS (SELECT 1 FROM quotas q WHERE q.user_id = u.id);
"

echo "[INFO] Initializing quotas for users without quota records..."
RESULT=$(docker exec paper-translate-postgres \
    psql -U "${POSTGRES_USER:-paper_translate}" \
    -d "${POSTGRES_DB:-paper_translate}" \
    -t -A -c "$SQL" 2>/dev/null)
echo "[OK] $RESULT"

echo ""
echo "=========================================="
echo " 配额初始化完成"
echo "=========================================="
echo ""
echo "配额汇总:"
docker exec paper-translate-postgres \
    psql -U "${POSTGRES_USER:-paper_translate}" \
    -d "${POSTGRES_DB:-paper_translate}" \
    -t -A \
    -c "SELECT plan, COUNT(*) AS users, SUM(used_daily) AS total_daily_used, SUM(used_monthly) AS total_monthly_used FROM quotas GROUP BY plan ORDER BY plan;" 2>/dev/null | while IFS='|' read -r plan users daily monthly; do
        echo "  Plan: $plan | Users: $users | Daily Used: $daily | Monthly Used: $monthly"
    done

echo ""

if [ "$RESET_ALL" = true ]; then
    echo "[HINT] 已重置所有配额为 0，建议在每月 1 日运行此脚本"
fi
echo "[HINT] 添加 crontab 自动重置："
echo "  0 0 1 * * cd $PROJECT_DIR && bash scripts/init-quotas.sh --reset-all --force"
