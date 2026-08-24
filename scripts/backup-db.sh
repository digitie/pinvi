#!/usr/bin/env bash
# Create a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

unset PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PSQLRC

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PINVI_BACKUP_DIR:-${ROOT_DIR}/.tmp/backups}"
BACKUP_CATALOG_PATH="${PINVI_BACKUP_CATALOG_PATH:-}"
SCHEMA="${PINVI_BACKUP_SCHEMA:-app}"
MIN_FREE_BYTES="${PINVI_BACKUP_MIN_FREE_BYTES:-1073741824}"
DATABASE_URL="${PINVI_BACKUP_DATABASE_URL:-${PINVI_DATABASE_URL:-}}"
ENVIRONMENT="${PINVI_ENVIRONMENT:-development}"
STRICT_ENVIRONMENT=0
if [[ "${ENVIRONMENT}" == "staging" || "${ENVIRONMENT}" == "production" ]]; then
  STRICT_ENVIRONMENT=1
fi
DOCKER_FALLBACK="${PINVI_BACKUP_DOCKER_FALLBACK:-1}"
DOCKER_BIN="${PINVI_BACKUP_DOCKER_BIN:-docker}"
DOCKER_IMAGE="${PINVI_BACKUP_DOCKER_IMAGE:-postgis/postgis:16-3.5}"
DOCKER_NETWORK="${PINVI_BACKUP_DOCKER_NETWORK:-}"
CONTAINER_BACKUP_DIR="/backup"
TRUSTED_BACKUP="${PINVI_BACKUP_TRUSTED:-0}"
PINNED_SOURCE_HOSTADDR=""
SOURCE_IDENTITY_BEFORE_DUMP=""

