#!/usr/bin/env bash
# Guarded entrypoint for TripMate same-database schema-swap restore.

set -euo pipefail

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
DATABASE_URL="${TRIPMATE_RESTORE_DATABASE_URL:-${TRIPMATE_DATABASE_URL:-}}"
SOURCE_SCHEMA="${TRIPMATE_BACKUP_SCHEMA:-app}"
TMP_DIR=""

phase preparing running "precheck started"

if [[ -z "${DATABASE_URL}" ]]; then
  phase preparing failed "TRIPMATE_DATABASE_URL or TRIPMATE_RESTORE_DATABASE_URL is required"
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! -f "${SNAPSHOT}" ]]; then
  phase preparing failed "snapshot file not found"
  exit 2
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  phase preparing failed "pg_restore not found"
  exit 127
fi

if [[ -f "${SNAPSHOT}.sha256" ]]; then
  if ! command -v sha256sum >/dev/null 2>&1; then
    phase preparing failed "sha256sum not found"
    exit 127
  fi
  sha256sum -c "${SNAPSHOT}.sha256" >/dev/null
fi

pg_restore --list "${SNAPSHOT}" >/dev/null
phase preparing success "snapshot verified for ${RESTORE_SCHEMA}"

if [[ "${TRIPMATE_RESTORE_HOTSWAP_EXECUTE:-0}" != "1" ]]; then
  phase restoring failed "guard refused schema-swap; set TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1 only after staging drill"
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

if ! command -v psql >/dev/null 2>&1; then
  phase preparing failed "psql not found"
  exit 127
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

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
psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" \
  -c "DROP SCHEMA IF EXISTS ${RESTORE_SCHEMA} CASCADE" >/dev/null
pg_restore \
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
psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f "${TMP_DIR}/schema-remapped.sql" >/dev/null

pg_restore \
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
psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f "${TMP_DIR}/data-remapped.sql" >/dev/null
phase restoring success "restored into ${RESTORE_SCHEMA}"

# pg_restore --no-privileges로 복원했으므로 GRANT가 비어 있다. 앱 role이 스키마 owner가
# 아니면 swap 직후 permission denied가 난다. swap 전에 RESTORE_SCHEMA에 GRANT를 재적용한다
# (GRANT는 객체에 귀속되어 schema rename 후에도 유지된다).
APP_ROLE="${TRIPMATE_RESTORE_APP_ROLE:-}"
if [[ -n "${APP_ROLE}" ]]; then
  if [[ ! "${APP_ROLE}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    phase restoring failed "unsafe app role name: ${APP_ROLE}"
    exit 2
  fi
  psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" <<SQL >/dev/null
GRANT USAGE ON SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ${RESTORE_SCHEMA} TO ${APP_ROLE};
SQL
  phase restoring success "re-granted privileges to ${APP_ROLE}"
else
  phase restoring success "TRIPMATE_RESTORE_APP_ROLE unset; assuming single-owner role (no GRANT re-apply)"
fi

phase validating running "validating restored schema"
users_exists="$(psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" -tAc "SELECT to_regclass('${RESTORE_SCHEMA}.users') IS NOT NULL")"
if [[ "${users_exists}" != "t" ]]; then
  phase validating failed "restored schema is missing users table"
  exit 3
fi
phase validating success "restored schema passed basic checks"

phase draining running "write drain"
if [[ "${TRIPMATE_RESTORE_API_TRIGGER:-0}" == "1" && -n "${TRIPMATE_RESTORE_DRAIN_COMMAND:-}" ]]; then
  phase draining failed "API-triggered restore cannot run TRIPMATE_RESTORE_DRAIN_COMMAND; pre-drain externally and set TRIPMATE_RESTORE_ALLOW_NO_DRAIN=1"
  exit 3
fi
if [[ -n "${TRIPMATE_RESTORE_DRAIN_COMMAND:-}" ]]; then
  bash -lc "${TRIPMATE_RESTORE_DRAIN_COMMAND}"
  phase draining success "drain command completed"
elif [[ "${TRIPMATE_RESTORE_ALLOW_NO_DRAIN:-0}" == "1" ]]; then
  phase draining skipped "TRIPMATE_RESTORE_ALLOW_NO_DRAIN=1"
else
  phase draining failed "TRIPMATE_RESTORE_DRAIN_COMMAND is required unless TRIPMATE_RESTORE_ALLOW_NO_DRAIN=1"
  exit 3
fi

phase switching running "renaming schemas"
psql -v ON_ERROR_STOP=1 "${DATABASE_URL}" <<SQL >/dev/null
BEGIN;
ALTER SCHEMA ${SOURCE_SCHEMA} RENAME TO ${PREVIOUS_SCHEMA};
ALTER SCHEMA ${RESTORE_SCHEMA} RENAME TO ${SOURCE_SCHEMA};
COMMIT;
SQL
phase switching success "schema-swap completed"
