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
  if [[ "${status}" == "running" ]]; then
    ACTIVE_PHASE="${name}"
  fi
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
OPERATION_LEASE_FD="${PINVI_M05_OPERATION_LEASE_FD:-}"
OPERATION_LEASE_TOKEN="${PINVI_M05_OPERATION_LEASE_TOKEN:-}"
SOURCE_SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
TMP_DIR=""
LOCK_HOLDER_PID=""
LOCK_HOLDER_BACKEND_PID=""
LOCK_HOLDER_ACTIVE=0
LOCK_INPUT_FD=""
LOCK_SIGNAL_FD=""
LOCK_COMMAND_SEQUENCE=0
SQL_SEQUENCE=0
CLEANUP_MODE=0
WRITE_FENCE_ACTIVE=0
RELEASE_FAILURE_INJECTED=0
RELEASE_SQL_FAILURE_INJECTED=0
RELEASE_DATABASE_SQL_FAILURE_INJECTED=0
RESTORE_FAILURE_INJECTED=0
FORENSICS_RELEASE_FAILURE_INJECTED=0
FORENSICS_HISTORY_APPEND_FAILURE_INJECTED=0
# The release transaction and the filesystem forensic state have no shared
# atomic commit.  Mark the interval *before* the first physical writer grant
# so EXIT/INT/TERM handling fails closed even if the process is interrupted
# between the database commit and the next shell assignment.
RELEASE_WINDOW_MAY_HAVE_OPENED=0
RELEASE_WRITE_FENCE_COMPLETED=0
RELEASE_WINDOW_REFENCED=0
RELEASE_TERMINAL_SEALED=0
REFENCE_SQL_FAILURE_INJECTED=0
PUBLIC_CONNECT_REVOKED=0
FENCED_CONNECT_ROLES=""
CONNECT_RESTORE_GRANTS=""
APP_CONNECT_RESTORE_GRANTS=""
RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS=""
FENCE_EXECUTOR_ROLE=""
HOTSWAP_EXECUTOR_ROLE=""
LOCK_SESSION_FENCED=0
ACTIVE_PHASE="preparing"
FORENSICS_ENABLED=0
FORENSICS_STARTED=0
FORENSICS_TERMINAL=0
FORENSICS_FAILURE_RECORDED=0
FORENSICS_STATE_DIRECTORY=""
FORENSICS_MODE_ARGUMENT=""
FORENSICS_HELPER=""
FORENSICS_OPERATION_ID=""
FORENSICS_DRAIN_RECEIPT_SHA256=""
FORENSICS_SCRIPT_SHA256=""
FORENSICS_RELEASE_INTENT_MARKER_SHA256=""
RESTORE_LIST_SHA256=""
SOURCE_SCHEMA_OID_BEFORE=""
ACL_TOPOLOGY_SHA256=""
FORENSICS_SCHEMA_OID=""
RESTORE_SCHEMA_OID=""
APP_SCHEMA_OID_AFTER_SWITCH=""
PREVIOUS_SCHEMA_OID_AFTER_SWITCH=""
RELEASE_RECEIPT_TOPOLOGY_SHA256=""
RELEASE_RECEIPT_RECORD_SHA256=""
RELEASE_RECEIPT_REQUIRED=0
TEST_MODE="${PINVI_M05_RESTORE_TEST_MODE:-0}"
APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}"
STRICT_RESTORE_ENVIRONMENT=0
if [[ "${TEST_MODE}" != "1" && ( "${PINVI_ENVIRONMENT:-}" == "staging" || "${PINVI_ENVIRONMENT:-}" == "production" ) ]]; then
  STRICT_RESTORE_ENVIRONMENT=1
fi
TRUSTED_SNAPSHOT_CHECKSUM=""
TRUSTED_SNAPSHOT_LIST_SHA256=""
TRUSTED_SOURCE_DATABASE=""
TRUSTED_SOURCE_DATABASE_OID=""
TRUSTED_SOURCE_SYSTEM_IDENTIFIER=""
TRUSTED_SOURCE_HOSTADDR=""
TRUSTED_SOURCE_PORT=""
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

