#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")
DATABASE_NAME="tripmate"
OUTPUT_PATH=""

usage() {
  cat <<'USAGE'
Usage: scripts/backup-db.sh [--output .tmp/backups/tripmate-YYYYMMDDTHHMMSS.dump] [--database tripmate]

TripMate Postgres 컨테이너에서 custom-format pg_dump 백업을 생성한다.
WSL2 Ubuntu 또는 ODROID M1S Ubuntu 24.04 같은 Linux 환경에서 실행한다.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_PATH="${2:?--output 값이 필요합니다.}"
      shift 2
      ;;
    --database)
      DATABASE_NAME="${2:?--database 값이 필요합니다.}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

cd "${ROOT_DIR}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "이 스크립트는 Linux(WSL2 Ubuntu 또는 ODROID Ubuntu)에서 실행한다." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. docker compose --env-file 실행을 위해 필요합니다." >&2
  exit 1
fi

if [[ -z "${OUTPUT_PATH}" ]]; then
  OUTPUT_PATH=".tmp/backups/${DATABASE_NAME}-$(date +%Y%m%dT%H%M%S%z).dump"
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")"

"${COMPOSE[@]}" up -d postgres >/dev/null
"${COMPOSE[@]}" exec -T postgres pg_dump \
  -U tripmate \
  -d "${DATABASE_NAME}" \
  -Fc \
  --no-owner \
  --no-acl > "${OUTPUT_PATH}"

if [[ ! -s "${OUTPUT_PATH}" ]]; then
  echo "백업 파일이 비어 있습니다: ${OUTPUT_PATH}" >&2
  exit 1
fi

echo "DB 백업 완료: ${OUTPUT_PATH}"
