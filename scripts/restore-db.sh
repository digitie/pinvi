#!/usr/bin/env bash
# Restore a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

SCHEMA="${PINVI_RESTORE_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
JOBS="${PINVI_RESTORE_JOBS:-2}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
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

if [[ -n "${APP_ROLE}" && ! "${APP_ROLE}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  echo "invalid restore app role name" >&2
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

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found" >&2
  exit 127
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "pg_restore not found" >&2
  exit 127
fi

# Validate the destination authority before CREATE SCHEMA/pg_restore can alter it. A
# role-split deployment must never discover a typo or privileged runtime login only
# after `--clean` has dropped the existing schema objects.
if [[ -n "${APP_ROLE}" ]]; then
  runtime_role_safe="$(psql --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication AND NOT pg_has_role(r.oid, current_user, 'member') AND r.oid <> current_user::regrole AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = '${SCHEMA}' AND c.relowner = r.oid) FROM pg_roles r WHERE r.rolname = '${APP_ROLE}'")"
  if [[ "${runtime_role_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE must name an existing non-superuser non-owner runtime login" >&2
    exit 3
  fi
else
  restore_owner_safe="$(psql --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}') OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}' AND nspowner = current_user::regrole)")"
  if [[ "${restore_owner_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE is required when the restore executor does not own the target schema" >&2
    exit 3
  fi
fi

# ``pg_dump --schema`` does not carry CREATE SCHEMA. Bootstrap a fresh staging
# database explicitly; an existing schema is intentionally left untouched.
psql \
  --set=ON_ERROR_STOP=1 \
  --dbname="${DATABASE_URL}" \
  --command="CREATE SCHEMA IF NOT EXISTS \"${SCHEMA}\""

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

# ``--no-owner --no-privileges`` does not recreate runtime grants. The login and
# ownership safety were already checked before any mutation above.
if [[ -n "${APP_ROLE}" ]]; then
  psql \
    --set=ON_ERROR_STOP=1 \
    --dbname="${DATABASE_URL}" \
    --command="GRANT USAGE ON SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\""
else
  : # preflight already established the documented single-owner mode.
fi

echo "RESTORED_FILE=${BACKUP_FILE}"