assert_operation_lease() {
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" != "1" ]]; then
    return 0
  fi
  if [[ ! "${OPERATION_LEASE_TOKEN}" =~ ^m05-v1-[0-9a-f]{64}$ ||
    ! "${OPERATION_LEASE_FD}" =~ ^[0-9]+$ ||
    ! -e "/proc/self/fd/${OPERATION_LEASE_FD}" ]]; then
    phase preparing failed "strict hotswap requires a trusted target operation lease"
    exit 3
  fi
  local expected_path actual_path
  expected_path="/var/lib/pinvi/restore-forensics/operation-leases/${OPERATION_LEASE_TOKEN#m05-v1-}.lock"
  actual_path="$(readlink -f "/proc/self/fd/${OPERATION_LEASE_FD}" 2>/dev/null || true)"
  if [[ "${actual_path}" != "${expected_path}" || -L "${expected_path}" ||
    ! -f "${expected_path}" || "$(stat -c '%u:%a' "${expected_path}")" != "0:600" ]]; then
    phase preparing failed "trusted target operation lease is invalid"
    exit 3
  fi
  if ! flock -n "${OPERATION_LEASE_FD}"; then
    phase preparing failed "another M05 target mutation is already running"
    exit 3
  fi
  phase preparing success "shared target operation lease acquired"
}

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
      version|dump_filename|schema|dump_sha256|pg_restore_list_sha256|source_database|source_database_oid|source_system_identifier|source_hostaddr|source_port|created_at) ;;
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
  if [[ -v "manifest[created_at]" &&
    ! "${manifest[created_at]}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
    phase preparing failed "trusted snapshot manifest created_at is invalid"
    exit 3
  fi
  TRUSTED_SNAPSHOT_CHECKSUM="${manifest[dump_sha256]}"
  TRUSTED_SNAPSHOT_LIST_SHA256="${manifest[pg_restore_list_sha256]}"
  # A root-owned archive is not automatically an archive for this live target.
  # Keep the complete source identity so the executing hotswap can bind it to
  # the independently attested target before it acquires the advisory lock or
  # changes any database privilege.
  TRUSTED_SOURCE_DATABASE="${manifest[source_database]}"
  TRUSTED_SOURCE_DATABASE_OID="${manifest[source_database_oid]}"
  TRUSTED_SOURCE_SYSTEM_IDENTIFIER="${manifest[source_system_identifier]}"
  TRUSTED_SOURCE_HOSTADDR="${manifest[source_hostaddr]}"
  TRUSTED_SOURCE_PORT="${manifest[source_port]}"
}

assert_operation_lease
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
release_receipt_seal_is_exact() {
  # Shell flags are not evidence: a TERM can land after a durable seal and
  # before the assignment that normally records completion.  Only the strict
  # helper may certify the same raw intent marker and receipt record together.
  if [[ "${FORENSICS_ENABLED}" != "1" || "${RELEASE_RECEIPT_REQUIRED}" != "1" ||
    ! "${FORENSICS_OPERATION_ID}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ||
    ! "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${RELEASE_RECEIPT_RECORD_SHA256}" =~ ^[0-9a-f]{64}$ ||
    -z "${FORENSICS_HELPER}" || -z "${FORENSICS_MODE_ARGUMENT}" || -z "${FORENSICS_STATE_DIRECTORY}" ]]; then
    return 1
  fi
  /usr/bin/python3 -I "${FORENSICS_HELPER}" assert-release-receipt-seal \
    "${FORENSICS_MODE_ARGUMENT}" --state-dir "${FORENSICS_STATE_DIRECTORY}" \
    --operation-id "${FORENSICS_OPERATION_ID}" \
    --intent-marker-sha256 "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" \
    --receipt-record-sha256 "${RELEASE_RECEIPT_RECORD_SHA256}" >/dev/null
}

cleanup() {
  local cleanup_status=$?
  trap - EXIT
  set +e
  CLEANUP_MODE=1
  # A signal, crash-like shell error, or filesystem failure can occur after
  # the release SQL starts but before the terminal forensic marker commits.
  # Never infer that writers stayed fenced from a missing completion flag:
  # refence the live database first, retain the switched schemas/candidate,
  # and leave the marker latched for explicit root incident recovery.
  if [[ "${cleanup_status}" != "0" && "${WRITE_FENCE_ACTIVE}" == "1" &&
        "${RELEASE_WINDOW_MAY_HAVE_OPENED}" == "1" &&
        "${RELEASE_WINDOW_REFENCED}" != "1" ]]; then
    if release_receipt_seal_is_exact; then
      # The sealed receipt is the terminal forensic commit.  Leave current.json
      # for trusted root acknowledgement, but do not accidentally re-fence a
      # database whose release was already proven and sealed.
      RELEASE_TERMINAL_SEALED=1
      FORENSICS_TERMINAL=1
      WRITE_FENCE_ACTIVE=0
    elif reapply_write_fence_after_post_release_forensic_failure; then
      RELEASE_WINDOW_REFENCED=1
    else
      phase "${ACTIVE_PHASE}" failed "release-window writer fence reapplication failed; explicit root escalation is required"
      cleanup_status=3
    fi
  fi
  if [[ "${cleanup_status}" != "0" && "${FORENSICS_STARTED}" == "1" &&
        "${FORENSICS_TERMINAL}" != "1" && "${FORENSICS_FAILURE_RECORDED}" != "1" ]]; then
    local failure_code="runner_failure"
    if [[ "${RELEASE_WINDOW_MAY_HAVE_OPENED}" == "1" ]]; then
      if [[ "${RELEASE_WINDOW_REFENCED}" == "1" ]]; then
        if [[ "${RELEASE_WRITE_FENCE_COMPLETED}" == "1" ]]; then
          failure_code="post_release_forensics_persist_failed_refenced"
        else
          failure_code="release_window_interrupted_refenced"
        fi
      elif [[ "${RELEASE_WRITE_FENCE_COMPLETED}" == "1" ]]; then
        failure_code="post_release_forensics_persist_failed_refence_failed"
      else
        failure_code="release_window_interrupted_refence_failed"
      fi
    fi
    if ! record_forensics_failure "${failure_code}"; then
      phase "${ACTIVE_PHASE}" failed "forensic failure latch could not be persisted; explicit root escalation is required"
      cleanup_status=3
    fi
  fi
  if [[ "${cleanup_status}" != "0" && "${WRITE_FENCE_ACTIVE}" == "1" ]]; then
    phase draining failed "database write fence remains active; explicit root recovery is required"
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
  exit "${cleanup_status}"
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
  RESTORE_LIST_SHA256="$("${PG_RESTORE_BIN}" --list "${SNAPSHOT}" | sha256sum | awk 'NR == 1 { print $1 }')"
  if [[ "${RESTORE_LIST_SHA256}" != "${TRUSTED_SNAPSHOT_LIST_SHA256}" ]]; then
    phase preparing failed "trusted snapshot archive inventory failed"
    exit 3
  fi
else
  RESTORE_LIST_SHA256="$("${PG_RESTORE_BIN}" --list "${SNAPSHOT}" | sha256sum | awk 'NR == 1 { print $1 }')"
  if [[ ! "${RESTORE_LIST_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
    phase preparing failed "snapshot archive inventory failed"
    exit 3
  fi
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
  if [[ -s "${TMP_DIR}/lock.err" ]]; then
    cat -- "${TMP_DIR}/lock.err" >&2 || true
  fi
  phase preparing failed "another schema-swap is running or the restore lock could not be acquired"
  exit 3
}

advisory_lock_is_alive() {
  [[ "${LOCK_HOLDER_ACTIVE}" == "1" ]] && kill -0 "${LOCK_HOLDER_PID}" >/dev/null 2>&1
}

assert_advisory_lock_alive() {
  if ! advisory_lock_is_alive; then
    phase preparing failed "schema-swap database advisory lock was lost"
    return 1
  fi
}

configure_forensics() {
  local runner_directory helper_metadata helper_mode
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" == "1" ]]; then
    if [[ ! "${PINVI_M05_FORENSICS_OPERATION_ID:-}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ||
      ! "${PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256:-}" =~ ^[0-9a-f]{64}$ ]]; then
      phase preparing failed "strict hotswap requires a fixed forensic operation receipt"
      exit 3
    fi
    if [[ "${PINVI_M05_FORENSICS_STATE_DIR:-}" != "/var/lib/pinvi/restore-forensics" ]]; then
      phase preparing failed "strict hotswap requires the fixed forensic state directory"
      exit 3
    fi
    FORENSICS_ENABLED=1
    FORENSICS_MODE_ARGUMENT="--strict"
    FORENSICS_STATE_DIRECTORY="/var/lib/pinvi/restore-forensics"
    FORENSICS_OPERATION_ID="${PINVI_M05_FORENSICS_OPERATION_ID}"
    FORENSICS_DRAIN_RECEIPT_SHA256="${PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256}"
    RELEASE_RECEIPT_REQUIRED=1
  elif [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
    ( -n "${PINVI_M05_FORENSICS_OPERATION_ID:-}" ||
      -n "${PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256:-}" ||
      -n "${PINVI_M05_FORENSICS_STATE_DIR:-}" ) ]]; then
    if [[ ! "${PINVI_M05_FORENSICS_OPERATION_ID:-}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ||
      ! "${PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256:-}" =~ ^[0-9a-f]{64}$ ||
      "${PINVI_M05_FORENSICS_STATE_DIR:-}" != /* ]]; then
      phase preparing failed "test forensic lifecycle requires an operation receipt and absolute state directory"
      exit 3
    fi
    FORENSICS_ENABLED=1
    FORENSICS_MODE_ARGUMENT="--test-mode"
    FORENSICS_STATE_DIRECTORY="${PINVI_M05_FORENSICS_STATE_DIR}"
    FORENSICS_OPERATION_ID="${PINVI_M05_FORENSICS_OPERATION_ID}"
    FORENSICS_DRAIN_RECEIPT_SHA256="${PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256}"
    if [[ "${PINVI_RESTORE_TEST_REQUIRE_RELEASE_RECEIPT:-0}" == "1" ]]; then
      RELEASE_RECEIPT_REQUIRED=1
    fi
  else
    return 0
  fi

  runner_directory="${BASH_SOURCE[0]%/*}"
  if [[ "${runner_directory}" == "${BASH_SOURCE[0]}" ]]; then
    runner_directory="."
  fi
  runner_directory="$(cd -- "${runner_directory}" && pwd -P)"
  FORENSICS_HELPER="${runner_directory}/m05_hotswap_forensics.py"
  if [[ ! -f "${FORENSICS_HELPER}" || -L "${FORENSICS_HELPER}" ]]; then
    phase preparing failed "trusted forensic helper is unavailable"
    exit 3
  fi
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" == "1" ]]; then
    helper_metadata="$(stat -c '%u:%a' "${FORENSICS_HELPER}")"
    helper_mode="${helper_metadata#*:}"
    if [[ "${helper_metadata%%:*}" != "0" || ! "${helper_mode}" =~ ^[0-7]{3,4}$ ||
      $((8#${helper_mode} & 8#022)) -ne 0 ]]; then
      phase preparing failed "trusted forensic helper permissions are invalid"
      exit 3
    fi
  fi
}

forensics_command() {
  local command="$1"
  shift
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  /usr/bin/python3 -I "${FORENSICS_HELPER}" "${command}" \
    "${FORENSICS_MODE_ARGUMENT}" --state-dir "${FORENSICS_STATE_DIRECTORY}" "$@"
}

assert_forensics_inactive() {
  local status
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  if ! status="$(forensics_command status --allow-absent)"; then
    phase preparing failed "forensic lifecycle status could not be read"
    exit 3
  fi
  if [[ "${status}" != '{"active":false}' ]]; then
    phase preparing failed "unresolved hotswap forensic marker blocks a new hotswap"
    exit 3
  fi
}

forensics_begin() {
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  FORENSICS_SCRIPT_SHA256="$(sha256sum "${BASH_SOURCE[0]}" | awk 'NR == 1 { print $1 }')"
  if [[ ! "${FORENSICS_SCRIPT_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
    phase preparing failed "hotswap runner checksum is invalid for forensic lifecycle"
    exit 3
  fi
  if ! forensics_command begin \
    --operation-id "${FORENSICS_OPERATION_ID}" \
    --script-sha256 "${FORENSICS_SCRIPT_SHA256}" \
    --snapshot-sha256 "${actual_checksum}" \
    --drain-receipt-sha256 "${FORENSICS_DRAIN_RECEIPT_SHA256}" \
    --pg-restore-list-sha256 "${RESTORE_LIST_SHA256}" \
    --source-identity-sha256 "$(source_identity_sha256)" \
    --target-identity-sha256 "$(target_identity_sha256)" \
    --acl-topology-sha256 "${ACL_TOPOLOGY_SHA256}" \
    --holder-backend-pid "${LOCK_HOLDER_BACKEND_PID}" \
    --source-schema "${SOURCE_SCHEMA}" \
    --restore-schema "${RESTORE_SCHEMA}" \
    --previous-schema "${PREVIOUS_SCHEMA}" \
    --app-role "${APP_ROLE}" \
    --fence-executor-role "${FENCE_EXECUTOR_ROLE}" \
    --restore-executor-role "${HOTSWAP_EXECUTOR_ROLE}" \
    --source-schema-oid-before "${SOURCE_SCHEMA_OID_BEFORE}" \
    --write-roles "$(write_roles_sql)" >/dev/null; then
    phase preparing failed "forensic lifecycle marker could not be created"
    exit 3
  fi
  FORENSICS_STARTED=1
}

forensics_capture_release_intent_marker_sha256() {
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  # ``status`` is a presentation command and appends one newline.  The receipt
  # is bound to the raw canonical current.json bytes, exactly like the helper's
  # append-only ledger. Command substitution strips only that terminal newline;
  # canonical marker JSON itself contains no line break.
  local marker_raw
  if ! marker_raw="$(forensics_command status)"; then
    phase switching failed "fence-release intent marker could not be read"
    return 1
  fi
  if ! FORENSICS_RELEASE_INTENT_MARKER_SHA256="$(printf '%s' "${marker_raw}" | sha256sum | awk 'NR == 1 { print $1 }')"; then
    phase switching failed "fence-release intent marker could not be hashed"
    return 1
  fi
  if [[ ! "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
    phase switching failed "fence-release intent marker hash is invalid"
    return 1
  fi
}

forensics_transition() {
  local state="$1"
  shift
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  if ! forensics_command transition --operation-id "${FORENSICS_OPERATION_ID}" --state "${state}" "$@"; then
    phase "${ACTIVE_PHASE}" failed "forensic lifecycle transition could not be persisted"
    return 1
  fi
}

forensics_seal_release_receipt() {
  local -a test_seal_arguments=()
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  if [[ "${RELEASE_RECEIPT_REQUIRED}" != "1" ||
    ! "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${RELEASE_RECEIPT_RECORD_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
    phase "${ACTIVE_PHASE}" failed "post-release forensic seal requires a verified release receipt"
    return 1
  fi
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_FORENSICS_RELEASE_ONCE:-0}" == "1" &&
        "${FORENSICS_RELEASE_FAILURE_INJECTED}" == "0" ]]; then
    FORENSICS_RELEASE_FAILURE_INJECTED=1
    phase "${ACTIVE_PHASE}" failed "test-only post-release forensic seal failure injected"
    return 1
  fi
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_FORENSICS_HISTORY_APPEND_ONCE:-0}" == "1" &&
        "${FORENSICS_HISTORY_APPEND_FAILURE_INJECTED}" == "0" ]]; then
    FORENSICS_HISTORY_APPEND_FAILURE_INJECTED=1
    test_seal_arguments+=(--test-fail-history-append-once)
  fi
  if ! forensics_command seal-release-receipt \
    --operation-id "${FORENSICS_OPERATION_ID}" \
    --intent-marker-sha256 "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" \
    --receipt-record-sha256 "${RELEASE_RECEIPT_RECORD_SHA256}" \
    "${test_seal_arguments[@]}"; then
    phase "${ACTIVE_PHASE}" failed "post-release forensic seal could not be persisted"
    return 1
  fi
}

record_forensics_failure() {
  local code="${1:-runner_failure}"
  if [[ "${FORENSICS_ENABLED}" != "1" || "${FORENSICS_STARTED}" != "1" ||
    "${FORENSICS_TERMINAL}" == "1" ]]; then
    return 0
  fi
  if forensics_command failure --operation-id "${FORENSICS_OPERATION_ID}" \
    --phase "${ACTIVE_PHASE}" --code "${code}" >/dev/null; then
    FORENSICS_FAILURE_RECORDED=1
    return 0
  fi
  return 1
}

source_identity_sha256() {
  local identity
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" == "1" ]]; then
    identity="${TRUSTED_SOURCE_DATABASE}|${TRUSTED_SOURCE_DATABASE_OID}|${TRUSTED_SOURCE_SYSTEM_IDENTIFIER}|${TRUSTED_SOURCE_HOSTADDR}|${TRUSTED_SOURCE_PORT}"
  else
    identity="${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME:-}|${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID:-}|${PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER:-}|${PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR:-}|${PINVI_RESTORE_EXPECTED_SOURCE_PORT:-}"
  fi
  printf '%s' "${identity}" | sha256sum | awk 'NR == 1 { print $1 }'
}

target_identity_sha256() {
  printf '%s' "${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}|${PINVI_RESTORE_EXPECTED_DATABASE_OID:-}|${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER:-}|${PINVI_RESTORE_EXPECTED_HOSTADDR:-}|${PINVI_RESTORE_EXPECTED_PORT:-}" \
    | sha256sum | awk 'NR == 1 { print $1 }'
}

assert_restore_schema_absent() {
  local candidate_absent
  candidate_absent="$("${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc \
    "SELECT to_regnamespace('${RESTORE_SCHEMA}') IS NULL" | tr -d '[:space:]')"
  if [[ "${candidate_absent}" != "t" ]]; then
    phase preparing failed "restore candidate schema already exists; preserve it for explicit forensic recovery"
    exit 3
  fi
}

direct_schema_oid() {
  local schema_name="$1"
  local schema_oid
  schema_oid="$("${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc \
    "SELECT COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = '${schema_name}'), '')" | tr -d '[:space:]')"
  if [[ ! "${schema_oid}" =~ ^[0-9]+$ ]]; then
    phase "${ACTIVE_PHASE}" failed "schema oid is unavailable for forensic lifecycle"
    exit 3
  fi
  printf '%s\n' "${schema_oid}"
}

lock_session_scalar() {
  local expression="$1"
  local phase_name="$2"
  local marker value_marker observed value=""
  LOCK_COMMAND_SEQUENCE=$((LOCK_COMMAND_SEQUENCE + 1))
  marker="M05_SQL_DONE|${LOCK_COMMAND_SEQUENCE}"
  value_marker="M05_SCALAR|${LOCK_COMMAND_SEQUENCE}|"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  cat >&"${LOCK_INPUT_FD}" <<SQL
\\set ON_ERROR_STOP off
SELECT '${value_marker}' || (${expression});
\\if :ERROR
ROLLBACK;
SELECT 'M05_SQL_FAILED|${LOCK_COMMAND_SEQUENCE}';
\\else
SELECT '${marker}';
\\endif
\\set ON_ERROR_STOP on
SQL
  while IFS= read -r observed <&"${LOCK_SIGNAL_FD}"; do
    if [[ "${observed}" == "${value_marker}"* ]]; then
      if [[ -n "${value}" ]]; then
        phase "${phase_name}" failed "forensic scalar returned multiple values"
        return 1
      fi
      value="${observed#${value_marker}}"
      continue
    fi
    if [[ "${observed}" == "${marker}" ]]; then
      if [[ -z "${value}" ]]; then
        phase "${phase_name}" failed "forensic scalar returned no value"
        return 1
      fi
      FORENSICS_SCHEMA_OID="${value}"
      return 0
    fi
    if [[ "${observed}" == "M05_SQL_FAILED|${LOCK_COMMAND_SEQUENCE}" ]]; then
      phase "${phase_name}" failed "forensic scalar query failed"
      return 1
    fi
  done
  # The only connection that remains usable after the CONNECT fence is the
  # pre-opened lock holder.  Preserve psql's diagnostic when it disappears so
  # an operator can distinguish a transport loss from a server-side fence or
  # termination decision without attempting any recovery mutation.
  cat -- "${TMP_DIR}/lock.err" >&2 2>/dev/null || true
  phase "${phase_name}" failed "pre-opened hotswap executor session was lost"
  return 1
}

lock_schema_oid() {
  local schema_name="$1"
  lock_session_scalar "SELECT oid::text FROM pg_namespace WHERE nspname = '${schema_name}'" "${ACTIVE_PHASE}"
  if [[ ! "${FORENSICS_SCHEMA_OID}" =~ ^[0-9]+$ ]]; then
    phase "${ACTIVE_PHASE}" failed "schema oid is unavailable for forensic lifecycle"
    exit 3
  fi
}

calculate_acl_topology_sha256() {
  local runner_directory topology_sql topology_sha256
  runner_directory="${BASH_SOURCE[0]%/*}"
  if [[ "${runner_directory}" == "${BASH_SOURCE[0]}" ]]; then
    runner_directory="."
  fi
  runner_directory="$(cd -- "${runner_directory}" && pwd -P)"
  topology_sql="${runner_directory}/m05_hotswap_topology.sql"
  if [[ ! -f "${topology_sql}" || -L "${topology_sql}" ]]; then
    phase "${ACTIVE_PHASE}" failed "trusted ACL topology query is unavailable"
    exit 3
  fi
  if ! topology_sha256="$("${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -Atq --dbname="${DATABASE_URL}" \
    --set="app_role=${APP_ROLE}" --set="fence_role=${FENCE_EXECUTOR_ROLE}" \
    --set="source_schema=${SOURCE_SCHEMA}" --set="previous_schema=${PREVIOUS_SCHEMA}" \
    --set="restore_schema=${RESTORE_SCHEMA}" --file="${topology_sql}" | tr -d '[:space:]')"; then
    phase "${ACTIVE_PHASE}" failed "ACL topology could not be read for forensic lifecycle"
    exit 3
  fi
  if [[ ! "${topology_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
    phase "${ACTIVE_PHASE}" failed "ACL topology is invalid for forensic lifecycle"
    exit 3
  fi
  printf '%s\n' "${topology_sha256}"
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

assert_trusted_snapshot_matches_expected_source() {
  if [[ "${STRICT_RESTORE_ENVIRONMENT}" != "1" ||
    "${PINVI_RESTORE_HOTSWAP_EXECUTE:-0}" != "1" ]]; then
    return 0
  fi
  for variable in PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID \
    PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR \
    PINVI_RESTORE_EXPECTED_SOURCE_PORT; do
    if [[ -z "${!variable:-}" ]]; then
      phase preparing failed "${variable} is required for an executing schema swap"
      exit 3
    fi
  done
  if [[ ! "${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ||
    ! "${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID}" =~ ^[0-9]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER}" =~ ^[0-9]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR}" =~ ^[0-9A-Fa-f:.]+$ ||
    ! "${PINVI_RESTORE_EXPECTED_SOURCE_PORT}" =~ ^[0-9]+$ ]]; then
    phase preparing failed "trusted snapshot expected source identity contains unsafe values"
    exit 3
  fi
  local manifest_identity expected_identity
  manifest_identity="${TRUSTED_SOURCE_DATABASE}|${TRUSTED_SOURCE_DATABASE_OID}|${TRUSTED_SOURCE_SYSTEM_IDENTIFIER}|${TRUSTED_SOURCE_HOSTADDR}|${TRUSTED_SOURCE_PORT}"
  expected_identity="${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME}|${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID}|${PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER}|${PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR}|${PINVI_RESTORE_EXPECTED_SOURCE_PORT}"
  if [[ "${manifest_identity}" != "${expected_identity}" ]]; then
    phase preparing failed "trusted snapshot source identity does not match the expected source"
    exit 3
  fi
  phase preparing success "trusted snapshot source identity bound to expected source"
}

configure_forensics
assert_forensics_inactive
assert_trusted_snapshot_matches_expected_source
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

if [[ "${TEST_MODE}" == "1" ]]; then
  HOTSWAP_EXECUTOR_ROLE="m05_test_executor"
  FENCE_EXECUTOR_ROLE="m05_test_fence"
else
  HOTSWAP_EXECUTOR_ROLE="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" -tAc \
    "SELECT current_user" | tr -d '[:space:]')"
  if [[ ! "${HOTSWAP_EXECUTOR_ROLE}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase preparing failed "restore executor identity is invalid"
    exit 3
  fi
fi

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
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  if [[ "${LOCK_SESSION_FENCED}" == "1" ]]; then
    execute_lock_session_file "${sql_file}" "${phase_name}" "strict"
    return $?
  fi
  # Before the database CONNECT fence, every executable restore statement uses
  # a disposable connection that verifies the holder PID from inside its
  # transaction, so an ordinary SQL error cannot kill the holder.
  if ! "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" \
    --file="${sql_file}"; then
    phase "${phase_name}" failed "schema-swap SQL execution failed"
    return 1
  fi
  assert_advisory_lock_alive
}

execute_guarded_sql_file() {
  local sql_file="$1"
  local phase_name="$2"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  if [[ "${LOCK_SESSION_FENCED}" == "1" ]]; then
    execute_lock_session_file "${sql_file}" "${phase_name}" "strict"
    return $?
  fi
  if ! "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" \
    --file="${sql_file}"; then
    phase "${phase_name}" failed "guarded restore transaction rolled back"
    return 1
  fi
  assert_advisory_lock_alive
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

execute_validation_sql_file() {
  # Before CONNECT is fenced, validation uses a disposable connection.  After
  # fencing the hotswap role, every connection with that credential must be
  # rejected; validation therefore stays on the pre-opened lock session.
  local sql_file="$1"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  if [[ "${LOCK_SESSION_FENCED}" == "1" ]]; then
    execute_lock_session_file "${sql_file}" validating "validation"
    return $?
  fi
  if ! "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" \
    --file="${sql_file}"; then
    phase validating failed "restored schema validation failed"
    return 1
  fi
  assert_advisory_lock_alive
}

execute_lock_session_file() {
  local sql_file="$1"
  local phase_name="$2"
  local lock_sql_file
  local marker
  LOCK_COMMAND_SEQUENCE=$((LOCK_COMMAND_SEQUENCE + 1))
  marker="M05_SQL_DONE|${LOCK_COMMAND_SEQUENCE}"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  lock_sql_file="${TMP_DIR}/lock-session-${LOCK_COMMAND_SEQUENCE}.sql"
  if ! sed '/^[[:space:]]*COMMIT;[[:space:]]*$/d' "${sql_file}" >"${lock_sql_file}"; then
    phase "${phase_name}" failed "schema-swap SQL could not be staged for the lock session"
    return 1
  fi
  cat >&"${LOCK_INPUT_FD}" <<SQL
\\set ON_ERROR_STOP off
\\i ${lock_sql_file}
\\if :ERROR
ROLLBACK;
SELECT 'M05_SQL_FAILED|${LOCK_COMMAND_SEQUENCE}';
\\else
COMMIT;
\\if :ERROR
ROLLBACK;
SELECT 'M05_SQL_FAILED|${LOCK_COMMAND_SEQUENCE}';
\\else
SELECT '${marker}';
\\endif
\\endif
\\set ON_ERROR_STOP on
SQL
  local observed=""
  while IFS= read -r observed <&"${LOCK_SIGNAL_FD}"; do
    if [[ "${observed}" == "${marker}" ]]; then
      assert_advisory_lock_alive
      return $?
    fi
    if [[ "${observed}" == "M05_SQL_FAILED|${LOCK_COMMAND_SEQUENCE}" ]]; then
      cat -- "${TMP_DIR}/lock.err" >&2 2>/dev/null || true
      phase "${phase_name}" failed "schema-swap SQL execution failed"
      return 1
    fi
  done
  phase "${phase_name}" failed "pre-opened hotswap executor session was lost"
  return 1
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
  execute_guarded_sql_file "${wrapper}" restoring
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
  execute_guarded_sql_file "${wrapper}" restoring
}

strip_pg_restore_transaction_wrappers() {
  # pg_restore emits a top-level BEGIN/COMMIT pair for each generated section.
  # The persistent lock session supplies the only transaction boundary, so
  # remove only those generated wrapper lines before the guarded executor sees
  # the archive SQL.  COPY payload lines are kept byte-for-byte.
  awk '
    BEGIN { in_copy = 0 }
    {
      if (in_copy) {
        print
        if ($0 == "\\.") in_copy = 0
        next
      }
      if ($0 ~ /^[[:space:]]*COPY[[:space:]].*;[[:space:]]*$/) {
        print
        in_copy = 1
        next
      }
      normalized = $0
      sub(/^[[:space:]]*/, "", normalized)
      sub(/[[:space:]]*$/, "", normalized)
      if (normalized == "BEGIN;" || normalized == "COMMIT;") next
      print
    }
  '
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
      printf "CREATE SCHEMA %s;\n", target
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

connect_restore_grants_json() {
  # DB receipt 함수가 다시 catalog에서 계산하는 canonical JSONB와 byte-for-byte
  # 같은 shape을 만든다. role/grant spec은 inventory 단계에서 이미 검증했지만,
  # 이 직전 경계도 untrusted shell text를 SQL/JSON으로 승격하지 않게 좁힌다.
  local grant_specs="$1"
  local expected_role="$2"
  local grant_spec role_name grantable
  local first=1
  if [[ ! "${expected_role}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    return 1
  fi
  printf '['
  if [[ -n "${grant_specs}" ]]; then
    IFS=',' read -r -a receipt_grant_specs <<<"${grant_specs}"
    for grant_spec in "${receipt_grant_specs[@]}"; do
      role_name="${grant_spec%%:*}"
      grantable="${grant_spec##*:}"
      if [[ "${grant_spec}" != *:* || "${role_name}" != "${expected_role}" ||
        ( "${grantable}" != "0" && "${grantable}" != "1" ) ]]; then
        return 1
      fi
      if [[ "${first}" == "0" ]]; then
        printf ','
      fi
      if [[ "${grantable}" == "1" ]]; then
        printf '{"grant_option":true,"role":"%s"}' "${role_name}"
      else
        printf '{"grant_option":false,"role":"%s"}' "${role_name}"
      fi
      first=0
    done
  fi
  printf ']'
}

assert_release_receipt_acl() {
  if [[ "${RELEASE_RECEIPT_REQUIRED}" != "1" ]]; then
    return 0
  fi
  # This is a pre-mutation boundary.  A receipt must not be forgeable by
  # PUBLIC/app/hotswap/fence.  The 0101 public ``ops`` schema USAGE is an
  # intentional read-name-resolution policy; table/function capability and
  # every owner must remain outside the three runtime principals.
  local receipt_acl_safe
  if ! receipt_acl_safe="$(${PSQL_BIN} --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${FENCE_DATABASE_URL}" -tAc "
WITH configured AS (
  SELECT '${APP_ROLE}'::name AS app_role,
         '${HOTSWAP_EXECUTOR_ROLE}'::name AS hotswap_role,
         '${FENCE_EXECUTOR_ROLE}'::name AS fence_role
),
database_owner AS (
  SELECT database_row.datdba AS oid
  FROM pg_database database_row
  WHERE database_row.datname = current_database()
),
roles AS (
  SELECT configured.*, app.oid AS app_oid, hotswap.oid AS hotswap_oid,
         fence.oid AS fence_oid
  FROM configured
  JOIN pg_roles app ON app.rolname = configured.app_role
  JOIN pg_roles hotswap ON hotswap.rolname = configured.hotswap_role
  JOIN pg_roles fence ON fence.rolname = configured.fence_role
),
receipt_schema AS (
  SELECT namespace.oid, namespace.nspowner, namespace.nspacl
  FROM pg_namespace namespace
  WHERE namespace.nspname = 'ops'
),
receipt_table AS (
  SELECT relation.oid, relation.relowner, relation.relacl
  FROM pg_class relation
  JOIN receipt_schema schema ON schema.oid = relation.relnamespace
  WHERE relation.relname = 'm05_hotswap_release_receipts'
    AND relation.relkind = 'r'
),
receipt_functions AS (
  SELECT procedure.oid, procedure.proowner, procedure.proacl
  FROM pg_proc procedure
  JOIN receipt_schema schema ON schema.oid = procedure.pronamespace
  WHERE procedure.oid IN (
    'ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name)'::regprocedure,
    'ops.record_m05_hotswap_release_receipt(uuid, text, text, text, text, text, text, text, name, name, name, name, name, name, oid, oid, oid, oid, jsonb, jsonb, boolean, text)'::regprocedure,
    'ops.verify_m05_hotswap_release_receipt(uuid, text)'::regprocedure
  )
)
SELECT
  (SELECT count(*) FROM database_owner) = 1
  AND (SELECT count(*) FROM roles) = 1
  AND (SELECT count(*) FROM receipt_schema) = 1
  AND (SELECT count(*) FROM receipt_table) = 1
  AND (SELECT count(*) FROM receipt_functions) = 3
  AND (SELECT fence_oid FROM roles) = (SELECT oid FROM database_owner)
  AND (SELECT nspowner FROM receipt_schema) NOT IN (
    SELECT app_oid FROM roles UNION SELECT hotswap_oid FROM roles UNION SELECT fence_oid FROM roles
  )
  AND (SELECT relowner FROM receipt_table) NOT IN (
    SELECT app_oid FROM roles UNION SELECT hotswap_oid FROM roles UNION SELECT fence_oid FROM roles
  )
  AND NOT EXISTS (
    SELECT 1
    FROM receipt_functions procedure
    CROSS JOIN roles
    WHERE procedure.proowner IN (roles.app_oid, roles.hotswap_oid, roles.fence_oid)
  )
  AND EXISTS (
    SELECT 1
    FROM receipt_schema schema
    CROSS JOIN LATERAL aclexplode(COALESCE(schema.nspacl, acldefault('n', schema.nspowner))) acl
    WHERE acl.grantee = 0
      AND acl.privilege_type = 'USAGE'
      AND NOT acl.is_grantable
  )
  AND NOT EXISTS (
    SELECT 1
    FROM receipt_schema schema
    CROSS JOIN LATERAL aclexplode(COALESCE(schema.nspacl, acldefault('n', schema.nspowner))) acl
    WHERE NOT (
      acl.grantee = schema.nspowner
      OR (acl.grantee = 0 AND acl.privilege_type = 'USAGE' AND NOT acl.is_grantable)
    )
  )
  AND EXISTS (
    SELECT 1
    FROM receipt_table relation
    CROSS JOIN roles
    CROSS JOIN LATERAL aclexplode(COALESCE(relation.relacl, acldefault('r', relation.relowner))) acl
    WHERE acl.grantee = roles.fence_oid
      AND acl.privilege_type = 'SELECT'
      AND NOT acl.is_grantable
  )
  AND NOT EXISTS (
    SELECT 1
    FROM receipt_table relation
    CROSS JOIN roles
    CROSS JOIN LATERAL aclexplode(COALESCE(relation.relacl, acldefault('r', relation.relowner))) acl
    WHERE NOT (
      acl.grantee = relation.relowner
      OR (acl.grantee = roles.fence_oid AND acl.privilege_type = 'SELECT' AND NOT acl.is_grantable)
    )
  )
  AND (
    SELECT count(*)
    FROM receipt_functions procedure
    CROSS JOIN roles
    CROSS JOIN LATERAL aclexplode(COALESCE(procedure.proacl, acldefault('f', procedure.proowner))) acl
    WHERE acl.grantee = roles.fence_oid
      AND acl.privilege_type = 'EXECUTE'
      AND NOT acl.is_grantable
  ) = 3
  AND NOT EXISTS (
    SELECT 1
    FROM receipt_functions procedure
    CROSS JOIN roles
    CROSS JOIN LATERAL aclexplode(COALESCE(procedure.proacl, acldefault('f', procedure.proowner))) acl
    WHERE NOT (
      acl.grantee = procedure.proowner
      OR (acl.grantee = roles.fence_oid AND acl.privilege_type = 'EXECUTE' AND NOT acl.is_grantable)
    )
  );
" | tr -d '[:space:]')"; then
    phase draining failed "M05 release receipt ACL could not be read"
    exit 3
  fi
  if [[ "${receipt_acl_safe}" != "t" ]]; then
    phase draining failed "M05 release receipt ACL is not canonical"
    exit 3
  fi
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

assert_hotswap_executor_reconnect_fenced() {
  if [[ "${TEST_MODE}" == "1" ]]; then
    return 0
  fi
  local reconnect_error="${TMP_DIR}/hotswap-reconnect-fence.err"
  if "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DATABASE_URL}" \
    -tAc "SELECT 1" >/dev/null 2>"${reconnect_error}"; then
    phase draining failed "hotswap executor retained a connectable second session"
    return 1
  fi
  if [[ "$(database_connect_granted "${FENCE_DATABASE_URL}" "${HOTSWAP_EXECUTOR_ROLE}")" != "f" ]]; then
    phase draining failed "hotswap executor CONNECT privilege was not revoked"
    return 1
  fi
  phase draining success "hotswap executor reconnect is fenced while lock session remains open"
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
        return 1
      fi
    done
  fi
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" &&
    "$(public_connect_granted "${FENCE_DATABASE_URL}")" != "f" ]]; then
    phase draining failed "PUBLIC CONNECT fence was not applied"
    return 1
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
  cat >"${sql_file}" <<SQL
DO \$m05\$
DECLARE
  attempts integer := 0;
  active_count bigint;
BEGIN
  LOOP
    PERFORM pg_terminate_backend(activity.pid)
    FROM pg_stat_activity activity
    WHERE activity.datname = current_database()
      AND activity.pid <> pg_backend_pid()
      AND activity.pid <> ${LOCK_HOLDER_BACKEND_PID};
    SELECT count(*)
      INTO active_count
    FROM pg_stat_activity activity
    WHERE activity.datname = current_database()
      AND activity.pid <> pg_backend_pid()
      AND activity.pid <> ${LOCK_HOLDER_BACKEND_PID}
      AND (activity.xact_start IS NOT NULL OR activity.state <> 'idle');
    EXIT WHEN active_count = 0;
    attempts := attempts + 1;
    IF attempts >= 50 THEN
      RAISE EXCEPTION 'database write fence could not drain active transactions';
    END IF;
    PERFORM pg_sleep(0.1);
  END LOOP;
END
\$m05\$;
SQL
  if ! execute_sql_file "${sql_file}" draining; then
    return 1
  fi
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
  if ! execute_sql_file "${sql_file}" draining; then
    return 1
  fi
}

assert_restored_schema() {
  local sql_file="${TMP_DIR}/restored-schema-check.sql"
  cat >"${sql_file}" <<SQL
DO \$m05\$
DECLARE
  probe_nonce text := md5(
    clock_timestamp()::text || ':' || txid_current()::text || ':' || pg_backend_pid()::text
  );
  probe_sequence bigint;
  delivery_update_event uuid := md5(probe_nonce || ':delivery-update')::uuid;
  delivery_delete_event uuid := md5(probe_nonce || ':delivery-delete')::uuid;
  receipt_update_event uuid := md5(probe_nonce || ':receipt-update')::uuid;
  receipt_delete_event uuid := md5(probe_nonce || ':receipt-delete')::uuid;
  impact_update_event uuid := md5(probe_nonce || ':impact-update')::uuid;
  impact_delete_event uuid := md5(probe_nonce || ':impact-delete')::uuid;
BEGIN
  IF to_regclass('${RESTORE_SCHEMA}.users') IS NULL THEN
    RAISE EXCEPTION 'restored schema is missing users table';
  END IF;
  IF to_regclass('${RESTORE_SCHEMA}.admin_audit_log') IS NULL THEN
    RAISE EXCEPTION 'restored schema is missing admin audit log table';
  END IF;
  IF (
    SELECT count(*)
    FROM (VALUES
      ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only', 63), 31),
      ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_truncate_append_only', 63), 34),
      ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_append_only', 63), 31),
      ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_truncate_append_only', 63), 34),
      ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_append_only', 63), 31),
      ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only', 63), 34)
    ) expected(table_name, trigger_name, trigger_type)
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
        AND t.tgtype = expected.trigger_type
        AND t.tgenabled = 'A'
        AND NOT t.tgisinternal
        AND p.proname = 'guard_ktm_feature_reference_reconciliation_append_only'
        AND pn.nspname = '${RESTORE_SCHEMA}'
        AND NOT p.prosecdef
    )
  ) <> 6 THEN
    RAISE EXCEPTION 'restored schema is missing an ENABLE ALWAYS M05 append-only trigger';
  END IF;
  -- A trigger name/function pair is not a behavioral proof: a malicious or
  -- accidental no-op body can preserve all catalog rows.  Insert valid
  -- disposable rows and prove both row-level UPDATE and DELETE are rejected
  -- per table.  The receipt-to-impact RESTRICT FK makes a standalone receipt
  -- TRUNCATE invalid before any trigger fires, so direct TRUNCATE probes cover
  -- delivery attempts and impacts, while the paired receipt/impact probe
  -- explicitly requires the receipt diagnostic first.  Each exception block
  -- is a subtransaction, so the allowed INSERT is rolled back with the
  -- expected 55000 and cannot leave audit evidence behind.  The receipt table
  -- has a globally unique event_sequence, so start above its real high-water
  -- mark and derive every other probe key/hash from this execution's nonce.
  SELECT COALESCE(max(event_sequence), 0)
  INTO probe_sequence
  FROM ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts;
  IF probe_sequence > 9223372036854775803 THEN
    RAISE EXCEPTION 'M05 append-only probe cannot allocate an event sequence';
  END IF;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_delivery_attempts (
      event_id, attempt_sequence, event_sequence, event_sha256, status,
      block_fingerprint_sha256, observation_root_sha256
    ) VALUES (
      delivery_update_event, 1, probe_sequence + 1,
      md5(probe_nonce || ':delivery-update-event-sha-a') ||
        md5(probe_nonce || ':delivery-update-event-sha-b'),
      'applied', NULL,
      md5(probe_nonce || ':delivery-update-observation-a') ||
        md5(probe_nonce || ':delivery-update-observation-b')
    );
    UPDATE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_delivery_attempts
    SET status = status
    WHERE event_id = delivery_update_event AND attempt_sequence = 1;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_delivery_attempts (
      event_id, attempt_sequence, event_sequence, event_sha256, status,
      block_fingerprint_sha256, observation_root_sha256
    ) VALUES (
      delivery_delete_event, 1, probe_sequence + 2,
      md5(probe_nonce || ':delivery-delete-event-sha-a') ||
        md5(probe_nonce || ':delivery-delete-event-sha-b'),
      'applied', NULL,
      md5(probe_nonce || ':delivery-delete-observation-a') ||
        md5(probe_nonce || ':delivery-delete-observation-b')
    );
    DELETE FROM ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_delivery_attempts
    WHERE event_id = delivery_delete_event AND attempt_sequence = 1;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt DELETE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      receipt_update_event, probe_sequence + 1,
      md5(probe_nonce || ':receipt-update-event-sha-a') ||
        md5(probe_nonce || ':receipt-update-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':receipt-update-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':receipt-update-impact-root-a') ||
        md5(probe_nonce || ':receipt-update-impact-root-b'),
      0,
      md5(probe_nonce || ':receipt-update-receipt-sha-a') ||
        md5(probe_nonce || ':receipt-update-receipt-sha-b')
    );
    UPDATE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts
    SET action = action
    WHERE event_id = receipt_update_event;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected applied-receipt UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      receipt_delete_event, probe_sequence + 2,
      md5(probe_nonce || ':receipt-delete-event-sha-a') ||
        md5(probe_nonce || ':receipt-delete-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':receipt-delete-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':receipt-delete-impact-root-a') ||
        md5(probe_nonce || ':receipt-delete-impact-root-b'),
      0,
      md5(probe_nonce || ':receipt-delete-receipt-sha-a') ||
        md5(probe_nonce || ':receipt-delete-receipt-sha-b')
    );
    DELETE FROM ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts
    WHERE event_id = receipt_delete_event;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected applied-receipt DELETE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      impact_update_event, probe_sequence + 3,
      md5(probe_nonce || ':impact-update-event-sha-a') ||
        md5(probe_nonce || ':impact-update-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-update-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':impact-update-root-a') ||
        md5(probe_nonce || ':impact-update-root-b'),
      1,
      md5(probe_nonce || ':impact-update-receipt-sha-a') ||
        md5(probe_nonce || ':impact-update-receipt-sha-b')
    );
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts (
      event_id, impact_index, target_relation, target_id, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid, outcome
    ) VALUES (
      impact_update_event, 0, 'trip_day_pois',
      md5(probe_nonce || ':impact-update-target')::uuid,
      concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-update-old-feature')::uuid, NULL, NULL, 'detach'
    );
    UPDATE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts
    SET outcome = outcome
    WHERE event_id = impact_update_event AND impact_index = 0;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      impact_delete_event, probe_sequence + 4,
      md5(probe_nonce || ':impact-delete-event-sha-a') ||
        md5(probe_nonce || ':impact-delete-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-delete-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':impact-delete-root-a') ||
        md5(probe_nonce || ':impact-delete-root-b'),
      1,
      md5(probe_nonce || ':impact-delete-receipt-sha-a') ||
        md5(probe_nonce || ':impact-delete-receipt-sha-b')
    );
    INSERT INTO ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts (
      event_id, impact_index, target_relation, target_id, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid, outcome
    ) VALUES (
      impact_delete_event, 0, 'trip_day_pois',
      md5(probe_nonce || ':impact-delete-target')::uuid,
      concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-delete-old-feature')::uuid, NULL, NULL, 'detach'
    );
    DELETE FROM ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts
    WHERE event_id = impact_delete_event AND impact_index = 0;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact DELETE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_delivery_attempts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_delivery_attempts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt TRUNCATE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_impacts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact TRUNCATE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_applied_receipts,
      ${RESTORE_SCHEMA}.ktm_feature_reference_reconciliation_impacts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_applied_receipts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger did not reject the receipt TRUNCATE first';
      END IF;
  END;
END
\$m05\$;
SQL
  if ! execute_validation_sql_file "${sql_file}"; then
    if [[ "${CLEANUP_MODE}" == "1" ]]; then
      return 1
    fi
    exit 3
  fi
}

assert_admin_audit_contract() {
  local sql_file="${TMP_DIR}/admin-audit-contract-check.sql"
  cat >"${sql_file}" <<SQL
CREATE OR REPLACE FUNCTION pg_temp.m05_canonical_jsonb(value jsonb)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS \$m05json\$
DECLARE
  result text;
BEGIN
  IF value IS NULL OR jsonb_typeof(value) = 'null' THEN
    RETURN 'null';
  ELSIF jsonb_typeof(value) = 'object' THEN
    SELECT COALESCE(
      '{' || string_agg(
        to_json(object_value.key)::text || ':' ||
          pg_temp.m05_canonical_jsonb(object_value.value),
        ',' ORDER BY object_value.key
      ) || '}',
      '{}'
    )
    INTO result
    FROM jsonb_each(value) AS object_value(key, value);
    RETURN result;
  ELSIF jsonb_typeof(value) = 'array' THEN
    SELECT COALESCE(
      '[' || string_agg(pg_temp.m05_canonical_jsonb(array_value.value), ',' ORDER BY array_value.ordinality) || ']',
      '[]'
    )
    INTO result
    FROM jsonb_array_elements(value) WITH ORDINALITY AS array_value(value, ordinality);
    RETURN result;
  ELSIF jsonb_typeof(value) = 'string' THEN
    RETURN to_json(value #>> '{}')::text;
  END IF;
  RETURN value::text;
END;
\$m05json\$;

DO \$m05\$
DECLARE
  audit_row_ctid tid;
BEGIN
  IF to_regclass('${RESTORE_SCHEMA}.admin_audit_log') IS NULL THEN
    RAISE EXCEPTION 'restored schema is missing admin audit log table';
  END IF;
  IF (
    SELECT count(*)
    FROM (VALUES
      ('log_id', 'bigint', true),
      ('actor_user_id', 'uuid', true),
      ('action', 'character varying(64)', true),
      ('resource_type', 'character varying(64)', true),
      ('resource_id', 'character varying(128)', false),
      ('before_state', 'jsonb', false),
      ('after_state', 'jsonb', false),
      ('access_reason', 'text', false),
      ('target_pii_fields', 'character varying(64)[]', false),
      ('ip_hash', 'character varying(64)', true),
      ('user_agent', 'character varying(512)', false),
      ('request_id', 'uuid', true),
      ('prev_hash', 'character varying(64)', true),
      ('content_hash', 'character varying(64)', true),
      ('occurred_at', 'timestamp with time zone', true)
    ) expected(column_name, type_name, not_null)
    WHERE EXISTS (
      SELECT 1
      FROM pg_attribute attribute
      JOIN pg_class relation ON relation.oid = attribute.attrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
      WHERE namespace.nspname = '${RESTORE_SCHEMA}'
        AND relation.relname = 'admin_audit_log'
        AND attribute.attname = expected.column_name
        AND NOT attribute.attisdropped
        AND attribute.attnotnull = expected.not_null
        AND format_type(attribute.atttypid, attribute.atttypmod) = expected.type_name
    )
  ) <> 15 THEN
    RAISE EXCEPTION 'restored admin audit log does not satisfy the runtime column contract';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
      AND constraint_row.contype = 'p'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
           AND attribute.attname = 'log_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  ) THEN
    RAISE EXCEPTION 'restored admin audit log is missing the log_id primary key';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
      AND constraint_row.contype = 'u'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
           AND attribute.attname = 'prev_hash'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  ) THEN
    RAISE EXCEPTION 'restored admin audit log is missing the prev_hash unique chain guard';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_attrdef default_value
    WHERE default_value.adrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
      AND default_value.adnum = (
        SELECT attribute.attnum
        FROM pg_attribute attribute
        WHERE attribute.attrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
          AND attribute.attname = 'log_id'
          AND NOT attribute.attisdropped
      )
      AND pg_get_expr(default_value.adbin, default_value.adrelid) LIKE 'nextval(%'
  ) THEN
    RAISE EXCEPTION 'restored admin audit log cannot allocate log_id for reflection';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
      AND constraint_row.contype = 'f'
      AND constraint_row.confrelid = '${RESTORE_SCHEMA}.users'::regclass
      AND constraint_row.confdeltype = 'r'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '${RESTORE_SCHEMA}.admin_audit_log'::regclass
           AND attribute.attname = 'actor_user_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
      AND constraint_row.confkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '${RESTORE_SCHEMA}.users'::regclass
           AND attribute.attname = 'user_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  ) THEN
    RAISE EXCEPTION 'restored admin audit log is missing the actor user foreign key';
  END IF;
  IF (
    SELECT count(*)
    FROM (VALUES
      ('trg_admin_audit_log_append_only', 31),
      ('trg_admin_audit_log_truncate_append_only', 34)
    ) expected(trigger_name, trigger_type)
    WHERE EXISTS (
      SELECT 1
      FROM pg_trigger trigger
      JOIN pg_class relation ON relation.oid = trigger.tgrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid = trigger.tgfoid
      JOIN pg_namespace procedure_namespace ON procedure_namespace.oid = procedure.pronamespace
      WHERE namespace.nspname = '${RESTORE_SCHEMA}'
        AND relation.relname = 'admin_audit_log'
        AND trigger.tgname = expected.trigger_name
        AND trigger.tgtype = expected.trigger_type
        AND trigger.tgenabled = 'A'
        AND NOT trigger.tgisinternal
        AND procedure.proname = 'guard_admin_audit_log_append_only'
        AND procedure_namespace.nspname = '${RESTORE_SCHEMA}'
        AND NOT procedure.prosecdef
        AND procedure.proconfig = ARRAY['search_path=pg_catalog']
        AND regexp_replace(btrim(procedure.prosrc), '[[:space:]]+', ' ', 'g') =
          'BEGIN IF TG_OP = ''INSERT'' THEN RETURN NEW; END IF; RAISE EXCEPTION ''% is append-only'', TG_TABLE_SCHEMA || ''.'' || TG_TABLE_NAME USING ERRCODE = ''55000''; END;'
    )
  ) <> 2 THEN
    RAISE EXCEPTION 'restored admin audit log is missing a canonical ENABLE ALWAYS append-only guard';
  END IF;
  IF EXISTS (
    WITH ordered AS (
      SELECT log_id, prev_hash, content_hash, actor_user_id, action,
             resource_type, resource_id, before_state, after_state,
             access_reason, target_pii_fields, ip_hash, user_agent,
             request_id, occurred_at,
             lag(content_hash) OVER (ORDER BY log_id) AS previous_content_hash
      FROM ${RESTORE_SCHEMA}.admin_audit_log
    ),
    hashed AS (
      SELECT ordered.*,
             encode(
               x_extension.digest(
                 convert_to(
                   prev_hash || pg_temp.m05_canonical_jsonb(
                     jsonb_build_object(
                       'actor_user_id', actor_user_id::text,
                       'action', action,
                       'resource_type', resource_type,
                       'resource_id', resource_id,
                       'before_state', before_state,
                       'after_state', after_state,
                       'access_reason', access_reason,
                       'target_pii_fields', to_jsonb(target_pii_fields),
                       'ip_hash', ip_hash,
                       'user_agent', user_agent,
                       'request_id', request_id::text,
                       'occurred_at', occurred_at
                     )
                   )::text,
                   'UTF8'
                 ),
                 'sha256'
               ),
               'hex'
             ) AS expected_content_hash
      FROM ordered
    )
    SELECT 1
    FROM hashed
    WHERE prev_hash !~ '^[0-9a-f]{64}$'
       OR content_hash !~ '^[0-9a-f]{64}$'
       OR prev_hash <> COALESCE(previous_content_hash, repeat('0', 64))
       OR content_hash <> expected_content_hash
  ) THEN
    RAISE EXCEPTION 'restored admin audit hash chain or content hash is invalid';
  END IF;
  BEGIN
    TRUNCATE TABLE ${RESTORE_SCHEMA}.admin_audit_log;
    RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed TRUNCATE';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%${RESTORE_SCHEMA}.admin_audit_log is append-only%' THEN
        RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected TRUNCATE diagnostic';
      END IF;
  END;
  SELECT ctid
    INTO audit_row_ctid
  FROM ${RESTORE_SCHEMA}.admin_audit_log
  ORDER BY log_id
  LIMIT 1;
  IF audit_row_ctid IS NOT NULL THEN
    BEGIN
      UPDATE ${RESTORE_SCHEMA}.admin_audit_log
      SET action = 'm05-audit-guard-probe'
      WHERE ctid = audit_row_ctid;
      RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed UPDATE';
    EXCEPTION
      WHEN SQLSTATE '55000' THEN
        IF SQLERRM NOT ILIKE '%${RESTORE_SCHEMA}.admin_audit_log is append-only%' THEN
          RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected UPDATE diagnostic';
        END IF;
    END;
    BEGIN
      DELETE FROM ${RESTORE_SCHEMA}.admin_audit_log
      WHERE ctid = audit_row_ctid;
      RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed DELETE';
    EXCEPTION
      WHEN SQLSTATE '55000' THEN
        IF SQLERRM NOT ILIKE '%${RESTORE_SCHEMA}.admin_audit_log is append-only%' THEN
          RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected DELETE diagnostic';
        END IF;
    END;
  END IF;
END
\$m05\$;
SQL
  if ! execute_validation_sql_file "${sql_file}"; then
    if [[ "${CLEANUP_MODE}" == "1" ]]; then
      return 1
    fi
    exit 3
  fi
}

