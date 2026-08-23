#!/usr/bin/env bash
# Create a Pinvi app-schema PostgreSQL custom-format backup.

set -euo pipefail

unset PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PSQLRC

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PINVI_BACKUP_DIR:-${ROOT_DIR}/.tmp/backups}"
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
if [[ -z "${PG_DUMP_BIN}" && "${STRICT_ENVIRONMENT}" == "1" ]]; then
  PG_DUMP_BIN="$(pinned_tool pg_dump || true)"
fi
if [[ -z "${PG_DUMP_BIN}" ]]; then
  PG_DUMP_BIN="pg_dump"
fi

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  if [[ "${BACKUP_DIR}" != /* || -L "${BACKUP_DIR}" ]]; then
    echo "strict backup requires an absolute non-symlink backup directory" >&2
    exit 3
  fi
  if [[ "${DOCKER_FALLBACK}" == "1" ]]; then
    echo "strict backup forbids docker pg_dump fallback" >&2
    exit 3
  fi
  if [[ "${PG_DUMP_BIN}" != /* || ! -f "${PG_DUMP_BIN}" || ! -x "${PG_DUMP_BIN}" || -L "${PG_DUMP_BIN}" ]]; then
    echo "strict backup requires a regular pinned pg_dump executable" >&2
    exit 3
  fi
  resolved_pg_dump="$(realpath -e "${PG_DUMP_BIN}")"
  case "${resolved_pg_dump}" in
    /usr/local/bin/pg_dump|/usr/bin/pg_dump|/bin/pg_dump|/usr/lib/postgresql/[0-9]*/bin/pg_dump) ;;
    *)
      if [[ "${PINVI_BACKUP_PRIVATE_TOOL_COPY:-0}" != "1" ]]; then
        echo "strict backup pg_dump is outside the trusted tool directories" >&2
        exit 3
      fi
      ;;
  esac
  if [[ ! "${PINVI_BACKUP_PG_DUMP_SHA256:-}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "strict backup requires a pg_dump digest pin" >&2
    exit 3
  fi
  if [[ "$(sha256sum "${PG_DUMP_BIN}" | awk 'NR == 1 { print $1 }')" != "${PINVI_BACKUP_PG_DUMP_SHA256}" ]]; then
    echo "strict backup pg_dump digest pin failed" >&2
    exit 3
  fi
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PINVI_DATABASE_URL or PINVI_BACKUP_DATABASE_URL is required" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]]; then
  DATABASE_URL="postgresql://${DATABASE_URL#postgresql+asyncpg://}"
fi

if [[ ! "${SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "invalid backup schema name" >&2
  exit 2
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum not found" >&2
  exit 127
fi

mkdir -p "${BACKUP_DIR}"
if [[ "${STRICT_ENVIRONMENT}" == "1" && ! -d "${BACKUP_DIR}" ]]; then
  echo "strict backup directory is not a regular directory" >&2
  exit 3
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
cleanup() {
  rm -f "${tmp_file}" "${tmp_file}.sha256"
  if [[ -n "${PRIVATE_TOOL_DIR}" && -d "${PRIVATE_TOOL_DIR}" ]]; then
    rm -rf "${PRIVATE_TOOL_DIR}"
  fi
}
trap cleanup EXIT

if [[ "${STRICT_ENVIRONMENT}" == "1" ]]; then
  PRIVATE_TOOL_DIR="$(mktemp -d)"
  chmod 700 "${PRIVATE_TOOL_DIR}"
  cp -- "${PG_DUMP_BIN}" "${PRIVATE_TOOL_DIR}/pg_dump"
  chmod 700 "${PRIVATE_TOOL_DIR}/pg_dump"
  if [[ "$(sha256sum "${PRIVATE_TOOL_DIR}/pg_dump" | awk 'NR == 1 { print $1 }')" != "${PINVI_BACKUP_PG_DUMP_SHA256}" ]]; then
    echo "strict backup pg_dump changed while copying to the private directory" >&2
    exit 3
  fi
  PG_DUMP_BIN="${PRIVATE_TOOL_DIR}/pg_dump"
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

run_pg_dump

tmp_dir="$(dirname "${tmp_file}")"
tmp_name="$(basename "${tmp_file}")"
(cd "${tmp_dir}" && sha256sum "${tmp_name}" >"${tmp_name}.sha256")
(cd "${tmp_dir}" && sha256sum -c "${tmp_name}.sha256") >/dev/null

mv "${tmp_file}" "${backup_file}"
trap - EXIT
rm -f "${tmp_file}.sha256"
backup_dirname="$(dirname "${backup_file}")"
backup_name="$(basename "${backup_file}")"
(cd "${backup_dirname}" && sha256sum "${backup_name}" >"${backup_name}.sha256")
(cd "${backup_dirname}" && sha256sum -c "${backup_name}.sha256") >/dev/null

echo "BACKUP_FILE=${backup_file}"
