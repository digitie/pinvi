#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
COMPOSE_FILE="${PINVI_DOCKER_COMPOSE_FILE:-infra/docker-compose.app.yml}"

API_PORT="${PINVI_API_PORT:-12501}"
WEB_PORT="${PINVI_WEB_PORT:-12505}"
RUSTFS_PORT="${PINVI_RUSTFS_PORT:-12101}"
RUSTFS_CONSOLE_PORT="${PINVI_RUSTFS_CONSOLE_PORT:-12105}"
SMOKE_KEEP_RUNNING=""

usage() {
  cat <<'EOF'
Usage:
  scripts/docker-app.sh build
  scripts/docker-app.sh up
  scripts/docker-app.sh down
  scripts/docker-app.sh reset
  scripts/docker-app.sh status
  scripts/docker-app.sh logs [api|web|postgres|rustfs]
  scripts/docker-app.sh migrate
  scripts/docker-app.sh smoke [--keep-running]

Defaults:
  API URL:            http://127.0.0.1:12501
  Web URL:            http://127.0.0.1:12505
  RustFS API URL:     http://127.0.0.1:12101
  RustFS console URL: http://127.0.0.1:12105

Environment overrides:
  PINVI_DOCKER_PROJECT=pinvi-app
  PINVI_DOCKER_COMPOSE_FILE=infra/docker-compose.app.yml
  PINVI_API_PORT=12501
  PINVI_WEB_PORT=12505
  PINVI_RUSTFS_PORT=12101
  PINVI_RUSTFS_CONSOLE_PORT=12105
EOF
}

log() {
  printf '[docker-app] %s\n' "$*"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found" >&2
    exit 127
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose plugin not found" >&2
    exit 127
  fi
}

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

free_host_port() {
  local port="$1"
  local docker_ids pids

  docker_ids="$(docker ps --filter "publish=${port}" --format '{{.ID}}' || true)"
  if [[ -n "$docker_ids" ]]; then
    log "removing containers publishing host port ${port}"
    # shellcheck disable=SC2086
    docker rm -f $docker_ids >/dev/null
  fi

  pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN || true)"
  fi
  if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null || true)"
  fi
  if [[ -n "$pids" ]]; then
    log "stopping processes listening on host port ${port}: ${pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

free_app_ports() {
  free_host_port "$API_PORT"
  free_host_port "$WEB_PORT"
  free_host_port "$RUSTFS_PORT"
  free_host_port "$RUSTFS_CONSOLE_PORT"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "${label} did not become ready: ${url}" >&2
  return 1
}

build() {
  require_docker
  log "building app-api and app-web"
  compose build app-api app-web
}

up_deps() {
  require_docker
  log "starting Postgres + RustFS"
  compose up -d app-postgres app-rustfs app-rustfs-init
}

migrate() {
  require_docker
  local attempt
  for attempt in 1 2 3 4 5; do
    log "running Alembic upgrade head (attempt ${attempt}/5)"
    if compose run --rm app-api alembic upgrade head; then
      return 0
    fi
    sleep 3
  done
  echo "alembic upgrade head failed after 5 attempts" >&2
  return 1
}

up() {
  require_docker
  free_app_ports
  up_deps
  migrate
  log "starting API + Web"
  compose up -d app-api app-web
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  log "ready: API http://127.0.0.1:${API_PORT}, Web http://127.0.0.1:${WEB_PORT}, RustFS http://127.0.0.1:${RUSTFS_PORT}"
}

down() {
  require_docker
  compose down --remove-orphans
}

reset() {
  require_docker
  compose down -v --remove-orphans
}

status() {
  require_docker
  compose ps
}

logs() {
  require_docker
  case "${1:-api}" in
    api) compose logs -f app-api ;;
    web) compose logs -f app-web ;;
    postgres) compose logs -f app-postgres ;;
    rustfs) compose logs -f app-rustfs ;;
    *) echo "usage: scripts/docker-app.sh logs [api|web|postgres|rustfs]" >&2; exit 2 ;;
  esac
}

smoke() {
  SMOKE_KEEP_RUNNING="${1:-}"
  require_docker
  cleanup_smoke() {
    if [[ "$SMOKE_KEEP_RUNNING" != "--keep-running" ]]; then
      reset
    fi
  }
  trap cleanup_smoke EXIT

  reset
  build
  up

  log "GET /health"
  curl -fsS "http://127.0.0.1:${API_PORT}/health"
  echo
  log "GET /health/db"
  curl -fsS "http://127.0.0.1:${API_PORT}/health/db"
  echo
  log "GET / (web)"
  curl -fsS -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:${WEB_PORT}/"
  log "GET RustFS health"
  curl -fsS "http://127.0.0.1:${RUSTFS_PORT}/health/live"
  echo
  log "smoke test passed"
  trap - EXIT
  cleanup_smoke
}

main() {
  cd "$ROOT_DIR"
  local command="${1:-}"
  [[ -n "$command" ]] || { usage; exit 2; }
  shift || true

  case "$command" in
    build) build ;;
    up) up ;;
    down) down ;;
    reset) reset ;;
    status) status ;;
    logs) logs "$@" ;;
    migrate) migrate ;;
    smoke) smoke "$@" ;;
    help|-h|--help) usage ;;
    *) echo "unknown command: $command" >&2; usage; exit 2 ;;
  esac
}

main "$@"
