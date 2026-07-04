#!/usr/bin/env bash
# Одноразовая подготовка окружения для запуска бота БЕЗ Docker (venv + systemd).
#
# Делает (идемпотентно, можно гонять повторно):
#   1) проверяет/ставит системные пакеты: python3.12(+venv), ffmpeg, git   (apt)
#   2) создаёт .venv в корне проекта
#   3) editable-установка проекта (pip install -e .) — апдейт кода = только рестарт
#   4) создаёт .env из .env.example (если нет)
#   5) применяет миграции Alembic (alembic upgrade head)
#
# Запуск:
#   bash scripts/setup_direct.sh              # полная подготовка
#   bash scripts/setup_direct.sh --with-dev   # + dev-зависимости (pytest, ruff)
#   bash scripts/setup_direct.sh --no-apt     # пропустить установку системных пакетов
#   bash scripts/setup_direct.sh --no-migrate # не запускать alembic upgrade head
#
# После установки запуск вручную (из корня проекта):
#   .venv/bin/python -m app.main
# либо через systemd — см. deploy/bot-tracker.service (правь WorkingDirectory/EnvironmentFile).
#
# Обновление кода в будущем:
#   git pull && .venv/bin/pip install -e . && sudo systemctl restart bot-<name>
#   (pip install -e . нужен только если менялись зависимости в pyproject.toml)
#   Если появились новые миграции: .venv/bin/alembic upgrade head

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WITH_DEV=0
DO_APT=1
DO_MIGRATE=1

for arg in "$@"; do
  case "$arg" in
    --with-dev) WITH_DEV=1 ;;
    --no-apt) DO_APT=0 ;;
    --no-migrate) DO_MIGRATE=0 ;;
    -h|--help)
      sed -n '2,27p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $arg" >&2
      echo "Помощь: bash scripts/setup_direct.sh --help" >&2
      exit 1
      ;;
  esac
done

# --- 1. Выбор интерпретатора Python >= 3.12 --------------------------------
pick_python() {
  local candidate
  # python3.12 — предпочтительный (см. pyproject.toml); затем другие 3.12+
  for candidate in python3.12 python3.13 python3.14 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

venv_pkg_for_python() {
  local py="$1"
  "$py" -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")'
}

python_can_create_venv() {
  local py="$1"
  local tmp
  tmp="$(mktemp -d)"
  if "$py" -m venv "$tmp/testvenv" 2>/dev/null; then
    rm -rf "$tmp"
    return 0
  fi
  rm -rf "$tmp"
  return 1
}

# --- 2. Системные пакеты (apt) ---------------------------------------------
install_system_deps() {
  if [[ "$DO_APT" -eq 0 ]]; then
    echo "==> Пропускаю установку системных пакетов (--no-apt)"
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "==> apt-get не найден — пропускаю системные пакеты (поставь python3.12, python3.12-venv, ffmpeg, git вручную)"
    return 0
  fi

  local pkgs=()
  command -v git >/dev/null 2>&1 || pkgs+=(git)
  command -v ffmpeg >/dev/null 2>&1 || pkgs+=(ffmpeg)   # нужен для конвертации голосовых

  local py=""
  if pick_python >/dev/null 2>&1; then
    py="$(pick_python)"
    if ! python_can_create_venv "$py"; then
      pkgs+=("$(venv_pkg_for_python "$py")")
    fi
  else
    pkgs+=(python3.12 python3.12-venv)
  fi

  if [[ ${#pkgs[@]} -eq 0 ]]; then
    echo "==> Системные пакеты уже на месте (git, ffmpeg, python + venv)"
    return 0
  fi

  echo "==> Ставлю системные пакеты: ${pkgs[*]}"
  local SUDO=""
  [[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
  $SUDO apt-get update
  $SUDO apt-get install -y "${pkgs[@]}"
}

install_system_deps

PY="$(pick_python || true)"
if [[ -z "${PY:-}" ]]; then
  echo "ERROR: не найден Python >= 3.12. Установи python3.12 (+python3.12-venv) и повтори." >&2
  exit 1
fi
echo "==> Python: $PY ($("$PY" --version 2>&1))"

# --- 3. venv ----------------------------------------------------------------
if [[ -d .venv ]] && [[ ! -x .venv/bin/python ]]; then
  echo "==> Удаляю неполный .venv (прошлый запуск не завершился)"
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  echo "==> Создаю виртуальное окружение .venv"
  "$PY" -m venv .venv
else
  echo "==> .venv уже существует — переиспользую"
fi

VENV_PY=".venv/bin/python"
"$VENV_PY" -m pip install --upgrade pip >/dev/null

# --- 4. Установка проекта (editable) ---------------------------------------
if [[ "$WITH_DEV" -eq 1 ]]; then
  echo "==> Устанавливаю проект в editable-режиме (+dev)"
  "$VENV_PY" -m pip install -e ".[dev]"
else
  echo "==> Устанавливаю проект в editable-режиме"
  "$VENV_PY" -m pip install -e .
fi

# --- 5. .env ----------------------------------------------------------------
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Создан .env из .env.example — заполни как минимум TELEGRAM_BOT_TOKEN, LLM_*."
  echo "    (UID/GID в .env нужны только для Docker — для прямого запуска их можно игнорировать)"
else
  echo "==> .env уже есть — не трогаю"
fi

mkdir -p data backups

# --- 6. Миграции ------------------------------------------------------------
if [[ "$DO_MIGRATE" -eq 1 ]]; then
  echo "==> Применяю миграции (alembic upgrade head)"
  ".venv/bin/alembic" upgrade head
else
  echo "==> Пропускаю миграции (--no-migrate). Позже: .venv/bin/alembic upgrade head"
fi

# --- Итог -------------------------------------------------------------------
cat <<EOF

Готово. Окружение подготовлено.

Проверка запуска (из корня проекта, Ctrl+C для остановки):
  .venv/bin/python -m app.main

Постоянный запуск через systemd:
  1) правь deploy/bot-tracker.service: WorkingDirectory=$ROOT,
     EnvironmentFile=$ROOT/.env, ExecStart=$ROOT/.venv/bin/python -m app.main,
     ReadWritePaths=$ROOT/data, и уникальное имя юнита на инстанс
  2) sudo cp deploy/bot-tracker.service /etc/systemd/system/bot-<name>.service
  3) sudo systemctl daemon-reload && sudo systemctl enable --now bot-<name>
  4) логи: journalctl -u bot-<name> -f

Первый ведущий: см. docs/SETUP_INSTANCE.md §5
  — сначала /group в боте (узнать chat_id), затем scripts/seed_member.py

Обновление кода в будущем:
  git pull && sudo systemctl restart bot-<name>
  (pip install -e . — только если менялись зависимости; alembic upgrade head — если новые миграции)
EOF
