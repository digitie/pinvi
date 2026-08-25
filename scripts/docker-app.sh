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
DAGSTER_PORT="${PINVI_DAGSTER_DEV_PORT:-12802}"
SMOKE_KEEP_RUNNING=""
MIGRATOR_ONE_SHOT_PASSWORD=""
MIGRATOR_LOGIN_NEEDS_SEAL="0"
MIGRATOR_LEGACY_REBASELINE="0"
RUNTIME_API_WAS_RUNNING="0"
RUNTIME_WEB_WAS_RUNNING="0"
RUNTIME_DAGSTER_WAS_RUNNING="0"
RUNTIME_API_CONTAINER_ID=""
RUNTIME_API_IMAGE_ID=""
RUNTIME_WEB_CONTAINER_ID=""
RUNTIME_WEB_IMAGE_ID=""
RUNTIME_DAGSTER_CONTAINER_ID=""
RUNTIME_DAGSTER_IMAGE_ID=""
RUNTIME_WRITERS_DRAINED="0"
RUNTIME_DEPLOY_PRESERVE="0"
RUNTIME_API_CONTAINER_NAME=""
RUNTIME_WEB_CONTAINER_NAME=""
RUNTIME_DAGSTER_CONTAINER_NAME=""
RUNTIME_API_BACKUP_NAME=""
RUNTIME_WEB_BACKUP_NAME=""
RUNTIME_DAGSTER_BACKUP_NAME=""

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
  local force_kill="${PINVI_DEV_FORCE_KILL:-0}"
  local docker_ids pids

  docker_ids="$(docker ps --filter "publish=${port}" --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.ID}}' || true)"
  pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN || true)"
  fi
  if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null || true)"
  fi
  if [[ -n "$docker_ids" || -n "$pids" ]] && [[ "$force_kill" != "1" ]]; then
    echo "host port ${port} is already in use; refusing to terminate it" >&2
    echo "set PINVI_DEV_FORCE_KILL=1 only after explicitly approving termination" >&2
    return 2
  fi

  if [[ -n "$docker_ids" ]]; then
    log "removing containers publishing host port ${port}"
    # shellcheck disable=SC2086
    docker rm -f $docker_ids >/dev/null
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
  free_host_port "$DAGSTER_PORT"
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

wait_for_container_health() {
  local container_id="$1"
  local label="$2"
  local status=""
  for _ in $(seq 1 30); do
    status="$(docker container inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$container_id" 2>/dev/null || true)"
    case "$status" in
      healthy) return 0 ;;
      unhealthy|exited|dead) break ;;
      none)
        echo "${label} has no Docker healthcheck" >&2
        return 1
        ;;
    esac
    sleep 2
  done
  echo "${label} did not become healthy: ${status:-missing}" >&2
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
  require_docker
  log "starting Postgres + RustFS dependencies"
  compose up -d app-postgres app-rustfs app-rustfs-init
}

runtime_writer_container_id() {
  local service="$1"
  pinvi_runtime_container_ids "$service" running
}

runtime_writer_container_name() {
  local container_id="$1"
  docker container inspect --format '{{.Name}}' "$container_id" | sed 's#^/##'
}

runtime_writer_any_container_id() {
  local service="$1"
  pinvi_runtime_container_ids "$service"
}

runtime_writer_container_is_exact() {
  local service="$1"
  local container_id="$2"
  local expected_image_id="$3"
  local running actual_image_id
  if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
    return 1
  fi
  if [[ "$running" != "true" ]]; then
    return 1
  fi
  if ! actual_image_id="$(docker container inspect --format '{{.Image}}' "$container_id")"; then
    return 1
  fi
  if [[ "$actual_image_id" != "$expected_image_id" ]]; then
    echo "${service} restore image drifted from the pre-migration container" >&2
    return 1
  fi
}

