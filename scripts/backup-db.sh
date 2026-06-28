#!/usr/bin/env bash
# Create a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PINVI_BACKUP_DIR:-${ROOT_DIR}/.tmp/backups}"
SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
MIN_FREE_BYTES="${PINVI_BACKUP_MIN_FREE_BYTES:-1073741824}"
DATABASE_URL="${PINVI_BACKUP_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"

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

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump not found" >&2
  exit 127
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

# pg_dump custom format is a single-file artifact. Parallel jobs are used at restore time.
pg_dump \
  --format=custom \
  --schema="${SCHEMA}" \
  --no-owner \
  --no-privileges \
  --file="${tmp_file}" \
  "${DATABASE_URL}"

sha256sum "${tmp_file}" >"${tmp_file}.sha256"
sha256sum -c "${tmp_file}.sha256" >/dev/null

mv "${tmp_file}" "${backup_file}"
trap - EXIT
rm -f "${tmp_file}.sha256"
sha256sum "${backup_file}" >"${backup_file}.sha256"
sha256sum -c "${backup_file}.sha256" >/dev/null

echo "BACKUP_FILE=${backup_file}"
