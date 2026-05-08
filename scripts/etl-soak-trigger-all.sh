#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-trigger-all.sh

soak 검증 대상 Dagster job을 같은 suffix 기준으로 1회 수동 실행한다.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

cd "${ROOT_DIR}"

SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"
mkdir -p "${SOAK_DIR}"

REQUIRED_JOBS=(
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

JOBS=("${REQUIRED_JOBS[@]}")

env_file_has_value() {
  local key="$1"
  [[ -n "${!key:-}" ]] || grep -Eq "^${key}=.+" .env 2>/dev/null
}

if env_file_has_value TRIPMATE_KHOA_API_KEY; then
  JOBS+=(
    khoa_beach_observation_hourly
    khoa_beach_index_forecast_twice_daily
    khoa_mudflat_index_forecast_twice_daily
    khoa_sea_split_index_forecast_twice_daily
  )
else
  echo "TRIPMATE_KHOA_API_KEY가 없어 KHOA 지수/관측 job 4개는 이번 수동 실행에서 제외합니다." >&2
fi

run_dagster() {
  "${COMPOSE[@]}" exec -T dagster "$@"
}

wait_for_job() {
  local job_id="$1"
  local attempt
  for attempt in $(seq 1 60); do
    if run_dagster dagster job list -m app.dagster_etl.definitions | grep -Fq "${job_id}"; then
      return 0
    fi
    sleep 10
  done
  echo "Dagster job ${job_id}를 찾지 못했습니다." >&2
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

for job_id in "${JOBS[@]}"; do
  wait_for_job "${job_id}"
  if [[ "${job_id}" == "juso_monthly_address_dataset" ]]; then
    config_path="${SOAK_DIR}/juso-run-config-${RUN_SUFFIX}.yaml"
    cat > "${config_path}" <<YAML
ops:
  download_and_load_juso_monthly_address:
    config:
      run_type: manual
      source_year_month: "${JUSO_SOURCE_YEAR_MONTH}"
YAML
    run_dagster dagster job execute \
      -m app.dagster_etl.definitions \
      -j "${job_id}" \
      -c "/opt/tripmate/.tmp/etl-soak/$(basename "${config_path}")"
  else
    run_dagster dagster job execute -m app.dagster_etl.definitions -j "${job_id}"
  fi
done

echo "Executed ${#JOBS[@]} Dagster jobs for soak run ${RUN_SUFFIX}."
echo "Juso manual source_year_month=${JUSO_SOURCE_YEAR_MONTH}"
