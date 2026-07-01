#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
ENV_FILE="$PROJECT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] .env file not found at $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

usage() {
    cat <<EOF
Usage: $(basename "$0") [options] <backup_file>

Options:
  -l, --list       List available backups
  -h, --help       Show this help message

Arguments:
  backup_file      Path to the backup file to restore (.sql.gz or .sql)

Examples:
  ./$(basename "$0") --list
  ./$(basename "$0") ../backups/paper_translate_20240101_120000.sql.gz
  ./$(basename "$0") ../backups/paper_translate_20240101_120000.sql
EOF
    exit 0
}

list_backups() {
    echo "Available backups in $BACKUP_DIR:"
    echo "=========================================="
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        echo "No backups found."
        exit 0
    fi
    find "$BACKUP_DIR" -name '*.sql.gz' -o -name '*.sql' | sort -r | while read -r f; do
        size=$(du -h "$f" | cut -f1)
        echo "  $f  ($size)"
    done
    exit 0
}

if [ $# -lt 1 ]; then
    usage
fi

case "${1:-}" in
    -l|--list)
        list_backups
        ;;
    -h|--help)
        usage
        ;;
    *)
        RESTORE_FILE="$1"
        ;;
esac

if [ ! -f "$RESTORE_FILE" ]; then
    echo "[ERROR] Backup file not found: $RESTORE_FILE"
    list_backups
    exit 1
fi

echo "=========================================="
echo " Database Restore Script"
echo "=========================================="
echo ""
echo "[WARN] THIS IS A DESTRUCTIVE OPERATION!"
echo "[WARN] Database '${POSTGRES_DB:-paper_translate}' will be DROPPED and RECREATED."
echo "[WARN] All current data will be LOST."
echo ""
echo "Source backup: $RESTORE_FILE"
echo ""

read -r -p "Are you ABSOLUTELY SURE? Type 'yes' to confirm: " confirm
if [ "$confirm" != "yes" ]; then
    echo "[INFO] Restore cancelled."
    exit 0
fi

read -r -p "Enter the database name to restore into [${POSTGRES_DB:-paper_translate}]: " db_name
db_name="${db_name:-${POSTGRES_DB:-paper_translate}}"

echo "[INFO] Step 1/4: Checking PostgreSQL container..."
if ! docker ps --format '{{.Names}}' | grep -q "^paper-translate-postgres$"; then
    echo "[ERROR] PostgreSQL container 'paper-translate-postgres' is not running."
    exit 1
fi

echo "[INFO] Step 2/4: Dropping existing connections to $db_name..."
docker exec paper-translate-postgres \
    psql -U "${POSTGRES_USER:-paper_translate}" -d postgres \
    -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '$db_name' AND pid <> pg_backend_pid();" 2>/dev/null || true

echo "[INFO] Step 3/4: Dropping and recreating database..."
docker exec paper-translate-postgres \
    psql -U "${POSTGRES_USER:-paper_translate}" -d postgres \
    -c "DROP DATABASE IF EXISTS $db_name;"
docker exec paper-translate-postgres \
    psql -U "${POSTGRES_USER:-paper_translate}" -d postgres \
    -c "CREATE DATABASE $db_name WITH ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';"

echo "[INFO] Step 4/4: Restoring from backup..."
case "$RESTORE_FILE" in
    *.gz)
        gunzip -c "$RESTORE_FILE" | docker exec -i paper-translate-postgres \
            pg_restore -U "${POSTGRES_USER:-paper_translate}" -d "$db_name" --clean --if-exists
        ;;
    *.sql)
        cat "$RESTORE_FILE" | docker exec -i paper-translate-postgres \
            psql -U "${POSTGRES_USER:-paper_translate}" -d "$db_name"
        ;;
    *)
        echo "[ERROR] Unsupported backup format. Use .sql or .sql.gz files."
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo " Restore completed successfully!"
echo "=========================================="
echo " Database: $db_name"
echo " Source:   $RESTORE_FILE"
echo ""
echo "[INFO] Restarting API and Worker to pick up restored data..."
docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" restart api worker

echo "[INFO] Restore process finished."