preserve_runtime_writers() {
  local api_name="" web_name="" dagster_name=""
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]]; then
    api_name="$(runtime_writer_container_name "$RUNTIME_API_CONTAINER_ID")"
    RUNTIME_API_CONTAINER_NAME="$api_name"
    RUNTIME_API_BACKUP_NAME="${api_name}.pinvi-predeploy"
    if docker container inspect "$RUNTIME_API_BACKUP_NAME" >/dev/null 2>&1; then
      echo "pre-deploy API snapshot name already exists: $RUNTIME_API_BACKUP_NAME" >&2
      return 1
    fi
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]]; then
    web_name="$(runtime_writer_container_name "$RUNTIME_WEB_CONTAINER_ID")"
    RUNTIME_WEB_CONTAINER_NAME="$web_name"
    RUNTIME_WEB_BACKUP_NAME="${web_name}.pinvi-predeploy"
    if docker container inspect "$RUNTIME_WEB_BACKUP_NAME" >/dev/null 2>&1; then
      echo "pre-deploy Web snapshot name already exists: $RUNTIME_WEB_BACKUP_NAME" >&2
      return 1
    fi
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    dagster_name="$(runtime_writer_container_name "$RUNTIME_DAGSTER_CONTAINER_ID")"
    RUNTIME_DAGSTER_CONTAINER_NAME="$dagster_name"
    RUNTIME_DAGSTER_BACKUP_NAME="${dagster_name}.pinvi-predeploy"
    if docker container inspect "$RUNTIME_DAGSTER_BACKUP_NAME" >/dev/null 2>&1; then
      echo "pre-deploy Dagster snapshot name already exists: $RUNTIME_DAGSTER_BACKUP_NAME" >&2
      return 1
    fi
  fi
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]] && ! docker rename \
    "$RUNTIME_API_CONTAINER_ID" "$RUNTIME_API_BACKUP_NAME"; then
    return 1
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]] && ! docker rename \
    "$RUNTIME_WEB_CONTAINER_ID" "$RUNTIME_WEB_BACKUP_NAME"; then
    [[ -z "$RUNTIME_API_BACKUP_NAME" ]] || docker rename \
      "$RUNTIME_API_BACKUP_NAME" "$RUNTIME_API_CONTAINER_NAME" || true
    return 1
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]] && ! docker rename \
    "$RUNTIME_DAGSTER_CONTAINER_ID" "$RUNTIME_DAGSTER_BACKUP_NAME"; then
    if [[ -n "$RUNTIME_WEB_BACKUP_NAME" ]] && docker container inspect \
      "$RUNTIME_WEB_BACKUP_NAME" >/dev/null 2>&1; then
      docker rename "$RUNTIME_WEB_BACKUP_NAME" "$RUNTIME_WEB_CONTAINER_NAME" || true
    fi
    if [[ -n "$RUNTIME_API_BACKUP_NAME" ]] && docker container inspect \
      "$RUNTIME_API_BACKUP_NAME" >/dev/null 2>&1; then
      docker rename "$RUNTIME_API_BACKUP_NAME" "$RUNTIME_API_CONTAINER_NAME" || true
    fi
    return 1
  fi
}

rollback_preserved_runtime_writers() {
  local rollback_failed="0"
  local current_id
  local service backup name
  for service in app-api app-web app-dagster; do
    case "$service" in
      app-api) [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]] || continue ;;
      app-web) [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]] || continue ;;
      app-dagster) [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]] || continue ;;
    esac
    current_id="$(runtime_writer_any_container_id "$service" || true)"
    case "$service" in
      app-api) [[ "$current_id" == "$RUNTIME_API_CONTAINER_ID" ]] && current_id=""; backup="$RUNTIME_API_BACKUP_NAME"; name="$RUNTIME_API_CONTAINER_NAME" ;;
      app-web) [[ "$current_id" == "$RUNTIME_WEB_CONTAINER_ID" ]] && current_id=""; backup="$RUNTIME_WEB_BACKUP_NAME"; name="$RUNTIME_WEB_CONTAINER_NAME" ;;
      app-dagster) [[ "$current_id" == "$RUNTIME_DAGSTER_CONTAINER_ID" ]] && current_id=""; backup="$RUNTIME_DAGSTER_BACKUP_NAME"; name="$RUNTIME_DAGSTER_CONTAINER_NAME" ;;
    esac
    if [[ -n "$current_id" ]]; then
      if [[ "$current_id" == *$'\n'* ]] || ! docker rm -f "$current_id" >/dev/null; then
        rollback_failed="1"
      fi
    fi
    if docker container inspect "$backup" >/dev/null 2>&1; then
      docker rename "$backup" "$name" || rollback_failed="1"
    fi
  done
  if [[ "$rollback_failed" == "0" ]] && ! restore_runtime_writers_without_rollback; then
    rollback_failed="1"
  fi
  if [[ "$rollback_failed" == "0" ]]; then
    RUNTIME_DEPLOY_PRESERVE="0"
  fi
  [[ "$rollback_failed" == "0" ]]
}

