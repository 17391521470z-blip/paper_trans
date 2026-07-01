#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"

cd "$PROJECT_DIR"

echo "=========================================="
echo " Rollback Script"
echo "=========================================="
echo ""
echo "[WARN] This will revert the codebase to the previous Git commit and restart all services."
echo "[WARN] Current commit: $(git log --oneline -1)"
echo ""

read -r -p "Are you sure you want to rollback? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "[INFO] Rollback cancelled."
    exit 0
fi

echo "[INFO] Step 1/4: Stopping all services..."
docker compose -f "$COMPOSE_FILE" down --timeout 60

echo "[INFO] Step 2/4: Reverting to previous Git commit..."
git reset --hard HEAD~1

echo "[INFO] Step 3/4: Rebuilding and starting services..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "[INFO] Step 4/4: Running health check..."
sleep 15
HEALTH_URL="http://localhost/api/v1/health"
MAX_RETRIES=12
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        echo "[OK] Health check passed! API is healthy."
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "[ERROR] Health check failed after $MAX_RETRIES attempts."
        echo "[ERROR] Check logs: docker compose -f $COMPOSE_FILE logs --tail=50"
        exit 1
    fi
    echo "[INFO] Waiting for API to be ready... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

echo ""
echo "=========================================="
echo " Rollback completed!"
echo " Rolled back to: $(git log --oneline -1)"
echo "=========================================="
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
