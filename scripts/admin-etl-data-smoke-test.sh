#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")
PROFILED_COMPOSE=("${COMPOSE[@]}" --profile admin)
API_PORT="${TRIPMATE_API_PORT:-18082}"
WEB_PORT="${TRIPMATE_WEB_PORT:-13082}"
DAGSTER_PORT="${TRIPMATE_DAGSTER_PORT:-23000}"
KEEP_RUNNING=false
REQUIRE_LOADED_DATA=true

usage() {
  cat <<'USAGE'
Usage: scripts/admin-etl-data-smoke-test.sh [--keep-running] [--allow-empty]

ETL용 docker-compose.yml의 Postgres를 그대로 사용해 관리자 API/Web을 올리고,
기본 관리자 로그인, 관리자 데이터셋 목록, etl_run_logs row 조회, 웹 /admin/login
응답을 확인한다.

--keep-running  검증 후 api/web 컨테이너를 유지한다.
--allow-empty    ETL row가 아직 없는 초기 migration smoke에서도 통과한다.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-running)
      KEEP_RUNNING=true
      shift
      ;;
    --allow-empty)
      REQUIRE_LOADED_DATA=false
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

cleanup() {
  if [[ "${KEEP_RUNNING}" == "false" ]]; then
    "${COMPOSE[@]}" stop web api >/dev/null 2>&1 || true
    "${COMPOSE[@]}" rm -f web api >/dev/null 2>&1 || true
  fi
}

wait_for_container_health() {
  local service_name="$1"
  local container_id
  container_id="$("${PROFILED_COMPOSE[@]}" ps -q "${service_name}")"

  for _ in {1..90}; do
    local status
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}" 2>/dev/null || true)"
    if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
      return 0
    fi
    sleep 2
  done

  "${PROFILED_COMPOSE[@]}" logs --tail=200 "${service_name}" >&2 || true
  echo "${service_name} health check failed" >&2
  return 1
}

wait_for_http() {
  local url="$1"
  python3 - "${url}" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1]
last_error = None
for _ in range(90):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if 200 <= response.status < 500:
                print(f"{url} -> {response.status}")
                raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
    time.sleep(2)

raise SystemExit(f"{url} did not respond: {last_error}")
PY
}

admin_api_smoke() {
  python3 - "${API_PORT}" "${REQUIRE_LOADED_DATA}" <<'PY'
import http.cookiejar
import json
import sys
import urllib.request

api_port = sys.argv[1]
require_loaded_data = sys.argv[2].lower() == "true"
base_url = f"http://127.0.0.1:{api_port}"

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

login_request = urllib.request.Request(
    f"{base_url}/admin/auth/login",
    data=json.dumps({"email": "admin@ad.min", "password": "admin"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with opener.open(login_request, timeout=10) as response:
    payload = json.loads(response.read().decode())
    assert response.status == 200
    assert payload["user"]["email"] == "admin@ad.min"

with opener.open(f"{base_url}/admin/datasets", timeout=20) as response:
    dataset_payload = json.loads(response.read().decode())
    assert response.status == 200

datasets = dataset_payload["datasets"]
table_counts = {dataset["table_name"]: int(dataset["row_count"]) for dataset in datasets}
table_names = set(table_counts)

assert "users" not in table_names
assert "sessions" not in table_names
assert "etl_run_logs" in table_names

required_etl_tables = {
    "address_code_standard",
    "fuel_serving_avg_price",
    "rest_area_serving_master",
    "weather_serving_short_term",
    "air_quality_serving_station",
    "map_features",
}
missing = sorted(required_etl_tables - table_names)
assert not missing, f"missing expected admin ETL tables: {missing}"

with opener.open(f"{base_url}/admin/datasets/etl_run_logs/rows?limit=50", timeout=20) as response:
    rows_payload = json.loads(response.read().decode())
    assert response.status == 200
    assert rows_payload["table_name"] == "etl_run_logs"

if require_loaded_data:
    assert table_counts["etl_run_logs"] > 0, "etl_run_logs has no rows"
    loaded_tables = {
        name: table_counts[name]
        for name in sorted(required_etl_tables)
        if table_counts.get(name, 0) > 0
    }
    assert loaded_tables, "no loaded ETL serving/source table rows are visible to admin"
    assert rows_payload["rows"], "etl_run_logs rows endpoint returned no rows"
else:
    loaded_tables = {}

print(
    json.dumps(
        {
            "admin_api": "passed",
            "dataset_count": len(datasets),
            "etl_run_logs": table_counts["etl_run_logs"],
            "loaded_tables": loaded_tables,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
}

trap cleanup EXIT

cd "${ROOT_DIR}"

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. ETL/Admin smoke는 저장소 루트 .env를 사용합니다." >&2
  exit 1
fi

export TRIPMATE_API_PORT="${API_PORT}"
export TRIPMATE_WEB_PORT="${WEB_PORT}"
export TRIPMATE_DAGSTER_PORT="${DAGSTER_PORT}"
export NEXT_PUBLIC_TRIPMATE_API_URL="${NEXT_PUBLIC_TRIPMATE_API_URL:-http://127.0.0.1:${API_PORT}}"
export NEXT_PUBLIC_TRIPMATE_DAGSTER_URL="${NEXT_PUBLIC_TRIPMATE_DAGSTER_URL:-http://127.0.0.1:${DAGSTER_PORT}}"

"${COMPOSE[@]}" up -d postgres
wait_for_container_health postgres

"${PROFILED_COMPOSE[@]}" up -d --build api web
wait_for_container_health api
wait_for_http "http://127.0.0.1:${WEB_PORT}/admin/login"
admin_api_smoke

echo "admin ETL data smoke passed"
echo "web: http://127.0.0.1:${WEB_PORT}/admin/login"
echo "api: http://127.0.0.1:${API_PORT}/health"
echo "dagster: http://127.0.0.1:${DAGSTER_PORT}"