drain_runtime_writers() {
  local drain_failed="0"
  local api_container_id api_image_id web_container_id web_image_id
  local dagster_container_id dagster_image_id
  RUNTIME_API_WAS_RUNNING="0"
  RUNTIME_WEB_WAS_RUNNING="0"
  RUNTIME_DAGSTER_WAS_RUNNING="0"
  RUNTIME_API_CONTAINER_ID=""
  RUNTIME_API_IMAGE_ID=""
  RUNTIME_WEB_CONTAINER_ID=""
  RUNTIME_WEB_IMAGE_ID=""
  RUNTIME_DAGSTER_CONTAINER_ID=""
  RUNTIME_DAGSTER_IMAGE_ID=""
  RUNTIME_WRITERS_DRAINED="0"
  RUNTIME_API_CONTAINER_NAME=""
  RUNTIME_WEB_CONTAINER_NAME=""
  RUNTIME_DAGSTER_CONTAINER_NAME=""
  RUNTIME_API_BACKUP_NAME=""
  RUNTIME_WEB_BACKUP_NAME=""
  RUNTIME_DAGSTER_BACKUP_NAME=""
  if ! api_container_id="$(runtime_writer_container_id app-api)"; then
    drain_failed="1"
  elif [[ -n "$api_container_id" ]]; then
    if [[ "$api_container_id" == *$'\n'* ]]; then
      drain_failed="1"
    elif ! api_image_id="$(docker container inspect --format '{{.Image}}' "$api_container_id")"; then
      drain_failed="1"
    fi
  fi
  if ! web_container_id="$(runtime_writer_container_id app-web)"; then
    drain_failed="1"
  elif [[ -n "$web_container_id" ]]; then
    if [[ "$web_container_id" == *$'\n'* ]]; then
      drain_failed="1"
    elif ! web_image_id="$(docker container inspect --format '{{.Image}}' "$web_container_id")"; then
      drain_failed="1"
    fi
  fi
  if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
    drain_failed="1"
  elif [[ -n "$dagster_container_id" ]]; then
    if [[ "$dagster_container_id" == *$'\n'* ]]; then
      drain_failed="1"
    elif ! dagster_image_id="$(docker container inspect --format '{{.Image}}' "$dagster_container_id")"; then
      drain_failed="1"
    fi
  fi
  [[ "$drain_failed" == "0" ]] || return 1
  if [[ -n "$api_container_id" ]]; then
    RUNTIME_API_CONTAINER_ID="$api_container_id"
    RUNTIME_API_IMAGE_ID="$api_image_id"
    RUNTIME_API_WAS_RUNNING="1"
  fi
  if [[ -n "$web_container_id" ]]; then
    RUNTIME_WEB_CONTAINER_ID="$web_container_id"
    RUNTIME_WEB_IMAGE_ID="$web_image_id"
    RUNTIME_WEB_WAS_RUNNING="1"
  fi
  if [[ -n "$dagster_container_id" ]]; then
    RUNTIME_DAGSTER_CONTAINER_ID="$dagster_container_id"
    RUNTIME_DAGSTER_IMAGE_ID="$dagster_image_id"
    RUNTIME_DAGSTER_WAS_RUNNING="1"
  fi
  log "stopping API, Web, and Dagster writers before migration"
  if ! compose stop app-web; then
    drain_failed="1"
  fi
  if ! compose stop app-api; then
    drain_failed="1"
  fi
  if ! compose --profile etl stop app-dagster; then
    drain_failed="1"
  fi
  if [[ "$drain_failed" == "0" && "$RUNTIME_DEPLOY_PRESERVE" == "1" ]]; then
    if ! preserve_runtime_writers; then
      drain_failed="1"
    fi
  fi
  if [[ "$drain_failed" == "0" ]]; then
    RUNTIME_WRITERS_DRAINED="1"
    return 0
  fi
  return 1
}

