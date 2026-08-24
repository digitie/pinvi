#!/usr/bin/env bash
# Sprint 5 staging restore drill for Pinvi app-schema backups.

set -euo pipefail

unset PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PSQLRC

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA="${PINVI_RESTORE_DRILL_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
JOBS="${PINVI_RESTORE_DRILL_JOBS:-${PINVI_RESTORE_JOBS:-2}}"
ROLLBACK_REHEARSAL="${PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL:-precheck}"
SNAPSHOT="${2:-}"
TRUSTED_SNAPSHOT="${SNAPSHOT}"
TMP_DIR=""

phase() {
  local name="$1"
  local status="$2"
  local message="${3:-}"
  printf 'DRILL_PHASE=%s:%s:%s\n' "${name}" "${status}" "${message}"
}

evidence() {
  local key="$1"
  local value="$2"
  printf 'DRILL_EVIDENCE=%s=%s\n' "${key}" "${value}"
}

mask_snapshot() {
  local path="$1"
  printf 'backup://%s' "$(basename "${path}")"
}

usage() {
  cat >&2 <<'EOF'
Usage: scripts/restore-staging-drill.sh run /path/to/snapshot.dump

Required:
  PINVI_RESTORE_STAGING_DATABASE_URL   staging DB URL. The script refuses to use
                                      PINVI_DATABASE_URL unless explicitly allowed.

Optional:
  PINVI_RESTORE_HOTSWAP_DATABASE_URL   dedicated schema-owner URL for restore/hotswap;
                                      defaults to the staging URL.
  PINVI_RESTORE_FENCE_DATABASE_URL     dedicated non-CREATEDB target-owner URL used for
                                      database CONNECT fencing; defaults to the staging URL
                                      only in test mode.
  PINVI_RESTORE_DRILL_SCHEMA=app
  PINVI_RESTORE_DRILL_JOBS=2
  PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL=none|precheck|drain
  PINVI_RESTORE_DRILL_ALLOW_NON_STAGING=1  (test mode only)
EOF
}

cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

if [[ "${1:-}" != "run" || -z "${SNAPSHOT}" ]]; then
  usage
  exit 2
fi

TEST_MODE="${PINVI_M05_RESTORE_TEST_MODE:-0}"
if [[ "${TEST_MODE}" != "0" && "${TEST_MODE}" != "1" ]]; then
  phase precheck failed "PINVI_M05_RESTORE_TEST_MODE must be 0 or 1"
  exit 2
fi
if [[ "${TEST_MODE}" == "1" && "${PINVI_ENVIRONMENT:-}" != "test" ]]; then
  phase precheck failed "M05 restore test mode requires PINVI_ENVIRONMENT=test"
  exit 3
fi

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  phase precheck failed "unsafe schema name"
  exit 2
fi

STAGING_DATABASE_URL="${PINVI_RESTORE_STAGING_DATABASE_URL:-}"
DATABASE_URL="${PINVI_RESTORE_HOTSWAP_DATABASE_URL:-${STAGING_DATABASE_URL}}"
FENCE_DATABASE_URL="${PINVI_RESTORE_FENCE_DATABASE_URL:-${STAGING_DATABASE_URL}}"
if [[ -z "${STAGING_DATABASE_URL}" ]]; then
  if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" &&
    "${PINVI_RESTORE_DRILL_ALLOW_NON_STAGING:-0}" == "1" ]]; then
    STAGING_DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
    DATABASE_URL="${PINVI_RESTORE_HOTSWAP_DATABASE_URL:-${STAGING_DATABASE_URL}}"
    FENCE_DATABASE_URL="${PINVI_RESTORE_FENCE_DATABASE_URL:-${STAGING_DATABASE_URL}}"
  else
    phase precheck failed "PINVI_RESTORE_STAGING_DATABASE_URL is required for staging drill"
    exit 2
  fi
fi

