#!/usr/bin/env bash
# `docs/runbooks/docker-app.md` §3 smoke test.

set -euo pipefail

PROJECT="${PROJECT:-tripmate-app-smoke}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.app.yml}"
KEEP_RUNNING="${1:-}"

API_PORT="${TRIPMATE_API_PORT:-18082}"
WEB_PORT="${TRIPMATE_WEB_PORT:-13082}"
API_BASE="http://127.0.0.1:${API_PORT}"
WEB_BASE="http://127.0.0.1:${WEB_PORT}"

cleanup() {
  if [[ -z "${KEEP_RUNNING}" ]]; then
    echo "==> down -v --remove-orphans"
    docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" down -v --remove-orphans
  else
    echo "==> --keep-running 옵션 — 컨테이너 유지"
  fi
}
trap cleanup EXIT

echo "==> 정리"
docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" down -v --remove-orphans

echo "==> 빌드"
docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" build app-api app-web

echo "==> Postgres + RustFS 먼저"
docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" up -d app-postgres app-rustfs app-rustfs-init

echo "==> 의존 대기 (최대 60초)"
for _ in $(seq 1 12); do
  if docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" ps app-postgres | grep -q "healthy"; then
    break
  fi
  sleep 5
done

echo "==> Alembic upgrade head (명시 실행 — auto-migrate 금지)"
docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" run --rm app-api alembic upgrade head

echo "==> API + Web 기동"
docker compose -p "${PROJECT}" -f "${COMPOSE_FILE}" up -d app-api app-web

echo "==> 헬스 대기"
for _ in $(seq 1 12); do
  if curl -fsS "${API_BASE}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "==> GET ${API_BASE}/health"
curl -fsS "${API_BASE}/health"
echo
echo "==> GET ${API_BASE}/health/db"
curl -fsS "${API_BASE}/health/db"
echo
echo "==> GET ${WEB_BASE}/ (HTML)"
curl -fsS -o /dev/null -w "%{http_code}\n" "${WEB_BASE}/"

echo "✅ smoke test passed"
