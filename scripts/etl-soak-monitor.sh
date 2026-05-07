#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-monitor.sh [--duration-hours 6] [--check-interval-minutes 10]

etl-soak-status.sh를 주기적으로 실행해 .tmp/etl-soak/status-*.log에 저장한다.
운영 DB가 아니라 로컬/검증용 soak stack 상태 확인에만 사용한다.
USAGE
}

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
printf '%s\n' "${DURATION_HOURS}" > "${SOAK_DIR}/duration-hours"
printf '%s\n' "${CHECK_INTERVAL_MINUTES}" > "${SOAK_DIR}/check-interval-minutes"

started_at="$(date -u +%s)"
if [[ -f "${SOAK_DIR}/started-at" ]]; then
  started_at="$(cat "${SOAK_DIR}/started-at")"
fi
deadline=$((started_at + DURATION_HOURS * 3600))

while true; do
  now="$(date -u +%s)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_path="${SOAK_DIR}/status-${stamp}.log"
  "${ROOT_DIR}/scripts/etl-soak-status.sh" | tee "${log_path}"
  cp "${log_path}" "${SOAK_DIR}/latest-status.log"
  if (( now >= deadline )); then
    echo "soak 목표 시간에 도달했습니다: ${DURATION_HOURS}시간"
    exit 0
  fi
  sleep $((CHECK_INTERVAL_MINUTES * 60))
done