assert_cache_target_boundary_contract() {
  local sql_file="${TMP_DIR}/cache-target-boundary-contract-check.sql"
  cat >"${sql_file}" <<SQL
DO \$m05\$
BEGIN
  IF to_regclass('${RESTORE_SCHEMA}.ktm_cache_target_boundary_audits') IS NULL THEN
    RAISE EXCEPTION 'restored schema is missing the M05 final-boundary audit table';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '${RESTORE_SCHEMA}.ktm_cache_target_boundary_audits'::regclass
      AND constraint_row.conname = 'ck_ktm_ct_boundary_contract'
      AND pg_get_constraintdef(constraint_row.oid) LIKE '%contract_version = ''pinvi-cache-target-final-boundary/v1''%'
      AND pg_get_constraintdef(constraint_row.oid) LIKE '%status = ''succeeded''%'
      AND pg_get_constraintdef(constraint_row.oid) LIKE '%schema_revision = ''20260824_0101''%'
  ) THEN
    RAISE EXCEPTION 'restored schema is not bound to the 20260824_0101 final-boundary contract';
  END IF;
END
\$m05\$;
SQL
  if ! execute_validation_sql_file "${sql_file}"; then
    if [[ "${CLEANUP_MODE}" == "1" ]]; then
      return 1
    fi
    exit 3
  fi
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
    AND has_function_privilege(
      current_user,
      'x_extension.digest(bytea,text)'::regprocedure,
      'EXECUTE'
    )
    AND EXISTS (
      SELECT 1
      FROM pg_proc procedure
      JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
      CROSS JOIN LATERAL aclexplode(
        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
      ) acl
      WHERE procedure.oid = 'x_extension.digest(bytea,text)'::regprocedure
        AND namespace.nspname = 'x_extension'
        AND acl.grantee = r.oid
        AND acl.privilege_type = 'EXECUTE'
        AND NOT acl.is_grantable
    )
    AND NOT EXISTS (
      SELECT 1
      FROM pg_proc procedure
      JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
      CROSS JOIN LATERAL aclexplode(
        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
      ) acl
      WHERE procedure.oid = 'x_extension.digest(bytea,text)'::regprocedure
        AND namespace.nspname = 'x_extension'
        AND acl.grantee = 0
        AND acl.privilege_type = 'EXECUTE'
    )
    AND EXISTS (
      SELECT 1
      FROM pg_auth_members m
      WHERE m.member = r.oid
        AND m.roleid = to_regrole('pg_signal_backend')
        AND NOT m.admin_option
        AND m.inherit_option
        AND m.set_option
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
    phase draining failed "restore executor requires direct digest execution and only non-admin pg_signal_backend membership"
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
    AND NOT owner_role.rolinherit
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
    phase draining failed "schema-swap requires exactly one canonical runtime writer role (observed: ${writer_logins})"
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
  AND NOT has_database_privilege(
    (SELECT oid FROM app_role),
    current_database(),
    'CREATE'
  )
  AND NOT has_schema_privilege(
    (SELECT oid FROM app_role),
    'public',
    'CREATE'
  )
  AND NOT EXISTS (
    SELECT 1 FROM source_schema s WHERE s.nspowner <> current_user::regrole
  )
  AND EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN source_schema s ON s.oid = c.relnamespace
    WHERE c.relname = 'admin_audit_log'
      AND c.relkind IN ('r', 'p')
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
  -- The restored app role must not retain an executable SECURITY DEFINER
  -- escape hatch outside the swap schema.  It can otherwise mutate the app schema
  -- through a function owned by the hotswap role even after direct DML has
  -- been fenced.  System functions are intentionally excluded; every other
  -- schema is part of the live authority surface.
  AND NOT EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.prosecdef
      AND n.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema')
      AND n.nspname <> '${SOURCE_SCHEMA}'
      AND has_function_privilege((SELECT oid FROM app_role), p.oid, 'EXECUTE')
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

prepare_write_fence_inventory() {
  local writer_logins app_connect_roles
  assert_advisory_lock_alive
  if [[ "${TEST_MODE}" == "1" ]]; then
    FENCED_CONNECT_ROLES="${APP_ROLE},${HOTSWAP_EXECUTOR_ROLE}"
    APP_CONNECT_RESTORE_GRANTS=""
    RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS=""
    CONNECT_RESTORE_GRANTS=""
    PUBLIC_CONNECT_REVOKED=0
    SOURCE_SCHEMA_OID_BEFORE="$(direct_schema_oid "${SOURCE_SCHEMA}")"
    ACL_TOPOLOGY_SHA256="$(calculate_acl_topology_sha256)"
    return 0
  fi
  assert_restore_executor_safe
  assert_fence_target_identity
  assert_fence_executor_safe
  assert_release_receipt_acl
  assert_configured_roles_safe
  assert_supported_acl_topology
  writer_logins="$(writer_login_roles)"
  assert_role_list_safe "${writer_logins}" "database writer inventory"
  assert_writer_fence_capable "${writer_logins}"
  app_connect_roles="$(writer_connect_roles "${writer_logins}")"
  assert_role_list_safe "${app_connect_roles}" "database connection fence inventory"
  if [[ "${writer_logins}" != "${APP_ROLE}" || "${app_connect_roles}" != "${APP_ROLE}" ]]; then
    phase draining failed "database write fence requires exactly the canonical app connection role"
    exit 3
  fi
  if [[ "${HOTSWAP_EXECUTOR_ROLE}" == "${APP_ROLE}" ]]; then
    phase draining failed "hotswap executor was already present in the runtime writer inventory"
    exit 3
  fi
  FENCED_CONNECT_ROLES="${APP_ROLE},${HOTSWAP_EXECUTOR_ROLE}"
  assert_role_list_safe "${FENCED_CONNECT_ROLES}" "database connection fence inventory"
  APP_CONNECT_RESTORE_GRANTS="$(connect_restore_grants "${APP_ROLE}")"
  RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS="$(connect_restore_grants "${HOTSWAP_EXECUTOR_ROLE}")"
  if [[ -n "${APP_CONNECT_RESTORE_GRANTS}" && -n "${RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS}" ]]; then
    CONNECT_RESTORE_GRANTS="${APP_CONNECT_RESTORE_GRANTS},${RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS}"
  elif [[ -n "${APP_CONNECT_RESTORE_GRANTS}" ]]; then
    CONNECT_RESTORE_GRANTS="${APP_CONNECT_RESTORE_GRANTS}"
  else
    CONNECT_RESTORE_GRANTS="${RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS}"
  fi
  PUBLIC_CONNECT_REVOKED=0
  if [[ "$(public_connect_granted "${FENCE_DATABASE_URL}")" == "t" ]]; then
    PUBLIC_CONNECT_REVOKED=1
  fi
  SOURCE_SCHEMA_OID_BEFORE="$(direct_schema_oid "${SOURCE_SCHEMA}")"
  ACL_TOPOLOGY_SHA256="$(calculate_acl_topology_sha256)"
}

enter_write_fence() {
  local roles_sql reference_sql_failure=""
  roles_sql="$(write_roles_sql)"
  if ! assert_advisory_lock_alive; then
    return 1
  fi
  if [[ "${TEST_MODE}" == "1" ]]; then
    phase draining success "test-mode write fence simulated"
    return 0
  fi
  if [[ -z "${FENCED_CONNECT_ROLES}" || -z "${SOURCE_SCHEMA_OID_BEFORE}" ||
    -z "${ACL_TOPOLOGY_SHA256}" ]]; then
    phase draining failed "database write fence inventory was not prepared"
    return 1
  fi
  WRITE_FENCE_ACTIVE=1
  local fence_sql="${TMP_DIR}/enter-fence.sql"
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_REFENCE_SQL_ONCE:-0}" == "1" &&
        "${RELEASE_WINDOW_MAY_HAVE_OPENED}" == "1" &&
        "${RELEASE_WRITE_FENCE_COMPLETED}" == "1" &&
        "${REFENCE_SQL_FAILURE_INJECTED}" == "0" ]]; then
    REFENCE_SQL_FAILURE_INJECTED=1
    reference_sql_failure="SELECT m05_missing_reference_sql_probe();"
  fi
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
${reference_sql_failure}
  COMMIT;
