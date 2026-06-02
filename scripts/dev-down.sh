#!/usr/bin/env bash
# Stop local dev services that use TripMate's fixed dev ports.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="${ROOT}/.tmp/dev/pids"

PORTS=(
  "${TRIPMATE_API_DEV_PORT:-9021}"
  "${TRIPMATE_WEB_DEV_PORT:-9022}"
  "${TRIPMATE_DAGSTER_DEV_PORT:-9023}"
)

kill_pid_file() {
  local name="$1"
  local file="${PID_DIR}/${name}.pid"

  if [[ ! -f "${file}" ]]; then
    return
  fi

  local pid
  pid="$(cat "${file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "==> stopping ${name} pid ${pid}"
    kill "${pid}" 2>/dev/null || true
  fi
  rm -f "${file}"
}

kill_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "${port}" 2>/dev/null || true)"
  fi

  if [[ -z "${pids}" ]]; then
    return
  fi

  echo "==> port ${port} occupied by ${pids}; terminating"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 1
  for pid in ${pids}; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  done
}

kill_pid_file api
kill_pid_file web
kill_pid_file dagster

for port in "${PORTS[@]}"; do
  kill_port "${port}"
done

echo "==> dev ports clear: ${PORTS[*]}"