restore_runtime_writers_without_rollback() {
  local restore_failed="0"
  local running
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]]; then
    log "restoring the pre-migration API container"
    if ! running="$(docker container inspect --format '{{.State.Running}}' "$RUNTIME_API_CONTAINER_ID")"; then
      restore_failed="1"
    else
      if [[ "$running" != "true" ]] && ! docker start "$RUNTIME_API_CONTAINER_ID" >/dev/null; then
        restore_failed="1"
      fi
      if ! runtime_writer_container_is_exact app-api "$RUNTIME_API_CONTAINER_ID" "$RUNTIME_API_IMAGE_ID"; then
        restore_failed="1"
      fi
      if ! wait_for_url "http://127.0.0.1:${API_PORT}/health" "API restore"; then
        restore_failed="1"
      fi
      if ! wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB restore"; then
        restore_failed="1"
      fi
      if ! wait_for_url \
        "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" \
        "M05 worker restore"; then
        restore_failed="1"
      fi
      if ! wait_for_container_health "$RUNTIME_API_CONTAINER_ID" "API container restore"; then
        restore_failed="1"
      fi
    fi
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]]; then
    log "restoring the pre-migration Web container"
    if ! running="$(docker container inspect --format '{{.State.Running}}' "$RUNTIME_WEB_CONTAINER_ID")"; then
      restore_failed="1"
    else
      if [[ "$running" != "true" ]] && ! docker start "$RUNTIME_WEB_CONTAINER_ID" >/dev/null; then
        restore_failed="1"
      fi
      if ! runtime_writer_container_is_exact app-web "$RUNTIME_WEB_CONTAINER_ID" "$RUNTIME_WEB_IMAGE_ID"; then
        restore_failed="1"
      fi
      if ! wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web restore"; then
        restore_failed="1"
      fi
      if ! wait_for_container_health "$RUNTIME_WEB_CONTAINER_ID" "Web container restore"; then
        restore_failed="1"
      fi
    fi
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    log "restoring the pre-migration Dagster container"
    if ! running="$(docker container inspect --format '{{.State.Running}}' "$RUNTIME_DAGSTER_CONTAINER_ID")"; then
      restore_failed="1"
    else
      if [[ "$running" != "true" ]] && ! docker start "$RUNTIME_DAGSTER_CONTAINER_ID" >/dev/null; then
        restore_failed="1"
      fi
      if ! runtime_writer_container_is_exact app-dagster "$RUNTIME_DAGSTER_CONTAINER_ID" "$RUNTIME_DAGSTER_IMAGE_ID"; then
        restore_failed="1"
      fi
      if ! wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster restore"; then
        restore_failed="1"
      fi
      if ! wait_for_container_health \
        "$RUNTIME_DAGSTER_CONTAINER_ID" "Dagster container restore"; then
        restore_failed="1"
      fi
    fi
  fi
  if [[ "$restore_failed" != "0" ]]; then
    return 1
  fi
  RUNTIME_API_WAS_RUNNING="0"
  RUNTIME_WEB_WAS_RUNNING="0"
  RUNTIME_DAGSTER_WAS_RUNNING="0"
  RUNTIME_API_CONTAINER_ID=""
  RUNTIME_API_IMAGE_ID=""
  RUNTIME_WEB_CONTAINER_ID=""
  RUNTIME_WEB_IMAGE_ID=""
  RUNTIME_DAGSTER_CONTAINER_ID=""
  RUNTIME_DAGSTER_IMAGE_ID=""
  RUNTIME_WRITERS_DRAINED="0"
}

restore_runtime_writers() {
  if [[ "$RUNTIME_DEPLOY_PRESERVE" == "1" ]]; then
    rollback_preserved_runtime_writers
    return
  fi
  restore_runtime_writers_without_rollback
}

