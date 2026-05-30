#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

if ! touch /app/data/.write_test 2>/dev/null; then
  echo "ERROR: /app/data is not writable for uid=$(id -u) gid=$(id -g)." >&2
  echo "Set UID/GID in .env to match host (id -u / id -g) and restart." >&2
  exit 1
fi
rm -f /app/data/.write_test

# Применяем миграции, затем запускаем бота (§14 ТЗ).
echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python -m app.main
