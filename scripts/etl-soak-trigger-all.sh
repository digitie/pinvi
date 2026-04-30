#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-trigger-all.sh

soak 검증 대상 Airflow DAG를 unpause하고 같은 suffix로 1회 수동 trigger한다.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

cd "${ROOT_DIR}"

REQUIRED_DAGS=(
  legal_dong_code_standard_quarterly
  juso_monthly_address_dataset
  opinet_region_code_quarterly
  opinet_avg_price_daily
  opinet_lowest_station_daily
  rest_area_master_monthly
  rest_area_oil_price_daily
  rest_area_service_monthly
  weather_short_term_sigungu_grid
  weather_kma_alert
  weather_mid_term_nationwide
  air_quality_station_daily
  air_quality_forecast_daily
  air_quality_sido_measurement_hourly
  kma_recommended_tour_course_annual
  kma_beach_catalog_annual
  kma_beach_ultra_short_forecast_hourly
  kma_beach_village_forecast_3hourly
  kma_beach_wave_height_hourly
  kma_beach_water_temperature_hourly
  kma_beach_tide_sun_daily
  mof_beach_info_annual
  mof_beach_water_quality_annual
  public_cultural_festival_quarterly
  public_arboretum_basic_annual
  public_tourist_information_center_annual
  public_recreation_forest_semiannual
  public_museum_art_gallery_annual
  public_campground_daily
)

DAGS=("${REQUIRED_DAGS[@]}")

env_file_has_value() {
  local key="$1"
  [[ -n "${!key:-}" ]] || grep -Eq "^${key}=.+" .env 2>/dev/null
}

if env_file_has_value TRIPMATE_KHOA_API_KEY; then
  DAGS+=(
    khoa_beach_observation_hourly
    khoa_beach_index_forecast_twice_daily
    khoa_mudflat_index_forecast_twice_daily
    khoa_sea_split_index_forecast_twice_daily
  )
else
  echo "TRIPMATE_KHOA_API_KEY가 없어 KHOA 지수/관측 DAG 4개는 이번 수동 trigger에서 제외합니다." >&2
fi

run_airflow() {
  "${COMPOSE[@]}" exec -T airflow-scheduler airflow "$@"
}

wait_for_dag() {
  local dag_id="$1"
  local attempt
  for attempt in $(seq 1 60); do
    if run_airflow dags list | awk '{print $1}' | grep -Fxq "${dag_id}"; then
      return 0
    fi
    sleep 10
  done
  echo "DAG ${dag_id}를 Airflow에서 찾지 못했습니다." >&2
  return 1
}

RUN_SUFFIX="$(date +%Y%m%dT%H%M%S%z)"
JUSO_SOURCE_YEAR_MONTH="${TRIPMATE_JUSO_SOAK_SOURCE_YEAR_MONTH:-}"
if [[ -z "${JUSO_SOURCE_YEAR_MONTH}" ]]; then
  KST_DAY="$(TZ=Asia/Seoul date +%d)"
  JUSO_MONTH_OFFSET=1
  if ((10#${KST_DAY} < 10)); then
    JUSO_MONTH_OFFSET=2
  fi
  JUSO_SOURCE_YEAR_MONTH="$(
    TZ=Asia/Seoul date -d "$(TZ=Asia/Seoul date +%Y-%m-15) -${JUSO_MONTH_OFFSET} month" +%Y%m
  )"
fi

for dag_id in "${DAGS[@]}"; do
  wait_for_dag "${dag_id}"
  run_airflow dags unpause "${dag_id}" >/dev/null || true
  if [[ "${dag_id}" == "juso_monthly_address_dataset" ]]; then
    run_airflow dags trigger "${dag_id}" \
      --run-id "manual__soak__${RUN_SUFFIX}__${dag_id}" \
      --conf "{\"source_year_month\":\"${JUSO_SOURCE_YEAR_MONTH}\"}"
  else
    run_airflow dags trigger "${dag_id}" --run-id "manual__soak__${RUN_SUFFIX}__${dag_id}"
  fi
done

echo "Triggered ${#DAGS[@]} DAGs for soak run ${RUN_SUFFIX}."
echo "Juso manual source_year_month=${JUSO_SOURCE_YEAR_MONTH}"