if [[ -z "${STAGING_DATABASE_URL}" || -z "${DATABASE_URL}" || -z "${FENCE_DATABASE_URL}" ]]; then
  phase precheck failed "staging database URL is empty"
  exit 2
fi
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" &&
  -z "${PINVI_RESTORE_FENCE_DATABASE_URL:-}" ]]; then
  phase precheck failed "PINVI_RESTORE_FENCE_DATABASE_URL is required for a non-test staging drill"
  exit 2
fi

if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" &&
  "${PINVI_ENVIRONMENT:-}" != "staging" ]]; then
  phase precheck failed "staging restore drill requires PINVI_ENVIRONMENT=staging"
  exit 2
fi
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" &&
  -n "${PINVI_DATABASE_URL:-}" && "${DATABASE_URL}" == "${PINVI_DATABASE_URL}" ]]; then
  phase precheck failed "staging restore target must not be the application database"
  exit 3
fi

if [[ "${STAGING_DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  STAGING_DATABASE_URL="postgresql://${STAGING_DATABASE_URL#postgresql+asyncpg://}"
fi
if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi
if [[ "${FENCE_DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  FENCE_DATABASE_URL="postgresql://${FENCE_DATABASE_URL#postgresql+asyncpg://}"
fi

phase precheck running "snapshot and tooling checks"
evidence snapshot "$(mask_snapshot "${SNAPSHOT}")"

if [[ ! -f "${SNAPSHOT}" ]]; then
  phase precheck failed "snapshot file not found"
  exit 2
fi

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
PG_RESTORE_BIN="${PINVI_RESTORE_PG_RESTORE_BIN:-}"
if [[ -z "${PG_RESTORE_BIN}" ]]; then
  PG_RESTORE_BIN="$(pinned_tool pg_restore || true)"
fi
BASH_BIN="${PINVI_RESTORE_BASH_BIN:-}"
if [[ -z "${BASH_BIN}" ]]; then
  BASH_BIN="$(pinned_tool bash || true)"
fi
for tool_path in "${PG_RESTORE_BIN}" "${PSQL_BIN}" "${BASH_BIN}"; do
  if [[ "${tool_path}" != /* || ! -x "${tool_path}" ]]; then
    phase precheck failed "restore tooling is not pinned"
    exit 127
  fi
done
if ! command -v sha256sum >/dev/null 2>&1; then
  phase precheck failed "sha256sum not found"
  exit 127
fi
BASH_SHA256="${PINVI_RESTORE_BASH_SHA256:-$(sha256sum "${BASH_BIN}" | awk 'NR == 1 { print $1 }')}"
assert_trusted_tool_path() {
  local name="$1"
  local path="$2"
  if [[ "${path}" != /* || ! -f "${path}" || ! -x "${path}" || -L "${path}" ]]; then
    phase precheck failed "${name} path is not a trusted executable"
    exit 127
  fi
  local resolved
  resolved="$(realpath -e "${path}")"
  case "${resolved}" in
    /usr/local/bin/${name}|/usr/bin/${name}|/bin/${name}) ;;
    /usr/lib/postgresql/[0-9]*/bin/${name}) ;;
    *)
      phase precheck failed "${name} path is outside the trusted tool directories"
      exit 127
      ;;
  esac
}

if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
  :
else
  if [[ "${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
    assert_trusted_tool_path "pg_restore" "${PG_RESTORE_BIN}"
    assert_trusted_tool_path "psql" "${PSQL_BIN}"
  fi
  for tool_spec in \
    "pg_restore:${PG_RESTORE_BIN}:${PINVI_RESTORE_PG_RESTORE_SHA256:-}" \
    "psql:${PSQL_BIN}:${PINVI_RESTORE_PSQL_SHA256:-}" \
    "bash:${BASH_BIN}:${BASH_SHA256}"; do
    IFS=: read -r tool_name tool_path tool_digest <<<"${tool_spec}"
    if [[ ! "${tool_digest}" =~ ^[0-9a-f]{64}$ ]] || \
      [[ "$(sha256sum "${tool_path}" | awk 'NR == 1 { print $1 }')" != "${tool_digest}" ]]; then
      phase precheck failed "${tool_name} digest pin failed"
      exit 3
    fi
  done
fi
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" ||
  "${PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST:-0}" == "1" ]]; then
  evidence restore_tool_binding verified
fi

TMP_DIR="$(mktemp -d)"
copy_verified_private() {
  local name="$1"
  local source="$2"
  local expected="$3"
  local target="${TMP_DIR}/${name}"
  if [[ -L "${source}" || ! -f "${source}" ]]; then
    phase precheck failed "${name} source must be a regular file"
    exit 3
  fi
  cp -- "${source}" "${target}"
  chmod 700 "${target}"
  if [[ "$(sha256sum "${target}" | awk 'NR == 1 { print $1 }')" != "${expected}" ]]; then
    phase precheck failed "${name} changed while copying to the private restore directory"
    exit 3
  fi
  printf '%s\n' "${target}"
}

PSQL_DIGEST="${PINVI_RESTORE_PSQL_SHA256:-}"
PG_RESTORE_DIGEST="${PINVI_RESTORE_PG_RESTORE_SHA256:-}"
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
  PSQL_DIGEST="$(sha256sum "${PSQL_BIN}" | awk 'NR == 1 { print $1 }')"
  PG_RESTORE_DIGEST="$(sha256sum "${PG_RESTORE_BIN}" | awk 'NR == 1 { print $1 }')"
fi
PSQL_BIN="$(copy_verified_private psql "${PSQL_BIN}" "${PSQL_DIGEST}")"
PG_RESTORE_BIN="$(copy_verified_private pg_restore "${PG_RESTORE_BIN}" "${PG_RESTORE_DIGEST}")"

if [[ -L "${SNAPSHOT}" || ! -f "${SNAPSHOT}" || -L "${SNAPSHOT}.sha256" || ! -f "${SNAPSHOT}.sha256" ]]; then
  phase precheck failed "snapshot and checksum sidecar must be regular files"
  exit 3
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  phase precheck failed "sha256sum not found"
  exit 127
fi
expected_checksum="$(awk 'NR == 1 { print $1 }' "${SNAPSHOT}.sha256")"
actual_checksum="$(sha256sum "${SNAPSHOT}" | awk 'NR == 1 { print $1 }')"
if [[ ! "${expected_checksum}" =~ ^[0-9a-f]{64}$ || "${expected_checksum}" != "${actual_checksum}" ]]; then
  phase precheck failed "snapshot checksum failed"
  exit 3
fi
SNAPSHOT_COPY="${TMP_DIR}/snapshot.dump"
cp -- "${SNAPSHOT}" "${SNAPSHOT_COPY}"
if [[ "$(sha256sum "${SNAPSHOT_COPY}" | awk 'NR == 1 { print $1 }')" != "${expected_checksum}" ]]; then
  phase precheck failed "snapshot changed while copying to the private restore directory"
  exit 3
fi
printf '%s  %s\n' "${expected_checksum}" "$(basename "${SNAPSHOT_COPY}")" >"${SNAPSHOT_COPY}.sha256"
chmod 600 "${SNAPSHOT_COPY}.sha256"
SNAPSHOT="${SNAPSHOT_COPY}"
evidence checksum verified

if ! "${PG_RESTORE_BIN}" --list "${SNAPSHOT}" >/dev/null; then
  phase precheck failed "pg_restore list failed"
  exit 3
fi
evidence pg_restore_list ok

if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" != "1" ]]; then
  for variable in PINVI_RESTORE_EXPECTED_DATABASE_NAME PINVI_RESTORE_EXPECTED_DATABASE_OID \
    PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER PINVI_RESTORE_EXPECTED_HOSTADDR PINVI_RESTORE_EXPECTED_PORT; do
    if [[ -z "${!variable:-}" ]]; then
      phase precheck failed "${variable} is required for a non-test staging restore"
      exit 3
    fi
  done
fi

psql_scalar_url() {
  local database_url="$1"
  local sql="$2"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${database_url}" -tAc "${sql}" \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

psql_scalar() {
  local sql="$1"
  psql_scalar_url "${DATABASE_URL}" "${sql}"
}

staging_public_connect_state() {
  if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
    printf 'f\n'
    return 0
  fi
  psql_scalar_url "${STAGING_DATABASE_URL}" "
SELECT EXISTS (
  SELECT 1
  FROM pg_database db
  CROSS JOIN LATERAL aclexplode(COALESCE(db.datacl, acldefault('d', db.datdba))) acl
  WHERE db.datname = current_database()
    AND acl.grantee = 0
    AND acl.privilege_type = 'CONNECT'
)"
}

m05_advisory_lock_present() {
  if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
    printf 'f\n'
    return 0
  fi
  psql_scalar_url "${STAGING_DATABASE_URL}" "
SELECT EXISTS (
  SELECT 1
  FROM pg_locks
  WHERE locktype = 'advisory'
    AND classid = 1414679892
    AND objid = 1213421392
    AND granted
)"
}

schema_oid() {
  psql_scalar "SELECT COALESCE(to_regnamespace('${SCHEMA}')::oid::text, 'missing')"
}

table_count() {
  local table="$1"
  local exists
  exists="$(psql_scalar "SELECT to_regclass('${SCHEMA}.${table}') IS NOT NULL")"
  if [[ "${exists}" != "t" ]]; then
    printf 'missing\n'
    return
  fi
  psql_scalar "SELECT count(*)::text FROM ${SCHEMA}.${table}"
}

audit_chain_links() {
  local exists
  exists="$(psql_scalar "SELECT to_regclass('${SCHEMA}.admin_audit_log') IS NOT NULL")"
  if [[ "${exists}" != "t" ]]; then
    printf 'missing\n'
    return
  fi
  psql_scalar "
WITH ordered AS (
  SELECT
    log_id,
    prev_hash,
    content_hash,
    lag(content_hash) OVER (ORDER BY log_id) AS previous_content_hash
  FROM ${SCHEMA}.admin_audit_log
),
broken AS (
  SELECT log_id
  FROM ordered
  WHERE prev_hash <> COALESCE(previous_content_hash, repeat('0', 64))
  ORDER BY log_id
  LIMIT 1
)
SELECT
  COALESCE((SELECT 'broken:' || log_id::text FROM broken), 'valid')"
}

before_oid="$(schema_oid)"
evidence before_schema_oid "${before_oid}"

phase restore running "restoring app schema into staging database"
REQUIRE_FRESH_SCHEMA=1
if [[ "${PINVI_M05_RESTORE_TEST_MODE:-0}" == "1" ]]; then
  REQUIRE_FRESH_SCHEMA="${PINVI_RESTORE_REQUIRE_FRESH_SCHEMA:-0}"
fi
set +e
restore_output="$(PINVI_RESTORE_DATABASE_URL="${DATABASE_URL}" \
  PINVI_RESTORE_SCHEMA="${SCHEMA}" \
  PINVI_RESTORE_JOBS="${JOBS}" \
  PINVI_RESTORE_PSQL_BIN="${PSQL_BIN}" \
  PINVI_RESTORE_PG_RESTORE_BIN="${PG_RESTORE_BIN}" \
  PINVI_RESTORE_PSQL_SHA256="${PINVI_RESTORE_PSQL_SHA256:-}" \
  PINVI_RESTORE_PG_RESTORE_SHA256="${PINVI_RESTORE_PG_RESTORE_SHA256:-}" \
  PINVI_RESTORE_PRIVATE_TOOL_COPY="${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" \
  PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST="${PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST:-0}" \
  PINVI_RESTORE_REQUIRE_FRESH_SCHEMA="${REQUIRE_FRESH_SCHEMA}" \
  PINVI_RESTORE_APP_ROLE="${PINVI_RESTORE_APP_ROLE:-}" \
  PINVI_RESTORE_EXPECTED_DATABASE_NAME="${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" \
  PINVI_RESTORE_EXPECTED_DATABASE_OID="${PINVI_RESTORE_EXPECTED_DATABASE_OID:-}" \
  PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER="${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER:-}" \
  PINVI_RESTORE_EXPECTED_HOSTADDR="${PINVI_RESTORE_EXPECTED_HOSTADDR:-}" \
  PINVI_RESTORE_EXPECTED_PORT="${PINVI_RESTORE_EXPECTED_PORT:-}" \
  PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME="${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME:-}" \
  PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID="${PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID:-}" \
  PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER="${PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER:-}" \
  PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR="${PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR:-}" \
  PINVI_RESTORE_EXPECTED_SOURCE_PORT="${PINVI_RESTORE_EXPECTED_SOURCE_PORT:-}" \
  PINVI_RESTORE_TRUSTED_BACKUP_DIR="${PINVI_RESTORE_TRUSTED_BACKUP_DIR:-}" \
  "${ROOT_DIR}/scripts/restore-db.sh" "${TRUSTED_SNAPSHOT}" 2>&1)"
restore_status="$?"
set -e
if [[ "${restore_status}" != "0" ]]; then
  phase restore failed "restore-db.sh failed"
  exit 3
fi
while IFS= read -r restore_line; do
  case "${restore_line}" in
    RESTORE_TARGET_BINDING=*|RESTORE_SOURCE_BINDING=*) printf '%s\n' "${restore_line}" ;;
    RESTORE_COMMAND=*) printf '%s\n' "${restore_line}" ;;
    RESTORED_FILE=*) evidence restored_file "$(mask_snapshot "${SNAPSHOT}")" ;;
  esac
done <<<"${restore_output}"
phase restore success "restore-db.sh completed"

phase validate running "checking restored schema"
after_oid="$(schema_oid)"
users_count="$(table_count users)"
trips_count="$(table_count trips)"
audit_count="$(table_count admin_audit_log)"
audit_links="$(audit_chain_links)"
evidence after_schema_oid "${after_oid}"
evidence users_count "${users_count}"
evidence trips_count "${trips_count}"
evidence admin_audit_log_count "${audit_count}"
evidence admin_audit_chain_links "${audit_links}"

if [[ "${after_oid}" == "missing" || "${users_count}" == "missing" || "${audit_links}" != "valid" ]]; then
  phase validate failed "restored schema health check failed"
  exit 4
fi
phase validate success "restored schema passed DB health checks"

rollback_precheck_rehearsal() {
  local restore_schema="${SCHEMA}_restore_drill_$(date -u +%Y%m%d%H%M%S)"
  local previous_schema="${SCHEMA}_previous_drill_$(date -u +%Y%m%d%H%M%S)"
  local oid_before="$1"
  TMP_DIR="$(mktemp -d)"
  set +e
    PINVI_RESTORE_DATABASE_URL="${DATABASE_URL}" \
    PINVI_BACKUP_SCHEMA="${SCHEMA}" \
    PINVI_RESTORE_PSQL_BIN="${PSQL_BIN}" \
    PINVI_RESTORE_PG_RESTORE_BIN="${PG_RESTORE_BIN}" \
    PINVI_RESTORE_PSQL_SHA256="${PINVI_RESTORE_PSQL_SHA256:-}" \
    PINVI_RESTORE_PG_RESTORE_SHA256="${PINVI_RESTORE_PG_RESTORE_SHA256:-}" \
    PINVI_RESTORE_PRIVATE_TOOL_COPY="${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" \
    PINVI_RESTORE_BASH_BIN="${BASH_BIN}" \
    PINVI_RESTORE_BASH_SHA256="${BASH_SHA256}" \
    PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST="${PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST:-0}" \
    PINVI_RESTORE_EXPECTED_DATABASE_NAME="${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" \
    PINVI_RESTORE_EXPECTED_DATABASE_OID="${PINVI_RESTORE_EXPECTED_DATABASE_OID:-}" \
    PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER="${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER:-}" \
    PINVI_RESTORE_EXPECTED_HOSTADDR="${PINVI_RESTORE_EXPECTED_HOSTADDR:-}" \
    PINVI_RESTORE_EXPECTED_PORT="${PINVI_RESTORE_EXPECTED_PORT:-}" \
    PINVI_RESTORE_TRUSTED_BACKUP_DIR="${PINVI_RESTORE_TRUSTED_BACKUP_DIR:-}" \
    PINVI_RESTORE_FENCE_DATABASE_URL="${FENCE_DATABASE_URL}" \
    PINVI_RESTORE_HOTSWAP_EXECUTE=0 \
    "${ROOT_DIR}/scripts/restore-hotswap.sh" run \
    "${TRUSTED_SNAPSHOT}" "${restore_schema}" "${previous_schema}" \
    >"${TMP_DIR}/hotswap.out" 2>"${TMP_DIR}/hotswap.err"
  local code="$?"
  set -e
  local oid_after
  oid_after="$(schema_oid)"
  if [[ "${code}" == "0" || "${oid_after}" != "${oid_before}" ]]; then
    phase rollback failed "dry-run guard did not preserve current schema"
    exit 5
  fi
  evidence rollback_rehearsal "precheck_guard_schema_unchanged"
}

report_hotswap_failure() {
  local output_path="$1"
  local error_path="$2"
  if [[ -s "${output_path}" ]]; then
    cat -- "${output_path}" >&2 || true
  fi
  if [[ -s "${error_path}" ]]; then
    cat -- "${error_path}" >&2 || true
  fi
}

rollback_drain_rehearsal() {
  local ts
  ts="$(date -u +%Y%m%d%H%M%S)"
  local restore_schema="${SCHEMA}_restore_drill_${ts}"
  local previous_schema="${SCHEMA}_previous_drill_${ts}"
  local oid_before="$1"
  local public_connect_before lock_before
  public_connect_before="$(staging_public_connect_state)"
  lock_before="$(m05_advisory_lock_present)"
  if [[ "${lock_before}" == "t" ]]; then
    phase rollback failed "M05 advisory lock was already held before rollback rehearsal"
    exit 5
  fi
  TMP_DIR="$(mktemp -d)"
  set +e
  PINVI_RESTORE_DATABASE_URL="${DATABASE_URL}" \
  PINVI_BACKUP_SCHEMA="${SCHEMA}" \
    PINVI_RESTORE_PSQL_BIN="${PSQL_BIN}" \
    PINVI_RESTORE_PG_RESTORE_BIN="${PG_RESTORE_BIN}" \
    PINVI_RESTORE_PSQL_SHA256="${PINVI_RESTORE_PSQL_SHA256:-}" \
    PINVI_RESTORE_PG_RESTORE_SHA256="${PINVI_RESTORE_PG_RESTORE_SHA256:-}" \
    PINVI_RESTORE_PRIVATE_TOOL_COPY="${PINVI_RESTORE_PRIVATE_TOOL_COPY:-0}" \
    PINVI_RESTORE_BASH_BIN="${BASH_BIN}" \
    PINVI_RESTORE_BASH_SHA256="${BASH_SHA256}" \
    PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST="${PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST:-0}" \
    PINVI_RESTORE_EXPECTED_DATABASE_NAME="${PINVI_RESTORE_EXPECTED_DATABASE_NAME:-}" \
    PINVI_RESTORE_EXPECTED_DATABASE_OID="${PINVI_RESTORE_EXPECTED_DATABASE_OID:-}" \
    PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER="${PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER:-}" \
    PINVI_RESTORE_EXPECTED_HOSTADDR="${PINVI_RESTORE_EXPECTED_HOSTADDR:-}" \
    PINVI_RESTORE_EXPECTED_PORT="${PINVI_RESTORE_EXPECTED_PORT:-}" \
    PINVI_RESTORE_TRUSTED_BACKUP_DIR="${PINVI_RESTORE_TRUSTED_BACKUP_DIR:-}" \
    PINVI_RESTORE_FENCE_DATABASE_URL="${FENCE_DATABASE_URL}" \
    PINVI_RESTORE_HOTSWAP_EXECUTE=1 \
    PINVI_RESTORE_DRAIN_COMMAND= \
    PINVI_RESTORE_ALLOW_NO_DRAIN=0 \
    "${ROOT_DIR}/scripts/restore-hotswap.sh" run \
    "${TRUSTED_SNAPSHOT}" "${restore_schema}" "${previous_schema}" \
    >"${TMP_DIR}/hotswap.out" 2>"${TMP_DIR}/hotswap.err"
  local code="$?"
  set -e
  if [[ "${code}" != "0" ]]; then
    report_hotswap_failure "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err"
  fi
  local oid_after
  oid_after="$(schema_oid)"
  local public_connect_after lock_after
  public_connect_after="$(staging_public_connect_state)"
  lock_after="$(m05_advisory_lock_present)"
  "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 "${DATABASE_URL}" \
    -c "DROP SCHEMA IF EXISTS ${restore_schema} CASCADE" >/dev/null
  if [[ "${code}" == "0" || "${oid_after}" != "${oid_before}" ||
    "${public_connect_after}" != "${public_connect_before}" || "${lock_after}" != "f" ]]; then
    phase rollback failed "drain-failure rehearsal did not preserve current schema"
    exit 5
  fi
  if ! grep -Fq -- "RESTORE_PHASE=draining:failed:PINVI_RESTORE_DRAIN_COMMAND or PINVI_RESTORE_DRAIN_VERIFIED=1 is required" \
    "${TMP_DIR}/hotswap.out"; then
    phase rollback failed "drain-failure rehearsal did not produce the expected drain guard"
    exit 5
  fi
  if grep -Fq -- "database write fence cleanup failed" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err" ||
    grep -Fq -- "database owner fence SQL failed" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err" ||
    grep -Fq -- "database CONNECT fence was not applied" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err" ||
    grep -Fq -- "database CONNECT grant was not restored" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err" ||
    grep -Fq -- "PUBLIC CONNECT" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err" ||
    grep -Fq -- "schema-swap database advisory lock was lost" "${TMP_DIR}/hotswap.out" "${TMP_DIR}/hotswap.err"; then
    phase rollback failed "drain-failure rehearsal detected fence or lock cleanup failure"
    exit 5
  fi
  evidence rollback_database_fence restored
  evidence rollback_advisory_lock released
  evidence rollback_rehearsal "drain_failed_schema_unchanged"
}

phase rollback running "rehearsing failed restore safety"
case "${ROLLBACK_REHEARSAL}" in
  none)
    evidence rollback_rehearsal skipped
    phase rollback skipped "rollback rehearsal disabled"
    ;;
  precheck)
    rollback_precheck_rehearsal "${after_oid}"
    phase rollback success "precheck guard preserved current schema"
    ;;
  drain)
    rollback_drain_rehearsal "${after_oid}"
    phase rollback success "drain failure preserved current schema"
    ;;
  *)
    phase rollback failed "unknown rollback rehearsal mode"
    exit 2
    ;;
esac

phase complete success "staging restore drill completed"
