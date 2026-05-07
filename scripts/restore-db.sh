#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")
DATABASE_NAME="tripmate"
INPUT_PATH=""
CONFIRMED=false

usage() {
  cat <<'USAGE'
Usage: scripts/restore-db.sh --yes --input .tmp/backups/tripmate.dump [--database tripmate]

TripMate Postgres 컨테이너에 custom-format pg_dump 백업을 복구한다.
기존 DB object를 --clean --if-exists로 덮어쓰므로 운영에서는 먼저 백업을 만들고 점검 창에서 실행한다.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      CONFIRMED=true
      shift
      ;;
    --input)
      INPUT_PATH="${2:?--input 값이 필요합니다.}"
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

if [[ "${CONFIRMED}" != "true" ]]; then
  usage >&2
  exit 2
fi

if [[ -z "${INPUT_PATH}" || ! -f "${INPUT_PATH}" ]]; then
  echo "복구할 dump 파일을 찾지 못했습니다: ${INPUT_PATH:-<empty>}" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "이 스크립트는 Linux(WSL2 Ubuntu 또는 ODROID Ubuntu)에서 실행한다." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. docker compose --env-file 실행을 위해 필요합니다." >&2
  exit 1
fi

"${COMPOSE[@]}" up -d postgres >/dev/null
"${COMPOSE[@]}" exec -T postgres psql -U tripmate -d "${DATABASE_NAME}" -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid();
SQL

cat "${INPUT_PATH}" | "${COMPOSE[@]}" exec -T postgres pg_restore \
  -U tripmate \
  -d "${DATABASE_NAME}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl

echo "DB 복구 완료: ${INPUT_PATH} -> ${DATABASE_NAME}"
