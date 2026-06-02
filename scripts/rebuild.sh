#!/usr/bin/env bash
# Полная пересборка образа и пересоздание контейнера bot (без git pull).
#
#   ./scripts/rebuild.sh              # build + up --force-recreate
#   ./scripts/rebuild.sh --no-cache   # пересборка без кэша Docker
#   ./scripts/rebuild.sh --logs       # tail логов
#
# С git pull на сервере: ./scripts/deploy.sh
# Только перезапуск: ./scripts/restart.sh
# Замена data/app.db: ./scripts/restore_db.sh (не rebuild)
#
set -euo pipefail

# shellcheck source=scripts/deploy_lib.sh
source "$(cd "$(dirname "$0")" && pwd)/deploy_lib.sh"
_deploy_lib_init

usage() {
  sed -n '3,10p' "$0" | sed 's/^# \?//'
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

_rebuild() {
  local no_cache="${1:-0}"
  _check_token
  _fix_data_perms
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
