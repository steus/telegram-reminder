#!/usr/bin/env bash
# Деплой / обновление bot-tracker на VPS (Docker Compose).
#
#   ./scripts/deploy.sh --init          # первый раз: .env, каталоги, UID/GID
#   ./scripts/deploy.sh                 # git pull + пересборка + up -d
#   ./scripts/rebuild.sh                # пересборка образа без git pull
#   ./scripts/restart.sh                # только перезапуск bot
#   ./scripts/deploy.sh --db ./app.db   # залить БД (бот остановится на время копии)
#   ./scripts/deploy.sh --fix-perms   # только права на data/ по UID/GID из .env
#   ./scripts/deploy.sh --logs          # tail логов
#   ./scripts/deploy.sh --status        # ps + health check data writable
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

usage() {
  sed -n '3,12p' "$0" | sed 's/^# \?//'
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

_init_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  fi
  local uid gid
  uid="$(id -u)"
  gid="$(id -g)"
  if grep -qE '^UID=' .env; then
    sed -i "s/^UID=.*/UID=${uid}/" .env
  else
    echo "UID=${uid}" >> .env
  fi
  if grep -qE '^GID=' .env; then
    sed -i "s/^GID=.*/GID=${gid}/" .env
  else
    echo "GID=${gid}" >> .env
  fi
  echo "Set UID/GID in .env to ${uid}/${gid} (current user)."
  echo ""
  echo "Next: edit .env — at minimum TELEGRAM_BOT_TOKEN, LLM_*, GOOGLE_SERVICE_ACCOUNT_JSON."
  echo "Then: ./scripts/deploy.sh"
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

_copy_db() {
  local src="$1"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: file not found: $src" >&2
    exit 1
  fi
  "${COMPOSE[@]}" stop bot 2>/dev/null || true
  mkdir -p data
  cp -a "$src" data/app.db
  rm -f data/app.db-shm data/app.db-wal
  _fix_perms
  echo "Database copied to data/app.db"
}

_up() {
  _check_token
  _fix_perms
  if [[ -d .git ]]; then
    echo "git pull..."
    git pull --ff-only
  fi
  echo "Building and starting containers..."
  "${COMPOSE[@]}" up -d --build
  echo ""
  echo "OK. Logs: ./scripts/deploy.sh --logs"
  echo "Backup: ./scripts/backup_db.sh"
  echo "Cron example:"
  echo "  0 3 * * * cd ${ROOT} && ./scripts/backup_db.sh >> /var/log/bot-tracker-backup.log 2>&1"
}

_status() {
  "${COMPOSE[@]}" ps
  echo ""
  local uid gid
  uid="$(_read_env_var UID "$(id -u)")"
  gid="$(_read_env_var GID "$(id -g)")"
  ls -la data/ 2>/dev/null || echo "data/ missing"
  if [[ -d data ]] && touch data/.write_test 2>/dev/null; then
    rm -f data/.write_test
    echo "data/ is writable for current shell user."
  else
    echo "WARN: data/ not writable — run ./scripts/deploy.sh --fix-perms"
  fi
  echo "Container runs as UID/GID from .env: ${uid}/${gid}"
}

_logs() {
  "${COMPOSE[@]}" logs -f --tail=100 bot
}

main() {
  _ensure_docker
  local cmd="${1:-}"

  case "$cmd" in
    -h|--help|help) usage 0 ;;
    --init) _init_env ;;
    --fix-perms) _fix_perms ;;
    --db)
      [[ -n "${2:-}" ]] || {
        echo "Usage: ./scripts/deploy.sh --db /path/to/app.db" >&2
        exit 1
      }
      _copy_db "$2"
      _up
      ;;
    --logs) _logs ;;
    --status) _status ;;
    "")
      _up
      ;;
    *)
      echo "Unknown option: $cmd" >&2
      usage 1
      ;;
  esac
}

main "$@"
