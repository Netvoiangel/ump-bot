#!/usr/bin/env bash
set -euo pipefail

<<<<<<< HEAD
# Обновление кода + пересборка/перезапуск контейнера.
# Работает и для Docker, и для Podman (см. scripts/compose.sh).
#
# Пример:
#   ./update_bot.sh
#   RUNTIME=podman ./update_bot.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

echo "==> git pull"
git pull --rebase

echo "==> compose down (best-effort)"
./scripts/compose.sh down --remove-orphans || true

echo "==> compose build"
./scripts/compose.sh up -d --build

echo "==> compose ps"
./scripts/compose.sh ps

=======
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
>>>>>>> origin/main

