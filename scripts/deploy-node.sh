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
  scripts/deploy-node.sh migrate   # owner-only migration + one-shot admin bootstrap
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
  PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/absolute/host/path/bootstrap-admin.json

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
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    compose --profile etl pull app-dagster
    pinvi_verify_runtime_image_provenance app-api app-web app-dagster
  else
    pinvi_verify_runtime_image_provenance app-api app-web
  fi
}

build_images() {
  pinvi_prepare_api_image_provenance
  log "building app images from the attested source revision"
  compose build app-api app-web
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    compose --profile etl build app-dagster
  fi
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    pinvi_verify_runtime_image_provenance app-api app-web app-dagster
  else
    pinvi_verify_runtime_image_provenance app-api app-web
  fi
}

drain_runtime_writers() {
  log "stopping API and Dagster writers before migration"
  compose stop app-api
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    compose --profile etl stop app-dagster
  fi
}

m05_legacy_rebaseline_profile() {
  case "${PINVI_M05_LEGACY_REBASELINE:-0}" in
    0|1) printf '%s\n' "${PINVI_M05_LEGACY_REBASELINE:-0}" ;;
    *) echo "PINVI_M05_LEGACY_REBASELINE must be 0 or 1" >&2; exit 2 ;;
  esac
}

legacy_rebaseline_receipt_file() {
  local receipt="${PINVI_M05_LEGACY_REBASELINE_RECEIPT_HOST_PATH:-}"
  local parent receipt_uid receipt_mode parent_uid parent_mode
  [[ "$receipt" == /* && "$receipt" != *:* && "$receipt" != *$'\n'* ]] || {
    echo "PINVI_M05_LEGACY_REBASELINE_RECEIPT_HOST_PATH must be an absolute host path" >&2
    exit 2
  }
  [[ -f "$receipt" && ! -L "$receipt" ]] || {
    echo "legacy rebaseline receipt must be a regular non-symlink file" >&2
    exit 2
  }
  parent="$(dirname -- "$receipt")"
  [[ -d "$parent" && ! -L "$parent" ]] || {
    echo "legacy rebaseline receipt parent must be a regular directory" >&2
    exit 2
  }
  receipt_uid="$(stat -c '%u' -- "$receipt")"
  receipt_mode="$(stat -c '%a' -- "$receipt")"
  parent_uid="$(stat -c '%u' -- "$parent")"
  parent_mode="$(stat -c '%a' -- "$parent")"
  [[ "$receipt_uid" == "0" && "$receipt_mode" == "600" ]] || {
    echo "legacy rebaseline receipt must be root-owned mode 0600" >&2
    exit 2
  }
  [[ "$parent_uid" == "0" ]] && (( (8#$parent_mode & 8#077) == 0 )) || {
    echo "legacy rebaseline receipt parent must be root-owned and private" >&2
    exit 2
  }
  printf '%s\n' "$receipt"
}

prepare_migrator_login() {
  local legacy_rebaseline="$1"
  local disable_login="0"
  if [[ "$legacy_rebaseline" == "1" ]]; then
    # legacy is run as the existing root/app owner, never as the reusable migrator login.
    disable_login="1"
  fi
  compose run --rm \
    -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
    -e PINVI_MIGRATOR_DISABLE_LOGIN="$disable_login" \
    app-db-runtime-role
}

seal_migrator_login() {
  local legacy_rebaseline="$1"
  log "sealing one-shot migrator login"
  compose run --rm \
    -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
    -e PINVI_MIGRATOR_DISABLE_LOGIN=1 \
    app-db-runtime-role
}

run_admin_bootstrap() {
  local credential_file="$1"
  local legacy_rebaseline="$2"
  local legacy_receipt_file="${3:-}"
  local service="app-migrator"
  local runner_user="$(id -u):$(id -g)"
  local profile_args=()
  local legacy_args=()
  if [[ "$legacy_rebaseline" == "1" ]]; then
    [[ -n "$legacy_receipt_file" ]] || {
      echo "legacy rebaseline receipt is required" >&2
      exit 2
    }
    service="app-legacy-rebaseline-migrator"
    runner_user="0:0"
    profile_args=(--profile legacy-rebaseline)
    legacy_args=(
      -e PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH=/run/pinvi/m05/legacy-rebaseline-receipt.json
      -v "$legacy_receipt_file:/run/pinvi/m05/legacy-rebaseline-receipt.json:ro"
    )
  fi
  compose "${profile_args[@]}" run --rm --no-deps \
    --user "$runner_user" \
    -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE="$credential_file" \
    -v "$credential_file:$credential_file:ro" \
    "${legacy_args[@]}" \
    "$service" pinvi-admin-bootstrap
}

migrate() {
  pinvi_verify_runtime_image_provenance app-api
  local credential_file
  credential_file="$(bootstrap_credential_file)"
  local legacy_rebaseline
  legacy_rebaseline="$(m05_legacy_rebaseline_profile)"
  local legacy_receipt_file=""
  if [[ "$legacy_rebaseline" == "1" ]]; then
    legacy_receipt_file="$(legacy_rebaseline_receipt_file)"
  fi
  drain_runtime_writers
  log "starting database dependencies and runtime DB role"
  compose up -d app-postgres app-rustfs app-rustfs-init
  if ! prepare_migrator_login "$legacy_rebaseline"; then
    log "migrator preparation failed; sealing the one-shot login"
    seal_migrator_login "$legacy_rebaseline" || \
      log "migrator preparation failure could not be followed by a sealing run"
    return 1
  fi
  log "running Pinvi admin bootstrap"
  if run_admin_bootstrap "$credential_file" "$legacy_rebaseline" "$legacy_receipt_file"; then
    if ! seal_migrator_login "$legacy_rebaseline"; then
      log "migration succeeded but the one-shot migrator login could not be sealed"
      return 1
    fi
    return 0
  fi
  if ! seal_migrator_login "$legacy_rebaseline"; then
    log "failed migration could not be followed by a sealing run"
    return 1
  fi
  return 1
}

bootstrap_credential_file() {
  local path="${PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE:-}"
  if [[ -z "$path" || "$path" != /* || "$path" == *:* || ! -f "$path" ]]; then
    echo "PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE must point to an absolute regular host file without ':'" >&2
    exit 2
  fi
  printf '%s\n' "$path"
}

up() {
  pinvi_verify_runtime_image_provenance app-api app-web
  log "starting API + Web"
  compose up -d app-api app-web
  pinvi_verify_or_remove_running_app
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    dagster_up
  fi
}

dagster_up() {
  pinvi_verify_runtime_image_provenance app-dagster
  log "starting Dagster webserver (port ${DAGSTER_PORT})"
  compose --profile etl up -d app-dagster
  pinvi_verify_or_remove_running_dagster
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
  pinvi_verify_runtime_image_provenance app-api app-web
  pinvi_verify_or_remove_running_app
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" "M05 worker"
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
