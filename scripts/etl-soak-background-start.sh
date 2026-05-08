#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-background-start.sh --yes [--duration-hours 6] [--check-interval-minutes 10]

DB 초기화/기준 파일 적재/Dagster job 수동 실행과 strict monitor를 백그라운드로 시작한다.
reset-start.log, monitor.log, pid 파일은 .tmp/etl-soak/ 아래에 남긴다.
운영 DB에서 실행하지 않는다.
USAGE
}

if [[ "${1:-}" != "--yes" ]]; then
  usage >&2
  exit 2
fi
shift

DURATION_HOURS=6
CHECK_INTERVAL_MINUTES=10
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration-hours)
      DURATION_HOURS="${2:?--duration-hours 값이 필요합니다.}"
      shift 2
      ;;
    --check-interval-minutes)
      CHECK_INTERVAL_MINUTES="${2:?--check-interval-minutes 값이 필요합니다.}"
      shift 2
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

cd "${ROOT_DIR}"
mkdir -p "${SOAK_DIR}"

rm -f \
  "${SOAK_DIR}/reset-start.log" \
  "${SOAK_DIR}/monitor.log" \
  "${SOAK_DIR}/reset-start.pid" \
  "${SOAK_DIR}/monitor.pid" \
  "${SOAK_DIR}/started-at" \
  "${SOAK_DIR}/started-at-iso" \
  "${SOAK_DIR}/duration-hours" \
  "${SOAK_DIR}/check-interval-minutes"

start_detached() {
  local name="$1"
  local command="$2"
  nohup setsid bash -lc "${command}" >/dev/null 2>&1 &
  local pid=$!
  printf '%s\n' "${pid}" > "${SOAK_DIR}/${name}.pid"
  echo "${name} pid=${pid}"
}

reset_command=$(
  printf "cd %q && scripts/etl-soak-reset-and-start.sh --yes --duration-hours %q --check-interval-minutes %q > %q 2>&1" \
    "${ROOT_DIR}" \
    "${DURATION_HOURS}" \
    "${CHECK_INTERVAL_MINUTES}" \
    "${SOAK_DIR}/reset-start.log"
)
monitor_command=$(
  printf "cd %q && while [ ! -f %q ]; do sleep 10; done; scripts/etl-soak-monitor.sh --duration-hours %q --check-interval-minutes %q --strict > %q 2>&1" \
    "${ROOT_DIR}" \
    "${SOAK_DIR}/started-at" \
    "${DURATION_HOURS}" \
    "${CHECK_INTERVAL_MINUTES}" \
    "${SOAK_DIR}/monitor.log"
)

start_detached reset-start "${reset_command}"
start_detached monitor "${monitor_command}"

echo "reset log: ${SOAK_DIR}/reset-start.log"
echo "monitor log: ${SOAK_DIR}/monitor.log"
