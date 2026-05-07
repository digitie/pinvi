#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")
SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-reset-and-start.sh --yes [--duration-hours 6] [--check-interval-minutes 10]

로컬/검증용 Docker volume을 삭제하고 TripMate DB, Airflow DB를 새로 만든 뒤
migration, 로컬 기준 파일 적재, Airflow DAG trigger를 수행한다.
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
    *)
      usage >&2
      exit 2
      ;;
  esac
done

cd "${ROOT_DIR}"

export AIRFLOW_UID="${AIRFLOW_UID:-$(id -u)}"
export TRIPMATE_ETL_CONFIG_PATH="${TRIPMATE_ETL_CONFIG_PATH:-/opt/tripmate/config/etl-datasets.soak.json}"

mkdir -p .tmp/airflow-downloads .tmp/airflow-logs "${SOAK_DIR}"

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. API 인증키를 저장한 뒤 다시 실행하세요." >&2
  exit 1
fi

for key in TRIPMATE_DATA_GO_SERVICE_KEY TRIPMATE_OPINET_API_KEY TRIPMATE_EXPRESSWAY_API_KEY; do
  if ! grep -Eq "^${key}=.+" .env; then
    echo ".env에 ${key} 값이 필요합니다." >&2
    exit 1
  fi
done

echo "Docker volume을 초기화하고 soak용 Airflow stack을 시작합니다."
"${COMPOSE[@]}" down -v --remove-orphans
"${COMPOSE[@]}" up -d --build postgres airflow-postgres airflow-redis airflow-init airflow-webserver airflow-scheduler airflow-dag-processor airflow-worker

wait_for_healthy() {
  local service="$1"
  local container_id
  local status
  local attempt
  for attempt in $(seq 1 90); do
    container_id="$("${COMPOSE[@]}" ps -q "${service}")"
    if [[ -n "${container_id}" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
      if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
        echo "${service}: ${status}"
        return 0
      fi
    fi
    sleep 10
  done
  echo "${service}가 제한 시간 안에 healthy/running 상태가 되지 못했습니다." >&2
  return 1
}

wait_for_healthy postgres
wait_for_healthy airflow-webserver
wait_for_healthy airflow-scheduler
wait_for_healthy airflow-worker

echo "Alembic migration을 빈 DB에 적용합니다."
"${COMPOSE[@]}" exec -T airflow-scheduler bash -lc \
  'cd /opt/tripmate/apps/api && python -c "from alembic.config import main; main(argv=[\"upgrade\", \"head\"])"'

LEGAL_CODE_CSV="$(find "${ROOT_DIR}/dataset" -maxdepth 1 -type f -name '*법정동코드*.csv' | sort | tail -n 1 || true)"
if [[ -n "${LEGAL_CODE_CSV}" ]]; then
  LEGAL_CODE_CONTAINER_PATH="/opt/tripmate/dataset/$(basename "${LEGAL_CODE_CSV}")"
  echo "법정동코드 기준 CSV를 적재합니다: $(basename "${LEGAL_CODE_CSV}")"
  "${COMPOSE[@]}" exec -T airflow-scheduler bash -lc \
    "cd /opt/tripmate/apps/api && python -m app.cli.legal_dong_code '${LEGAL_CODE_CONTAINER_PATH}'"
else
  echo "dataset/ 하위에서 법정동코드 CSV를 찾지 못했습니다. legal_dong_code_standard DAG 다운로드에 의존합니다." >&2
fi

VWorld_ZIPS=(
  /opt/tripmate/dataset/N3A_G0010000.zip
  /opt/tripmate/dataset/N3A_G0100000.zip
  /opt/tripmate/dataset/N3A_G0110000.zip
)
if [[ -f "${ROOT_DIR}/dataset/N3A_G0010000.zip" && -f "${ROOT_DIR}/dataset/N3A_G0100000.zip" && -f "${ROOT_DIR}/dataset/N3A_G0110000.zip" ]]; then
  echo "VWorld 행정경계 SHP ZIP 3종을 적재합니다."
  "${COMPOSE[@]}" exec -T airflow-scheduler bash -lc \
    "cd /opt/tripmate/apps/api && python -m app.cli.vworld_boundary ${VWorld_ZIPS[*]}"
else
  echo "dataset/ 하위에서 VWorld SHP ZIP 3종을 모두 찾지 못했습니다. 경계 기반 ETL 일부가 빈 결과가 될 수 있습니다." >&2
fi

date -u +%s > "${SOAK_DIR}/started-at"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SOAK_DIR}/started-at-iso"
printf '%s\n' "${DURATION_HOURS}" > "${SOAK_DIR}/duration-hours"
printf '%s\n' "${CHECK_INTERVAL_MINUTES}" > "${SOAK_DIR}/check-interval-minutes"

"${ROOT_DIR}/scripts/etl-soak-trigger-all.sh"
"${ROOT_DIR}/scripts/etl-soak-status.sh" | tee "${SOAK_DIR}/initial-status.log"

echo "ETL soak가 시작되었습니다. ${CHECK_INTERVAL_MINUTES}분 단위 점검으로 ${DURATION_HOURS}시간 동안 확인합니다."