SQL
  if ! execute_sql_file "${fence_sql}" draining; then
    return 1
  fi
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
  if ! execute_fence_sql_file "${database_fence_sql}" draining; then
    return 1
  fi
  if ! assert_database_fence_applied; then
    return 1
  fi
  if ! assert_hotswap_executor_reconnect_fenced; then
    return 1
  fi
  LOCK_SESSION_FENCED=1
  if ! wait_for_database_quiescence; then
    return 1
  fi
  if ! assert_no_connectable_writer_roles; then
    return 1
  fi
  phase draining success "database write fence revoked all non-owner runtime writes"
}

release_receipt_sql() {
  if [[ "${RELEASE_RECEIPT_REQUIRED}" != "1" ]]; then
    return 0
  fi
  local app_grants_json restore_executor_grants_json public_connect
  local source_identity target_identity
  if ! app_grants_json="$(connect_restore_grants_json "${APP_CONNECT_RESTORE_GRANTS}" "${APP_ROLE}")" ||
    ! restore_executor_grants_json="$(connect_restore_grants_json "${RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS}" "${HOTSWAP_EXECUTOR_ROLE}")"; then
    phase switching failed "release receipt CONNECT grant encoding is invalid"
    return 1
  fi
  if [[ "${PUBLIC_CONNECT_REVOKED}" == "1" ]]; then
    public_connect=true
  else
    public_connect=false
  fi
  source_identity="$(source_identity_sha256)"
  target_identity="$(target_identity_sha256)"
  if [[ ! "${FORENSICS_OPERATION_ID}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ||
    ! "${FORENSICS_RELEASE_INTENT_MARKER_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${FORENSICS_SCRIPT_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${actual_checksum}" =~ ^[0-9a-f]{64}$ ||
    ! "${FORENSICS_DRAIN_RECEIPT_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${RESTORE_LIST_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${source_identity}" =~ ^[0-9a-f]{64}$ ||
    ! "${target_identity}" =~ ^[0-9a-f]{64}$ ||
    ! "${ACL_TOPOLOGY_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${SOURCE_SCHEMA_OID_BEFORE}" =~ ^[0-9]+$ ||
    ! "${RESTORE_SCHEMA_OID}" =~ ^[0-9]+$ ||
    ! "${APP_SCHEMA_OID_AFTER_SWITCH}" =~ ^[0-9]+$ ||
    ! "${PREVIOUS_SCHEMA_OID_AFTER_SWITCH}" =~ ^[0-9]+$ ]]; then
    phase switching failed "release receipt inputs are incomplete"
    return 1
  fi
  cat <<SQL
SELECT ops.record_m05_hotswap_release_receipt(
  '${FORENSICS_OPERATION_ID}'::uuid,
  '${FORENSICS_RELEASE_INTENT_MARKER_SHA256}',
  '${FORENSICS_SCRIPT_SHA256}',
  '${actual_checksum}',
  '${FORENSICS_DRAIN_RECEIPT_SHA256}',
  '${RESTORE_LIST_SHA256}',
  '${target_identity}',
  '${source_identity}',
  '${SOURCE_SCHEMA}'::name,
  '${RESTORE_SCHEMA}'::name,
  '${PREVIOUS_SCHEMA}'::name,
  '${APP_ROLE}'::name,
  '${FENCE_EXECUTOR_ROLE}'::name,
  '${HOTSWAP_EXECUTOR_ROLE}'::name,
  ${SOURCE_SCHEMA_OID_BEFORE}::oid,
  ${RESTORE_SCHEMA_OID}::oid,
  ${APP_SCHEMA_OID_AFTER_SWITCH}::oid,
  ${PREVIOUS_SCHEMA_OID_AFTER_SWITCH}::oid,
  '${app_grants_json}'::jsonb,
  '${restore_executor_grants_json}'::jsonb,
  ${public_connect},
  '${ACL_TOPOLOGY_SHA256}'
);
SQL
}

