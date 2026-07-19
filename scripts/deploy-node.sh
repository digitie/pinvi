#!/usr/bin/env bash
# Deploy Pinvi docker-compose.app.yml on a single operation node.

set -euo pipefail

ROOT_DIR="${PINVI_ROOT_DIR:-/opt/pinvi}"
COMPOSE_FILE="${PINVI_COMPOSE_FILE:-infra/docker-compose.app.yml}"
# 운영 도메인/시크릿 주입. 기본 .env, 운영은 PINVI_ENV_FILE=infra/.env.prod (gitignore, ADR-047).
ENV_FILE="${PINVI_ENV_FILE:-.env}"
PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
API_PORT="${PINVI_API_PORT:-12801}"
WEB_PORT="${PINVI_WEB_PORT:-12805}"
RUSTFS_PORT="${PINVI_RUSTFS_PORT:-12101}"
DAGSTER_PORT="${PINVI_DAGSTER_DEV_PORT:-12802}"
# Dagster webserver(profile etl)를 같이 띄울지. 운영에서 pinvi-dagster.<domain>을 쓰면 1.
ENABLE_DAGSTER="${PINVI_ENABLE_DAGSTER:-0}"

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-node.sh deploy
  scripts/deploy-node.sh build
  scripts/deploy-node.sh pull
  scripts/deploy-node.sh migrate
  scripts/deploy-node.sh up
  scripts/deploy-node.sh dagster   # Dagster webserver(profile etl)만 기동
  scripts/deploy-node.sh smoke
  scripts/deploy-node.sh status

Required on production nodes:
  PINVI_API_IMAGE=pinvi-api:latest-main
  PINVI_WEB_IMAGE=pinvi-web:latest-main
  PINVI_ENVIRONMENT=production
  PINVI_RATE_LIMIT_BACKEND=postgres

Optional env:
  PINVI_ENV_FILE=infra/.env.prod   # 도메인/시크릿 주입(gitignore). 기본 .env
  PINVI_ENABLE_DAGSTER=1           # up/deploy 시 Dagster webserver(:12802)도 기동

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
  if [[ -f "$ENV_FILE" ]]; then
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
  fi
}

# compose()가 env file까지 해석한 뒤 source revision을 확정해야 한다.
# shellcheck source=scripts/api-image-provenance.sh
source "$ROOT_DIR/scripts/api-image-provenance.sh"

preflight() {
  require_command docker
  require_command curl
  require_command git
  require_command python3
  docker compose version >/dev/null
  [[ -f "$COMPOSE_FILE" ]] || { echo "compose file missing: $COMPOSE_FILE" >&2; exit 2; }
}

pull_images() {
  pinvi_prepare_api_image_provenance
  log "pulling app images"
  compose pull app-api app-web
  pinvi_verify_api_image_provenance
}

build_images() {
  pinvi_prepare_api_image_provenance
  log "building app images from the attested source revision"
  compose build app-api app-web
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    compose --profile etl build app-dagster
  fi
  pinvi_verify_api_image_provenance
}

migrate() {
  pinvi_verify_api_image_provenance
  log "starting database dependencies"
  compose up -d app-postgres app-rustfs app-rustfs-init
  log "running Pinvi Alembic migration"
  compose run --rm app-api alembic upgrade head
}

up() {
  pinvi_verify_api_image_provenance
  log "starting API + Web"
  compose up -d app-api app-web
  pinvi_verify_or_remove_running_app
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    dagster_up
  fi
}

dagster_up() {
  log "starting Dagster webserver (port ${DAGSTER_PORT})"
  compose --profile etl up -d app-dagster
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
  pinvi_verify_api_image_provenance
  pinvi_verify_or_remove_running_app
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster"
  fi
  log "smoke passed"
}

status() {
  compose ps
}

deploy() {
  build_images
  migrate
  up
  smoke
  status
}

main() {
  cd "$ROOT_DIR"
  trap pinvi_cleanup_api_build_context EXIT
  preflight
  case "${1:-}" in
    deploy|build|pull|migrate|up|dagster|smoke)
      pinvi_prepare_api_image_provenance require-immutable
      ;;
  esac
  case "${1:-}" in
    build) build_images ;;
    pull) pull_images ;;
    migrate) migrate ;;
    up) up ;;
    dagster) dagster_up ;;
    smoke) smoke ;;
    status) status ;;
    deploy) deploy ;;
    help|-h|--help) usage ;;
    *) usage; exit 2 ;;
  esac
  pinvi_cleanup_api_build_context
  trap - EXIT
}

main "$@"
