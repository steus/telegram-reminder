# Общие функции для deploy/rebuild/restore_db (source, не запускать напрямую).
# shellcheck shell=bash

_deploy_lib_init() {
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT"
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
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

# Права на data/ — без удаления WAL/SHM (иначе при работающем боте возможна потеря данных).
_fix_data_perms() {
  local uid gid
  uid="$(_read_env_var UID "$(id -u)")"
  gid="$(_read_env_var GID "$(id -g)")"
  mkdir -p data backups
  chown -R "${uid}:${gid}" data backups
  chmod 755 data backups
  if [[ -f data/app.db ]]; then
    chmod 664 data/app.db
  fi
  echo "Permissions: data/ backups/ → ${uid}:${gid}"
}

_remove_sqlite_sidecars() {
  rm -f data/app.db-shm data/app.db-wal
}

_stop_bot() {
  "${COMPOSE[@]}" stop bot 2>/dev/null || true
}