read_release_receipt_after_commit() {
  if [[ "${RELEASE_RECEIPT_REQUIRED}" != "1" ]]; then
    return 0
  fi
  local receipt_values
  if ! receipt_values="$(PGOPTIONS='-c default_transaction_read_only=on' "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -Atq \
    --dbname="${FENCE_DATABASE_URL}" -c "
SELECT receipt.record_sha256 || '|' || receipt.post_release_acl_topology_sha256 || '|' ||
  CASE WHEN ops.verify_m05_hotswap_release_receipt(
    receipt.operation_id, receipt.marker_sha256
  ) THEN 't' ELSE 'f' END
FROM ops.m05_hotswap_release_receipts receipt
WHERE receipt.operation_id = '${FORENSICS_OPERATION_ID}'::uuid
  AND receipt.marker_sha256 = '${FORENSICS_RELEASE_INTENT_MARKER_SHA256}';
" | tr -d '[:space:]')"; then
    phase switching failed "release receipt could not be read after CONNECT release"
    return 1
  fi
  IFS='|' read -r RELEASE_RECEIPT_RECORD_SHA256 RELEASE_RECEIPT_TOPOLOGY_SHA256 receipt_record_valid <<<"${receipt_values}"
  if [[ ! "${RELEASE_RECEIPT_RECORD_SHA256}" =~ ^[0-9a-f]{64}$ ||
    ! "${RELEASE_RECEIPT_TOPOLOGY_SHA256}" =~ ^[0-9a-f]{64}$ ||
    "${receipt_record_valid:-}" != "t" ]]; then
    phase switching failed "release receipt is missing or invalid after CONNECT release"
    return 1
  fi
}

