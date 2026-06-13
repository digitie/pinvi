#!/usr/bin/env bash
# Deploy Pinvi docker-compose.app.yml on a single operation node.

set -euo pipefail

ROOT_DIR="${PINVI_ROOT_DIR:-/opt/pinvi}"
COMPOSE_FILE="${PINVI_COMPOSE_FILE:-infra/docker-compose.app.yml}"
PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
API_PORT="${PINVI_API_PORT:-12501}"
WEB_PORT="${PINVI_WEB_PORT:-12505}"
RUSTFS_PORT="${PINVI_RUSTFS_PORT:-12101}"

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-node.sh deploy
  scripts/deploy-node.sh pull
  scripts/deploy-node.sh migrate
  scripts/deploy-node.sh up
  scripts/deploy-node.sh smoke
  scripts/deploy-node.sh status

Required on production nodes:
  PINVI_API_IMAGE=ghcr.io/<owner>/pinvi-api:<tag>
  PINVI_WEB_IMAGE=ghcr.io/<owner>/pinvi-web:<tag>
  PINVI_ENVIRONMENT=production
  PINVI_RATE_LIMIT_BACKEND=postgres

Run this script on the target node from /opt/pinvi or set PINVI_ROOT_DIR.
EOF
}

log() {
  printf '[deploy-node] %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 not found" >&2
    exit 127
  fi
}

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

preflight() {
  require_command docker
  require_command curl
  docker compose version >/dev/null
  [[ -f "$COMPOSE_FILE" ]] || { echo "compose file missing: $COMPOSE_FILE" >&2; exit 2; }
}

pull_images() {
  log "pulling app images"
  compose pull app-api app-web
}

migrate() {
  log "starting database dependencies"
  compose up -d app-postgres app-rustfs app-rustfs-init
  log "running Pinvi Alembic migration"
  compose run --rm app-api alembic upgrade head
}

up() {
  log "starting API + Web"
  compose up -d app-api app-web
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

smoke() {
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  log "smoke passed"
}

status() {
  compose ps
}

deploy() {
  pull_images
  migrate
  up
  smoke
  status
}

main() {
  cd "$ROOT_DIR"
  preflight
  case "${1:-}" in
    pull) pull_images ;;
    migrate) migrate ;;
    up) up ;;
    smoke) smoke ;;
    status) status ;;
    deploy) deploy ;;
    help|-h|--help) usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
