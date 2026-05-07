#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEPALIVE_DIR="${ROOT_DIR}/.tmp/etl-soak"
PID_FILE="${KEEPALIVE_DIR}/docker-keepalive.pid"

usage() {
  cat <<'USAGE'
Usage: scripts/docker-keepalive.sh [--duration-hours 7] [--interval-seconds 15] [--stop]

Repeatedly calls a lightweight Docker CLI command so Docker Desktop/WSL2
does not idle during long local soak validation. This does not mutate
containers; it only supports local test stability.
USAGE
}

DURATION_HOURS=7
INTERVAL_SECONDS=15
STOP=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration-hours)
      DURATION_HOURS="${2:?--duration-hours requires a value}"
      shift 2
      ;;
    --interval-seconds)
      INTERVAL_SECONDS="${2:?--interval-seconds requires a value}"
      shift 2
      ;;
    --stop)
      STOP=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "${KEEPALIVE_DIR}"

if [[ "${STOP}" == "true" ]]; then
  if [[ -f "${PID_FILE}" ]]; then
    existing_pid="$(cat "${PID_FILE}")"
    if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
      kill "${existing_pid}"
      echo "docker keepalive stopped: ${existing_pid}"
    fi
    rm -f "${PID_FILE}"
  fi
  exit 0
fi

if [[ -f "${PID_FILE}" ]]; then
  existing_pid="$(cat "${PID_FILE}")"
  if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "docker keepalive already running: ${existing_pid}"
    exit 0
  fi
fi

if ! [[ "${DURATION_HOURS}" =~ ^[0-9]+$ && "${INTERVAL_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "duration-hours and interval-seconds must be non-negative integers" >&2
  exit 2
fi

echo "$$" > "${PID_FILE}"
trap 'rm -f "${PID_FILE}"' EXIT

end_epoch=$(( "$(date +%s)" + DURATION_HOURS * 3600 ))
tick=0
echo "docker keepalive started at $(date -Is), duration=${DURATION_HOURS}h, interval=${INTERVAL_SECONDS}s"

while (( "$(date +%s)" < end_epoch )); do
  docker ps >/dev/null
  tick=$((tick + 1))
  if (( tick % 40 == 0 )); then
    echo "docker keepalive tick ${tick} at $(date -Is)"
  fi
  sleep "${INTERVAL_SECONDS}"
done

echo "docker keepalive finished at $(date -Is)"