release_write_fence() {
  local roles_sql release_sql_failure=""
  roles_sql="$(write_roles_sql)"
  local fence_sql="${TMP_DIR}/release-fence.sql"
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_RELEASE_ONCE:-0}" == "1" &&
        "${RELEASE_FAILURE_INJECTED}" == "0" ]]; then
    RELEASE_FAILURE_INJECTED=1
    return 1
  fi
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_RELEASE_SQL_ONCE:-0}" == "1" &&
        "${RELEASE_SQL_FAILURE_INJECTED}" == "0" ]]; then
    RELEASE_SQL_FAILURE_INJECTED=1
    release_sql_failure="SELECT m05_missing_release_sql_probe();"
  fi
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
${release_sql_failure}
COMMIT;
SQL
  if ! execute_sql_file "${fence_sql}" draining; then
    return 1
  fi
  local database_fence_sql="${TMP_DIR}/release-database-fence.sql"
  local database_release_sql_failure="" receipt_sql=""
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_RELEASE_DATABASE_SQL_ONCE:-0}" == "1" &&
        "${RELEASE_DATABASE_SQL_FAILURE_INJECTED}" == "0" ]]; then
    RELEASE_DATABASE_SQL_FAILURE_INJECTED=1
    database_release_sql_failure="SELECT m05_missing_release_database_sql_probe();"
  fi
  if ! receipt_sql="$(release_receipt_sql)"; then
    return 1
  fi
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
${database_release_sql_failure}
${receipt_sql}
COMMIT;
SQL
  if ! execute_fence_sql_file "${database_fence_sql}" draining; then
    return 1
  fi
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_COMMIT_ONCE:-0}" == "1" &&
        "${RELEASE_RECEIPT_REQUIRED}" == "1" ]]; then
    # Deliberately bypass EXIT cleanup at the only irreducible cross-store
    # boundary: the DB transaction is durable, but the filesystem seal has not
    # been attempted. Normal recovery must refuse this unsealed marker; only a
    # fresh, explicit root read-only escalation can certify it.
    kill -KILL "$$"
  fi
  if ! read_release_receipt_after_commit; then
    return 1
  fi
  if ! assert_database_fence_restored; then
    return 1
  fi
  assert_supported_acl_topology
}

