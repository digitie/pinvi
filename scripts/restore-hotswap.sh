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
FENCE_DATABASE_URL="${PINVI_RESTORE_FENCE_DATABASE_URL:-${DATABASE_URL}}"
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
FENCE_EXECUTOR_ROLE=""
TEST_MODE="${PINVI_M05_RESTORE_TEST_MODE:-0}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
STRICT_RESTORE_ENVIRONMENT=0
if [[ "${TEST_MODE}" != "1" && ( "${PINVI_ENVIRONMENT:-}" == "staging" || "${PINVI_ENVIRONMENT:-}" == "production" ) ]]; then
  STRICT_RESTORE_ENVIRONMENT=1
fi
TRUSTED_SNAPSHOT_CHECKSUM=""
TRUSTED_SNAPSHOT_LIST_SHA256=""
declare -a WRITE_ROLES=()
declare -A WRITE_ROLE_SEEN=()

if [[ "${TEST_MODE}" != "0" && "${TEST_MODE}" != "1" ]]; then
  phase preparing failed "PINVI_M05_RESTORE_TEST_MODE must be 0 or 1"
  exit 2
fi
if [[ "${TEST_MODE}" == "1" && "${PINVI_ENVIRONMENT:-}" != "test" ]]; then
  phase preparing failed "M05 restore test mode requires PINVI_ENVIRONMENT=test"
  exit 3
fi

phase preparing running "precheck started"

if [[ -z "${DATABASE_URL}" ]]; then
  phase preparing failed "PINVI_DATABASE_URL or PINVI_RESTORE_DATABASE_URL is required"
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi
if [[ "${FENCE_DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  FENCE_DATABASE_URL="postgresql://${FENCE_DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ "${PINVI_RESTORE_HOTSWAP_EXECUTE:-0}" == "1" && "${TEST_MODE}" != "1" &&
  -z "${PINVI_RESTORE_FENCE_DATABASE_URL:-}" ]]; then
  phase preparing failed "PINVI_RESTORE_FENCE_DATABASE_URL is required for an executing schema swap"
  exit 3
fi

if [[ -L "${SNAPSHOT}" || ! -f "${SNAPSHOT}" ]]; then
  phase preparing failed "snapshot file not found"
  exit 2
fi

