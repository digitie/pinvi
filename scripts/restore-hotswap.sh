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
LOCK_HOLDER_BACKEND_PID=""
LOCK_HOLDER_ACTIVE=0
LOCK_INPUT_FD=""
LOCK_SIGNAL_FD=""
SQL_SEQUENCE=0
CLEANUP_MODE=0
WRITE_FENCE_ACTIVE=0
PUBLIC_CONNECT_REVOKED=0
FENCED_CONNECT_ROLES=""
CONNECT_RESTORE_GRANTS=""
TEST_MODE="${PINVI_M05_RESTORE_TEST_MODE:-0}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
declare -a WRITE_ROLES=()
declare -A WRITE_ROLE_SEEN=()

phase preparing running "precheck started"

if [[ -z "${DATABASE_URL}" ]]; then
  phase preparing failed "PINVI_DATABASE_URL or PINVI_RESTORE_DATABASE_URL is required"
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ -L "${SNAPSHOT}" || ! -f "${SNAPSHOT}" ]]; then
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
if [[ "${TEST_MODE}" != "1" && "${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
  assert_trusted_tool_path "pg_restore" "${PG_RESTORE_BIN}"
fi

if [[ -L "${SNAPSHOT}.sha256" || ! -f "${SNAPSHOT}.sha256" ]]; then
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
if [[ "${TEST_MODE}" != "1" && "${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
  assert_trusted_tool_path "psql" "${PSQL_BIN}"
fi

BASH_BIN="${PINVI_RESTORE_BASH_BIN:-$(pinned_tool bash || true)}"
if [[ "${BASH_BIN}" != /* || ! -x "${BASH_BIN}" ]]; then
  phase preparing failed "bash not found"
  exit 127
fi
verify_tool_digest "bash" "${BASH_BIN}" "${PINVI_RESTORE_BASH_SHA256:-}"
if [[ "${TEST_MODE}" != "1" && "${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
  assert_trusted_tool_path "bash" "${BASH_BIN}"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  set +e
  CLEANUP_MODE=1
  local cleanup_failed=0
  if [[ "${WRITE_FENCE_ACTIVE}" == "1" ]]; then
    if ! declare -F release_write_fence >/dev/null || ! release_write_fence; then
      phase draining failed "database write fence cleanup failed; manual writer lockout is required"
      cleanup_failed=1
    fi
  fi
  if [[ -n "${LOCK_HOLDER_PID}" ]]; then
    kill "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
    wait "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${LOCK_INPUT_FD}" ]]; then
    exec {LOCK_INPUT_FD}>&- || true
    LOCK_INPUT_FD=""
  fi
  if [[ -n "${LOCK_SIGNAL_FD}" ]]; then
    exec {LOCK_SIGNAL_FD}<&- || true
    LOCK_SIGNAL_FD=""
  fi
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
  if [[ "${cleanup_failed}" == "1" ]]; then
    exit 3
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
  BASH_BIN="$(copy_tool_to_private_dir bash "${BASH_BIN}" "${PINVI_RESTORE_BASH_SHA256}")"
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
  local lock_input="${TMP_DIR}/lock.input"
  local lock_signal="${TMP_DIR}/lock.signal"
  mkfifo -m 600 "${lock_input}" "${lock_signal}"
  (
    "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -Atq "${DATABASE_URL}" \
      >"${lock_signal}" 2>"${TMP_DIR}/lock.err" <"${lock_input}"
  ) &
  LOCK_HOLDER_PID="$!"
  exec {LOCK_SIGNAL_FD}<"${lock_signal}"
  exec {LOCK_INPUT_FD}>"${lock_input}"
  cat >&"${LOCK_INPUT_FD}" <<'SQL'
\set ON_ERROR_STOP on
DO $m05$
BEGIN
  IF NOT pg_try_advisory_lock(1414679892, 1213421392) THEN
    RAISE EXCEPTION 'another M05 schema-swap is already running';
  END IF;
END
$m05$;
SELECT 'M05_LOCK_ACQUIRED|' || pg_backend_pid()::text;
SQL
  local marker=""
  while IFS= read -r marker <&"${LOCK_SIGNAL_FD}"; do
    if [[ "${marker}" == M05_LOCK_ACQUIRED\|[0-9]* ]]; then
      local backend_pid="${marker#M05_LOCK_ACQUIRED|}"
      if [[ ! "${backend_pid}" =~ ^[0-9]+$ ]]; then
        phase preparing failed "schema-swap advisory lock returned an invalid backend PID"
        exit 3
      fi
      LOCK_HOLDER_ACTIVE=1
      LOCK_HOLDER_BACKEND_PID="${backend_pid}"
      phase preparing success "schema-swap advisory lock acquired for the full run"
      return 0
    fi
  done
  wait "${LOCK_HOLDER_PID}" >/dev/null 2>&1 || true
  phase preparing failed "another schema-swap is running or the restore lock could not be acquired"
  exit 3
}

advisory_lock_is_alive() {
  [[ "${LOCK_HOLDER_ACTIVE}" == "1" ]] && kill -0 "${LOCK_HOLDER_PID}" >/dev/null 2>&1
}

assert_advisory_lock_alive() {
  if ! advisory_lock_is_alive; then
    phase preparing failed "schema-swap database advisory lock was lost"
    if [[ "${CLEANUP_MODE}" == "1" ]]; then
      return 1
    fi
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
  if [[ "${TEST_MODE}" == "1" && -z "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" ]]; then
    return 0
  fi
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

execute_sql_file() {
  local sql_file="$1"
  local phase_name="$2"
  if ! advisory_lock_is_alive; then
    phase "${phase_name}" failed "schema-swap database advisory lock was lost before SQL dispatch"
    if [[ "${CLEANUP_MODE}" == "1" ]]; then
      return 1
    fi
    exit 3
  fi
  local command_id=$((SQL_SEQUENCE + 1))
  SQL_SEQUENCE="${command_id}"
  cat -- "${sql_file}" >&"${LOCK_INPUT_FD}"
  printf "\nSELECT 'M05_SQL_DONE|%s';\n" "${command_id}" >&"${LOCK_INPUT_FD}"
  local marker=""
  while true; do
    if IFS= read -r -t 1 marker <&"${LOCK_SIGNAL_FD}"; then
      if [[ "${marker}" == "M05_SQL_DONE|${command_id}" ]]; then
        return 0
      fi
    elif ! kill -0 "${LOCK_HOLDER_PID}" >/dev/null 2>&1; then
      phase "${phase_name}" failed "schema-swap lock session ended during SQL execution"
      if [[ "${CLEANUP_MODE}" == "1" ]]; then
        return 1
      fi
      exit 3
    fi
  done
}

advisory_lock_sql_guard() {
  cat <<SQL
DO \$m05\$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_locks
    WHERE pid = ${LOCK_HOLDER_BACKEND_PID}
      AND locktype = 'advisory'
      AND classid = 1414679892
      AND objid = 1213421392
      AND granted
  ) THEN
    RAISE EXCEPTION 'schema-swap database advisory lock was lost before mutation';
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
    printf 'BEGIN;\n'
    advisory_lock_sql_guard
    write_identity_guard
    printf '%s;\n' "${command}"
    advisory_lock_sql_guard
    write_identity_guard
    printf 'COMMIT;\n'
  } >"${wrapper}"
  execute_sql_file "${wrapper}" restoring
}

run_guarded_file() {
  local sql_file="$1"
  local wrapper="${TMP_DIR}/guarded-$(basename "${sql_file}")"
  assert_advisory_lock_alive
  if awk '
    BEGIN { in_copy = 0; unsafe = 0 }
    {
      line = $0
      normalized = tolower(line)
      if (!in_copy && normalized ~ /^[[:space:]]*copy([[:space:]]|$)/ && normalized ~ /;[[:space:]]*$/) {
        in_copy = 1
        next
      }
      if (in_copy) {
        if (line == "\\.") in_copy = 0
        next
      }
      if (
        normalized ~ /^[[:space:]]*\\[[:alpha:]!]/ ||
        normalized ~ /pg_advisory_(lock|unlock)/ ||
        normalized ~ /pg_(cancel|terminate)_backend/ ||
        normalized ~ /discard[[:space:]]+all/ ||
        normalized ~ /(^|[;[:space:]])(begin|start[[:space:]]+transaction|commit|rollback|abort)([;[:space:]]|$)/
      ) {
        unsafe = 1
        exit
      }
    }
    END { exit unsafe ? 0 : 1 }
  ' "${sql_file}"; then
    phase restoring failed "restore SQL contains a session, lock, or transaction control"
    exit 3
  fi
  {
    printf 'BEGIN;\n'
    advisory_lock_sql_guard
    write_identity_guard
    cat "${sql_file}"
    advisory_lock_sql_guard
    write_identity_guard
    printf '\nCOMMIT;\n'
  } >"${wrapper}"
  execute_sql_file "${wrapper}" restoring
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

add_write_role() {
  local role="$1"
  if [[ -z "${role}" ]]; then
    return 0
  fi
  if [[ ! "${role}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase draining failed "unsafe restore write role: ${role}"
    exit 3
  fi
  if [[ -z "${WRITE_ROLE_SEEN[${role}]:-}" ]]; then
    WRITE_ROLES+=("${role}")
    WRITE_ROLE_SEEN["${role}"]=1
  fi
}

write_roles_sql() {
  local role
  local joined=""
  for role in "${WRITE_ROLES[@]}"; do
    if [[ -n "${joined}" ]]; then
      joined+=","
    fi
    joined+="${role}"
  done
  printf '%s' "${joined}"
}

if [[ -z "${APP_ROLE}" ]]; then
  phase draining failed "PINVI_RESTORE_APP_ROLE is required for the database write fence"
  exit 3
fi
if [[ ! "${APP_ROLE}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  phase draining failed "unsafe app role name: ${APP_ROLE}"
  exit 3
fi
add_write_role "${APP_ROLE}"
if [[ -n "${PINVI_RESTORE_WRITE_ROLES:-}" ]]; then
  IFS=',' read -r -a configured_write_roles <<<"${PINVI_RESTORE_WRITE_ROLES}"
  for configured_role in "${configured_write_roles[@]}"; do
    add_write_role "${configured_role}"
  done
fi

public_connect_sql() {
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" ]]; then
    cat <<'SQL'
DO $m05$
BEGIN
  EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', current_database());
END
$m05$;
SQL
  fi
}

writer_login_roles() {
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH RECURSIVE role_closure(login_oid, role_oid) AS (
  SELECT r.oid, r.oid FROM pg_roles r WHERE r.rolcanlogin
  UNION
  SELECT rc.login_oid, membership.roleid
  FROM role_closure rc
  JOIN pg_auth_members membership ON membership.member = rc.role_oid
)
SELECT COALESCE(string_agg(DISTINCT login.rolname, ',' ORDER BY login.rolname), '')
FROM pg_roles login
JOIN role_closure closure ON closure.login_oid = login.oid
JOIN pg_roles effective ON effective.oid = closure.role_oid
WHERE login.rolcanlogin
  AND has_database_privilege(login.rolname, current_database(), 'CONNECT')
  AND (
    effective.rolsuper
    OR effective.rolbypassrls
    OR effective.rolcreaterole
    OR effective.rolcreatedb
    OR effective.rolreplication
    OR (to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${SOURCE_SCHEMA}', 'CREATE'))
    OR (to_regnamespace('${RESTORE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${RESTORE_SCHEMA}', 'CREATE'))
    OR EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
        AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
        AND (
          c.relowner = effective.oid
          OR pg_has_role(effective.oid, c.relowner, 'member')
          OR has_table_privilege(effective.rolname, c.oid, 'INSERT')
          OR has_table_privilege(effective.rolname, c.oid, 'UPDATE')
          OR has_table_privilege(effective.rolname, c.oid, 'DELETE')
          OR has_table_privilege(effective.rolname, c.oid, 'TRUNCATE')
          OR has_table_privilege(effective.rolname, c.oid, 'REFERENCES')
          OR has_table_privilege(effective.rolname, c.oid, 'TRIGGER')
        )
    )
    OR EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
        AND c.relkind = 'S'
        AND (
          c.relowner = effective.oid
          OR pg_has_role(effective.oid, c.relowner, 'member')
          OR has_sequence_privilege(effective.rolname, c.oid, 'USAGE')
          OR has_sequence_privilege(effective.rolname, c.oid, 'SELECT')
          OR has_sequence_privilege(effective.rolname, c.oid, 'UPDATE')
        )
    )
  )
" | tr -d '[:space:]'
}

assert_role_list_safe() {
  local role_list="$1"
  local context="$2"
  local role
  if [[ -z "${role_list}" ]]; then
    return 0
  fi
  IFS=',' read -r -a role_names <<<"${role_list}"
  for role in "${role_names[@]}"; do
    if [[ ! "${role}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
      phase draining failed "${context} contains an unsafe role name"
      exit 3
    fi
  done
}

writer_connect_roles() {
  local writer_logins="$1"
  if [[ -z "${writer_logins}" ]]; then
    printf '%s\n' ""
    return 0
  fi
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH RECURSIVE role_closure(role_oid) AS (
  SELECT oid FROM pg_roles WHERE rolname = ANY(string_to_array('${writer_logins}', ','))
  UNION
  SELECT membership.roleid
  FROM role_closure closure
  JOIN pg_auth_members membership ON membership.member = closure.role_oid
)
SELECT COALESCE(string_agg(DISTINCT roles.rolname, ',' ORDER BY roles.rolname), '')
FROM pg_roles roles
JOIN role_closure closure ON closure.role_oid = roles.oid
" | tr -d '[:space:]'
}

assert_writer_fence_capable() {
  local writer_logins="$1"
  if [[ -z "${writer_logins}" ]]; then
    return 0
  fi
  local unsafe_roles
  unsafe_roles="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH RECURSIVE role_closure(role_oid) AS (
  SELECT oid FROM pg_roles WHERE rolname = ANY(string_to_array('${writer_logins}', ','))
  UNION
  SELECT membership.roleid
  FROM role_closure closure
  JOIN pg_auth_members membership ON membership.member = closure.role_oid
)
SELECT COALESCE(string_agg(DISTINCT roles.rolname, ',' ORDER BY roles.rolname), '')
FROM pg_roles roles
JOIN role_closure closure ON closure.role_oid = roles.oid
JOIN pg_database db ON db.datname = current_database()
WHERE roles.rolsuper
   OR roles.rolcreaterole
   OR roles.rolcreatedb
   OR roles.rolreplication
   OR roles.rolbypassrls
    OR db.datdba = roles.oid
   OR EXISTS (
     SELECT 1
     FROM pg_namespace n
     WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
       AND n.nspowner = roles.oid
   )
   OR EXISTS (
     SELECT 1
     FROM pg_class c
     JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
       AND c.relowner = roles.oid
   )
" | tr -d '[:space:]')"
  if [[ -n "${unsafe_roles}" ]]; then
    phase draining failed "database write fence cannot contain privileged writer roles: ${unsafe_roles}"
    exit 3
  fi
}

connect_restore_grants() {
  local roles_sql="$1"
  if [[ -z "${roles_sql}" ]]; then
    printf '%s\n' ""
    return 0
  fi
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH grants AS (
  SELECT roles.rolname, bool_or(aclexplode.is_grantable) AS grantable
  FROM pg_database db
  CROSS JOIN LATERAL aclexplode(COALESCE(db.datacl, acldefault('d', db.datdba))) acl
  JOIN pg_roles roles ON roles.oid = acl.grantee
  WHERE db.datname = current_database()
    AND roles.rolname = ANY(string_to_array('${roles_sql}', ','))
    AND acl.privilege_type = 'CONNECT'
  GROUP BY roles.rolname
)
SELECT COALESCE(string_agg(rolname || ':' || CASE WHEN grantable THEN '1' ELSE '0' END, ',' ORDER BY rolname), '')
FROM grants
" | tr -d '[:space:]'
}

public_connect_granted() {
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
SELECT EXISTS (
  SELECT 1
  FROM pg_database db
  CROSS JOIN LATERAL aclexplode(COALESCE(db.datacl, acldefault('d', db.datdba))) acl
  WHERE db.datname = current_database()
    AND acl.grantee = 0
    AND acl.privilege_type = 'CONNECT'
)
" | tr -d '[:space:]'
}

wait_for_database_quiescence() {
  local sql_file="${TMP_DIR}/quiescence.sql"
  cat >"${sql_file}" <<'SQL'
DO $m05$
DECLARE
  attempts integer := 0;
  active_count bigint;
BEGIN
  LOOP
    PERFORM pg_terminate_backend(activity.pid)
    FROM pg_stat_activity activity
    WHERE activity.datname = current_database()
      AND activity.pid <> pg_backend_pid();
    SELECT count(*)
      INTO active_count
    FROM pg_stat_activity activity
    WHERE activity.datname = current_database()
      AND activity.pid <> pg_backend_pid()
      AND (activity.xact_start IS NOT NULL OR activity.state <> 'idle');
    EXIT WHEN active_count = 0;
    attempts := attempts + 1;
    IF attempts >= 50 THEN
      RAISE EXCEPTION 'database write fence could not drain active transactions';
    END IF;
    PERFORM pg_sleep(0.1);
  END LOOP;
END
$m05$;
SQL
  execute_sql_file "${sql_file}" draining
}

assert_no_connectable_writer_roles() {
  local sql_file="${TMP_DIR}/writer-fence-check.sql"
  cat >"${sql_file}" <<SQL
DO \$m05\$
DECLARE
  writer_names text;
BEGIN
  WITH RECURSIVE role_closure(login_oid, role_oid) AS (
    SELECT r.oid, r.oid
    FROM pg_roles r
    WHERE r.rolcanlogin
    UNION
    SELECT rc.login_oid, membership.roleid
    FROM role_closure rc
    JOIN pg_auth_members membership ON membership.member = rc.role_oid
  )
  SELECT COALESCE(string_agg(DISTINCT login.rolname, ',' ORDER BY login.rolname), '')
    INTO writer_names
  FROM pg_roles login
  JOIN role_closure closure ON closure.login_oid = login.oid
  JOIN pg_roles effective ON effective.oid = closure.role_oid
  WHERE login.rolcanlogin
    AND has_database_privilege(login.rolname, current_database(), 'CONNECT')
    AND (
      effective.rolsuper
      OR effective.rolbypassrls
      OR effective.rolcreaterole
      OR effective.rolcreatedb
      OR effective.rolreplication
      OR (to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${SOURCE_SCHEMA}', 'CREATE'))
      OR (to_regnamespace('${RESTORE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${RESTORE_SCHEMA}', 'CREATE'))
      OR EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND (
            c.relowner = effective.oid
            OR pg_has_role(effective.oid, c.relowner, 'member')
            OR has_table_privilege(effective.rolname, c.oid, 'INSERT')
            OR has_table_privilege(effective.rolname, c.oid, 'UPDATE')
            OR has_table_privilege(effective.rolname, c.oid, 'DELETE')
            OR has_table_privilege(effective.rolname, c.oid, 'TRUNCATE')
            OR has_table_privilege(effective.rolname, c.oid, 'REFERENCES')
            OR has_table_privilege(effective.rolname, c.oid, 'TRIGGER')
          )
      )
      OR EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
          AND c.relkind = 'S'
          AND (
            c.relowner = effective.oid
            OR pg_has_role(effective.oid, c.relowner, 'member')
            OR has_sequence_privilege(effective.rolname, c.oid, 'USAGE')
            OR has_sequence_privilege(effective.rolname, c.oid, 'SELECT')
            OR has_sequence_privilege(effective.rolname, c.oid, 'UPDATE')
          )
      )
    );
  IF writer_names <> '' THEN
    RAISE EXCEPTION 'database write fence found connectable writers: %', writer_names;
  END IF;
END
\$m05\$;
SQL
  execute_sql_file "${sql_file}" draining
}

assert_restored_schema() {
  local sql_file="${TMP_DIR}/restored-schema-check.sql"
  cat >"${sql_file}" <<SQL
DO \$m05\$
BEGIN
  IF to_regclass('${RESTORE_SCHEMA}.users') IS NULL THEN
    RAISE EXCEPTION 'restored schema is missing users table';
  END IF;
END
\$m05\$;
SQL
  execute_sql_file "${sql_file}" validating
}

assert_configured_roles_safe() {
  local roles_sql unsafe_roles
  roles_sql="$(write_roles_sql)"
  unsafe_roles="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH RECURSIVE role_closure(role_oid) AS (
  SELECT oid FROM pg_roles WHERE rolname = ANY(string_to_array('${roles_sql}', ','))
  UNION
  SELECT membership.roleid
  FROM role_closure closure
  JOIN pg_auth_members membership ON membership.member = closure.role_oid
)
SELECT COALESCE(string_agg(DISTINCT effective.rolname, ',' ORDER BY effective.rolname), '')
FROM pg_roles effective
JOIN role_closure closure ON closure.role_oid = effective.oid
WHERE effective.rolsuper
   OR effective.rolbypassrls
   OR effective.rolcreaterole
   OR effective.rolcreatedb
   OR effective.rolreplication
   OR (to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${SOURCE_SCHEMA}', 'CREATE'))
   OR (to_regnamespace('${RESTORE_SCHEMA}') IS NOT NULL AND has_schema_privilege(effective.rolname, '${RESTORE_SCHEMA}', 'CREATE'))
   OR EXISTS (
     SELECT 1
     FROM pg_namespace n
     WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
       AND (n.nspowner = effective.oid OR pg_has_role(effective.oid, n.nspowner, 'member'))
   )
   OR EXISTS (
     SELECT 1
     FROM pg_class c
     JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname IN ('${SOURCE_SCHEMA}', '${RESTORE_SCHEMA}')
       AND (c.relowner = effective.oid OR pg_has_role(effective.oid, c.relowner, 'member'))
   )
" | tr -d '[:space:]')"
  if [[ -n "${unsafe_roles}" ]]; then
    phase draining failed "configured restore role has privileged or owner membership: ${unsafe_roles}"
    exit 3
  fi
}

enter_write_fence() {
  local roles_sql
  roles_sql="$(write_roles_sql)"
  assert_advisory_lock_alive
  assert_configured_roles_safe
  local writer_logins
  writer_logins="$(writer_login_roles)"
  assert_role_list_safe "${writer_logins}" "database writer inventory"
  assert_writer_fence_capable "${writer_logins}"
  FENCED_CONNECT_ROLES="$(writer_connect_roles "${writer_logins}")"
  assert_role_list_safe "${FENCED_CONNECT_ROLES}" "database connection fence inventory"
  CONNECT_RESTORE_GRANTS="$(connect_restore_grants "${FENCED_CONNECT_ROLES}")"
  if [[ -n "${writer_logins}" && -z "${FENCED_CONNECT_ROLES}" ]]; then
    phase draining failed "database write fence could not identify writer roles"
    exit 3
  fi
  PUBLIC_CONNECT_WAS_GRANTED="$(public_connect_granted)"
  if [[ "${PUBLIC_CONNECT_WAS_GRANTED}" == "t" ]]; then
    PUBLIC_CONNECT_REVOKED=1
  fi
  WRITE_FENCE_ACTIVE=1
  local fence_sql="${TMP_DIR}/enter-fence.sql"
  cat >"${fence_sql}" <<SQL
BEGIN;
$(advisory_lock_sql_guard)
$(write_identity_guard)
DO \$m05\$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY string_to_array('${roles_sql}', ',') LOOP
    IF to_regrole(role_name) IS NULL THEN
      RAISE EXCEPTION 'restore write role does not exist: %', role_name;
    END IF;
    IF role_name = current_user THEN
      RAISE EXCEPTION 'restore write role must not be the restore executor: %', role_name;
    END IF;
  END LOOP;
  FOR role_name IN
    WITH RECURSIVE role_closure(role_oid) AS (
      SELECT oid FROM pg_roles WHERE rolname = ANY(string_to_array('${roles_sql}', ','))
      UNION
      SELECT membership.roleid
      FROM role_closure closure
      JOIN pg_auth_members membership ON membership.member = closure.role_oid
    )
    SELECT rolname FROM pg_roles JOIN role_closure ON role_closure.role_oid = pg_roles.oid
  LOOP
    IF to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL THEN
      EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM %I', '${SOURCE_SCHEMA}', role_name);
      EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM %I', '${SOURCE_SCHEMA}', role_name);
      EXECUTE format('REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I FROM %I', '${SOURCE_SCHEMA}', role_name);
    END IF;
    IF to_regnamespace('${RESTORE_SCHEMA}') IS NOT NULL THEN
      EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM %I', '${RESTORE_SCHEMA}', role_name);
      EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM %I', '${RESTORE_SCHEMA}', role_name);
      EXECUTE format('REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I FROM %I', '${RESTORE_SCHEMA}', role_name);
    END IF;
  END LOOP;
  IF to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL THEN
    EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM PUBLIC', '${SOURCE_SCHEMA}');
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM PUBLIC', '${SOURCE_SCHEMA}');
    EXECUTE format('REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC', '${SOURCE_SCHEMA}');
  END IF;
  IF to_regnamespace('${RESTORE_SCHEMA}') IS NOT NULL THEN
    EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM PUBLIC', '${RESTORE_SCHEMA}');
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM PUBLIC', '${RESTORE_SCHEMA}');
    EXECUTE format('REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC', '${RESTORE_SCHEMA}');
  END IF;
END
\$m05\$;
DO \$m05\$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY string_to_array('${FENCED_CONNECT_ROLES}', ',') LOOP
    IF role_name <> '' THEN
      EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM %I', current_database(), role_name);
    END IF;
  END LOOP;
END
\$m05\$;
$(public_connect_sql)
  COMMIT;
SQL
  execute_sql_file "${fence_sql}" draining
  wait_for_database_quiescence
  assert_no_connectable_writer_roles
  phase draining success "database write fence revoked all non-owner runtime writes"
}

release_write_fence() {
  local roles_sql
  roles_sql="$(write_roles_sql)"
  local fence_sql="${TMP_DIR}/release-fence.sql"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  cat >"${fence_sql}" <<SQL
BEGIN;
$(advisory_lock_sql_guard)
$(write_identity_guard)
DO \$m05\$
DECLARE
  role_name text;
  schema_name text;
BEGIN
  FOREACH role_name IN ARRAY string_to_array('${roles_sql}', ',') LOOP
    IF to_regnamespace('${SOURCE_SCHEMA}') IS NOT NULL THEN
      EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', '${SOURCE_SCHEMA}', role_name);
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I', '${SOURCE_SCHEMA}', role_name);
      EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO %I', '${SOURCE_SCHEMA}', role_name);
    END IF;
    IF to_regnamespace('${PREVIOUS_SCHEMA}') IS NOT NULL THEN
      EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', '${PREVIOUS_SCHEMA}', role_name);
      EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.admin_audit_log TO %I', '${PREVIOUS_SCHEMA}', role_name);
      EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO %I', '${PREVIOUS_SCHEMA}', role_name);
    END IF;
  END LOOP;
END
\$m05\$;
$(public_connect_sql | sed 's/REVOKE CONNECT/GRANT CONNECT/; s/FROM PUBLIC/TO PUBLIC/')
DO \$m05\$
DECLARE
  grant_spec text;
  role_name text;
  grantable text;
BEGIN
  FOREACH grant_spec IN ARRAY string_to_array('${CONNECT_RESTORE_GRANTS}', ',') LOOP
    IF grant_spec <> '' THEN
      role_name := split_part(grant_spec, ':', 1);
      grantable := split_part(grant_spec, ':', 2);
      EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO %I%s',
        current_database(),
        role_name,
        CASE WHEN grantable = '1' THEN ' WITH GRANT OPTION' ELSE '' END
      );
    END IF;
  END LOOP;
END
\$m05\$;
COMMIT;
SQL
  if ! execute_sql_file "${fence_sql}" draining; then
    return 1
  fi
  WRITE_FENCE_ACTIVE=0
}

phase draining running "write fence"
enter_write_fence

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

phase validating running "validating restored schema"
assert_restored_schema
phase validating success "restored schema passed basic checks"

phase draining running "write drain"
if [[ "${PINVI_RESTORE_API_TRIGGER:-0}" == "1" && -n "${PINVI_RESTORE_DRAIN_COMMAND:-}" ]]; then
  phase draining failed "API-triggered restore cannot run PINVI_RESTORE_DRAIN_COMMAND"
  exit 3
fi
if [[ -n "${PINVI_RESTORE_DRAIN_COMMAND:-}" ]]; then
  "${BASH_BIN}" -lc "${PINVI_RESTORE_DRAIN_COMMAND}"
  phase draining success "external drain command completed after database write fence"
elif [[ "${PINVI_RESTORE_ALLOW_NO_DRAIN:-0}" == "1" && "${PINVI_RESTORE_DRAIN_VERIFIED:-0}" == "1" ]]; then
  phase draining skipped "external drain acknowledged; database write fence is active"
else
  phase draining failed "PINVI_RESTORE_DRAIN_COMMAND or PINVI_RESTORE_DRAIN_VERIFIED=1 is required"
  exit 3
fi

phase switching running "renaming schemas"
cat >"${TMP_DIR}/switch.sql" <<SQL
ALTER SCHEMA ${SOURCE_SCHEMA} RENAME TO ${PREVIOUS_SCHEMA};
ALTER SCHEMA ${RESTORE_SCHEMA} RENAME TO ${SOURCE_SCHEMA};
SQL
run_guarded_file "${TMP_DIR}/switch.sql"
release_write_fence
phase switching success "schema-swap completed"
