#!/usr/bin/env bash
# Sprint 5 staging restore drill for Pinvi app-schema backups.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA="${PINVI_RESTORE_DRILL_SCHEMA:-${PINVI_BACKUP_SCHEMA:-app}}"
JOBS="${PINVI_RESTORE_DRILL_JOBS:-${PINVI_RESTORE_JOBS:-2}}"
ROLLBACK_REHEARSAL="${PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL:-precheck}"
SNAPSHOT="${2:-}"
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
  PINVI_RESTORE_DRILL_SCHEMA=app
  PINVI_RESTORE_DRILL_JOBS=2
  PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL=none|precheck|drain
  PINVI_RESTORE_DRILL_ALLOW_NON_STAGING=1
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

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  phase precheck failed "unsafe schema name"
  exit 2
fi

DATABASE_URL="${PINVI_RESTORE_STAGING_DATABASE_URL:-}"
if [[ -z "${DATABASE_URL}" ]]; then
  if [[ "${PINVI_RESTORE_DRILL_ALLOW_NON_STAGING:-0}" == "1" ]]; then
    DATABASE_URL="${PINVI_RESTORE_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
  else
    phase precheck failed "PINVI_RESTORE_STAGING_DATABASE_URL is required for staging drill"
    exit 2
  fi
fi

if [[ -z "${DATABASE_URL}" ]]; then
  phase precheck failed "staging database URL is empty"
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

phase precheck running "snapshot and tooling checks"
evidence snapshot "$(mask_snapshot "${SNAPSHOT}")"

if [[ ! -f "${SNAPSHOT}" ]]; then
  phase precheck failed "snapshot file not found"
  exit 2
fi

for command_name in pg_restore psql; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    phase precheck failed "${command_name} not found"
    exit 127
  fi
done

if [[ -f "${SNAPSHOT}.sha256" ]]; then
  if ! command -v sha256sum >/dev/null 2>&1; then
    phase precheck failed "sha256sum not found"
    exit 127
  fi
  expected_checksum="$(awk 'NR == 1 { print $1 }' "${SNAPSHOT}.sha256")"
  actual_checksum="$(sha256sum "${SNAPSHOT}" | awk 'NR == 1 { print $1 }')"
  if [[ -z "${expected_checksum}" || "${expected_checksum}" != "${actual_checksum}" ]]; then
    phase precheck failed "snapshot checksum failed"
    exit 3
  fi
  evidence checksum verified
else
  evidence checksum missing
fi

if ! pg_restore --list "${SNAPSHOT}" >/dev/null; then
  phase precheck failed "pg_restore list failed"
  exit 3
fi
evidence pg_restore_list ok

psql_scalar() {
  local sql="$1"
  psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" -tAc "${sql}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
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
if ! PINVI_RESTORE_DATABASE_URL="${DATABASE_URL}" \
  PINVI_RESTORE_SCHEMA="${SCHEMA}" \
  PINVI_RESTORE_JOBS="${JOBS}" \
  "${ROOT_DIR}/scripts/restore-db.sh" "${SNAPSHOT}" >/dev/null; then
  phase restore failed "restore-db.sh failed"
  exit 3
fi
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
    PINVI_RESTORE_HOTSWAP_EXECUTE=0 \
    "${ROOT_DIR}/scripts/restore-hotswap.sh" run \
    "${SNAPSHOT}" "${restore_schema}" "${previous_schema}" \
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

rollback_drain_rehearsal() {
  local ts
  ts="$(date -u +%Y%m%d%H%M%S)"
  local restore_schema="${SCHEMA}_restore_drill_${ts}"
  local previous_schema="${SCHEMA}_previous_drill_${ts}"
  local oid_before="$1"
  TMP_DIR="$(mktemp -d)"
  set +e
  PINVI_RESTORE_DATABASE_URL="${DATABASE_URL}" \
    PINVI_BACKUP_SCHEMA="${SCHEMA}" \
    PINVI_RESTORE_HOTSWAP_EXECUTE=1 \
    PINVI_RESTORE_DRAIN_COMMAND= \
    PINVI_RESTORE_ALLOW_NO_DRAIN=0 \
    "${ROOT_DIR}/scripts/restore-hotswap.sh" run \
    "${SNAPSHOT}" "${restore_schema}" "${previous_schema}" \
    >"${TMP_DIR}/hotswap.out" 2>"${TMP_DIR}/hotswap.err"
  local code="$?"
  set -e
  local oid_after
  oid_after="$(schema_oid)"
  psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" \
    -c "DROP SCHEMA IF EXISTS ${restore_schema} CASCADE" >/dev/null
  if [[ "${code}" == "0" || "${oid_after}" != "${oid_before}" ]]; then
    phase rollback failed "drain-failure rehearsal did not preserve current schema"
    exit 5
  fi
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
