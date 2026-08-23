#!/usr/bin/env bash
# Guarded entrypoint for Pinvi same-database schema-swap restore.

set -euo pipefail

unset BASH_ENV CDPATH ENV GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM GIT_SSH GIT_SSH_COMMAND \
  LD_AUDIT LD_LIBRARY_PATH LD_PRELOAD PYTHONHOME PYTHONPATH RUBYLIB \
  PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PSQLRC
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

phase() {
  local name="$1"
  local status="$2"
  local message="${3:-}"
  printf 'RESTORE_PHASE=%s:%s:%s\n' "$name" "$status" "$message"
}

if [[ "${1:-}" != "run" || -z "${2:-}" || -z "${3:-}" || -z "${4:-}" ]]; then
  echo "Usage: scripts/restore-hotswap.sh run /path/to/snapshot.dump app_restore_YYYYMMDDHHMMSS app_previous_YYYYMMDDHHMMSS" >&2
  exit 2
fi

SNAPSHOT="$2"
RESTORE_SCHEMA="$3"
PREVIOUS_SCHEMA="$4"
DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
SOURCE_SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
TMP_DIR=""
LOCK_HOLDER_PID=""
LOCK_HOLDER_ACTIVE=0
WRITE_FENCE_ACTIVE=0
TEST_MODE="${PINVI_M05_RESTORE_TEST_MODE:-0}"

phase preparing running "precheck started"

if [[ -z "${DATABASE_URL}" ]]; then
  phase preparing failed "PINVI_DATABASE_URL or PINVI_RESTORE_DATABASE_URL is required"
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! -f "${SNAPSHOT}" ]]; then
  phase preparing failed "snapshot file not found"
  exit 2
fi

PINNED_TOOL_DIRS=("/usr/local/bin" "/usr/bin" "/bin" /usr/lib/postgresql/*/bin)
pinned_tool() {
  local name="$1"
  local candidate
  for directory in "${PINNED_TOOL_DIRS[@]}"; do
    candidate="${directory}/${name}"
    if [[ -f "${candidate}" && -x "${candidate}" && ! -L "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

verify_tool_digest() {
  local name="$1"
  local path="$2"
  local expected="$3"
  if [[ "${TEST_MODE}" != "1" ]]; then
    if [[ ! "${expected}" =~ ^[0-9a-f]{64}$ ]]; then
      phase preparing failed "${name} digest pin is required"
      exit 3
    fi
    local actual
    actual="$(sha256sum "${path}" | awk 'NR == 1 { print $1 }')"
    if [[ "${actual}" != "${expected}" ]]; then
      phase preparing failed "${name} digest pin failed"
      exit 3
    fi
  fi
}

assert_trusted_tool_path() {
  local name="$1"
  local path="$2"
  if [[ "${path}" != /* || ! -f "${path}" || ! -x "${path}" || -L "${path}" ]]; then
    phase preparing failed "${name} path is not a trusted executable"
    exit 3
  fi
  local resolved
  resolved="$(realpath -e "${path}")"
  case "${resolved}" in
    /usr/local/bin/${name}|/usr/bin/${name}|/bin/${name}) ;;
    /usr/lib/postgresql/[0-9]*/bin/${name}) ;;
    *)
      phase preparing failed "${name} path is outside the trusted tool directories"
      exit 3
      ;;
  esac
}

