#!/usr/bin/env bash
# Restore a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

SCHEMA="${PINVI_RESTORE_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
JOBS="${PINVI_RESTORE_JOBS:-2}"
BACKUP_FILE="${1:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
  echo "Usage: scripts/restore-db.sh /path/to/backup.dump" >&2
  exit 2
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PINVI_DATABASE_URL or PINVI_RESTORE_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "invalid restore schema name" >&2
  exit 2
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "backup file not found: ${BACKUP_FILE}" >&2
  exit 2
fi

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  if ! command -v sha256sum >/dev/null 2>&1; then
    echo "sha256sum not found" >&2
    exit 127
  fi
  expected_checksum="$(awk 'NR == 1 { print $1 }' "${BACKUP_FILE}.sha256")"
  actual_checksum="$(sha256sum "${BACKUP_FILE}" | awk 'NR == 1 { print $1 }')"
  if [[ -z "${expected_checksum}" || "${expected_checksum}" != "${actual_checksum}" ]]; then
    echo "backup checksum failed" >&2
    exit 3
  fi
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "pg_restore not found" >&2
  exit 127
fi

pg_restore \
  --clean \
  --if-exists \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  --schema="${SCHEMA}" \
  --jobs="${JOBS}" \
  --dbname="${DATABASE_URL}" \
  "${BACKUP_FILE}"

echo "RESTORED_FILE=${BACKUP_FILE}"
