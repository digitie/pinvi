#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
COMPOSE_FILE="${PINVI_DOCKER_COMPOSE_FILE:-infra/docker-compose.app.yml}"
# 운영 도메인/시크릿 주입. 기본 .env, 운영은 PINVI_ENV_FILE=infra/.env.prod (gitignore, ADR-047).
ENV_FILE="${PINVI_ENV_FILE:-.env}"

API_PORT="${PINVI_API_PORT:-12801}"
WEB_PORT="${PINVI_WEB_PORT:-12805}"
RUSTFS_PORT="${PINVI_RUSTFS_PORT:-12101}"
RUSTFS_CONSOLE_PORT="${PINVI_RUSTFS_CONSOLE_PORT:-12105}"
SMOKE_KEEP_RUNNING=""
MIGRATOR_ONE_SHOT_PASSWORD=""

usage() {
  cat <<'EOF'
Usage:
  scripts/docker-app.sh build
  scripts/docker-app.sh up
  scripts/docker-app.sh down
  scripts/docker-app.sh reset
  scripts/docker-app.sh status
  scripts/docker-app.sh logs [api|web|postgres|rustfs]
  scripts/docker-app.sh migrate   # owner-only migration + one-shot admin bootstrap
  scripts/docker-app.sh smoke [--keep-running]

Defaults:
  API URL:            http://127.0.0.1:12801
  Web URL:            http://127.0.0.1:12805
  RustFS API URL:     http://127.0.0.1:12101
  RustFS console URL: http://127.0.0.1:12105

Environment overrides:
  PINVI_DOCKER_PROJECT=pinvi-app
  PINVI_DOCKER_COMPOSE_FILE=infra/docker-compose.app.yml
  PINVI_API_PORT=12801
  PINVI_WEB_PORT=12805
  PINVI_RUSTFS_PORT=12101
  PINVI_RUSTFS_CONSOLE_PORT=12105
  PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/absolute/host/path/bootstrap-admin.json
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
  if [[ -f "$ENV_FILE" ]]; then
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
  fi
}

# compose()가 env file까지 해석한 뒤 source revision을 확정해야 한다.
# shellcheck source=scripts/api-image-provenance.sh
source "$ROOT_DIR/scripts/api-image-provenance.sh"
# shellcheck source=scripts/migrator-lifecycle-lock.sh
source "$ROOT_DIR/scripts/migrator-lifecycle-lock.sh"

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
  require_python
  pinvi_prepare_api_image_provenance
  log "building app-api and app-web"
  compose build app-api app-web
  pinvi_verify_runtime_image_provenance app-api app-web
}

require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found" >&2
    exit 127
  fi
}

up_deps() {
  local legacy_rebaseline="${1:-0}"
  require_docker
  log "starting Postgres + runtime DB role + RustFS"
  compose up -d app-postgres app-rustfs app-rustfs-init
  compose run --rm \
    -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
    -e PINVI_MIGRATOR_DISABLE_LOGIN=1 \
    app-db-runtime-role
}

drain_runtime_writers() {
  log "stopping API writers before migration"
  compose stop app-api
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
  MIGRATOR_ONE_SHOT_PASSWORD=""
  if [[ "$legacy_rebaseline" == "1" ]]; then
    # legacy is run as the existing root/app owner, never as the reusable migrator login.
    disable_login="1"
    compose run --rm \
      -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
      -e PINVI_MIGRATOR_DISABLE_LOGIN="$disable_login" \
      app-db-runtime-role
    return
  fi

  MIGRATOR_ONE_SHOT_PASSWORD="$(new_migrator_one_shot_password)"
  PINVI_MIGRATOR_DB_PASSWORD="$MIGRATOR_ONE_SHOT_PASSWORD" compose run --rm \
    -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
    -e PINVI_MIGRATOR_DISABLE_LOGIN="$disable_login" \
    app-db-runtime-role
}

