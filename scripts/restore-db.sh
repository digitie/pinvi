#!/usr/bin/env bash
# Restore a TripMate app-schema PostgreSQL custom-format backup.

set -euo pipefail

SCHEMA="${TRIPMATE_RESTORE_SCHEMA:-${TRIPMATE_BACKUP_SCHEMA:-app}}"
DATABASE_URL="${TRIPMATE_RESTORE_DATABASE_URL:-${TRIPMATE_DATABASE_URL:-}}"
JOBS="${TRIPMATE_RESTORE_JOBS:-2}"
BACKUP_FILE="${1:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
  echo "Usage: scripts/restore-db.sh /path/to/backup.dump" >&2
  exit 2
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "TRIPMATE_DATABASE_URL or TRIPMATE_RESTORE_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "backup file not found: ${BACKUP_FILE}" >&2
  exit 2
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
