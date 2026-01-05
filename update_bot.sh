#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "⚠️ Репозиторий имеет незакоммиченные изменения. Сохраните или закоммитьте их и повторите."
  exit 1
fi

echo ">>> Обновляю main..."
git fetch origin
git checkout main
git pull --ff-only origin main

echo ">>> Пересобираю и перезапускаю контейнер (Docker/Podman через scripts/compose.sh)..."
bash ./scripts/compose.sh down --remove-orphans || true
bash ./scripts/compose.sh up -d --build

echo "✅ Готово. Текущий статус:"
bash ./scripts/compose.sh ps