new_migrator_one_shot_password() {
  local password
  password="$(LC_ALL=C od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  [[ "$password" =~ ^[0-9a-f]{64}$ ]] || {
    echo "could not generate one-shot migrator password" >&2
    return 1
  }
  printf '%s' "$password"
}

compose_with_one_shot_migrator_password() {
  PINVI_MIGRATOR_DB_PASSWORD="$MIGRATOR_ONE_SHOT_PASSWORD" compose "$@"
}

seal_migrator_login() {
  local legacy_rebaseline="$1"
  log "sealing one-shot migrator login"
  if ! compose run --rm \
    -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
    -e PINVI_MIGRATOR_DISABLE_LOGIN=1 \
    app-db-runtime-role; then
    MIGRATOR_ONE_SHOT_PASSWORD=""
    return 1
  fi
  MIGRATOR_ONE_SHOT_PASSWORD=""
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
  if [[ "$legacy_rebaseline" == "1" ]]; then
    compose "${profile_args[@]}" run --rm --no-deps \
      --user "$runner_user" \
      -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE="$credential_file" \
      -v "$credential_file:$credential_file:ro" \
      "${legacy_args[@]}" \
      "$service" pinvi-admin-bootstrap
    return
  fi
  [[ -n "$MIGRATOR_ONE_SHOT_PASSWORD" ]] || {
    echo "one-shot migrator password is unavailable" >&2
    return 1
  }
  compose_with_one_shot_migrator_password "${profile_args[@]}" run --rm --no-deps \
    --user "$runner_user" \
    -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE="$credential_file" \
    -v "$credential_file:$credential_file:ro" \
    "${legacy_args[@]}" \
    "$service" pinvi-admin-bootstrap
}

reject_explicit_migrator_database_url() {
  if [[ -n "${PINVI_MIGRATOR_DATABASE_URL:-}" ]]; then
    echo "PINVI_MIGRATOR_DATABASE_URL is unsupported; use PINVI_MIGRATOR_DB_USER and PINVI_MIGRATOR_DB_PASSWORD" >&2
    exit 2
  fi
}

migrate_under_lifecycle_lock() {
  require_docker
  require_python
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
  local attempt
  for attempt in 1 2 3 4 5; do
    if ! prepare_migrator_login "$legacy_rebaseline"; then
      log "migrator preparation failed; sealing the one-shot login"
      seal_migrator_login "$legacy_rebaseline" || \
        log "migrator preparation failure could not be followed by a sealing run"
      return 1
    fi
    log "running Pinvi admin bootstrap (attempt ${attempt}/5)"
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
    sleep 3
  done
  echo "pinvi-admin-bootstrap failed after 5 attempts" >&2
  return 1
}

migrate() {
  reject_explicit_migrator_database_url
  pinvi_prepare_api_image_provenance
  acquire_migrator_lifecycle_lock
  migrate_under_lifecycle_lock
  release_migrator_lifecycle_lock
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
  reject_explicit_migrator_database_url
  require_docker
  require_python
  pinvi_verify_runtime_image_provenance app-api app-web
  local legacy_rebaseline
  legacy_rebaseline="$(m05_legacy_rebaseline_profile)"
  if [[ "$legacy_rebaseline" == "1" ]]; then
    legacy_rebaseline_receipt_file >/dev/null
  fi
  free_app_ports
  acquire_migrator_lifecycle_lock
  up_deps "$legacy_rebaseline"
  migrate_under_lifecycle_lock
  log "starting API + Web"
  compose up -d app-api app-web
  pinvi_verify_or_remove_running_app
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" "M05 worker"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  release_migrator_lifecycle_lock
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
  trap 'cleanup_smoke; pinvi_cleanup_api_build_context' EXIT

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
  trap pinvi_cleanup_api_build_context EXIT
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
  pinvi_cleanup_api_build_context
  trap - EXIT
}

main "$@"
