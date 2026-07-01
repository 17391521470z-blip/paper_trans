#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.prod.example"
LOG_DIR="$PROJECT_DIR/logs"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

cd "$PROJECT_DIR"

mkdir -p "$LOG_DIR"

echo "[$(date +"%Y-%m-%d %H:%M:%S")] Starting deployment..."

echo "[INFO] Step 1/7: Pulling latest code from git..."
git pull

echo "[INFO] Step 2/7: Ensuring .env file exists..."
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "[WARN] .env file created from .env.prod.example. Please edit .env with your actual secrets before proceeding."
        echo "[WARN] Run: vim $ENV_FILE"
        exit 1
    else
        echo "[ERROR] Neither .env nor .env.prod.example found!"
        exit 1
    fi
fi

echo "[INFO] Step 3/7: Pulling Docker images..."
docker compose -f "$COMPOSE_FILE" pull

echo "[INFO] Step 4/7: Starting services..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate

echo "[INFO] Step 5/7: Cleaning up unused Docker resources..."
docker system prune -f --volumes 2>/dev/null || true

echo "[INFO] Step 6/7: Checking service status..."
docker compose -f "$COMPOSE_FILE" ps

echo "[INFO] Step 7/7: Running health check..."
sleep 10
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
echo " Deployment completed successfully!"
echo " Timestamp: $TIMESTAMP"
echo "=========================================="
echo ""
echo "Services:"
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Logs: docker compose -f $COMPOSE_FILE logs -f"
echo "Stop:  docker compose -f $COMPOSE_FILE down"
