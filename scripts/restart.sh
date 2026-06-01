#!/usr/bin/env bash
# Перезапуск контейнера bot (без git pull и без пересборки образа).
#
#   ./scripts/restart.sh          # docker compose restart bot
#   ./scripts/restart.sh --logs   # tail логов после рестарта
#
# Обновление с git pull: ./scripts/deploy.sh
# Пересборка без pull: ./scripts/rebuild.sh
# После смены только .env или «подвис» бот — достаточно этого скрипта.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

usage() {
  sed -n '3,9p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

_ensure_docker() {
  command -v docker >/dev/null 2>&1 || {
    echo "ERROR: docker not found" >&2
    exit 1
  }
  docker compose version >/dev/null 2>&1 || {
    echo "ERROR: docker compose plugin not found" >&2
    exit 1
  }
}

_logs() {
  "${COMPOSE[@]}" logs -f --tail=100 bot
}

main() {
  _ensure_docker
  case "${1:-}" in
    -h|--help|help) usage 0 ;;
    --logs) _logs ;;
    "")
      echo "Restarting bot container..."
      "${COMPOSE[@]}" restart bot
      echo "OK. Logs: ./scripts/restart.sh --logs"
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
}

main "$@"
