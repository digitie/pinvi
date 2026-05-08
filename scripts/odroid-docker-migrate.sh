#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

cd "${ROOT_DIR}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "이 스크립트는 ODROID M1S Ubuntu 24.04 또는 WSL2 Ubuntu 같은 Linux에서 실행한다." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. 운영 비밀값은 서버 로컬 .env에만 저장하세요." >&2
  exit 1
fi

if [[ -z "$("${COMPOSE[@]}" ps -q dagster)" ]]; then
  echo "dagster가 실행 중이 아닙니다. 먼저 scripts/odroid-docker-start.sh를 실행하세요." >&2
  exit 1
fi

"${COMPOSE[@]}" exec -T dagster bash -lc \
  'cd /app && python -c "from alembic.config import main; main(argv=[\"upgrade\", \"head\"])"'

echo "Alembic migration 완료: head"