assert_trusted_snapshot_provenance() {
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" != "1" ]]; then
    return 0
  fi
  local trusted_dir snapshot_parent manifest_file item key value
  trusted_dir="${PINVI_RESTORE_TRUSTED_BACKUP_DIR:-}"
  if [[ "${trusted_dir}" != /* || -L "${trusted_dir}" || ! -d "${trusted_dir}" ]]; then
    phase preparing failed "strict restore requires a root-owned trusted backup directory"
    exit 3
  fi
  trusted_dir="$(realpath -e "${trusted_dir}")"
  snapshot_parent="$(realpath -e "$(dirname "${SNAPSHOT}")")"
  if [[ "${snapshot_parent}" != "${trusted_dir}" ]]; then
    phase preparing failed "snapshot is outside the trusted backup directory"
    exit 3
  fi
  if [[ "$(stat -c '%u:%a' "${trusted_dir}")" != "0:700" ]]; then
    phase preparing failed "trusted backup directory must be root-owned mode 0700"
    exit 3
  fi
  manifest_file="${SNAPSHOT}.m05-manifest"
  for item in "${SNAPSHOT}" "${SNAPSHOT}.sha256" "${manifest_file}"; do
    if [[ -L "${item}" || ! -f "${item}" || "$(stat -c '%u:%a' "${item}")" != "0:600" ]]; then
      phase preparing failed "trusted snapshot artifact is not a root-owned mode 0600 regular file"
      exit 3
    fi
  done
  declare -A manifest=()
  while IFS='=' read -r key value || [[ -n "${key:-}" ]]; do
    case "${key}" in
      version|dump_filename|schema|dump_sha256|pg_restore_list_sha256|source_database|source_database_oid|source_system_identifier|source_hostaddr|source_port) ;;
      *)
        phase preparing failed "trusted snapshot manifest has an invalid field"
        exit 3
        ;;
    esac
    if [[ -z "${value}" || -v "manifest[${key}]" || "${value}" == *$'\r'* ]]; then
      phase preparing failed "trusted snapshot manifest is malformed"
      exit 3
    fi
    manifest[${key}]="${value}"
  done <"${manifest_file}"
  for key in version dump_filename schema dump_sha256 pg_restore_list_sha256 source_database source_database_oid source_system_identifier source_hostaddr source_port; do
    if [[ ! -v "manifest[${key}]" ]]; then
      phase preparing failed "trusted snapshot manifest is incomplete"
      exit 3
    fi
  done
  if [[ "${manifest[version]}" != "1" ||
    "${manifest[dump_filename]}" != "$(basename "${SNAPSHOT}")" ||
    "${manifest[schema]}" != "${SOURCE_SCHEMA}" ||
    ! "${manifest[dump_sha256]}" =~ ^[0-9a-f]{64}$ ||
    ! "${manifest[pg_restore_list_sha256]}" =~ ^[0-9a-f]{64}$ ||
    ! "${manifest[source_database]}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ||
    ! "${manifest[source_database_oid]}" =~ ^[0-9]+$ ||
    ! "${manifest[source_system_identifier]}" =~ ^[0-9]+$ ||
    ! "${manifest[source_hostaddr]}" =~ ^[0-9A-Fa-f:.]+$ ||
    ! "${manifest[source_port]}" =~ ^[0-9]+$ ]]; then
    phase preparing failed "trusted snapshot manifest values are invalid"
    exit 3
  fi
  TRUSTED_SNAPSHOT_CHECKSUM="${manifest[dump_sha256]}"
  TRUSTED_SNAPSHOT_LIST_SHA256="${manifest[pg_restore_list_sha256]}"
}

assert_trusted_snapshot_provenance

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
if [[ ! "${expected_checksum}" =~ ^[0-9a-f]{64}$ || "${expected_checksum}" != "${actual_checksum}" ||
  ( -n "${TRUSTED_SNAPSHOT_CHECKSUM}" && "${expected_checksum}" != "${TRUSTED_SNAPSHOT_CHECKSUM}" ) ]]; then
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
terminate_restore() {
  if [[ "${CLEANUP_MODE}" != "1" ]]; then
    exit 143
  fi
}
trap terminate_restore TERM INT

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

if [[ "${STRICT_RESTORE_ENVIRONMENT}" == "1" ]]; then
  actual_restore_list_sha256="$("${PG_RESTORE_BIN}" --list "${SNAPSHOT}" | sha256sum | awk 'NR == 1 { print $1 }')"
  if [[ "${actual_restore_list_sha256}" != "${TRUSTED_SNAPSHOT_LIST_SHA256}" ]]; then
    phase preparing failed "trusted snapshot archive inventory failed"
    exit 3
  fi
else
  "${PG_RESTORE_BIN}" --list "${SNAPSHOT}" >/dev/null
fi
phase preparing success "snapshot verified for ${RESTORE_SCHEMA}"

start_advisory_lock() {
  local lock_input="${TMP_DIR}/lock.input"
  local lock_signal="${TMP_DIR}/lock.signal"
  mkfifo -m 600 "${lock_input}" "${lock_signal}"
  (
    exec "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -Atq "${DATABASE_URL}" \
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
  if [[ "${TEST_MODE}" == "1" && -z "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" ]]; then
    return 0
  fi
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
    --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" \
    | tr -d '[:space:]')"
  local expected="${PINVI_RESTORE_EXPECTED_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_HOSTADDR}|${PINVI_RESTORE_EXPECTED_PORT}"
  if [[ "${actual}" != "${expected}" ]]; then
    phase preparing failed "restore target identity changed before schema swap"
    exit 3
  fi
  phase preparing success "restore target identity verified"
}

validate_expected_target_values() {
  if [[ "${TEST_MODE}" == "1" && -z "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" ]]; then
    return 0
  fi
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
assert_expected_target

assert_fence_target_identity() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  local actual
  actual="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align \
    --dbname="${FENCE_DATABASE_URL}" \
    --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" \
    | tr -d '[:space:]')"
  local expected="${PINVI_RESTORE_EXPECTED_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_HOSTADDR}|${PINVI_RESTORE_EXPECTED_PORT}"
  if [[ "${actual}" != "${expected}" ]]; then
    phase preparing failed "database fence target does not match the restore target"
    exit 3
  fi
  phase preparing success "database fence target identity verified"
}

assert_fence_target_identity
start_advisory_lock

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
     OR COALESCE(host(inet_server_addr()), '') <> '${PINVI_RESTORE_EXPECTED_HOSTADDR}'
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

execute_fence_sql_file() {
  local sql_file="$1"
  local phase_name="$2"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  if ! "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${FENCE_DATABASE_URL}" \
    --file="${sql_file}"; then
    phase "${phase_name}" failed "database owner fence SQL failed"
    return 1
  fi
  if ! assert_advisory_lock_alive; then
    return 1
  fi
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
    function identifier_character(value) {
      return value ~ /^[[:alnum:]_$]$/
    }
    BEGIN {
      in_copy = 0
      block_comment_depth = 0
      quote = ""
      dollar_delimiter = ""
      single_quote_escape = 0
      unsafe = 0
      single_quote = sprintf("%c", 39)
      double_quote = sprintf("%c", 34)
    }
    {
      line = $0
      if (in_copy) {
        if (line == "\\.") in_copy = 0
        next
      }
      # pg_dump 16가 쓰는 dump token 경계만 허용한다. 그 외 psql meta command는
      # \copy ... PROGRAM, \i, \connect, \gexec처럼 SQL 경계를 벗어나거나
      # restore executor의 OS/다른 DB 권한을 사용할 수 있으므로 전부 거부한다.
      if (line ~ /^[[:space:]]*\\/) {
        if (line ~ /^[[:space:]]*\\(restrict|unrestrict)[[:space:]]+[^[:space:]]+[[:space:]]*$/) {
          next
        }
        unsafe = 1
        exit
      }
      clean = ""
      for (i = 1; i <= length(line); ) {
        character = substr(line, i, 1)
        pair = substr(line, i, 2)
        if (block_comment_depth > 0) {
          if (pair == "/*") {
            block_comment_depth++
            i += 2
          } else if (pair == "*/") {
            block_comment_depth--
            clean = clean " "
            i += 2
          } else {
            i++
          }
          continue
        }
        if (dollar_delimiter != "") {
          if (substr(line, i, length(dollar_delimiter)) == dollar_delimiter) {
            delimiter_length = length(dollar_delimiter)
            dollar_delimiter = ""
            clean = clean " "
            i += delimiter_length
          } else {
            i++
          }
          continue
        }
        if (quote == "single") {
          if (single_quote_escape && character == "\\") {
            clean = clean "  "
            i += 2
          } else if (character == single_quote) {
            if (substr(line, i + 1, 1) == single_quote) {
              clean = clean "  "
              i += 2
            } else {
              quote = ""
              clean = clean " "
              i++
            }
          } else {
            i++
          }
          continue
        }
        if (quote == "double") {
          if (character == double_quote) {
            if (substr(line, i + 1, 1) == double_quote) {
              clean = clean "  "
              i += 2
            } else {
              quote = ""
              clean = clean " "
              i++
            }
          } else {
            i++
          }
          continue
        }
        if (pair == "--") break
        if (pair == "/*") {
          block_comment_depth = 1
          clean = clean " "
          i += 2
          continue
        }
        if (character == single_quote) {
          quote = "single"
          previous = i > 1 ? substr(line, i - 1, 1) : ""
          before_previous = i > 2 ? substr(line, i - 2, 1) : ""
          single_quote_escape = tolower(previous) == "e" &&
            (i == 2 || !identifier_character(before_previous))
          clean = clean " "
          i++
          continue
        }
        if (character == double_quote) {
          quote = "double"
          clean = clean " "
          i++
          continue
        }
        if (character == "$") {
          candidate = substr(line, i)
          if (match(candidate, /^\$\$|^\$[[:alpha:]_][[:alnum:]_]*\$/)) {
            dollar_delimiter = substr(candidate, RSTART, RLENGTH)
            clean = clean " "
            i += RLENGTH
            continue
          }
        }
        clean = clean character
        i++
      }
      normalized = tolower(clean)
      if (normalized ~ /(^|[[:space:];])\\(copy|include|include_relative|ir|i|connect|c|gexec|g|watch|sf|p)([[:space:]]|$)/ || normalized ~ /pg_advisory_(lock|unlock)/ || normalized ~ /pg_(cancel|terminate)_backend/ || normalized ~ /discard[[:space:]]+all/ || normalized ~ /(^|[;[:space:]])(begin|start[[:space:]]+transaction|commit|end|rollback|abort)([;[:space:]]|$)/) {
        unsafe = 1
        exit
      }
      if (!in_copy && normalized ~ /^[[:space:]]*copy([[:space:]]|$)/ && normalized ~ /;[[:space:]]*$/) {
        in_copy = 1
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

public_connect_restore_sql() {
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" ]]; then
    cat <<'SQL'
DO $m05$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO PUBLIC', current_database());
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
  AND login.rolname <> current_user
  AND login.rolname <> '${FENCE_EXECUTOR_ROLE}'
  AND has_database_privilege(login.rolname, current_database(), 'CONNECT')
  AND (
    effective.rolsuper
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
WHERE roles.rolname <> current_user
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
WHERE roles.rolname <> current_user
  AND (
    roles.rolsuper
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
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${FENCE_DATABASE_URL}" -tAc "
WITH grants AS (
  SELECT roles.rolname, bool_or(acl.is_grantable) AS grantable
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
  local database_url="${1:-${DATABASE_URL}}"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${database_url}" -tAc "
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

database_connect_granted() {
  local database_url="$1"
  local role_name="$2"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${database_url}" -tAc \
    "SELECT has_database_privilege('${role_name}', current_database(), 'CONNECT')" \
    | tr -d '[:space:]'
}

assert_database_fence_applied() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  local role_name state
  if [[ -n "${FENCED_CONNECT_ROLES}" ]]; then
    IFS=',' read -r -a fenced_roles <<<"${FENCED_CONNECT_ROLES}"
    for role_name in "${fenced_roles[@]}"; do
      state="$(database_connect_granted "${FENCE_DATABASE_URL}" "${role_name}")"
      if [[ "${state}" != "f" ]]; then
        phase draining failed "database CONNECT fence was not applied"
        exit 3
      fi
    done
  fi
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" &&
    "$(public_connect_granted "${FENCE_DATABASE_URL}")" != "f" ]]; then
    phase draining failed "PUBLIC CONNECT fence was not applied"
    exit 3
  fi
}

assert_database_fence_restored() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  local grant_spec role_name state
  if [[ -n "${CONNECT_RESTORE_GRANTS}" ]]; then
    IFS=',' read -r -a grant_specs <<<"${CONNECT_RESTORE_GRANTS}"
    for grant_spec in "${grant_specs[@]}"; do
      role_name="${grant_spec%%:*}"
      state="$(database_connect_granted "${FENCE_DATABASE_URL}" "${role_name}")"
      if [[ "${state}" != "t" ]]; then
        phase draining failed "database CONNECT grant was not restored"
        return 1
      fi
    done
  fi
  local expected_public="f"
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" ]]; then
    expected_public="t"
  fi
  if [[ "$(public_connect_granted "${FENCE_DATABASE_URL}")" != "${expected_public}" ]]; then
    phase draining failed "PUBLIC CONNECT state was not restored"
    return 1
  fi
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
    AND login.rolname <> current_user
    AND login.rolname <> '${FENCE_EXECUTOR_ROLE}'
    AND has_database_privilege(login.rolname, current_database(), 'CONNECT')
    AND (
      effective.rolsuper
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
  IF (
    SELECT count(*)
    FROM (VALUES
      ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only', 63)),
      ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_truncate_append_only', 63)),
      ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_append_only', 63)),
      ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_truncate_append_only', 63)),
      ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_append_only', 63)),
      ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only', 63))
    ) expected(table_name, trigger_name)
    WHERE EXISTS (
      SELECT 1
      FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_proc p ON p.oid = t.tgfoid
      JOIN pg_namespace pn ON pn.oid = p.pronamespace
      WHERE n.nspname = '${RESTORE_SCHEMA}'
        AND c.relname = expected.table_name
        AND t.tgname = expected.trigger_name
        AND t.tgenabled = 'A'
        AND NOT t.tgisinternal
        AND p.proname = 'guard_ktm_feature_reference_reconciliation_append_only'
        AND pn.nspname = '${RESTORE_SCHEMA}'
    )
  ) <> 6 THEN
    RAISE EXCEPTION 'restored schema is missing an ENABLE ALWAYS M05 append-only trigger';
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

assert_restore_executor_safe() {
  local roles_sql
  roles_sql="$(write_roles_sql)"
  local executor_safe
  executor_safe="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
SELECT EXISTS (
  SELECT 1
  FROM pg_roles r
  WHERE r.rolname = current_user
    AND r.rolcanlogin
    AND has_database_privilege(current_user, current_database(), 'CONNECT')
    AND has_database_privilege(current_user, current_database(), 'CREATE')
    AND NOT r.rolsuper
    AND NOT r.rolcreaterole
    AND NOT r.rolcreatedb
    AND NOT r.rolreplication
    AND NOT r.rolbypassrls
    AND r.rolinherit
    AND has_schema_privilege(current_user, 'x_extension', 'USAGE')
    AND NOT has_schema_privilege(current_user, 'x_extension', 'CREATE')
    AND EXISTS (
      SELECT 1
      FROM pg_auth_members m
      WHERE m.member = r.oid
        AND m.roleid = to_regrole('pg_signal_backend')
    )
    AND NOT EXISTS (
      SELECT 1
      FROM pg_auth_members m
      WHERE m.member = r.oid
        AND m.roleid <> to_regrole('pg_signal_backend')
    )
    AND NOT EXISTS (
      SELECT 1
      FROM pg_auth_members m
      WHERE m.roleid = r.oid
    )
    AND current_user <> ALL(string_to_array('${roles_sql}', ','))
    AND EXISTS (
      SELECT 1
      FROM pg_namespace n
      WHERE n.nspname = '${SOURCE_SCHEMA}'
        AND n.nspowner = r.oid
    )
    AND (
      to_regnamespace('${RESTORE_SCHEMA}') IS NULL
      OR EXISTS (
        SELECT 1
        FROM pg_namespace n
        WHERE n.nspname = '${RESTORE_SCHEMA}'
          AND n.nspowner = r.oid
      )
    )
    AND NOT EXISTS (
      SELECT 1 FROM pg_namespace n WHERE n.nspname = '${PREVIOUS_SCHEMA}'
    )
  )
" | tr -d '[:space:]')"
  if [[ "${executor_safe}" != "t" ]]; then
    phase draining failed "restore executor must be a dedicated schema owner with database CREATE and only direct pg_signal_backend membership"
    exit 3
  fi
}

assert_fence_executor_safe() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  local executor_user fence_executor_user fence_safe
  executor_user="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc \
    "SELECT current_user" | tr -d '[:space:]')"
  if [[ ! "${executor_user}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase draining failed "restore executor identity is invalid"
    exit 3
  fi
  fence_executor_user="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${FENCE_DATABASE_URL}" -tAc \
    "SELECT current_user" | tr -d '[:space:]')"
  if [[ ! "${fence_executor_user}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase draining failed "database fence executor identity is invalid"
    exit 3
  fi
  FENCE_EXECUTOR_ROLE="${fence_executor_user}"
  fence_safe="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${FENCE_DATABASE_URL}" -tAc "
SELECT EXISTS (
  SELECT 1
  FROM pg_database db
  JOIN pg_roles owner_role ON owner_role.oid = db.datdba
  WHERE db.datname = current_database()
    AND current_user = owner_role.rolname
    AND current_user <> '${executor_user}'
    AND owner_role.rolcanlogin
    AND NOT owner_role.rolsuper
    AND NOT owner_role.rolcreaterole
    AND NOT owner_role.rolcreatedb
    AND NOT owner_role.rolreplication
    AND NOT owner_role.rolbypassrls
    AND owner_role.rolinherit
    AND NOT EXISTS (
      SELECT 1
      FROM pg_auth_members membership
      WHERE membership.member = owner_role.oid
         OR membership.roleid = owner_role.oid
    )
)
" | tr -d '[:space:]')"
  if [[ "${fence_safe}" != "t" ]]; then
    phase draining failed "database fence URL must be a dedicated non-superuser target owner"
    exit 3
  fi
}

assert_supported_acl_topology() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  if [[ -n "${PINVI_RESTORE_WRITE_ROLES:-}" ]]; then
    phase draining failed "schema-swap supports one canonical runtime role; PINVI_RESTORE_WRITE_ROLES is not supported"
    exit 3
  fi
  local writer_logins topology_safe
  writer_logins="$(writer_login_roles)"
  if [[ "${writer_logins}" != "${APP_ROLE}" ]]; then
    phase draining failed "schema-swap requires exactly one canonical runtime writer role"
    exit 3
  fi
  topology_safe="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc "
WITH source_schema AS (
  SELECT n.oid, n.nspowner, n.nspacl
  FROM pg_namespace n
  WHERE n.nspname = '${SOURCE_SCHEMA}'
),
app_role AS (
  SELECT oid FROM pg_roles WHERE rolname = '${APP_ROLE}'
),
fence_role AS (
  SELECT oid FROM pg_roles WHERE rolname = '${FENCE_EXECUTOR_ROLE}'
),
table_relations AS (
  SELECT c.oid, c.relowner, c.relacl
  FROM pg_class c
  JOIN source_schema s ON s.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
),
sequence_relations AS (
  SELECT c.oid, c.relowner, c.relacl
  FROM pg_class c
  JOIN source_schema s ON s.oid = c.relnamespace
  WHERE c.relkind = 'S'
)
SELECT
  (SELECT count(*) FROM source_schema) = 1
  AND (SELECT count(*) FROM app_role) = 1
  AND (SELECT count(*) FROM fence_role) = 1
  AND (SELECT oid FROM app_role) <> (SELECT oid FROM fence_role)
  AND EXISTS (
    SELECT 1
    FROM pg_roles r
    JOIN app_role a ON a.oid = r.oid
    WHERE r.rolcanlogin
      AND NOT r.rolinherit
      AND NOT r.rolsuper
      AND NOT r.rolcreaterole
      AND NOT r.rolcreatedb
      AND NOT r.rolreplication
      AND NOT r.rolbypassrls
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_auth_members m
    JOIN app_role a ON a.oid = m.member OR a.oid = m.roleid
  )
  AND NOT EXISTS (
    SELECT 1 FROM source_schema s WHERE s.nspowner <> current_user::regrole
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_auth_members m
    JOIN fence_role f ON f.oid = m.member OR f.oid = m.roleid
  )
  AND EXISTS (
    SELECT 1
    FROM pg_namespace n
    WHERE n.nspname = 'x_extension'
      AND has_schema_privilege((SELECT oid FROM app_role), n.oid, 'USAGE')
      AND NOT has_schema_privilege((SELECT oid FROM app_role), n.oid, 'CREATE')
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_namespace n
    JOIN fence_role f ON true
    WHERE n.nspname = 'x_extension'
      AND (
        n.nspowner = f.oid
        OR pg_has_role(f.oid, n.nspowner, 'member')
        OR has_schema_privilege(f.oid, n.oid, 'USAGE')
        OR has_schema_privilege(f.oid, n.oid, 'CREATE')
      )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN source_schema s ON s.oid = c.relnamespace
    WHERE c.relowner <> current_user::regrole
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN source_schema s ON s.oid = p.pronamespace
    WHERE p.proowner <> current_user::regrole
       OR p.proacl IS NOT NULL
       OR p.prosecdef
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN source_schema s ON s.oid = t.typnamespace
    WHERE t.typowner <> current_user::regrole OR t.typacl IS NOT NULL
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_attribute a
    JOIN table_relations c ON c.oid = a.attrelid
    WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
  )
  AND NOT EXISTS (
    SELECT 1
    FROM source_schema s
    WHERE NOT EXISTS (
      SELECT 1
      FROM aclexplode(COALESCE(s.nspacl, acldefault('n', s.nspowner))) acl
      WHERE acl.grantee = (SELECT oid FROM app_role)
        AND acl.privilege_type = 'USAGE'
        AND NOT acl.is_grantable
    )
    OR EXISTS (
      SELECT 1
      FROM aclexplode(COALESCE(s.nspacl, acldefault('n', s.nspowner))) acl
      WHERE NOT (
        acl.grantee = s.nspowner
        OR (
          acl.grantee = (SELECT oid FROM app_role)
          AND acl.privilege_type = 'USAGE'
          AND NOT acl.is_grantable
        )
      )
    )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM table_relations c
    WHERE c.relowner <> current_user::regrole
      OR (
        SELECT count(*)
        FROM aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) acl
        WHERE acl.grantee = (SELECT oid FROM app_role)
          AND acl.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
          AND NOT acl.is_grantable
      ) <> 4
      OR EXISTS (
        SELECT 1
        FROM aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) acl
        WHERE NOT (
          acl.grantee = c.relowner
          OR (
            acl.grantee = (SELECT oid FROM app_role)
            AND acl.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
            AND NOT acl.is_grantable
          )
        )
      )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM sequence_relations c
    WHERE c.relowner <> current_user::regrole
      OR (
        SELECT count(*)
        FROM aclexplode(COALESCE(c.relacl, acldefault('S', c.relowner))) acl
        WHERE acl.grantee = (SELECT oid FROM app_role)
          AND acl.privilege_type IN ('USAGE', 'SELECT', 'UPDATE')
          AND NOT acl.is_grantable
      ) <> 3
      OR EXISTS (
        SELECT 1
        FROM aclexplode(COALESCE(c.relacl, acldefault('S', c.relowner))) acl
        WHERE NOT (
          acl.grantee = c.relowner
          OR (
            acl.grantee = (SELECT oid FROM app_role)
            AND acl.privilege_type IN ('USAGE', 'SELECT', 'UPDATE')
            AND NOT acl.is_grantable
          )
        )
      )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_default_acl d
    JOIN source_schema s ON s.oid = d.defaclnamespace
    WHERE d.defaclrole = current_user::regrole
      AND (
        d.defaclobjtype NOT IN ('r', 'S')
        OR (
          d.defaclobjtype = 'r'
          AND (
            (
              SELECT count(*)
              FROM aclexplode(d.defaclacl) acl
              WHERE acl.grantee = (SELECT oid FROM app_role)
                AND acl.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
                AND NOT acl.is_grantable
            ) <> 4
            OR EXISTS (
              SELECT 1
              FROM aclexplode(d.defaclacl) acl
              WHERE NOT (
                acl.grantee = (SELECT oid FROM app_role)
                AND acl.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
                AND NOT acl.is_grantable
              )
            )
          )
        )
        OR (
          d.defaclobjtype = 'S'
          AND (
            (
              SELECT count(*)
              FROM aclexplode(d.defaclacl) acl
              WHERE acl.grantee = (SELECT oid FROM app_role)
                AND acl.privilege_type IN ('USAGE', 'SELECT', 'UPDATE')
                AND NOT acl.is_grantable
            ) <> 3
            OR EXISTS (
              SELECT 1
              FROM aclexplode(d.defaclacl) acl
              WHERE NOT (
                acl.grantee = (SELECT oid FROM app_role)
                AND acl.privilege_type IN ('USAGE', 'SELECT', 'UPDATE')
                AND NOT acl.is_grantable
              )
            )
          )
        )
      )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_default_acl d
    WHERE d.defaclrole = current_user::regrole
      AND d.defaclnamespace = 0
  )
" | tr -d '[:space:]')"
  if [[ "${topology_safe}" != "t" ]]; then
    phase draining failed "schema-swap requires canonical single-runtime-role ACLs; use an offline restore plan"
    exit 3
  fi
}

enter_write_fence() {
  local roles_sql
  roles_sql="$(write_roles_sql)"
  assert_advisory_lock_alive
  if [[ "${TEST_MODE}" == "1" ]]; then
    phase draining success "test-mode write fence simulated"
    return 0
  fi
  assert_restore_executor_safe
  assert_fence_target_identity
  assert_fence_executor_safe
  assert_configured_roles_safe
  assert_supported_acl_topology
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
  PUBLIC_CONNECT_WAS_GRANTED="$(public_connect_granted "${FENCE_DATABASE_URL}")"
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
  COMMIT;
SQL
  execute_sql_file "${fence_sql}" draining
  local database_fence_sql="${TMP_DIR}/enter-database-fence.sql"
  cat >"${database_fence_sql}" <<SQL
BEGIN;
$(advisory_lock_sql_guard)
$(write_identity_guard)
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
$(advisory_lock_sql_guard)
$(write_identity_guard)
COMMIT;
SQL
  execute_fence_sql_file "${database_fence_sql}" draining
  assert_database_fence_applied
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
COMMIT;
SQL
  if ! execute_sql_file "${fence_sql}" draining; then
    return 1
  fi
  local database_fence_sql="${TMP_DIR}/release-database-fence.sql"
  cat >"${database_fence_sql}" <<SQL
BEGIN;
$(advisory_lock_sql_guard)
$(write_identity_guard)
$(public_connect_restore_sql)
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
$(advisory_lock_sql_guard)
$(write_identity_guard)
COMMIT;
SQL
  if ! execute_fence_sql_file "${database_fence_sql}" draining; then
    return 1
  fi
  if ! assert_database_fence_restored; then
    return 1
  fi
  assert_supported_acl_topology
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
# 스키마(FK 포함)를 먼저 만든 뒤 data-only를 적재한다. pg_restore가 계산한
# dependency order를 사용하고, M05 ENABLE ALWAYS trigger와 FK 검증은 복구 중에도 켠다.
{
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
