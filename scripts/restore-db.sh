#!/usr/bin/env bash
# Restore a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

SCHEMA="${PINVI_RESTORE_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
JOBS="${PINVI_RESTORE_JOBS:-2}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
BACKUP_FILE="${1:-}"

pinned_tool() {
  local name="$1"
  local candidate
  if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
    command -v "${name}" || true
    return 0
  fi
  for candidate in "/usr/local/bin/${name}" "/usr/bin/${name}" "/bin/${name}" \
    /usr/lib/postgresql/*/bin/${name}; do
    if [[ -f "${candidate}" && -x "${candidate}" && ! -L "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

PSQL_BIN="${PINVI_RESTORE_PSQL_BIN:-}"
if [[ -z "${PSQL_BIN}" ]]; then
  PSQL_BIN="$(pinned_tool psql || true)"
fi

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

if [[ "${PSQL_BIN}" != /* || ! -x "${PSQL_BIN}" ]]; then
  echo "PINVI_RESTORE_PSQL_BIN is not an executable absolute path" >&2
  exit 127
fi

if [[ -n "${PINVI_RESTORE_PG_RESTORE_BIN:-}" ]]; then
  PG_RESTORE_BIN="${PINVI_RESTORE_PG_RESTORE_BIN}"
else
  PG_RESTORE_BIN="$(pinned_tool pg_restore || true)"
  if [[ -z "${PG_RESTORE_BIN}" ]]; then
    echo "pg_restore not found" >&2
    exit 127
  fi
fi
if [[ "${PG_RESTORE_BIN}" != /* || ! -x "${PG_RESTORE_BIN}" ]]; then
  echo "PINVI_RESTORE_PG_RESTORE_BIN is not an executable absolute path" >&2
  exit 127
fi
if [[ "${PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST:-0}" == "1" ]]; then
  if ! command -v sha256sum >/dev/null 2>&1; then
    echo "sha256sum not found" >&2
    exit 127
  fi
  actual_psql_sha256="$(sha256sum "${PSQL_BIN}" | awk 'NR == 1 { print $1 }')"
  actual_pg_restore_sha256="$(sha256sum "${PG_RESTORE_BIN}" | awk 'NR == 1 { print $1 }')"
  if [[ ! "${PINVI_RESTORE_PSQL_SHA256:-}" =~ ^[0-9a-f]{64}$ || \
    "${actual_psql_sha256}" != "${PINVI_RESTORE_PSQL_SHA256}" || \
    ! "${PINVI_RESTORE_PG_RESTORE_SHA256:-}" =~ ^[0-9a-f]{64}$ || \
    "${actual_pg_restore_sha256}" != "${PINVI_RESTORE_PG_RESTORE_SHA256}" ]]; then
    echo "restore tool digest pin failed" >&2
    exit 3
  fi
fi

assert_expected_target() {
  if [[ -z "${PINVI_RESTORE_EXPECTED_DATABASE_OID:-}" ]]; then
    return 0
  fi
  local actual
  actual="$("${PSQL_BIN}" --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(inet_server_addr()::text, '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" | tr -d '[:space:]')"
  local expected="${PINVI_RESTORE_EXPECTED_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_HOSTADDR}|${PINVI_RESTORE_EXPECTED_PORT}"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "restore target identity changed before mutation" >&2
    exit 3
  fi
  printf '%s\n' "RESTORE_TARGET_BINDING=verified"
}

# Validate the destination authority before CREATE SCHEMA/pg_restore can alter it. A
# role-split deployment must never discover a typo or privileged runtime login only
# after `--clean` has dropped the existing schema objects.
if [[ "${PINVI_RESTORE_REQUIRE_FRESH_SCHEMA:-0}" == "1" ]]; then
  assert_expected_target
  schema_exists="$("${PSQL_BIN}" --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT to_regnamespace('${SCHEMA}') IS NOT NULL")"
  if [[ "${schema_exists}" != "f" ]]; then
    echo "PINVI_RESTORE_REQUIRE_FRESH_SCHEMA requires a target without the app schema" >&2
    exit 3
  fi
fi
assert_expected_target
if [[ -n "${APP_ROLE}" ]]; then
  runtime_role_safe="$("${PSQL_BIN}" --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication AND NOT pg_has_role(r.oid, current_user, 'member') AND r.oid <> current_user::regrole AND NOT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname = '${SCHEMA}' AND (n.nspowner = r.oid OR pg_has_role(r.oid, n.nspowner, 'member'))) AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = '${SCHEMA}' AND (c.relowner = r.oid OR pg_has_role(r.oid, c.relowner, 'member'))) FROM pg_roles r WHERE r.rolname = '${APP_ROLE}'")"
  if [[ "${runtime_role_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE must name an existing non-superuser non-owner runtime login" >&2
    exit 3
  fi
else
  restore_owner_safe="$("${PSQL_BIN}" --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}') OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}' AND nspowner = current_user::regrole)")"
  if [[ "${restore_owner_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE is required when the restore executor does not own the target schema" >&2
    exit 3
  fi
fi

# ``pg_dump --schema`` does not carry CREATE SCHEMA. Bootstrap a fresh staging
# database explicitly; an existing schema is intentionally left untouched.
"${PSQL_BIN}" \
  --set=ON_ERROR_STOP=1 \
  --dbname="${DATABASE_URL}" \
  --command="CREATE SCHEMA IF NOT EXISTS \"${SCHEMA}\""

assert_expected_target

printf '%s\n' "RESTORE_COMMAND=pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges"
"${PG_RESTORE_BIN}" \
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
  "${PSQL_BIN}" \
    --set=ON_ERROR_STOP=1 \
    --dbname="${DATABASE_URL}" \
    --command="GRANT USAGE ON SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\""
else
  : # preflight already established the documented single-owner mode.
fi

echo "RESTORED_FILE=${BACKUP_FILE}"
