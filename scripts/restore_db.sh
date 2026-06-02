#!/usr/bin/env bash
# Заменить production-БД файлом-дампом. Не делает git pull и не пересобирает образ.
#
#   ./scripts/restore_db.sh /path/to/backup.db
#   ./scripts/restore_db.sh /path/to/backup.db --no-backup   # без копии текущей БД
#   ./scripts/restore_db.sh /path/to/backup.db --no-start    # только заменить файл
#
# Обычное обновление кода: ./scripts/deploy.sh (data/app.db не трогает).
#
set -euo pipefail

# shellcheck source=scripts/deploy_lib.sh
source "$(cd "$(dirname "$0")" && pwd)/deploy_lib.sh"
_deploy_lib_init

usage() {
  sed -n '3,10p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

main() {
  _ensure_docker

  local src="${1:-}"
  local do_backup=1
  local do_start=1

  shift || true
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-backup) do_backup=0 ;;
      --no-start) do_start=0 ;;
      -h|--help|help) usage 0 ;;
      *)
        echo "Unknown option: $1" >&2
        usage 1
        ;;
    esac
    shift
  done

  if [[ -z "$src" ]]; then
    echo "Usage: ./scripts/restore_db.sh /path/to/backup.db [--no-backup] [--no-start]" >&2
    exit 1
  fi
  if [[ ! -f "$src" ]]; then
    echo "ERROR: file not found: $src" >&2
    exit 1
  fi

  echo "Stopping bot before database replace..."
  _stop_bot

  if [[ -f data/app.db && "$do_backup" == 1 ]]; then
    echo "Backing up current database..."
    ./scripts/backup_db.sh
  fi

  mkdir -p data
  cp -a "$src" data/app.db
  _remove_sqlite_sidecars
  _fix_data_perms
  echo "Database restored to data/app.db from: $src"

  if [[ "$do_start" == 1 ]]; then
    echo "Starting bot..."
    "${COMPOSE[@]}" up -d bot
    echo "OK. Logs: ./scripts/deploy.sh --logs"
  else
    echo "Bot not started (--no-start). Run: ./scripts/restart.sh or ./scripts/deploy.sh"
  fi
}

main "$@"