pinned_tool() {
  local name="$1"
  local candidate
  for directory in /usr/local/bin /usr/bin /bin /usr/lib/postgresql/*/bin; do
    candidate="${directory}/${name}"
    if [[ -f "${candidate}" && -x "${candidate}" && ! -L "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

PG_DUMP_BIN="${PINVI_BACKUP_PG_DUMP_BIN:-}"
PG_RESTORE_BIN="${PINVI_BACKUP_PG_RESTORE_BIN:-}"
PSQL_BIN="${PINVI_BACKUP_PSQL_BIN:-}"

resolve_strict_tool() {
  local name="$1"
  local configured_path="$2"
  if [[ -n "${configured_path}" ]]; then
    printf '%s\n' "${configured_path}"
    return 0
  fi
  pinned_tool "${name}" || true
}

validate_strict_tool() {
  local name="$1"
  local path="$2"
  local digest="$3"
  if [[ "${path}" != /* || ! -f "${path}" || ! -x "${path}" || -L "${path}" ]]; then
    echo "strict backup requires a regular pinned ${name} executable" >&2
    exit 3
  fi
  local resolved
  resolved="$(realpath -e "${path}")"
  case "${resolved}" in
    /usr/local/bin/${name}|/usr/bin/${name}|/bin/${name}|/usr/lib/postgresql/[0-9]*/bin/${name}) ;;
    *)
      if [[ "${PINVI_BACKUP_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
        echo "strict backup ${name} is outside the trusted tool directories" >&2
        exit 3
      fi
      ;;
  esac
  if [[ ! "${digest}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "strict backup requires a ${name} digest pin" >&2
    exit 3
  fi
  if [[ "$(sha256sum "${path}" | awk 'NR == 1 { print $1 }')" != "${digest}" ]]; then
    echo "strict backup ${name} digest pin failed" >&2
    exit 3
  fi
}

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  PG_DUMP_BIN="$(resolve_strict_tool pg_dump "${PG_DUMP_BIN}")"
  PG_RESTORE_BIN="$(resolve_strict_tool pg_restore "${PG_RESTORE_BIN}")"
  PSQL_BIN="$(resolve_strict_tool psql "${PSQL_BIN}")"
else
  if [[ -z "${PG_DUMP_BIN}" ]]; then
    PG_DUMP_BIN="pg_dump"
  fi
fi

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  if [[ "${TRUSTED_BACKUP}" != "1" || "${EUID}" != "0" ]]; then
    echo "strict backup requires the root-only trusted backup producer" >&2
    exit 3
  fi
  if [[ "${BACKUP_DIR}" != /* || -L "${BACKUP_DIR}" ]]; then
    echo "strict backup requires an absolute non-symlink backup directory" >&2
    exit 3
  fi
  if [[ "${DOCKER_FALLBACK}" == "1" ]]; then
    echo "strict backup forbids docker pg_dump fallback" >&2
    exit 3
  fi
  validate_strict_tool pg_dump "${PG_DUMP_BIN}" "${PINVI_BACKUP_PG_DUMP_SHA256:-}"
  validate_strict_tool pg_restore "${PG_RESTORE_BIN}" "${PINVI_BACKUP_PG_RESTORE_SHA256:-}"
  validate_strict_tool psql "${PSQL_BIN}" "${PINVI_BACKUP_PSQL_SHA256:-}"
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PINVI_DATABASE_URL or PINVI_BACKUP_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  # A dump cannot be provenance-bound if pg_dump follows a hostname through a
  # DNS/LB/failover change and the manifest identity is read from a later
  # connection.  The root producer receives an already resolved hostaddr and
  # uses that exact endpoint for both identity observations and pg_dump.
  if [[ ! "${DATABASE_URL}" =~ (^|[?&])hostaddr=([0-9A-Fa-f:.]+)(&|$) ]]; then
    echo "strict backup requires a database URL with a pinned hostaddr" >&2
    exit 3
  fi
  if [[ "${PINVI_BACKUP_ENDPOINT_PINNED_BY_PRODUCER:-}" != "1" &&
    "${PINVI_M05_RESTORE_PRODUCER:-0}" != "1" ]]; then
    echo "strict backup requires a root producer-pinned database endpoint" >&2
    exit 3
  fi
  PINNED_SOURCE_HOSTADDR="${BASH_REMATCH[2]}"
fi

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "invalid backup schema name" >&2
  exit 2
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum not found" >&2
  exit 127
fi

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  if [[ ! -d "${BACKUP_DIR}" || -L "${BACKUP_DIR}" ]]; then
    echo "strict backup directory is not a regular directory" >&2
    exit 3
  fi
  backup_dir_metadata="$(stat -c '%u:%a' "${BACKUP_DIR}")"
  if [[ "${backup_dir_metadata}" != "0:700" ]]; then
    echo "strict backup directory must be root-owned mode 0700" >&2
    exit 3
  fi
  umask 077
  if [[ "${BACKUP_CATALOG_PATH}" != /* || -L "${BACKUP_CATALOG_PATH}" ]]; then
    echo "strict backup requires an absolute non-symlink metadata catalog path" >&2
    exit 3
  fi
  catalog_dir="$(dirname "${BACKUP_CATALOG_PATH}")"
  if [[ ! -d "${catalog_dir}" || -L "${catalog_dir}" || "$(stat -c '%u:%a' "${catalog_dir}")" != "0:700" ]]; then
    echo "strict backup metadata catalog directory must be root-owned mode 0700" >&2
    exit 3
  fi
else
  mkdir -p "${BACKUP_DIR}"
fi
available_kb="$(df -Pk "${BACKUP_DIR}" | awk 'NR == 2 { print $4 }')"
available_bytes="$((available_kb * 1024))"
if (( MIN_FREE_BYTES > 0 && available_bytes < MIN_FREE_BYTES )); then
  echo "backup disk guard failed: free_bytes=${available_bytes} required_bytes=${MIN_FREE_BYTES}" >&2
  exit 73
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
backup_file="${BACKUP_DIR}/pinvi-${SCHEMA}-${timestamp}.dump"
tmp_file="$(mktemp "${BACKUP_DIR}/.pinvi-${SCHEMA}-${timestamp}.dump.XXXXXX")"
PRIVATE_TOOL_DIR=""
LIST_FILE=""
MANIFEST_TMP_FILE=""
CATALOG_TMP_FILE=""
cleanup() {
  rm -f "${tmp_file}" "${tmp_file}.sha256" "${LIST_FILE}" "${MANIFEST_TMP_FILE}" "${CATALOG_TMP_FILE}"
  if [[ -n "${PRIVATE_TOOL_DIR}" && -d "${PRIVATE_TOOL_DIR}" ]]; then
    rm -rf "${PRIVATE_TOOL_DIR}"
  fi
}
trap cleanup EXIT

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  PRIVATE_TOOL_DIR="$(mktemp -d)"
  chmod 700 "${PRIVATE_TOOL_DIR}"
  copy_verified_tool() {
    local name="$1"
    local source="$2"
    local digest="$3"
    local target="${PRIVATE_TOOL_DIR}/${name}"
    cp -- "${source}" "${target}"
    chmod 700 "${target}"
    if [[ "$(sha256sum "${target}" | awk 'NR == 1 { print $1 }')" != "${digest}" ]]; then
      echo "strict backup ${name} changed while copying to the private directory" >&2
      exit 3
    fi
    printf '%s\n' "${target}"
  }
  PG_DUMP_BIN="$(copy_verified_tool pg_dump "${PG_DUMP_BIN}" "${PINVI_BACKUP_PG_DUMP_SHA256}")"
  PG_RESTORE_BIN="$(copy_verified_tool pg_restore "${PG_RESTORE_BIN}" "${PINVI_BACKUP_PG_RESTORE_SHA256}")"
  PSQL_BIN="$(copy_verified_tool psql "${PSQL_BIN}" "${PINVI_BACKUP_PSQL_SHA256}")"
fi

run_pg_dump() {
  # pg_dump custom format is a single-file artifact. Parallel jobs are used at restore time.
  if [[ "${PG_DUMP_BIN}" == /* && -x "${PG_DUMP_BIN}" ]] || command -v "${PG_DUMP_BIN}" >/dev/null 2>&1; then
    "${PG_DUMP_BIN}" \
      --format=custom \
      --schema="${SCHEMA}" \
      --no-owner \
      --no-privileges \
      --file="${tmp_file}" \
      "${DATABASE_URL}"
    return
  fi

  if [[ "${DOCKER_FALLBACK}" != "1" ]]; then
    echo "pg_dump not found: ${PG_DUMP_BIN}" >&2
    exit 127
  fi

  if ! command -v "${DOCKER_BIN}" >/dev/null 2>&1; then
    echo "pg_dump not found and docker fallback unavailable: ${DOCKER_BIN}" >&2
    exit 127
  fi

  backup_dir_abs="$(cd "${BACKUP_DIR}" && pwd -P)"
  tmp_name="$(basename "${tmp_file}")"
  container_tmp_file="${CONTAINER_BACKUP_DIR}/${tmp_name}"
  docker_args=(run --rm)
  if [[ -n "${DOCKER_NETWORK}" ]]; then
    docker_args+=(--network "${DOCKER_NETWORK}")
  fi
  docker_args+=(
    -v "${backup_dir_abs}:${CONTAINER_BACKUP_DIR}"
    --env PINVI_BACKUP_DATABASE_URL
    --env PINVI_BACKUP_SCHEMA
    --env PINVI_BACKUP_DUMP_FILE
    "${DOCKER_IMAGE}"
    sh
    -c
    'exec pg_dump --format=custom --schema="${PINVI_BACKUP_SCHEMA}" --no-owner --no-privileges --file="${PINVI_BACKUP_DUMP_FILE}" "${PINVI_BACKUP_DATABASE_URL}"'
  )

  PINVI_BACKUP_DATABASE_URL="${DATABASE_URL}" \
    PINVI_BACKUP_SCHEMA="${SCHEMA}" \
    PINVI_BACKUP_DUMP_FILE="${container_tmp_file}" \
    "${DOCKER_BIN}" "${docker_args[@]}"

  if [[ ! -f "${tmp_file}" ]]; then
    echo "docker pg_dump fallback did not create dump" >&2
    exit 1
  fi
}

strict_source_identity() {
  local identity database_name database_oid system_identifier hostaddr port
  identity="$("${PSQL_BIN}" --no-psqlrc --tuples-only --no-align --quiet --dbname="${DATABASE_URL}" \
    --command="SELECT current_database() || '|' || d.oid::text || '|' || (pg_control_system()).system_identifier::text || '|' || COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text FROM pg_database d WHERE d.datname = current_database()" \
    | tr -d '[:space:]')"
  IFS='|' read -r database_name database_oid system_identifier hostaddr port <<<"${identity}"
  if [[ ! "${database_name}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ||
    ! "${database_oid}" =~ ^[0-9]+$ ||
    ! "${system_identifier}" =~ ^[0-9]+$ ||
    ! "${hostaddr}" =~ ^[0-9A-Fa-f:.]+$ ||
    ! "${port}" =~ ^[0-9]+$ ]]; then
    echo "strict backup source identity is invalid" >&2
    exit 3
  fi
  if [[ -n "${PINNED_SOURCE_HOSTADDR}" && "${hostaddr}" != "${PINNED_SOURCE_HOSTADDR}" ]]; then
    echo "strict backup source identity does not match the pinned hostaddr" >&2
    exit 3
  fi
  printf '%s|%s|%s|%s|%s\n' \
    "${database_name}" "${database_oid}" "${system_identifier}" "${hostaddr}" "${port}"
}

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  SOURCE_IDENTITY_BEFORE_DUMP="$(strict_source_identity)"
fi

run_pg_dump

tmp_dir="$(dirname "${tmp_file}")"
tmp_name="$(basename "${tmp_file}")"
(cd "${tmp_dir}" && sha256sum "${tmp_name}" >"${tmp_name}.sha256")
(cd "${tmp_dir}" && sha256sum -c "${tmp_name}.sha256") >/dev/null

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  source_identity="$(strict_source_identity)"
  if [[ "${source_identity}" != "${SOURCE_IDENTITY_BEFORE_DUMP}" ]]; then
    echo "strict backup source identity changed during pg_dump" >&2
    exit 3
  fi
  IFS='|' read -r source_database source_database_oid source_system_identifier source_hostaddr source_port <<<"${source_identity}"
  LIST_FILE="$(mktemp)"
  "${PG_RESTORE_BIN}" --list "${tmp_file}" >"${LIST_FILE}"
  restore_list_sha256="$(sha256sum "${LIST_FILE}" | awk 'NR == 1 { print $1 }')"
fi

if [[ -e "${backup_file}" || -e "${backup_file}.sha256" || -e "${backup_file}.m05-manifest" ]]; then
  echo "backup target name already exists" >&2
  exit 3
fi
mv "${tmp_file}" "${backup_file}"
rm -f "${tmp_file}.sha256"
backup_dirname="$(dirname "${backup_file}")"
backup_name="$(basename "${backup_file}")"
(cd "${backup_dirname}" && sha256sum "${backup_name}" >"${backup_name}.sha256")
(cd "${backup_dirname}" && sha256sum -c "${backup_name}.sha256") >/dev/null

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  manifest_file="${backup_file}.m05-manifest"
  MANIFEST_TMP_FILE="$(mktemp "${BACKUP_DIR}/.pinvi-${SCHEMA}-${timestamp}.manifest.XXXXXX")"
  {
    printf 'version=1\n'
    printf 'dump_filename=%s\n' "${backup_name}"
    printf 'schema=%s\n' "${SCHEMA}"
    printf 'dump_sha256=%s\n' "$(sha256sum "${backup_file}" | awk 'NR == 1 { print $1 }')"
    printf 'pg_restore_list_sha256=%s\n' "${restore_list_sha256}"
    printf 'source_database=%s\n' "${source_database}"
    printf 'source_database_oid=%s\n' "${source_database_oid}"
    printf 'source_system_identifier=%s\n' "${source_system_identifier}"
    printf 'source_hostaddr=%s\n' "${source_hostaddr}"
    printf 'source_port=%s\n' "${source_port}"
  } >"${MANIFEST_TMP_FILE}"
  chmod 600 "${MANIFEST_TMP_FILE}"
  mv "${MANIFEST_TMP_FILE}" "${manifest_file}"
  MANIFEST_TMP_FILE=""
  # ordinary API는 dump/manifest가 아닌 이 metadata-only catalog만 read-only mount한다.
  CATALOG_TMP_FILE="$(mktemp "${catalog_dir}/.pinvi-backup-catalog.XXXXXX")"
  backup_size_bytes="$(stat -c '%s' "${backup_file}")"
  backup_created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    printf '{"snapshots":[{'
    printf '"checksum_sha256":"%s",' "$(sha256sum "${backup_file}" | awk 'NR == 1 { print $1 }')"
    printf '"created_at":"%s",' "${backup_created_at}"
    printf '"filename":"%s",' "${backup_name}"
    printf '"size_bytes":%s,' "${backup_size_bytes}"
    printf '"snapshot_id":"%s",' "${backup_name%.dump}"
    printf '"status":"verified"}],"version":1}\n'
  } >"${CATALOG_TMP_FILE}"
  chmod 600 "${CATALOG_TMP_FILE}"
  mv "${CATALOG_TMP_FILE}" "${BACKUP_CATALOG_PATH}"
  CATALOG_TMP_FILE=""
fi

trap - EXIT

echo "BACKUP_FILE=${backup_file}"