persist_post_release_forensics() {
  if [[ "${FORENSICS_ENABLED}" != "1" ]]; then
    return 0
  fi
  # release_write_fence() has already committed the receipt and independently
  # proved the receipt hash, the restored database fence, and the canonical ACL
  # topology.  This is intentionally an append-only seal, not another current
  # marker state: a write/fsync ambiguity cannot make a newer marker unarchiveable.
  forensics_seal_release_receipt
}

reapply_write_fence_after_post_release_forensic_failure() {
  local failure_phase="${ACTIVE_PHASE}"
  phase draining running "reapplying writer fence after post-release forensic persistence failure"
  if ! enter_write_fence; then
    ACTIVE_PHASE="${failure_phase}"
    return 1
  fi
  ACTIVE_PHASE="${failure_phase}"
  phase switching failed "post-release forensic persistence failed after writers were released; writer fence was reapplied"
}

phase draining running "write fence"
assert_restore_schema_absent
prepare_write_fence_inventory
forensics_begin
forensics_transition fence_intent \
  --acl-topology-sha256 "${ACL_TOPOLOGY_SHA256}" \
  --connect-restore-grants "${APP_CONNECT_RESTORE_GRANTS}" \
  --restore-executor-connect-restore-grants "${RESTORE_EXECUTOR_CONNECT_RESTORE_GRANTS}" \
  --fenced-connect-roles "${APP_ROLE}" \
  --public-connect-was-granted "${PUBLIC_CONNECT_REVOKED}" \
  --source-schema-oid-before "${SOURCE_SCHEMA_OID_BEFORE}" \
  --write-roles "$(write_roles_sql)"
