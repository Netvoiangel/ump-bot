#!/usr/bin/env bash
set -euo pipefail

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


