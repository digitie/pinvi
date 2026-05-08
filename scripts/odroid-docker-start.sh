#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

cd "${ROOT_DIR}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "이 스크립트는 ODROID M1S Ubuntu 24.04 또는 WSL2 Ubuntu 같은 Linux에서 실행한다." >&2
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" != "24.04" ]]; then
    echo "주의: 기준 환경은 Ubuntu 24.04입니다. 현재 VERSION_ID=${VERSION_ID:-unknown}" >&2
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker 명령을 찾지 못했습니다." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin을 찾지 못했습니다." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. 운영 비밀값은 서버 로컬 .env에만 저장하세요." >&2
  exit 1
fi

mkdir -p .tmp/dagster-downloads .tmp/dagster-logs .tmp/etl-soak .tmp/backups dataset

wait_for_service() {
  local service="$1"
  local container_id
  local status
  local attempt
  for attempt in $(seq 1 90); do
    container_id="$("${COMPOSE[@]}" ps -q "${service}")"
    if [[ -n "${container_id}" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
      if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
        echo "${service}: ${status}"
        return 0
      fi
    fi
    sleep 5
  done

  echo "${service}가 제한 시간 안에 healthy/running 상태가 되지 못했습니다." >&2
  "${COMPOSE[@]}" logs --tail=200 "${service}" >&2 || true
  return 1
}

"${COMPOSE[@]}" up -d --build postgres dagster
wait_for_service postgres
wait_for_service dagster
"${COMPOSE[@]}" ps

echo "Dagster UI: http://localhost:${TRIPMATE_DAGSTER_PORT:-23000}"
echo "Migration이 필요하면 scripts/odroid-docker-migrate.sh를 실행하세요."
