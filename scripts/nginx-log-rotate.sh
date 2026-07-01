#!/usr/bin/env bash
set -euo pipefail

NGINX_CONTAINER="paper-translate-nginx"
LOG_DIR="/var/log/nginx"
RETENTION_DAYS=7
COMPRESS=true
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -d, --days DAYS       Retention days for logs (default: 7)
  -f, --force           Force rotate even if not needed
  --no-compress         Skip compression
  -h, --help            Show this help message

Examples:
  ./$(basename "$0")                      # Rotate with defaults
  ./$(basename "$0") -d 14               # Keep 14 days
  ./$(basename "$0") -f --no-compress    # Force rotate without gzip
EOF
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        -d|--days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --no-compress)
            COMPRESS=false
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
echo " Nginx Log Rotation"
echo "=========================================="
echo " Container:    $NGINX_CONTAINER"
echo " Log dir:      $LOG_DIR"
echo " Retention:    $RETENTION_DAYS days"
echo " Compress:     $COMPRESS"
echo " Force:        $FORCE"
echo "=========================================="

if ! docker ps --format '{{.Names}}' | grep -q "^${NGINX_CONTAINER}$"; then
    echo "[ERROR] Nginx container '$NGINX_CONTAINER' is not running."
    echo "[ERROR] Start the services first."
    exit 1
fi

CURRENT_DATE=$(date +"%Y%m%d")
ROTATE_SUFFIX="${CURRENT_DATE}"

echo "[INFO] Step 1/3: Creating log directory if needed..."
docker exec "$NGINX_CONTAINER" mkdir -p "$LOG_DIR/archive"

echo "[INFO] Step 2/3: Rotating logs..."
ACCESS_LOG="$LOG_DIR/access.log"
ERROR_LOG="$LOG_DIR/error.log"

ACCESS_SIZE=$(docker exec "$NGINX_CONTAINER" wc -c < "$ACCESS_LOG" 2>/dev/null || echo 0)
ERROR_SIZE=$(docker exec "$NGINX_CONTAINER" wc -c < "$ERROR_LOG" 2>/dev/null || echo 0)

if [ "$ACCESS_SIZE" -eq 0 ] && [ "$ERROR_SIZE" -eq 0 ] && [ "$FORCE" = false ]; then
    echo "[INFO] Logs are empty. Nothing to rotate."
    exit 0
fi

echo "[INFO] Current access.log size: $(numfmt --to=iec-i "$ACCESS_SIZE" 2>/dev/null || echo "${ACCESS_SIZE}B")"
echo "[INFO] Current error.log size: $(numfmt --to=iec-i "$ERROR_SIZE" 2>/dev/null || echo "${ERROR_SIZE}B")"

docker exec "$NGINX_CONTAINER" sh -c "
    if [ -s $ACCESS_LOG ]; then
        cp $ACCESS_LOG ${LOG_DIR}/archive/access_${ROTATE_SUFFIX}.log
    fi
    if [ -s $ERROR_LOG ]; then
        cp $ERROR_LOG ${LOG_DIR}/archive/error_${ROTATE_SUFFIX}.log
    fi
"

docker exec "$NGINX_CONTAINER" nginx -s reopen

docker exec "$NGINX_CONTAINER" sh -c "
    : > $ACCESS_LOG
    : > $ERROR_LOG
"

if [ "$COMPRESS" = true ]; then
    echo "[INFO] Compressing rotated logs..."
    docker exec "$NGINX_CONTAINER" sh -c "
        if command -v gzip > /dev/null 2>&1; then
            cd ${LOG_DIR}/archive
            for f in access_${ROTATE_SUFFIX}.log error_${ROTATE_SUFFIX}.log; do
                if [ -f \"\$f\" ]; then
                    gzip -f \"\$f\"
                fi
            done
            echo 'Compression complete'
        else
            echo 'gzip not found in container, skipping compression'
        fi
    "
fi

echo "[INFO] Step 3/3: Cleaning up logs older than $RETENTION_DAYS days..."
docker exec "$NGINX_CONTAINER" find "$LOG_DIR/archive" -name '*.log' -mtime "+$RETENTION_DAYS" -delete 2>/dev/null || true
docker exec "$NGINX_CONTAINER" find "$LOG_DIR/archive" -name '*.log.gz' -mtime "+$RETENTION_DAYS" -delete 2>/dev/null || true

CLEANUP_COUNT=$(docker exec "$NGINX_CONTAINER" sh -c "find $LOG_DIR/archive -name '*.log*' | wc -l" 2>/dev/null || echo 0)
echo "[OK] Current archived logs: $CLEANUP_COUNT file(s)"

echo ""
echo "=========================================="
echo " Log rotation completed!"
echo "=========================================="
echo " Archive: $LOG_DIR/archive/ (inside container)"
echo " Archive: nginx_logs volume (host)"

CLEANUP_COUNT_HOST=$(find /var/lib/docker/volumes/paper-translate-prod-nginx-logs*/_data/archive -name '*.log*' 2>/dev/null | wc -l || echo 0)
if [ "$CLEANUP_COUNT_HOST" -gt 0 ]; then
    echo " Host archive count: $CLEANUP_COUNT_HOST file(s)"
fi
