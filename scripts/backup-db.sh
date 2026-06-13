#!/usr/bin/env bash
# Create a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PINVI_BACKUP_DIR:-${ROOT_DIR}/.tmp/backups}"
SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
DATABASE_URL="${PINVI_BACKUP_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PINVI_DATABASE_URL or PINVI_BACKUP_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
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

timestamp="$(date -u +%Y%m%d-%H%M%S)"
backup_file="${BACKUP_DIR}/pinvi-${SCHEMA}-${timestamp}.dump"

# pg_dump custom format is a single-file artifact. Parallel jobs are used at restore time.
pg_dump \
  --format=custom \
  --schema="${SCHEMA}" \
  --no-owner \
  --no-privileges \
  --file="${backup_file}" \
  "${DATABASE_URL}"

sha256sum "${backup_file}" >"${backup_file}.sha256"

echo "BACKUP_FILE=${backup_file}"
