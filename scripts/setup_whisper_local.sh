#!/usr/bin/env bash
# Установка whisper.cpp + модель для WHISPER_MODE=local.
# Запуск: bash scripts/setup_whisper_local.sh
# Требует: git, cmake, g++, make (sudo apt install cmake build-essential)

set -euo pipefail

WHISPER_DIR="${WHISPER_DIR:-$HOME/.local/share/whisper.cpp}"
MODEL="${WHISPER_MODEL:-base}"  # tiny | base | small | medium (base — баланс скорость/качество)

echo "==> Каталог: $WHISPER_DIR"
echo "==> Модель: ggml-$MODEL"

if ! command -v cmake >/dev/null 2>&1; then
  echo "Нужен cmake. Установи: sudo apt install cmake build-essential"
  exit 1
fi

if [ ! -d "$WHISPER_DIR/.git" ]; then
  git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
else
  echo "==> Репозиторий уже есть, пропускаю clone"
fi

cd "$WHISPER_DIR"
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

bash ./models/download-ggml-model.sh "$MODEL"

CLI="$WHISPER_DIR/build/bin/whisper-cli"
MODEL_PATH="$WHISPER_DIR/models/ggml-${MODEL}.bin"

if [ ! -x "$CLI" ]; then
  echo "Бинарь не найден: $CLI"
  exit 1
fi
if [ ! -f "$MODEL_PATH" ]; then
  echo "Модель не найдена: $MODEL_PATH"
  exit 1
fi

echo ""
echo "Готово. Добавь в .env:"
echo "WHISPER_MODE=local"
echo "WHISPER_CPP_PATH=$CLI"
echo "WHISPER_MODEL_PATH=$MODEL_PATH"
echo ""
echo "Проверка:"
echo "  $CLI -m $MODEL_PATH -f /path/to/test.ogg -l ru -nt"
