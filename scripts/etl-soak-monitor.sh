#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOAK_DIR="${ROOT_DIR}/.tmp/etl-soak"

usage() {
  cat <<'USAGE'
Usage: scripts/etl-soak-monitor.sh [--duration-hours 6] [--check-interval-minutes 10]
       scripts/etl-soak-monitor.sh --strict

etl-soak-status.sh를 주기적으로 실행해 .tmp/etl-soak/status-*.log에 저장한다.
운영 DB가 아니라 로컬/검증용 soak stack 상태 확인에만 사용한다.
--strict를 주면 Dagster/Postgres 미실행, 최신 ETL failed 상태, 미해결 관리자 알림을
발견했을 때 즉시 실패(exit 1)한다.
USAGE
}

DURATION_HOURS=6
CHECK_INTERVAL_MINUTES=10
STRICT=false
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
    --strict)
      STRICT=true
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

cd "${ROOT_DIR}"
mkdir -p "${SOAK_DIR}"
printf '%s\n' "${DURATION_HOURS}" > "${SOAK_DIR}/duration-hours"
printf '%s\n' "${CHECK_INTERVAL_MINUTES}" > "${SOAK_DIR}/check-interval-minutes"

COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

strict_check() {
  local started_epoch
  started_epoch="$(cat "${SOAK_DIR}/started-at" 2>/dev/null || date -u +%s)"

  for service in postgres dagster; do
    if ! "${COMPOSE[@]}" ps --status running --services | grep -qx "${service}"; then
      echo "[FAIL] ${service} service가 running 상태가 아닙니다." >&2
      "${COMPOSE[@]}" ps >&2 || true
      return 1
    fi
  done

  local latest_failed_count
  latest_failed_count="$(
    "${COMPOSE[@]}" exec -T postgres psql -U tripmate -d tripmate -tAX \
      -v ON_ERROR_STOP=1 \
      -v started_epoch="${started_epoch}" <<'SQL'
WITH latest AS (
  SELECT
    dataset_key,
    status,
    extra,
    row_number() OVER (
      PARTITION BY dataset_key
      ORDER BY started_at DESC NULLS LAST, id DESC
    ) AS rn
  FROM etl_run_logs
  WHERE started_at >= to_timestamp(:started_epoch)
)
SELECT count(*)
FROM latest
WHERE rn = 1
  AND status = 'failed'
  AND coalesce((extra ->> 'retry_exhausted')::boolean, true);
SQL
  )"

  local unresolved_admin_notifications
  unresolved_admin_notifications="$(
    "${COMPOSE[@]}" exec -T postgres psql -U tripmate -d tripmate -tAX \
      -v ON_ERROR_STOP=1 \
      -v started_epoch="${started_epoch}" <<'SQL'
SELECT count(*)
FROM admin_notifications AS notification
LEFT JOIN LATERAL (
  SELECT
    status,
    extra
  FROM etl_run_logs
  WHERE dataset_key = notification.dataset_key
    AND started_at >= notification.created_at
  ORDER BY started_at DESC NULLS LAST, id DESC
  LIMIT 1
) AS latest_after_notification ON true
WHERE notification.source = 'etl'
  AND notification.is_resolved = false
  AND notification.created_at >= to_timestamp(:started_epoch)
  AND NOT (
    latest_after_notification.status IN ('started', 'success', 'skipped')
    OR (
      latest_after_notification.status = 'failed'
      AND coalesce((latest_after_notification.extra ->> 'retry_exhausted')::boolean, true) = false
    )
  );
SQL
  )"

  if (( latest_failed_count > 0 || unresolved_admin_notifications > 0 )); then
    echo "[FAIL] ETL strict check failed: latest_failed=${latest_failed_count}, unresolved_admin_notifications=${unresolved_admin_notifications}" >&2
    "${COMPOSE[@]}" exec -T postgres psql -U tripmate -d tripmate -v ON_ERROR_STOP=1 <<'SQL' >&2
WITH latest AS (
  SELECT
    dataset_key,
    run_key,
    run_type,
    status,
    extra,
    left(coalesce(message, error_message, ''), 220) AS message,
    started_at,
    finished_at,
    row_number() OVER (
      PARTITION BY dataset_key
      ORDER BY started_at DESC NULLS LAST, id DESC
    ) AS rn
  FROM etl_run_logs
)
SELECT dataset_key, run_key, run_type, status, message, started_at, finished_at
FROM latest
WHERE rn = 1
  AND status = 'failed'
  AND coalesce((extra ->> 'retry_exhausted')::boolean, true)
ORDER BY dataset_key;

SELECT dataset_key, severity, title, left(message, 220) AS message, created_at
FROM admin_notifications
WHERE source = 'etl' AND is_resolved = false
ORDER BY created_at DESC
LIMIT 20;
SQL
    return 1
  fi
}

started_at="$(date -u +%s)"
if [[ -f "${SOAK_DIR}/started-at" ]]; then
  started_at="$(cat "${SOAK_DIR}/started-at")"
fi
deadline=$((started_at + DURATION_HOURS * 3600))

while true; do
  now="$(date -u +%s)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_path="${SOAK_DIR}/status-${stamp}.log"
  set +e
  "${ROOT_DIR}/scripts/etl-soak-status.sh" | tee "${log_path}"
  status_exit="${PIPESTATUS[0]}"
  set -e
  cp "${log_path}" "${SOAK_DIR}/latest-status.log"
  if (( status_exit != 0 )); then
    echo "[FAIL] etl-soak-status.sh 실패(exit=${status_exit})." >&2
    exit "${status_exit}"
  fi
  if [[ "${STRICT}" == "true" ]]; then
    strict_check
  fi
  if (( now >= deadline )); then
    echo "soak 목표 시간에 도달했습니다: ${DURATION_HOURS}시간"
    exit 0
  fi
  sleep $((CHECK_INTERVAL_MINUTES * 60))
done