enter_write_fence
forensics_transition fence_applied

phase restoring running "restoring ${SOURCE_SCHEMA} into ${RESTORE_SCHEMA}"
# The snapshot was intentionally produced with ``--schema`` and therefore
# does not carry a CREATE SCHEMA statement.  The pre-fence collision check
# established that this exact candidate name is absent; create it once under
# the fenced lock without an IF NOT EXISTS/DROP escape hatch.  Any later
# failure leaves this candidate and the forensic marker for explicit recovery.
run_guarded_command "CREATE SCHEMA ${RESTORE_SCHEMA}"
restore_archive_section() {
  local section="$1"
  local label="$2"
  local archive_sql="${TMP_DIR}/${label}.sql"
  local remapped_sql="${TMP_DIR}/${label}-remapped.sql"
  "${PG_RESTORE_BIN}" \
    --schema="${SOURCE_SCHEMA}" \
    --section="${section}" \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --file="${archive_sql}" \
    "${SNAPSHOT}"
  remap_sql "${archive_sql}" | strip_pg_restore_transaction_wrappers >"${remapped_sql}"
  run_guarded_file "${remapped_sql}"
  if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
        "${PINVI_RESTORE_TEST_FAIL_RESTORE_ONCE:-0}" == "1" &&
        "${RESTORE_FAILURE_INJECTED}" == "0" ]]; then
    RESTORE_FAILURE_INJECTED=1
    phase restoring failed "test-only restore failure injected after candidate mutation"
    exit 3
  fi
}

# Keep foreign keys and post-data triggers out of the data load.  The archive is
# trusted and the database writer fence is active; post-data then installs the
# canonical constraints/append-only triggers before behavioral validation.
restore_archive_section pre-data pre-data
restore_archive_section data data
restore_archive_section post-data post-data
phase restoring success "restored into ${RESTORE_SCHEMA}"
lock_schema_oid "${RESTORE_SCHEMA}"
restored_schema_oid="${FORENSICS_SCHEMA_OID}"
RESTORE_SCHEMA_OID="${restored_schema_oid}"

phase validating running "validating restored schema"
assert_cache_target_boundary_contract
assert_admin_audit_contract
assert_restored_schema
phase validating success "restored schema passed basic checks"
forensics_transition restore_ready --restore-schema-oid "${restored_schema_oid}"

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
if ! run_guarded_file "${TMP_DIR}/switch.sql"; then
  exit 3
fi
lock_schema_oid "${SOURCE_SCHEMA}"
switched_app_schema_oid="${FORENSICS_SCHEMA_OID}"
APP_SCHEMA_OID_AFTER_SWITCH="${switched_app_schema_oid}"
lock_schema_oid "${PREVIOUS_SCHEMA}"
switched_previous_schema_oid="${FORENSICS_SCHEMA_OID}"
PREVIOUS_SCHEMA_OID_AFTER_SWITCH="${switched_previous_schema_oid}"
forensics_transition switched \
  --app-schema-oid-after-switch "${switched_app_schema_oid}" \
  --previous-schema-oid-after-switch "${switched_previous_schema_oid}"
forensics_transition fence_release_intent --terminal-schema-mode switched
if ! forensics_capture_release_intent_marker_sha256; then
  exit 3
fi
RELEASE_WINDOW_MAY_HAVE_OPENED=1
if ! release_write_fence; then
  phase switching failed "schema-swap release failed; restored schema and writer fence remain for explicit root recovery"
  exit 3
fi
if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
      "${PINVI_RESTORE_TEST_FAIL_RELEASE_WINDOW_ONCE:-0}" == "1" ]]; then
  phase switching failed "test-only release-window interruption injected before forensic completion"
  exit 3
fi
RELEASE_WRITE_FENCE_COMPLETED=1
if ! persist_post_release_forensics; then
  phase switching failed "post-release forensic persistence failed after writers were released; cleanup will reapply the writer fence"
  exit 3
fi
if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
      "${PINVI_RESTORE_TEST_FAIL_AFTER_RELEASE_RECEIPT_SEAL_ONCE:-0}" == "1" &&
      "${RELEASE_RECEIPT_REQUIRED}" == "1" ]]; then
  # Catchable failure exercises EXIT cleanup's strict seal re-read. It must
  # retain current.json for root acknowledgement without re-fencing a release
  # that is already cryptographically bound to the same receipt.
  phase switching failed "test-only failure injected after release receipt seal"
  exit 3
fi
if [[ "${PINVI_ENVIRONMENT:-}" == "test" &&
      "${PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_SEAL_ONCE:-0}" == "1" &&
      "${RELEASE_RECEIPT_REQUIRED}" == "1" ]]; then
  # This seam is deliberately after the immutable seal and before any shell
  # completion flag. The next root recovery must re-run its DB proof before it
  # can archive the still-active marker.
  kill -KILL "$$"
fi
RELEASE_TERMINAL_SEALED=1
FORENSICS_TERMINAL=1
WRITE_FENCE_ACTIVE=0
phase switching success "schema-swap completed"
