#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")
SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"

cd "${ROOT_DIR}"
mkdir -p "${SOAK_DIR}"

run_or_warn() {
  local title="$1"
  shift
  echo
  echo "== ${title} =="
  if ! "$@"; then
    echo "[WARN] ${title} 확인에 실패했습니다." >&2
  fi
}

show_elapsed() {
  local marker="${SOAK_DIR}/started-at"
  local target_hours=6
  if [[ -f "${SOAK_DIR}/duration-hours" ]]; then
    target_hours="$(cat "${SOAK_DIR}/duration-hours")"
  fi
  if [[ ! -f "${marker}" ]]; then
    echo "soak 시작 marker가 없습니다: ${marker}"
    return 0
  fi

  local started now elapsed_hours
  started="$(cat "${marker}")"
  now="$(date -u +%s)"
  elapsed_hours=$(( (now - started) / 3600 ))
  echo "soak 경과 시간: ${elapsed_hours}시간 / 목표 ${target_hours}시간"
  if (( elapsed_hours >= target_hours )); then
    echo "${target_hours}시간 최종 검증 창에 도달했습니다."
  fi
}

run_sql() {
  "${COMPOSE[@]}" exec -T postgres psql -U tripmate -d tripmate -v ON_ERROR_STOP=1 "$@"
}

show_elapsed
run_or_warn "Docker Compose 상태" "${COMPOSE[@]}" ps
run_or_warn "Dagster job 목록" "${COMPOSE[@]}" exec -T dagster dagster job list -m app.dagster_etl.definitions
run_or_warn "Dagster 최근 로그" "${COMPOSE[@]}" logs --tail=120 dagster

run_or_warn "ETL 실행 로그 요약" run_sql <<'SQL'
SELECT
  dataset_key,
  status,
  count(*) AS run_count,
  max(started_at) AS last_started_at,
  max(finished_at) AS last_finished_at
FROM etl_run_logs
GROUP BY dataset_key, status
ORDER BY dataset_key, status;
SQL

run_or_warn "최근 ETL 실행 로그" run_sql <<'SQL'
SELECT
  dataset_key,
  run_key,
  run_type,
  status,
  left(coalesce(message, error_message, ''), 180) AS message,
  started_at,
  finished_at
FROM etl_run_logs
ORDER BY started_at DESC
LIMIT 30;
SQL

run_or_warn "주요 적재 테이블 row count" run_sql <<'SQL'
CREATE OR REPLACE FUNCTION pg_temp.table_count(table_name text) RETURNS bigint AS $$
DECLARE
  row_count bigint;
BEGIN
  IF to_regclass('public.' || table_name) IS NULL THEN
    RETURN NULL;
  END IF;
  EXECUTE format('SELECT count(*) FROM %I', table_name) INTO row_count;
  RETURN row_count;
END;
$$ LANGUAGE plpgsql;

SELECT table_name, row_count
FROM (
  SELECT
    table_name,
    pg_temp.table_count(table_name) AS row_count
  FROM (
    VALUES
      ('address_code_standard'),
      ('region_serving_boundary'),
      ('address_raw_juso_road_address'),
      ('address_serving_juso_road_address'),
      ('address_raw_juso_related_jibun'),
      ('address_serving_juso_related_jibun'),
      ('fuel_serving_opinet_region_code'),
      ('fuel_serving_avg_price'),
      ('fuel_serving_lowest_station'),
      ('rest_area_serving_master'),
      ('rest_area_serving_oil_price'),
      ('rest_area_serving_service'),
      ('weather_short_term_grid_mapping'),
      ('weather_serving_short_term'),
      ('weather_serving_kma_alert'),
      ('weather_serving_mid_term'),
      ('air_quality_serving_station'),
      ('air_quality_serving_forecast'),
      ('air_quality_serving_sido_measurement'),
      ('map_features'),
      ('source_records'),
      ('map_feature_provider_refs'),
      ('places'),
      ('place_source_records'),
      ('place_provider_refs'),
      ('tour_serving_public_cultural_festival'),
      ('weather_beach_location'),
      ('weather_serving_beach'),
      ('beach_profiles'),
      ('beach_provider_refs'),
      ('beach_source_records'),
      ('beach_observations'),
      ('beach_index_forecasts'),
      ('beach_water_quality_measurements'),
      ('ocean_activity_index_locations'),
      ('ocean_activity_index_source_records'),
      ('ocean_activity_index_forecasts')
  ) AS table_list(table_name)
) AS counted
WHERE row_count IS NOT NULL
ORDER BY table_name;
SQL

run_or_warn "관리자/Telegram 알림 대기 상태" run_sql <<'SQL'
SELECT 'admin_notifications_unresolved' AS metric, count(*)
FROM admin_notifications
WHERE is_resolved = false
UNION ALL
SELECT 'telegram_system_outbox_pending' AS metric, count(*)
FROM telegram_system_notification_outbox
WHERE status = 'pending';
SQL