PG_RESTORE_BIN="${PINVI_RESTORE_PG_RESTORE_BIN:-$(pinned_tool pg_restore || true)}"
if [[ "${PG_RESTORE_BIN}" != /* || ! -x "${PG_RESTORE_BIN}" ]]; then
  phase preparing failed "pg_restore not found"
  exit 127
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  phase preparing failed "sha256sum not found"
  exit 127
fi
verify_tool_digest "pg_restore" "${PG_RESTORE_BIN}" "${PINVI_RESTORE_PG_RESTORE_SHA256:-}"
if [[ "${TEST_MODE}" != "1" ]]; then
  assert_trusted_tool_path "pg_restore" "${PG_RESTORE_BIN}"
fi

if [[ ! -f "${SNAPSHOT}.sha256" ]]; then
  phase preparing failed "snapshot checksum sidecar is required"
  exit 3
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  phase preparing failed "sha256sum not found"
  exit 127
fi
expected_checksum="$(awk 'NR == 1 { print $1 }' "${SNAPSHOT}.sha256")"
actual_checksum="$(sha256sum "${SNAPSHOT}" | awk 'NR == 1 { print $1 }')"
if [[ ! "${expected_checksum}" =~ ^[0-9a-f]{64}$ || "${expected_checksum}" != "${actual_checksum}" ]]; then
  phase preparing failed "snapshot checksum failed"
  exit 3
fi

if [[ "${PINVI_RESTORE_HOTSWAP_EXECUTE:-0}" != "1" ]]; then
  phase restoring failed "guard refused schema-swap; set PINVI_RESTORE_HOTSWAP_EXECUTE=1 only after staging drill"
  phase validating skipped "restore did not run"
  phase draining skipped "restore did not run"
  phase switching skipped "restore did not run"
  exit 3
fi

for schema_name in "${SOURCE_SCHEMA}" "${RESTORE_SCHEMA}" "${PREVIOUS_SCHEMA}"; do
  if [[ ! "${schema_name}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase preparing failed "unsafe schema name: ${schema_name}"
    exit 2
  fi
done
if [[ "${SOURCE_SCHEMA}" == "${RESTORE_SCHEMA}" || "${SOURCE_SCHEMA}" == "${PREVIOUS_SCHEMA}" || \
  "${RESTORE_SCHEMA}" == "${PREVIOUS_SCHEMA}" ]]; then
  phase preparing failed "source, restore, and previous schemas must be distinct"
  exit 2
fi

PSQL_BIN="${PINVI_RESTORE_PSQL_BIN:-$(pinned_tool psql || true)}"
if [[ "${PSQL_BIN}" != /* || ! -x "${PSQL_BIN}" ]]; then
  phase preparing failed "psql not found"
  exit 127
fi
verify_tool_digest "psql" "${PSQL_BIN}" "${PINVI_RESTORE_PSQL_SHA256:-}"
if [[ "${TEST_MODE}" != "1" ]]; then
  assert_trusted_tool_path "psql" "${PSQL_BIN}"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  set +e
  if [[ "${WRITE_FENCE_ACTIVE}" == "1" ]]; then
    release_write_fence
  fi
  if [[ -n "${LOCK_HOLDER_PID}" ]]; then
    kill "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
    wait "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

copy_tool_to_private_dir() {
  local name="$1"
  local source="$2"
  local expected="$3"
  local target="${TMP_DIR}/${name}"
  cp -- "${source}" "${target}"
  chmod 700 "${target}"
  if [[ "$(sha256sum "${target}" | awk 'NR == 1 { print $1 }')" != "${expected}" ]]; then
    phase preparing failed "${name} changed while copying to the private restore directory"
    exit 3
  fi
  printf '%s\n' "${target}"
}

if [[ "${TEST_MODE}" != "1" ]]; then
  PG_RESTORE_BIN="$(copy_tool_to_private_dir pg_restore "${PG_RESTORE_BIN}" "${PINVI_RESTORE_PG_RESTORE_SHA256}")"
  PSQL_BIN="$(copy_tool_to_private_dir psql "${PSQL_BIN}" "${PINVI_RESTORE_PSQL_SHA256}")"
fi

cp -- "${SNAPSHOT}" "${TMP_DIR}/snapshot.dump"
if [[ "$(sha256sum "${TMP_DIR}/snapshot.dump" | awk 'NR == 1 { print $1 }')" != "${expected_checksum}" ]]; then
  phase preparing failed "snapshot changed while copying to the private restore directory"
  exit 3
fi
SNAPSHOT="${TMP_DIR}/snapshot.dump"

"${PG_RESTORE_BIN}" --list "${SNAPSHOT}" >/dev/null
phase preparing success "snapshot verified for ${RESTORE_SCHEMA}"

start_advisory_lock() {
  local lock_sql="${TMP_DIR}/lock.sql"
  local lock_signal="${TMP_DIR}/lock.signal"
  cat >"${lock_sql}" <<'SQL'
DO $m05$
BEGIN
  IF NOT pg_try_advisory_lock(1414679892, 1213421392) THEN
    RAISE EXCEPTION 'another M05 schema-swap is already running';
  END IF;
END
$m05$;
SELECT 'M05_LOCK_ACQUIRED';
SELECT pg_sleep(86400);
SQL
  mkfifo -m 600 "${lock_signal}"
  (
    "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -At "${DATABASE_URL}" \
      -f "${lock_sql}" >"${lock_signal}" 2>"${TMP_DIR}/lock.err"
  ) &
  LOCK_HOLDER_PID="$!"
  local marker=""
  while IFS= read -r marker; do
    if [[ "${marker}" == "M05_LOCK_ACQUIRED" ]]; then
      LOCK_HOLDER_ACTIVE=1
      phase preparing success "schema-swap advisory lock acquired for the full run"
      return 0
    fi
  done <"${lock_signal}"
  wait "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
  phase preparing failed "another schema-swap is running or the restore lock could not be acquired"
  exit 3
}

assert_advisory_lock_alive() {
  if [[ "${LOCK_HOLDER_ACTIVE}" != "1" ]] || ! kill -0 "${LOCK_HOLDER_PID}" >/dev/null 2>&1; then
    phase preparing failed "schema-swap advisory lock was lost"
    exit 3
  fi
}

assert_expected_target() {
  if [[ "${PINVI_RESTORE_HOTSWAP_EXECUTE:-0}" != "1" && -z "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" ]]; then
    return 0
  fi
  for variable in PINVI_RESTORE_EXPECTED_DATABASE_NAME PINVI_RESTORE_EXPECTED_DATABASE_OID \
    PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER PINVI_RESTORE_EXPECTED_HOSTADDR PINVI_RESTORE_EXPECTED_PORT; do
    if [[ -z "${!variable:-}" ]]; then
      phase preparing failed "${variable} is required for an executing schema swap"
      exit 3
    fi
  done
  local actual
  actual="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align \
    --dbname="${DATABASE_URL}" \
    --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(inet_server_addr()::text, '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" \
    | tr -d '[:space:]')"
  local expected="${PINVI_RESTORE_EXPECTED_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_HOSTADDR}|${PINVI_RESTORE_EXPECTED_PORT}"
  if [[ "${actual}" != "${expected}" ]]; then
    phase preparing failed "restore target identity changed before schema swap"
    exit 3
  fi
  phase preparing success "restore target identity verified"
}

start_advisory_lock
assert_expected_target

validate_expected_target_values() {
  if [[ "${PINVI_RESTORE_HOTSWAP_EXECUTE:-0}" != "1" &&
    -z "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" ]]; then
    return 0
  fi
  if [[ ! "${PINVI_RESTORE_EXPECTED_DATABASE_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ||
    ! "${PINVI_RESTORE_EXPECTED_DATABASE_OID}" =~ ^[0-9]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}" =~ ^[0-9]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_HOSTADDR}" =~ ^[0-9A-Fa-f:.]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_PORT}" =~ ^[0-9]+$ ]]; then
    phase preparing failed "restore target identity contains unsafe values"
    exit 3
  fi
}

validate_expected_target_values

write_identity_guard() {
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
}

run_guarded_command() {
  local command="$1"
  local wrapper="${TMP_DIR}/guarded-command.sql"
  assert_advisory_lock_alive
  {
    write_identity_guard
    printf '%s;\n' "${command}"
  } >"${wrapper}"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f "${wrapper}" >/dev/null
}

run_guarded_file() {
  local sql_file="$1"
  local wrapper="${TMP_DIR}/guarded-$(basename "${sql_file}")"
  assert_advisory_lock_alive
  if grep -Eq '^[[:space:]]*\\(connect|c)[[:space:]]' "${sql_file}"; then
    phase restoring failed "restore SQL contains a connection switch"
    exit 3
  fi
  {
    write_identity_guard
    cat "${sql_file}"
  } >"${wrapper}"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f "${wrapper}" >/dev/null
}

remap_sql() {
  local input="$1"
  awk -v source="${SOURCE_SCHEMA}" -v target="${RESTORE_SCHEMA}" '
    BEGIN { in_copy = 0 }
    $0 ~ ("^COPY " source "\\.") {
      sub("^COPY " source "\\.", "COPY " target ".")
      in_copy = 1
      print
      next
    }
    $0 == "\\." {
      in_copy = 0
      print
      next
    }
    in_copy == 1 {
      print
      next
    }
    $0 == ("CREATE SCHEMA " source ";") {
      printf "CREATE SCHEMA IF NOT EXISTS %s;\n", target
      next
    }
    {
      gsub("SCHEMA " source, "SCHEMA " target)
      gsub("search_path = " source, "search_path = " target)
      gsub(source "\\.", target ".")
      gsub("\"" source "\"\\.", target ".")
      print
    }
  ' "${input}"
}

phase restoring running "restoring ${SOURCE_SCHEMA} into ${RESTORE_SCHEMA}"
run_guarded_command "DROP SCHEMA IF EXISTS ${RESTORE_SCHEMA} CASCADE"
"${PG_RESTORE_BIN}" \
  --schema="${SOURCE_SCHEMA}" \
  --schema-only \
  --no-owner \
  --no-privileges \
  --file="${TMP_DIR}/schema.sql" \
  "${SNAPSHOT}"
{
  printf 'CREATE SCHEMA IF NOT EXISTS %s;\n' "${RESTORE_SCHEMA}"
  remap_sql "${TMP_DIR}/schema.sql"
} >"${TMP_DIR}/schema-remapped.sql"
run_guarded_file "${TMP_DIR}/schema-remapped.sql"

"${PG_RESTORE_BIN}" \
  --schema="${SOURCE_SCHEMA}" \
  --data-only \
  --no-owner \
  --no-privileges \
  --file="${TMP_DIR}/data.sql" \
  "${SNAPSHOT}"
# 스키마(FK 포함)를 먼저 만든 뒤 data-only를 적재하므로, FK 적재 순서/순환이 있으면 실패한다.
# 데이터 적재 동안만 트리거/FK 검증을 끈다(단일 세션 내 SET → 세션 종료 시 자동 해제).
{
  printf 'SET session_replication_role = replica;\n'
  remap_sql "${TMP_DIR}/data.sql"
} >"${TMP_DIR}/data-remapped.sql"
run_guarded_file "${TMP_DIR}/data-remapped.sql"
phase restoring success "restored into ${RESTORE_SCHEMA}"

# pg_restore --no-privileges로 복원했으므로 GRANT가 비어 있다. 앱 role이 스키마 owner가
# 아니면 swap 직후 permission denied가 난다. swap 전에 RESTORE_SCHEMA에 GRANT를 재적용한다
# (GRANT는 객체에 귀속되어 schema rename 후에도 유지된다).
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
if [[ -n "${APP_ROLE}" ]]; then
  if [[ ! "${APP_ROLE}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase restoring failed "unsafe app role name: ${APP_ROLE}"
    exit 2
  fi
  cat >"${TMP_DIR}/grants.sql" <<SQL
GRANT USAGE ON SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
SQL
  run_guarded_file "${TMP_DIR}/grants.sql"
  phase restoring success "re-granted privileges to ${APP_ROLE}"
else
  phase restoring success "PINVI_RESTORE_APP_ROLE unset; assuming single-owner role (no GRANT re-apply)"
fi

phase validating running "validating restored schema"
users_exists="$("${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${DATABASE_URL}" -tAc "SELECT to_regclass('${RESTORE_SCHEMA}.users') IS NOT NULL")"
if [[ "${users_exists}" != "t" ]]; then
  phase validating failed "restored schema is missing users table"
  exit 3
fi
phase validating success "restored schema passed basic checks"

enter_write_fence() {
  if [[ -z "${APP_ROLE:-}" ]]; then
    phase draining failed "PINVI_RESTORE_APP_ROLE is required for the database write fence"
    exit 3
  fi
  local fence_status
  WRITE_FENCE_ACTIVE=1
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f - >/dev/null <<SQL
$(write_identity_guard)
REVOKE CREATE ON SCHEMA ${SOURCE_SCHEMA}, ${RESTORE_SCHEMA} FROM ${APP_ROLE};
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA ${SOURCE_SCHEMA}, ${RESTORE_SCHEMA} FROM ${APP_ROLE};
REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA ${SOURCE_SCHEMA}, ${RESTORE_SCHEMA} FROM ${APP_ROLE};
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = '${APP_ROLE}' AND pid <> pg_backend_pid();
SQL
  fence_status="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 -tAc "
SELECT
  NOT EXISTS (
    SELECT 1 FROM pg_stat_activity
    WHERE usename = '${APP_ROLE}' AND pid <> pg_backend_pid()
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_namespace n
    JOIN pg_class c ON c.relnamespace = n.oid
    WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
      AND (
        has_schema_privilege('${APP_ROLE}', n.oid, 'CREATE')
        OR has_table_privilege('${APP_ROLE}', c.oid, 'INSERT')
        OR has_table_privilege('${APP_ROLE}', c.oid, 'UPDATE')
        OR has_table_privilege('${APP_ROLE}', c.oid, 'DELETE')
        OR has_table_privilege('${APP_ROLE}', c.oid, 'TRUNCATE')
      )
" | tr -d '[:space:]')"
  if [[ "${fence_status}" != "t" ]]; then
    phase draining failed "database write fence could not revoke active runtime writes"
    exit 3
  fi
  phase draining success "database write fence revoked runtime writes and terminated active sessions"
}

release_write_fence() {
  if [[ -z "${APP_ROLE:-}" ]]; then
    WRITE_FENCE_ACTIVE=0
    return 0
  fi
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=0 "${DATABASE_URL}" -f - >/dev/null 2>&1 <<SQL || true
DO $m05$
BEGIN
  IF to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL THEN
    EXECUTE 'GRANT USAGE ON SCHEMA ${SOURCE_SCHEMA} TO ${APP_ROLE}';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${SOURCE_SCHEMA} TO ${APP_ROLE}';
    EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA ${SOURCE_SCHEMA} TO ${APP_ROLE}';
  END IF;
END
$m05$;
SQL
  WRITE_FENCE_ACTIVE=0
}

phase draining running "write drain"
enter_write_fence
if [[ "${PINVI_RESTORE_API_TRIGGER:-0}" == "1" && -n "${PINVI_RESTORE_DRAIN_COMMAND:-}" ]]; then
  phase draining failed "API-triggered restore cannot run PINVI_RESTORE_DRAIN_COMMAND"
  exit 3
fi
if [[ -n "${PINVI_RESTORE_DRAIN_COMMAND:-}" ]]; then
  bash -lc "${PINVI_RESTORE_DRAIN_COMMAND}"
  phase draining success "external drain command completed after database write fence"
elif [[ "${PINVI_RESTORE_ALLOW_NO_DRAIN:-0}" == "1" && "${PINVI_RESTORE_DRAIN_VERIFIED:-0}" == "1" ]]; then
  phase draining skipped "external drain acknowledged; database write fence is active"
else
  phase draining failed "PINVI_RESTORE_DRAIN_COMMAND or PINVI_RESTORE_DRAIN_VERIFIED=1 is required"
  exit 3
fi

phase switching running "renaming schemas"
cat >"${TMP_DIR}/switch.sql" <<SQL
BEGIN;
ALTER SCHEMA ${SOURCE_SCHEMA} RENAME TO ${PREVIOUS_SCHEMA};
ALTER SCHEMA ${RESTORE_SCHEMA} RENAME TO ${SOURCE_SCHEMA};
COMMIT;
SQL
run_guarded_file "${TMP_DIR}/switch.sql"
release_write_fence
phase switching success "schema-swap completed"
