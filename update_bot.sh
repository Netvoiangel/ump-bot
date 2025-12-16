#!/usr/bin/env bash
set -euo pipefail

# Авто-пулл main и пересборка/перезапуск бота через Podman Compose.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "⚠️ Репозиторий имеет незакоммиченные изменения. Сохраните или закоммитьте их и повторите."
  exit 1
fi

echo ">>> Переключаюсь на main и тяну обновления..."
git checkout main
git pull --ff-only origin main

echo ">>> Пересобираю и перезапускаю контейнер..."
podman compose down
podman compose up -d --build

echo "✅ Готово. Текущий статус:"
podman compose ps

