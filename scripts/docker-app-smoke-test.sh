#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infra/docker-compose.app.yml"
PROJECT_NAME="${TRIPMATE_DOCKER_PROJECT:-tripmate-app-smoke}"
API_PORT="${TRIPMATE_API_PORT:-18082}"
WEB_PORT="${TRIPMATE_WEB_PORT:-13082}"
RUSTFS_PORT="${TRIPMATE_RUSTFS_PORT:-19000}"
RUSTFS_CONSOLE_PORT="${TRIPMATE_RUSTFS_CONSOLE_PORT:-19001}"
KEEP_RUNNING=false

if [[ "${1:-}" == "--keep-running" ]]; then
  KEEP_RUNNING=true
fi

compose() {
  docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" "$@"
}

cleanup() {
  if [[ "${KEEP_RUNNING}" == "false" ]]; then
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}

wait_for_container_health() {
  local service_name="$1"
  local container_id
  container_id="$(compose ps -q "${service_name}")"

  for _ in {1..90}; do
    local status
    status="$(docker inspect -f '{{.State.Health.Status}}' "${container_id}" 2>/dev/null || true)"
    if [[ "${status}" == "healthy" ]]; then
      return 0
    fi
    sleep 2
  done

  compose logs --tail=200 "${service_name}" >&2 || true
  echo "${service_name} health check failed" >&2
  return 1
}

wait_for_http() {
  local url="$1"
  python3 - "${url}" <<'PY'
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
last_error = None

for _ in range(90):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if 200 <= response.status < 500:
                print(f"{url} -> {response.status}")
                raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001 - shell smoke output should preserve the last failure
        last_error = exc
    time.sleep(2)

raise SystemExit(f"{url} did not respond: {last_error}")
PY
}

admin_api_smoke() {
  python3 - "${API_PORT}" <<'PY'
import http.cookiejar
import json
import sys
import urllib.request

api_port = sys.argv[1]
base_url = f"http://127.0.0.1:{api_port}"

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

login_request = urllib.request.Request(
    f"{base_url}/admin/auth/login",
    data=json.dumps({"email": "admin@ad.min", "password": "admin"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with opener.open(login_request, timeout=5) as response:
    login_payload = json.loads(response.read().decode())
    assert response.status == 200
    assert login_payload["user"]["email"] == "admin@ad.min"

with opener.open(f"{base_url}/admin/datasets", timeout=5) as response:
    dataset_payload = json.loads(response.read().decode())
    table_names = {dataset["table_name"] for dataset in dataset_payload["datasets"]}
    assert response.status == 200
    assert dataset_payload["default_page_size"] == 100
    assert dataset_payload["page_size_options"] == [50, 100, 200, 500]
    assert "users" not in table_names
    assert "sessions" not in table_names
    assert "etl_run_logs" in table_names

print("admin api smoke passed")
PY
}

trap cleanup EXIT

export TRIPMATE_API_PORT="${API_PORT}"
export TRIPMATE_WEB_PORT="${WEB_PORT}"
export TRIPMATE_RUSTFS_PORT="${RUSTFS_PORT}"
export TRIPMATE_RUSTFS_CONSOLE_PORT="${RUSTFS_CONSOLE_PORT}"
export NEXT_PUBLIC_TRIPMATE_API_URL="${NEXT_PUBLIC_TRIPMATE_API_URL:-http://127.0.0.1:${API_PORT}}"

cd "${ROOT_DIR}"

compose down -v --remove-orphans >/dev/null 2>&1 || true
compose build app-api app-web
compose up -d app-postgres app-rustfs
wait_for_container_health app-postgres
compose up app-rustfs-init
compose run --rm app-api alembic upgrade head
compose up -d app-api app-web
wait_for_container_health app-api
wait_for_http "http://127.0.0.1:${WEB_PORT}/admin/login"
admin_api_smoke

echo "docker app smoke passed"
echo "web: http://127.0.0.1:${WEB_PORT}/admin/login"
echo "api: http://127.0.0.1:${API_PORT}/health"
echo "rustfs: http://127.0.0.1:${RUSTFS_PORT}"
echo "rustfs console: http://127.0.0.1:${RUSTFS_CONSOLE_PORT}"
