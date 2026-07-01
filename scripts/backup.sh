#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env"
DRY_RUN=false

if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
    echo "[INFO] DRY RUN MODE - No actual backup will be performed."
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] .env file not found at $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${POSTGRES_DB:-paper_translate}_${TIMESTAMP}.sql"
BACKUP_FILE_GZ="${BACKUP_FILE}.gz"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}

echo "=========================================="
echo " Database Backup Script"
echo "=========================================="
echo " Timestamp:    $TIMESTAMP"
echo " Database:     ${POSTGRES_DB:-paper_translate}"
echo " Backup file:  $BACKUP_FILE_GZ"
echo " Retention:    $RETENTION_DAYS days"
echo " Dry run:      $DRY_RUN"
echo "=========================================="

if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] Would execute: docker exec paper-translate-postgres pg_dump -U ${POSTGRES_USER:-paper_translate} -d ${POSTGRES_DB:-paper_translate} --clean --if-exists --format=custom > $BACKUP_FILE"
    echo "[DRY-RUN] Would execute: gzip $BACKUP_FILE"
    echo "[DRY-RUN] Would execute: find $BACKUP_DIR -name '*.sql.gz' -mtime +$RETENTION_DAYS -delete"
    echo "[DRY-RUN] Would execute: find $BACKUP_DIR -name '*.sql' -mtime +$RETENTION_DAYS -delete"
    exit 0
fi

echo "[INFO] Step 1/4: Checking PostgreSQL container..."
if ! docker ps --format '{{.Names}}' | grep -q "^paper-translate-postgres$"; then
    echo "[ERROR] PostgreSQL container 'paper-translate-postgres' is not running."
    echo "[ERROR] Start the services first: docker compose -f $COMPOSE_FILE up -d postgres"
    exit 1
fi

echo "[INFO] Step 2/4: Dumping database..."
docker exec paper-translate-postgres \
    pg_dump -U "${POSTGRES_USER:-paper_translate}" \
    -d "${POSTGRES_DB:-paper_translate}" \
    --clean --if-exists \
    --format=custom \
    > "$BACKUP_FILE"

gzip "$BACKUP_FILE"
echo "[OK] Backup saved: $BACKUP_FILE_GZ"
echo "[INFO] Size: $(du -h "$BACKUP_FILE_GZ" | cut -f1)"

echo "[INFO] Step 3/4: Uploading to object storage (if configured)..."
if [ -n "${OSS_ACCESS_KEY_ID:-}" ] && [ -n "${OSS_BUCKET:-}" ]; then
    if command -v ossutil &> /dev/null; then
        ossutil cp "$BACKUP_FILE_GZ" "oss://${OSS_BUCKET}/db-backups/" \
            --access-key-id "$OSS_ACCESS_KEY_ID" \
            --access-key-secret "$OSS_ACCESS_KEY_SECRET" \
            --endpoint "${OSS_ENDPOINT:-oss-cn-hangzhou.aliyuncs.com}"
        echo "[OK] Backup uploaded to OSS: oss://${OSS_BUCKET}/db-backups/"
    else
        echo "[WARN] ossutil not found. Skipping OSS upload."
        echo "[WARN] Install ossutil: https://help.aliyun.com/document_detail/120075.html"
    fi
else
    echo "[INFO] OSS not configured. Skipping cloud upload."
fi

echo "[INFO] Step 4/4: Cleaning up backups older than $RETENTION_DAYS days..."
CLEANUP_COUNT=$(find "$BACKUP_DIR" -name '*.sql.gz' -mtime "+$RETENTION_DAYS" | wc -l)
find "$BACKUP_DIR" -name '*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name '*.sql' -mtime "+$RETENTION_DAYS" -delete
echo "[OK] Removed $CLEANUP_COUNT old backup(s)."

echo ""
echo "=========================================="
echo " Backup completed successfully!"
echo "=========================================="
echo " File: $BACKUP_FILE_GZ"
ls -lh "$BACKUP_FILE_GZ"
