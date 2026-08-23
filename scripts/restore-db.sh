#!/usr/bin/env bash
# Restore a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

unset BASH_ENV CDPATH ENV GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM GIT_SSH GIT_SSH_COMMAND \
  LD_AUDIT LD_LIBRARY_PATH LD_PRELOAD PYTHONHOME PYTHONPATH RUBYLIB \
  PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PSQLRC

SCHEMA="${PINVI_RESTORE_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
JOBS="${PINVI_RESTORE_JOBS:-2}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
BACKUP_FILE="${1:-}"
ORIGINAL_BACKUP_FILE="${BACKUP_FILE}"

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

if [[ -L "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "backup file not found: ${BACKUP_FILE}" >&2
  exit 2
fi

if [[ -L "${BACKUP_FILE}.sha256" || ! -f "${BACKUP_FILE}.sha256" ]]; then
  echo "backup checksum sidecar is required as a regular file" >&2
  exit 3
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum not found" >&2
  exit 127
fi
expected_checksum="$(awk 'NR == 1 { print $1 }' "${BACKUP_FILE}.sha256")"
actual_checksum="$(sha256sum "${BACKUP_FILE}" | awk 'NR == 1 { print $1 }')"
if [[ ! "${expected_checksum}" =~ ^[0-9a-f]{64}$ || "${expected_checksum}" != "${actual_checksum}" ]]; then
  echo "backup checksum failed" >&2
  exit 3
fi

# The restore process never reads the operator-writable backup path again. A private
# copy is re-hashed after copying so a replacement between checksum and pg_restore
# becomes a fail-closed error instead of a TOCTOU restore.
SNAPSHOT_TMP_DIR="$(mktemp -d)"
cleanup_snapshot() {
  rm -rf "${SNAPSHOT_TMP_DIR}"
}
trap cleanup_snapshot EXIT
cp -- "${BACKUP_FILE}" "${SNAPSHOT_TMP_DIR}/snapshot.dump"
if [[ "$(sha256sum "${SNAPSHOT_TMP_DIR}/snapshot.dump" | awk 'NR == 1 { print $1 }')" != "${expected_checksum}" ]]; then
  echo "backup changed while copying" >&2
  exit 3
fi
BACKUP_FILE="${SNAPSHOT_TMP_DIR}/snapshot.dump"

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
assert_trusted_tool_path() {
  local name="$1"
  local path="$2"
  if [[ "${path}" != /* || ! -f "${path}" || ! -x "${path}" || -L "${path}" ]]; then
    echo "${name} path is not a trusted executable" >&2
    exit 127
  fi
  local resolved
  resolved="$(realpath -e "${path}")"
  case "${resolved}" in
    /usr/local/bin/${name}|/usr/bin/${name}|/bin/${name}) ;;
    /usr/lib/postgresql/[0-9]*/bin/${name}) ;;
    *)
      echo "${name} path is outside the trusted tool directories" >&2
      exit 127
      ;;
  esac
}

if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" &&
  "${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
  assert_trusted_tool_path "psql" "${PSQL_BIN}"
  assert_trusted_tool_path "pg_restore" "${PG_RESTORE_BIN}"
  actual_psql_sha256="$(sha256sum "${PSQL_BIN}" | awk 'NR == 1 { print $1 }')"
  actual_pg_restore_sha256="$(sha256sum "${PG_RESTORE_BIN}" | awk 'NR == 1 { print $1 }')"
  if [[ ! "${PINVI_RESTORE_PSQL_SHA256:-}" =~ ^[0-9a-f]{64}$ || \
    "${actual_psql_sha256}" != "${PINVI_RESTORE_PSQL_SHA256}" || \
    ! "${PINVI_RESTORE_PG_RESTORE_SHA256:-}" =~ ^[0-9a-f]{64}$ || \
    "${actual_pg_restore_sha256}" != "${PINVI_RESTORE_PG_RESTORE_SHA256}" ]]; then
    echo "restore tool digest pin failed" >&2
    exit 3
  fi
  cp -- "${PSQL_BIN}" "${SNAPSHOT_TMP_DIR}/psql"
  cp -- "${PG_RESTORE_BIN}" "${SNAPSHOT_TMP_DIR}/pg_restore"
  chmod 700 "${SNAPSHOT_TMP_DIR}/psql" "${SNAPSHOT_TMP_DIR}/pg_restore"
  if [[ "$(sha256sum "${SNAPSHOT_TMP_DIR}/psql" | awk 'NR == 1 { print $1 }')" != "${PINVI_RESTORE_PSQL_SHA256}" || \
    "$(sha256sum "${SNAPSHOT_TMP_DIR}/pg_restore" | awk 'NR == 1 { print $1 }')" != "${PINVI_RESTORE_PG_RESTORE_SHA256}" ]]; then
    echo "restore tools changed while copying" >&2
    exit 3
  fi
  PSQL_BIN="${SNAPSHOT_TMP_DIR}/psql"
  PG_RESTORE_BIN="${SNAPSHOT_TMP_DIR}/pg_restore"
fi

assert_expected_target() {
  if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
    return 0
  fi
  for variable in PINVI_RESTORE_EXPECTED_DATABASE_NAME PINVI_RESTORE_EXPECTED_DATABASE_OID \
    PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER PINVI_RESTORE_EXPECTED_HOSTADDR PINVI_RESTORE_EXPECTED_PORT; do
    if [[ -z "${!variable:-}" ]]; then
      echo "${variable} is required for a non-test restore" >&2
      exit 3
    fi
  done
  local actual
  actual="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(inet_server_addr()::text, '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" | tr -d '[:space:]')"
  local expected="${PINVI_RESTORE_EXPECTED_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_HOSTADDR}|${PINVI_RESTORE_EXPECTED_PORT}"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "restore target identity changed before mutation" >&2
    exit 3
  fi
  printf '%s\n' "RESTORE_TARGET_BINDING=verified"
}

secure_restore_with_identity_guard() {
  local restore_sql
  local guarded_sql
  restore_sql="$(mktemp)"
  guarded_sql="$(mktemp)"
  cleanup_restore_sql() {
    rm -f "${restore_sql}" "${guarded_sql}"
  }
  trap 'cleanup_restore_sql; cleanup_snapshot' EXIT

  "${PG_RESTORE_BIN}" \
    --clean \
    --if-exists \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --schema="${SCHEMA}" \
    --file="${restore_sql}" \
    "${BACKUP_FILE}"
  if grep -Eiq '^[[:space:]]*(\\(connect|c)([[:space:]]|$)|c([[:space:]]|$)|begin([[:space:]]|;|$)|start[[:space:]]+transaction([[:space:]]|;|$)|commit([[:space:]]|;|$)|rollback([[:space:]]|;|$))' "${restore_sql}"; then
    echo "restore dump contains a connection switch" >&2
    exit 3
  fi
  {
    cat <<SQL
DO \$m05\$
BEGIN
  IF current_database() <> '${PINVI_RESTORE_EXPECTED_DATABASE_NAME}'
     OR (SELECT oid::text FROM pg_database WHERE datname = current_database()) <> '${PINVI_RESTORE_EXPECTED_DATABASE_OID}'
     OR (pg_control_system()).system_identifier::text <> '${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}'
     OR COALESCE(inet_server_addr()::text, '') <> '${PINVI_RESTORE_EXPECTED_HOSTADDR}'
     OR inet_server_port()::text <> '${PINVI_RESTORE_EXPECTED_PORT}'
  THEN
    RAISE EXCEPTION 'restore target identity changed before mutation';
  END IF;
END
\$m05\$;
SQL
    printf 'CREATE SCHEMA IF NOT EXISTS "%s";\n' "${SCHEMA}"
    cat "${restore_sql}"
    if [[ -n "${APP_ROLE}" ]]; then
      printf 'GRANT USAGE ON SCHEMA "%s" TO "%s";\n' "${SCHEMA}" "${APP_ROLE}"
      printf 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "%s" TO "%s";\n' "${SCHEMA}" "${APP_ROLE}"
      printf 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA "%s" TO "%s";\n' "${SCHEMA}" "${APP_ROLE}"
    fi
  } >"${guarded_sql}"
  "${PSQL_BIN}" \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname="${DATABASE_URL}" \
    --file="${guarded_sql}"
}

# Validate the destination authority before CREATE SCHEMA/pg_restore can alter it. A
# role-split deployment must never discover a typo or privileged runtime login only
# after `--clean` has dropped the existing schema objects.
if [[ "${PINVI_RESTORE_REQUIRE_FRESH_SCHEMA:-0}" == "1" ]]; then
  assert_expected_target
  schema_exists="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT to_regnamespace('${SCHEMA}') IS NOT NULL")"
  if [[ "${schema_exists}" != "f" ]]; then
    echo "PINVI_RESTORE_REQUIRE_FRESH_SCHEMA requires a target without the app schema" >&2
    exit 3
  fi
