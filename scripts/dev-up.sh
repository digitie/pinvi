#!/usr/bin/env bash
# Start Pinvi local dev services on fixed ports.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="${ROOT}/.tmp/dev/pids"
LOG_DIR="${ROOT}/.tmp/dev/logs"

API_PORT="${PINVI_API_DEV_PORT:-12801}"
WEB_PORT="${PINVI_WEB_DEV_PORT:-12805}"
DAGSTER_PORT="${PINVI_DAGSTER_DEV_PORT:-12802}"

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
export TMPDIR=/tmp
export TMP=/tmp
export TEMP=/tmp
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  . "${HOME}/.nvm/nvm.sh"
fi

mkdir -p "${PID_DIR}" "${LOG_DIR}"

"${ROOT}/scripts/dev-down.sh"

require_linux_command() {
  local name="$1"
  local path

  path="$(command -v "${name}" 2>/dev/null || true)"
  if [[ -z "${path}" ]]; then
    echo "ERROR: ${name} not found in WSL PATH" >&2
    exit 1
  fi
  if [[ "${path}" == /mnt/c/* || "${path}" == *.exe || "${path}" == *.cmd ]]; then
    echo "ERROR: ${name} resolves to Windows shim: ${path}" >&2
    exit 1
  fi
}

require_linux_command uv
require_linux_command node
require_linux_command npm

start_service() {
  local name="$1"
  shift

  echo "==> starting ${name}: $*"
  (
    cd "${ROOT}"
    if command -v setsid >/dev/null 2>&1; then
      setsid "$@" >"${LOG_DIR}/${name}.log" 2>&1 &
    else
      nohup "$@" >"${LOG_DIR}/${name}.log" 2>&1 &
    fi
    echo "$!" >"${PID_DIR}/${name}.pid"
  )
}

start_service api \
  bash -lc "cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port ${API_PORT}"

start_service web \
  env NEXT_PUBLIC_PINVI_API_URL="http://localhost:${API_PORT}" \
    npm --workspace apps/web run dev

start_service dagster \
  bash -lc "cd apps/etl && uv run dagster dev --host 0.0.0.0 --port ${DAGSTER_PORT}"

echo "==> API     http://localhost:${API_PORT}"
echo "==> Web     http://localhost:${WEB_PORT}"
echo "==> Dagster http://localhost:${DAGSTER_PORT}"
echo "==> logs    ${LOG_DIR}"
