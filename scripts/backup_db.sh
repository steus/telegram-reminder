#!/usr/bin/env bash
# Резервная копия SQLite (§14 ТЗ). Ручной прогон:
#   ./scripts/backup_db.sh
# Cron (ежедневно в 03:00, с хоста где лежит data/app.db):
#   0 3 * * * cd /opt/bot-tracker && ./scripts/backup_db.sh >> /var/log/bot-tracker-backup.log 2>&1
#
# Docker: том ./data смонтирован в контейнер — бэкап с хоста по тому же пути.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${DATABASE_PATH:-$ROOT/data/app.db}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$BACKUP_DIR/app_${STAMP}.db"

# sqlite3 .backup — консистентная копия при работающем боте (если sqlite3 установлен)
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$DEST'"
else
  cp -a "$DB_PATH" "$DEST"
fi

find "$BACKUP_DIR" -name 'app_*.db' -type f -mtime +"$KEEP_DAYS" -delete
echo "Backup saved: $DEST"
