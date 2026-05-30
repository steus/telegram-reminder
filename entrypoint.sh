#!/usr/bin/env bash
set -euo pipefail

# Применяем миграции, затем запускаем бота (§14 ТЗ).
echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python -m app.main