restore_runtime_writers_on_exit() {
  local exit_code="${1:-$?}"
  local cleanup_failed="0"
  if [[ "$MIGRATOR_LOGIN_NEEDS_SEAL" == "1" ]]; then
    if ! seal_migrator_login "$MIGRATOR_LEGACY_REBASELINE"; then
      cleanup_failed="1"
      log "migrator login sealing failed during process exit"
    fi
  fi
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" || "$RUNTIME_WEB_WAS_RUNNING" == "1" \
    || "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    if ! restore_runtime_writers; then
      cleanup_failed="1"
      log "runtime writer restoration failed during process exit"
    fi
  fi
  release_migrator_lifecycle_lock || true
  pinvi_cleanup_api_build_context || true
  if [[ "$exit_code" == "0" && "$cleanup_failed" != "0" ]]; then
    exit_code="1"
  fi
  return "$exit_code"
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
  local attempt
  log "sealing one-shot migrator login"
  for attempt in 1 2 3; do
    if compose run --rm \
      -e PINVI_M05_LEGACY_REBASELINE="$legacy_rebaseline" \
      -e PINVI_MIGRATOR_DISABLE_LOGIN=1 \
      app-db-runtime-role; then
      MIGRATOR_ONE_SHOT_PASSWORD=""
      MIGRATOR_LOGIN_NEEDS_SEAL="0"
      return 0
    fi
    log "migrator seal attempt ${attempt}/3 failed"
    if [[ "$attempt" != "3" ]]; then
      sleep 1
    fi
  done
  echo "migrator login could not be sealed after 3 attempts" >&2
  return 1
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
  if ! credential_file="$(bootstrap_credential_file)"; then
    return 1
  fi
  local legacy_rebaseline
  if ! legacy_rebaseline="$(m05_legacy_rebaseline_profile)"; then
    return 1
  fi
  local legacy_receipt_file=""
  if [[ "$legacy_rebaseline" == "1" ]]; then
    if ! legacy_receipt_file="$(legacy_rebaseline_receipt_file)"; then
      return 1
    fi
  fi
  MIGRATOR_LEGACY_REBASELINE="$legacy_rebaseline"
  if [[ "$RUNTIME_WRITERS_DRAINED" != "1" ]] && ! drain_runtime_writers; then
    log "runtime writer drain failed"
    restore_runtime_writers || log "runtime writer restoration failed"
    return 1
  fi
  local attempt
  for attempt in 1 2 3 4 5; do
    if [[ "$legacy_rebaseline" == "0" ]]; then
      MIGRATOR_LOGIN_NEEDS_SEAL="1"
    fi
    if ! prepare_migrator_login "$legacy_rebaseline"; then
      log "migrator preparation failed; sealing the one-shot login"
      seal_migrator_login "$legacy_rebaseline" || \
        log "migrator preparation failure could not be followed by a sealing run"
      restore_runtime_writers || log "runtime writer restoration failed"
      return 1
    fi
    log "running Pinvi admin bootstrap (attempt ${attempt}/5)"
    if run_admin_bootstrap "$credential_file" "$legacy_rebaseline" "$legacy_receipt_file"; then
      if ! seal_migrator_login "$legacy_rebaseline"; then
        log "migration succeeded but the one-shot migrator login could not be sealed"
        restore_runtime_writers || log "runtime writer restoration failed"
        return 1
      fi
      if [[ "$RUNTIME_DEPLOY_PRESERVE" != "1" ]]; then
        restore_runtime_writers || {
          log "runtime writer restoration failed"
          return 1
        }
      fi
      return 0
    fi
    if ! seal_migrator_login "$legacy_rebaseline"; then
      log "failed migration could not be followed by a sealing run"
      restore_runtime_writers || log "runtime writer restoration failed"
      return 1
    fi
    sleep 3
  done
  echo "pinvi-admin-bootstrap failed after 5 attempts" >&2
  restore_runtime_writers || log "runtime writer restoration failed"
  return 1
}

