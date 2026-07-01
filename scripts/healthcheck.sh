#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

EXIT_CODE=0

print_status() {
    local service="$1"
    local status="$2"
    local message="$3"
    if [ "$status" = "OK" ]; then
        echo -e "  [${GREEN}OK${NC}]     $service - $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "  [${YELLOW}WARN${NC}]   $service - $message"
    else
        echo -e "  [${RED}FAIL${NC}]   $service - $message"
        EXIT_CODE=1
    fi
}

echo "=========================================="
echo " Paper Translate - 完整健康检查"
echo " Timestamp: $(date +'%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

echo "[1/6] Docker 容器状态检查"
echo "------------------------"
EXPECTED_CONTAINERS=(
    "paper-translate-nginx"
    "paper-translate-frontend"
    "paper-translate-api"
    "paper-translate-worker"
    "paper-translate-redis"
    "paper-translate-postgres"
)

for container in "${EXPECTED_CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        status=$(docker inspect "$container" --format='{{.State.Status}}' 2>/dev/null)
        health=$(docker inspect "$container" --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null)
        if [ "$status" = "running" ]; then
            if [ "$health" = "healthy" ]; then
                print_status "$container" "OK" "Running, health: $health"
            elif [ "$health" = "none" ]; then
                print_status "$container" "OK" "Running (no healthcheck)"
            elif [ "$health" = "starting" ]; then
                print_status "$container" "WARN" "Running, health: starting"
            else
                print_status "$container" "FAIL" "Running but unhealthy (health: $health)"
            fi
        else
            print_status "$container" "FAIL" "Status: $status"
        fi
    else
        print_status "$container" "FAIL" "Container not running"
    fi
done

echo ""
echo "[2/6] API 健康检查"
echo "------------------"
HEALTH_URL="http://localhost/api/v1/health"
if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    RESPONSE=$(curl -s "$HEALTH_URL")
    print_status "API /health" "OK" "$RESPONSE"
else
    print_status "API /health" "FAIL" "Unreachable at $HEALTH_URL"
fi

echo ""
echo "[3/6] Redis 连通性检查"
echo "----------------------"
if docker exec paper-translate-redis redis-cli ping > /dev/null 2>&1; then
    REDIS_INFO=$(docker exec paper-translate-redis redis-cli INFO memory 2>/dev/null | grep -E "^used_memory_human|^maxmemory_human" | tr '\n' ' ' | tr -d '\r')
    print_status "Redis Ping" "OK" "PONG ($REDIS_INFO)"
else
    print_status "Redis Ping" "FAIL" "Cannot connect to Redis"
fi

echo ""
echo "[4/6] PostgreSQL 连通性检查"
echo "---------------------------"
POSTGRES_USER="${POSTGRES_USER:-paper_translate}"
POSTGRES_DB="${POSTGRES_DB:-paper_translate}"
if docker exec paper-translate-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
    PG_VERSION=$(docker exec paper-translate-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT version();" 2>/dev/null | head -1 | sed 's/^ *//')
    PG_CONN=$(docker exec paper-translate-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='$POSTGRES_DB';" 2>/dev/null | tr -d ' ')
    print_status "PostgreSQL" "OK" "Ready | $PG_CONN active connections"
else
    print_status "PostgreSQL" "FAIL" "Cannot connect to PostgreSQL"
fi

echo ""
echo "[5/6] 磁盘空间检查"
echo "------------------"
DISK_THRESHOLD=80
if command -v df &> /dev/null; then
    df -h / | tail -1 | while read -r fs size used avail usepct mounted; do
        use_pct_num=${usepct%\%}
        if [ "$use_pct_num" -gt "$DISK_THRESHOLD" ]; then
            print_status "Disk /" "FAIL" "${usepct} used (threshold: ${DISK_THRESHOLD}%)"
        else
            print_status "Disk /" "OK" "${usepct} used (${avail} available)"
        fi
    done
    DOCKER_DISK=$(docker system df 2>/dev/null | grep "Images" | awk '{print $4}')
    print_status "Docker Disk" "OK" "Images disk: ${DOCKER_DISK:-N/A}"
else
    print_status "Disk /" "WARN" "df command not available"
fi

echo ""
echo "[6/6] 内存使用检查"
echo "------------------"
MEM_THRESHOLD=80
if command -v free &> /dev/null; then
    MEM_INFO=$(free -m | grep "Mem:")
    MEM_TOTAL=$(echo "$MEM_INFO" | awk '{print $2}')
    MEM_USED=$(echo "$MEM_INFO" | awk '{print $3}')
    MEM_PCT=$(( MEM_USED * 100 / MEM_TOTAL ))
    if [ "$MEM_PCT" -gt "$MEM_THRESHOLD" ]; then
        print_status "Memory" "FAIL" "${MEM_PCT}% used (${MEM_USED}MB/${MEM_TOTAL}MB) - threshold: ${MEM_THRESHOLD}%"
    else
        print_status "Memory" "OK" "${MEM_PCT}% used (${MEM_USED}MB/${MEM_TOTAL}MB)"
    fi
else
    print_status "Memory" "WARN" "free command not available"
fi

if command -v docker stats &> /dev/null; then
    CONTAINER_MEM=$(docker stats --no-stream --format "table {{.Name}}\t{{.MemPerc}}\t{{.MemUsage}}" 2>/dev/null | tail -n +2)
    echo ""
    echo "容器内存使用详情:"
    echo "$CONTAINER_MEM" | while read -r line; do
        echo "  $line"
    done
fi

echo ""
echo "=========================================="
if [ "$EXIT_CODE" -eq 0 ]; then
    echo -e "  ${GREEN}All checks passed!${NC}"
else
    echo -e "  ${RED}Some checks failed. Review the output above.${NC}"
fi
echo "=========================================="
exit $EXIT_CODE
