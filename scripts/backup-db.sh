#!/usr/bin/env bash
# Create a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PINVI_BACKUP_DIR:-${ROOT_DIR}/.tmp/backups}"
SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
MIN_FREE_BYTES="${PINVI_BACKUP_MIN_FREE_BYTES:-1073741824}"
DATABASE_URL="${PINVI_BACKUP_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
PG_DUMP_BIN="${PINVI_BACKUP_PG_DUMP_BIN:-pg_dump}"
DOCKER_FALLBACK="${PINVI_BACKUP_DOCKER_FALLBACK:-1}"
DOCKER_BIN="${PINVI_BACKUP_DOCKER_BIN:-docker}"
DOCKER_IMAGE="${PINVI_BACKUP_DOCKER_IMAGE:-postgis/postgis:16-3.5}"
DOCKER_NETWORK="${PINVI_BACKUP_DOCKER_NETWORK:-}"
CONTAINER_BACKUP_DIR="/backup"

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PINVI_DATABASE_URL or PINVI_BACKUP_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "invalid backup schema name" >&2
  exit 2
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum not found" >&2
  exit 127
fi

mkdir -p "${BACKUP_DIR}"
available_kb="$(df -Pk "${BACKUP_DIR}" | awk 'NR == 2 { print $4 }')"
available_bytes="$((available_kb * 1024))"
if (( MIN_FREE_BYTES > 0 && available_bytes < MIN_FREE_BYTES )); then
  echo "backup disk guard failed: free_bytes=${available_bytes} required_bytes=${MIN_FREE_BYTES}" >&2
  exit 73
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
backup_file="${BACKUP_DIR}/pinvi-${SCHEMA}-${timestamp}.dump"
tmp_file="$(mktemp "${BACKUP_DIR}/.pinvi-${SCHEMA}-${timestamp}.XXXXXX.dump")"
cleanup() {
  rm -f "${tmp_file}" "${tmp_file}.sha256"
}
trap cleanup EXIT

run_pg_dump() {
  # pg_dump custom format is a single-file artifact. Parallel jobs are used at restore time.
  if command -v "${PG_DUMP_BIN}" >/dev/null 2>&1; then
    "${PG_DUMP_BIN}" \
      --format=custom \
      --schema="${SCHEMA}" \
      --no-owner \
      --no-privileges \
      --file="${tmp_file}" \
      "${DATABASE_URL}"
    return
  fi

  if [[ "${DOCKER_FALLBACK}" != "1" ]]; then
    echo "pg_dump not found: ${PG_DUMP_BIN}" >&2
    exit 127
  fi

  if ! command -v "${DOCKER_BIN}" >/dev/null 2>&1; then
    echo "pg_dump not found and docker fallback unavailable: ${DOCKER_BIN}" >&2
    exit 127
  fi

  backup_dir_abs="$(cd "${BACKUP_DIR}" && pwd -P)"
  tmp_name="$(basename "${tmp_file}")"
  container_tmp_file="${CONTAINER_BACKUP_DIR}/${tmp_name}"
  docker_args=(run --rm)
  if [[ -n "${DOCKER_NETWORK}" ]]; then
    docker_args+=(--network "${DOCKER_NETWORK}")
  fi
  docker_args+=(
    -v "${backup_dir_abs}:${CONTAINER_BACKUP_DIR}"
    --env PINVI_BACKUP_DATABASE_URL
    --env PINVI_BACKUP_SCHEMA
    --env PINVI_BACKUP_DUMP_FILE
    "${DOCKER_IMAGE}"
    sh
    -c
    'exec pg_dump --format=custom --schema="${PINVI_BACKUP_SCHEMA}" --no-owner --no-privileges --file="${PINVI_BACKUP_DUMP_FILE}" "${PINVI_BACKUP_DATABASE_URL}"'
  )

  PINVI_BACKUP_DATABASE_URL="${DATABASE_URL}" \
    PINVI_BACKUP_SCHEMA="${SCHEMA}" \
    PINVI_BACKUP_DUMP_FILE="${container_tmp_file}" \
    "${DOCKER_BIN}" "${docker_args[@]}"

  if [[ ! -f "${tmp_file}" ]]; then
    echo "docker pg_dump fallback did not create dump" >&2
    exit 1
  fi
}

run_pg_dump

tmp_dir="$(dirname "${tmp_file}")"
tmp_name="$(basename "${tmp_file}")"
(cd "${tmp_dir}" && sha256sum "${tmp_name}" >"${tmp_name}.sha256")
(cd "${tmp_dir}" && sha256sum -c "${tmp_name}.sha256") >/dev/null

mv "${tmp_file}" "${backup_file}"
trap - EXIT
rm -f "${tmp_file}.sha256"
backup_dirname="$(dirname "${backup_file}")"
backup_name="$(basename "${backup_file}")"
(cd "${backup_dirname}" && sha256sum "${backup_name}" >"${backup_name}.sha256")
(cd "${backup_dirname}" && sha256sum -c "${backup_name}.sha256") >/dev/null

echo "BACKUP_FILE=${backup_file}"
