#!/usr/bin/env bash
set -euo pipefail

# Унифицированный запуск compose для Docker/Podman.
# - Всегда выполняется из корня репозитория (чтобы не ловить "no compose.yaml ...").
# - По умолчанию выбирает Docker, если это настоящий Docker, иначе Podman.
# - Можно принудить: RUNTIME=docker|podman ./scripts/compose.sh up -d --build

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

die() {
  echo "ERROR: $*" >&2
  exit 2
}

docker_is_podman_emulation() {
  command -v docker >/dev/null 2>&1 || return 1
  docker --version 2>/dev/null | grep -qi podman
}

pick_runtime() {
  if [[ -n "${RUNTIME:-}" ]]; then
    echo "${RUNTIME}"
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && ! docker_is_podman_emulation; then
    echo "docker"
    return 0
  fi
  if command -v podman >/dev/null 2>&1; then
    echo "podman"
    return 0
  fi
  die "Не найден ни Docker, ни Podman."
}

rt="$(pick_runtime)"

case "${rt}" in
  docker)
    exec docker compose -f docker-compose.yml "$@"
    ;;
  podman)
    if podman compose version >/dev/null 2>&1; then
      exec podman compose -f docker-compose.yml "$@"
    fi
    command -v podman-compose >/dev/null 2>&1 || die "podman-compose не найден (и 'podman compose' недоступен)."
    exec podman-compose -f docker-compose.yml "$@"
    ;;
  *)
    die "Неизвестный RUNTIME='${rt}' (ожидалось docker|podman)."
    ;;
esac


