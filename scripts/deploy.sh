#!/usr/bin/env bash
# Деплой / обновление bot-tracker на VPS (Docker Compose).
#
#   ./scripts/deploy.sh --init          # первый раз: .env, каталоги, UID/GID
#   ./scripts/deploy.sh                 # git pull + пересборка + up -d
#   ./scripts/rebuild.sh                # пересборка образа без git pull
#   ./scripts/restart.sh                # только перезапуск bot
#   ./scripts/restore_db.sh FILE        # заменить data/app.db (отдельно от deploy)
#   ./scripts/deploy.sh --fix-perms   # только права на data/ по UID/GID из .env
#   ./scripts/deploy.sh --logs          # tail логов
#   ./scripts/deploy.sh --status        # ps + health check data writable
#
# git pull не меняет data/app.db (каталог data/ в .gitignore).
#
set -euo pipefail

# shellcheck source=scripts/deploy_lib.sh
source "$(cd "$(dirname "$0")" && pwd)/deploy_lib.sh"
_deploy_lib_init

usage() {
  sed -n '3,14p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

_check_token() {
  local token
  token="$(_read_env_var TELEGRAM_BOT_TOKEN)"
  if [[ -z "$token" ]]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN is empty in .env" >&2
    exit 1
  fi
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

_up() {
  _check_token
  _fix_data_perms
  if [[ -d .git ]]; then
    echo "git pull..."
    git pull --ff-only
  fi
  echo "Building and starting containers..."
  echo "(data/app.db on host is unchanged — use ./scripts/restore_db.sh to replace it)"
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
  if [[ -f data/app.db ]]; then
    echo "Database: data/app.db ($(stat -c '%y' data/app.db 2>/dev/null || stat -f '%Sm' data/app.db))"
  fi
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
    --fix-perms) _fix_data_perms ;;
    --db)
      echo "ERROR: --db removed from deploy.sh (it looked like deploy overwrote the DB)." >&2
      echo "Replace database explicitly:" >&2
      echo "  ./scripts/restore_db.sh /path/to/backup.db" >&2
      exit 1
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