migrate() {
  reject_explicit_migrator_database_url
  pinvi_prepare_api_image_provenance
  acquire_migrator_lifecycle_lock
  # EXIT handler가 실패 시 writer 복구와 lifecycle lock 해제를 담당한다. 조건문
  # 안에서 호출하면 Bash가 함수 내부의 errexit을 끄므로 migration 본문은 직접 호출한다.
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

finalize_preserved_runtime_writers() {
  local container_id
  for container_id in "$RUNTIME_API_CONTAINER_ID" "$RUNTIME_WEB_CONTAINER_ID" \
    "$RUNTIME_DAGSTER_CONTAINER_ID"; do
    if [[ -n "$container_id" ]]; then
      if ! docker rm "$container_id" >/dev/null; then
        log "pre-deploy runtime snapshot could not be removed; leaving it for manual cleanup"
      fi
    fi
  done
  RUNTIME_API_WAS_RUNNING="0"
  RUNTIME_WEB_WAS_RUNNING="0"
  RUNTIME_DAGSTER_WAS_RUNNING="0"
  RUNTIME_API_CONTAINER_ID=""
  RUNTIME_API_IMAGE_ID=""
  RUNTIME_WEB_CONTAINER_ID=""
  RUNTIME_WEB_IMAGE_ID=""
  RUNTIME_DAGSTER_CONTAINER_ID=""
  RUNTIME_DAGSTER_IMAGE_ID=""
  RUNTIME_WRITERS_DRAINED="0"
  RUNTIME_DEPLOY_PRESERVE="0"
  RUNTIME_API_CONTAINER_NAME=""
  RUNTIME_WEB_CONTAINER_NAME=""
  RUNTIME_DAGSTER_CONTAINER_NAME=""
  RUNTIME_API_BACKUP_NAME=""
  RUNTIME_WEB_BACKUP_NAME=""
  RUNTIME_DAGSTER_BACKUP_NAME=""
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
  RUNTIME_DEPLOY_PRESERVE="1"
  acquire_migrator_lifecycle_lock
  if ! drain_runtime_writers; then
    log "runtime writer drain failed"
    return 1
  fi
  free_app_ports
  up_deps
  migrate_under_lifecycle_lock
  log "starting API + Web"
  compose up -d app-api app-web
  pinvi_verify_or_remove_running_app
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" "M05 worker"
  local api_container_id
  api_container_id="$(runtime_writer_container_id app-api)"
  [[ -n "$api_container_id" && "$api_container_id" != *$'\n'* ]] || {
    echo "running API container could not be identified" >&2
    return 1
  }
  wait_for_container_health "$api_container_id" "API container"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  wait_for_container_health "$(runtime_writer_container_id app-web)" "Web container"
  finalize_preserved_runtime_writers
  release_migrator_lifecycle_lock
  log "ready: API http://127.0.0.1:${API_PORT}, Web http://127.0.0.1:${WEB_PORT}, RustFS http://127.0.0.1:${RUSTFS_PORT}"
}

down() {
  require_docker
  compose down --remove-orphans
}

configured_environment() {
  local environment_name="${PINVI_ENVIRONMENT:-}"
  local file_environment_name=""
  if [[ -f "$ENV_FILE" ]]; then
    file_environment_name="$(sed -nE \
      's/^[[:space:]]*PINVI_ENVIRONMENT[[:space:]]*=[[:space:]]*([^[:space:]#]+).*/\1/p' \
      "$ENV_FILE" | tail -n 1)"
    file_environment_name="${file_environment_name#\"}"
    file_environment_name="${file_environment_name%\"}"
    file_environment_name="${file_environment_name#\'}"
    file_environment_name="${file_environment_name%\'}"
  fi
  # An explicitly selected staging/production env file is authoritative. A
  # shell override must not turn a destructive reset back into a dev reset.
  if [[ "$file_environment_name" == "staging" || "$file_environment_name" == "production" ]]; then
    environment_name="$file_environment_name"
  elif [[ -z "$environment_name" ]]; then
    environment_name="$file_environment_name"
  fi
  printf '%s\n' "${environment_name:-smoke}"
}

reset() {
  require_docker
  case "$(configured_environment)" in
    staging|production)
      echo "reset is disabled for staging/production; use an approved recovery procedure" >&2
      return 2
      ;;
  esac
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
  smoke_on_exit() {
    local exit_code="${1:-$?}"
    local cleanup_failed="0"
    trap - EXIT
    if ! restore_runtime_writers_on_exit "$exit_code"; then
      cleanup_failed="1"
    fi
    if ! cleanup_smoke; then
      cleanup_failed="1"
    fi
    if [[ "$exit_code" == "0" && "$cleanup_failed" != "0" ]]; then
      exit_code="1"
    fi
    return "$exit_code"
  }
  trap 'smoke_on_exit "$?"' EXIT

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
  smoke_on_exit 0
}

main() {
  cd "$ROOT_DIR"
  trap 'restore_runtime_writers_on_exit "$?"' EXIT
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
