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

export AIRFLOW_UID="${AIRFLOW_UID:-$(id -u)}"
mkdir -p .tmp/airflow-downloads .tmp/airflow-logs .tmp/backups dataset

"${COMPOSE[@]}" up -d --build postgres airflow-postgres airflow-redis airflow-init airflow-webserver airflow-scheduler airflow-dag-processor airflow-worker
"${COMPOSE[@]}" ps
