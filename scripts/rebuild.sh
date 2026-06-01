#!/usr/bin/env bash
# Полная пересборка образа и пересоздание контейнера bot (без git pull).
#
#   ./scripts/rebuild.sh              # build + up --force-recreate
#   ./scripts/rebuild.sh --no-cache   # пересборка без кэша Docker
#   ./scripts/rebuild.sh --logs       # tail логов
#
# С git pull на сервере: ./scripts/deploy.sh
# Только перезапуск: ./scripts/restart.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

usage() {
  sed -n '3,10p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

_read_env_var() {
  local key="$1" default="${2:-}"
  if [[ -f .env ]]; then
    local val
    val="$(grep -E "^${key}=" .env | tail -1 | cut -d= -f2- || true)"
    if [[ -n "$val" ]]; then
      echo "$val"
      return
    fi
  fi
  echo "$default"
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

_check_token() {
  local token
  token="$(_read_env_var TELEGRAM_BOT_TOKEN)"
  if [[ -z "$token" ]]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN is empty in .env" >&2
    exit 1
  fi
}

_fix_perms() {
  local uid gid
  uid="$(_read_env_var UID "$(id -u)")"
  gid="$(_read_env_var GID "$(id -g)")"
  mkdir -p data backups
  chown -R "${uid}:${gid}" data backups
  chmod 755 data backups
  if [[ -f data/app.db ]]; then
    chmod 664 data/app.db
  fi
  rm -f data/app.db-shm data/app.db-wal
  echo "Permissions: data/ backups/ → ${uid}:${gid}"
}

_rebuild() {
  local no_cache="${1:-0}"
  _check_token
  _fix_perms
  local build_args=(build)
  if [[ "$no_cache" == 1 ]]; then
    echo "Building image bot (--no-cache)..."
    build_args+=(--no-cache)
  else
    echo "Building image bot..."
  fi
  build_args+=(bot)
  "${COMPOSE[@]}" "${build_args[@]}"
  echo "Recreating container..."
  "${COMPOSE[@]}" up -d --force-recreate --no-deps bot
  echo ""
  echo "OK. Logs: ./scripts/rebuild.sh --logs"
}

_logs() {
  "${COMPOSE[@]}" logs -f --tail=100 bot
}

main() {
  _ensure_docker
  case "${1:-}" in
    -h|--help|help) usage 0 ;;
    --no-cache) _rebuild 1 ;;
    --logs) _logs ;;
    "") _rebuild 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
}

main "$@"