fi
assert_expected_target
if [[ -n "${APP_ROLE}" ]]; then
  runtime_role_safe="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication AND NOT r.rolbypassrls AND NOT r.rolinherit AND NOT EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid) AND NOT pg_has_role(r.oid, current_user, 'member') AND r.oid <> current_user::regrole AND NOT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname = '${SCHEMA}' AND (n.nspowner = r.oid OR pg_has_role(r.oid, n.nspowner, 'member'))) AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = '${SCHEMA}' AND (c.relowner = r.oid OR pg_has_role(r.oid, c.relowner, 'member'))) FROM pg_roles r WHERE r.rolname = '${APP_ROLE}'")"
  runtime_role_membership_safe="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --dbname="${DATABASE_URL}" --command="WITH RECURSIVE role_closure(role_oid) AS ( SELECT oid FROM pg_roles WHERE rolname = '${APP_ROLE}' UNION SELECT membership.roleid FROM role_closure closure JOIN pg_auth_members membership ON membership.member = closure.role_oid ) SELECT COALESCE((SELECT bool_and( NOT effective.rolsuper AND NOT effective.rolcreaterole AND NOT effective.rolcreatedb AND NOT effective.rolreplication AND NOT effective.rolbypassrls AND NOT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname = '${SCHEMA}' AND (n.nspowner = effective.oid OR pg_has_role(effective.oid, n.nspowner, 'member'))) AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = '${SCHEMA}' AND (c.relowner = effective.oid OR pg_has_role(effective.oid, c.relowner, 'member') OR pg_has_role(r.oid, c.relowner, 'member'))) ) FROM role_closure closure JOIN pg_roles effective ON effective.oid = closure.role_oid JOIN pg_roles r ON r.rolname = '${APP_ROLE}'), false)")"
  if [[ "${runtime_role_safe}" != "t" || "${runtime_role_membership_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE must name an existing non-superuser non-owner runtime login" >&2
    exit 3
  fi
else
  restore_owner_safe="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --dbname="${DATABASE_URL}" --command="SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}') OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '${SCHEMA}' AND nspowner = current_user::regrole)")"
  if [[ "${restore_owner_safe}" != "t" ]]; then
    echo "PINVI_RESTORE_APP_ROLE is required when the restore executor does not own the target schema" >&2
    exit 3
  fi
fi

printf '%s\n' "RESTORE_COMMAND=pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges"
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" ]]; then
  secure_restore_with_identity_guard
else
  # ``pg_dump --schema`` does not carry CREATE SCHEMA. Bootstrap a fresh staging
  # database explicitly; an existing schema is intentionally left untouched.
  "${PSQL_BIN}" \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname="${DATABASE_URL}" \
    --command="CREATE SCHEMA IF NOT EXISTS \"${SCHEMA}\""

  assert_expected_target
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
      --no-psqlrc \
      --set=ON_ERROR_STOP=1 \
      --dbname="${DATABASE_URL}" \
      --command="GRANT USAGE ON SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\"; GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA \"${SCHEMA}\" TO \"${APP_ROLE}\""
  else
    : # preflight already established the documented single-owner mode.
  fi
fi

echo "RESTORED_FILE=${ORIGINAL_BACKUP_FILE}"
