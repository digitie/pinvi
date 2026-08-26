#!/usr/bin/env bash
# Deploy Pinvi docker-compose.app.yml on a single operation node.

set -euo pipefail

ROOT_DIR="${PINVI_ROOT_DIR:-/opt/pinvi}"
COMPOSE_FILE="${PINVI_COMPOSE_FILE:-infra/docker-compose.app.yml}"
CANONICAL_COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
# 운영 도메인/시크릿 주입. 기본 .env, 운영은 PINVI_ENV_FILE=infra/.env.prod (gitignore, ADR-047).
ENV_FILE="${PINVI_ENV_FILE:-.env}"
PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
FRESH_STACK_STATE_PATH="${PINVI_FRESH_STACK_STATE_PATH:-${PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH:-/var/lib/pinvi/restore-forensics/migrator-lifecycle.lock}.fresh-stack}"

compose_env_source_file() {
  local source_file="$ENV_FILE"
  [[ "$source_file" == /* ]] || source_file="$ROOT_DIR/$source_file"
  if [[ -f "$source_file" ]]; then
    printf '%s\n' "$source_file"
  elif [[ -f "$ROOT_DIR/.env" ]]; then
    # Compose falls back to the project-root .env when --env-file is absent.
    printf '%s\n' "$ROOT_DIR/.env"
  fi
}

compose_env_value() {
  local key="$1" default_value="$2" source_file value
  if [[ -n "${!key+x}" ]]; then
    printf '%s\n' "${!key}"
    return
  fi
  source_file="$(compose_env_source_file)"
  if [[ -n "$source_file" ]]; then
    value="$(sed -nE \
      "s/^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=[[:space:]]*([^[:space:]#]+).*/\\2/p" \
      "$source_file" | tail -n 1)"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    if [[ -n "$value" ]]; then
      printf '%s\n' "$value"
      return
    fi
  fi
  printf '%s\n' "$default_value"
}

API_PORT="$(compose_env_value PINVI_API_PORT 12801)"
WEB_PORT="$(compose_env_value PINVI_WEB_PORT 12805)"
RUSTFS_PORT="$(compose_env_value PINVI_RUSTFS_PORT 12101)"
RUSTFS_CONSOLE_PORT="$(compose_env_value PINVI_RUSTFS_CONSOLE_PORT 12105)"
DAGSTER_PORT="$(compose_env_value PINVI_DAGSTER_DEV_PORT 12802)"
CADVISOR_PORT="$(compose_env_value PINVI_CADVISOR_PORT 12301)"
PROMETHEUS_PORT="$(compose_env_value PINVI_PROMETHEUS_PORT 12401)"
GRAFANA_PORT="$(compose_env_value PINVI_GRAFANA_PORT 12205)"
# Dagster webserver(profile etl)를 같이 띄울지. 운영에서 pinvi-dagster.<domain>을 쓰면 1.
ENABLE_DAGSTER="$(compose_env_value PINVI_ENABLE_DAGSTER 0)"
DEPLOY_FRESH_STACK="$(compose_env_value PINVI_DEPLOY_FRESH_STACK 0)"
DEPLOY_MANAGER_UNAVAILABLE="$(compose_env_value PINVI_DOCKER_MANAGER_UNAVAILABLE 0)"
MIGRATOR_ONE_SHOT_PASSWORD=""
MIGRATOR_LOGIN_NEEDS_SEAL="0"
MIGRATOR_LEGACY_REBASELINE="0"
BOOTSTRAP_ADMIN_CREDENTIAL_SHA256=""
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
RUNTIME_NEW_WRITERS_STARTED="0"
RUNTIME_SNAPSHOT_RENAMED="0"
RUNTIME_API_CONTAINER_NAME=""
RUNTIME_WEB_CONTAINER_NAME=""
RUNTIME_DAGSTER_CONTAINER_NAME=""
RUNTIME_API_BACKUP_NAME=""
RUNTIME_WEB_BACKUP_NAME=""
RUNTIME_DAGSTER_BACKUP_NAME=""
RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
RUNTIME_NEW_API_CONTAINER_IDS=()
RUNTIME_NEW_WEB_CONTAINER_IDS=()
RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
RUNTIME_API_SNAPSHOT_RENAMED="0"
RUNTIME_WEB_SNAPSHOT_RENAMED="0"
RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0"
RUNTIME_CONTAINER_DISCOVERY_FAILED="0"
FRESH_STACK_DB_CONTAINER_ID=""
FRESH_STACK_DB_VOLUME_NAME=""
FRESH_STACK_DB_SYSTEM_IDENTIFIER=""
FRESH_STACK_ALEMBIC_VERSION=""
FRESH_STACK_MIGRATION_RECEIPT_SHA256=""
FRESH_STACK_API_IMAGE_ID=""
FRESH_STACK_WEB_IMAGE_ID=""
FRESH_STACK_DAGSTER_IMAGE_ID="none"
FRESH_STACK_COMPOSE_SHA256=""
FRESH_STACK_ENVIRONMENT_SOURCE_SHA256=""
FRESH_STACK_EFFECTIVE_COMPOSE_SHA256=""

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

Fresh fallback deploy (N150 only):
  PINVI_DOCKER_MANAGER_UNAVAILABLE=1 PINVI_DEPLOY_FRESH_STACK=1 \
  PINVI_DOCKER_PROJECT=pinvi-<isolated-name> scripts/deploy-node.sh deploy

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

require_local_docker_target() {
  if [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
    echo "deploy-node requires the local default Docker target; DOCKER_HOST/DOCKER_CONTEXT are unsupported" >&2
    return 2
  fi
  local context endpoint
  if ! context="$(docker context show 2>/dev/null)"; then
    echo "could not determine the Docker context; refusing container mutation" >&2
    return 1
  fi
  if [[ "$context" != "default" ]]; then
    echo "deploy-node requires the default local Docker context" >&2
    return 2
  fi
  if ! endpoint="$(docker context inspect default \
    --format '{{ (index .Endpoints "docker").Host }}' 2>/dev/null)"; then
    echo "could not inspect the default Docker endpoint; refusing container mutation" >&2
    return 1
  fi
  if [[ "$endpoint" != "unix:///var/run/docker.sock" ]]; then
    echo "deploy-node requires Docker endpoint unix:///var/run/docker.sock" >&2
    return 2
  fi
}

compose() {
  if [[ -f "$ENV_FILE" ]]; then
    PINVI_DOCKER_PROJECT="$PROJECT" docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    PINVI_DOCKER_PROJECT="$PROJECT" docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
  fi
}

# compose()가 env file까지 해석한 뒤 source revision을 확정해야 한다.
# shellcheck source=scripts/api-image-provenance.sh
source "$ROOT_DIR/scripts/api-image-provenance.sh"
# shellcheck source=scripts/migrator-lifecycle-lock.sh
source "$ROOT_DIR/scripts/migrator-lifecycle-lock.sh"

preflight() {
  require_command docker
  validate_configured_ports
  require_local_docker_target
  require_command curl
  require_command git
  require_command python3
  require_command sha256sum
  docker compose version >/dev/null
  [[ -f "$COMPOSE_FILE" ]] || { echo "compose file missing: $COMPOSE_FILE" >&2; exit 2; }
}

resolved_environment() {
  local environment_name="${PINVI_ENVIRONMENT:-}"
  local file_environment_name="" source_file
  source_file="$(compose_env_source_file)"
  if [[ -n "$source_file" ]]; then
    file_environment_name="$(sed -nE \
      's/^[[:space:]]*(export[[:space:]]+)?PINVI_ENVIRONMENT[[:space:]]*=[[:space:]]*([^[:space:]#]+).*/\2/p' \
      "$source_file" | tail -n 1)"
    file_environment_name="${file_environment_name#\"}"
    file_environment_name="${file_environment_name%\"}"
    file_environment_name="${file_environment_name#\'}"
    file_environment_name="${file_environment_name%\'}"
  fi
  if [[ -n "$environment_name" && -n "$file_environment_name" \
    && "$environment_name" != "$file_environment_name" ]]; then
    echo "PINVI_ENVIRONMENT disagrees with ${source_file}; refusing ambiguous deployment environment" >&2
    return 2
  fi
  printf '%s\n' "${file_environment_name:-$environment_name}"
}

require_node_mutation_environment() {
  local environment_name
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  case "$environment_name" in
    staging|production) ;;
    *)
      echo "deploy-node mutation requires PINVI_ENVIRONMENT=staging or production" >&2
      return 2
      ;;
  esac
  require_isolated_database_endpoint
}

require_canonical_compose_file() {
  local configured_file="$COMPOSE_FILE"
  if [[ "$configured_file" != /* ]]; then
    configured_file="$ROOT_DIR/$configured_file"
  fi
  if [[ "$configured_file" == "$CANONICAL_COMPOSE_FILE" \
    && -f "$CANONICAL_COMPOSE_FILE" && ! -L "$CANONICAL_COMPOSE_FILE" ]]; then
    return 0
  fi
  if [[ "$PINVI_PROVENANCE_PREPARED" == "1" \
    && -n "$PINVI_PROVENANCE_ARCHIVE_ROOT" \
    && "$configured_file" == "$PINVI_PROVENANCE_ARCHIVE_COMPOSE_FILE" \
    && "$configured_file" == "$PINVI_PROVENANCE_ARCHIVE_ROOT/context/infra/docker-compose.app.yml" \
    && -f "$configured_file" && ! -L "$configured_file" ]]; then
    local archive_compose_sha256
    archive_compose_sha256="$(sha256sum -- "$configured_file" | awk '{print $1}')"
    [[ "$archive_compose_sha256" == "$PINVI_PROVENANCE_ARCHIVE_COMPOSE_SHA256" ]] || {
      echo "immutable Compose archive was changed after provenance preparation" >&2
      return 2
    }
    return 0
  fi
  echo "fresh deploy requires the canonical application Compose file without an override" >&2
  return 2
}

require_isolated_database_endpoint() {
  local database_url legacy_database_url
  database_url="$(compose_env_value PINVI_DATABASE_URL "")"
  if [[ -n "$database_url" \
    && ! "$database_url" =~ ^postgresql\+asyncpg://[^@/]+@app-postgres:5432/pinvi$ ]]; then
    echo "deploy-node requires PINVI_DATABASE_URL to target the isolated app-postgres service" >&2
    return 2
  fi
  legacy_database_url="$(compose_env_value PINVI_LEGACY_REBASELINE_DATABASE_URL "")"
  if [[ -n "$legacy_database_url" \
    && ! "$legacy_database_url" =~ ^postgresql\+asyncpg://[^@/]+@app-postgres:5432/pinvi$ ]]; then
    echo "deploy-node requires the legacy rebaseline database URL to target the isolated app-postgres service" >&2
    return 2
  fi
}

validate_host_port() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]{0,4}$ ]] || (( value > 65535 )); then
    echo "${name} must be an integer host port between 1 and 65535" >&2
    return 2
  fi
}

validate_configured_ports() {
  validate_host_port PINVI_API_PORT "$API_PORT"
  validate_host_port PINVI_WEB_PORT "$WEB_PORT"
  validate_host_port PINVI_RUSTFS_PORT "$RUSTFS_PORT"
  validate_host_port PINVI_RUSTFS_CONSOLE_PORT "$RUSTFS_CONSOLE_PORT"
  validate_host_port PINVI_DAGSTER_DEV_PORT "$DAGSTER_PORT"
  validate_host_port PINVI_CADVISOR_PORT "$CADVISOR_PORT"
  validate_host_port PINVI_PROMETHEUS_PORT "$PROMETHEUS_PORT"
  validate_host_port PINVI_GRAFANA_PORT "$GRAFANA_PORT"
}

require_n150_execution_host() {
  local actual_arch actual_hostname actual_os_id actual_os_version
  actual_arch="$(uname -m)"
  actual_hostname="$(hostname -s 2>/dev/null || hostname)"
  actual_os_id="$(sed -n 's/^ID=//p' /etc/os-release 2>/dev/null | tr -d '"')"
  actual_os_version="$(sed -n 's/^VERSION_ID=//p' /etc/os-release 2>/dev/null | tr -d '"')"
  [[ "$actual_arch" == "x86_64" ]] || {
    echo "deploy-node is restricted to the N150 x86_64 execution host" >&2
    return 2
  }
  case "$actual_hostname" in
    n150|digitie-at-n150) ;;
    *)
      echo "deploy-node is restricted to the N150 execution host" >&2
      return 2
      ;;
  esac
  [[ "$actual_os_id" == "ubuntu" ]] || {
    echo "deploy-node requires an Ubuntu N150 execution host" >&2
    return 2
  }
  [[ "$actual_os_version" == "26.04" ]] || {
    echo "deploy-node requires the N150 Ubuntu 26.04 execution host" >&2
    return 2
  }
}

require_fresh_stack_contract() {
  local existing_containers existing_volumes existing_networks
  local all_containers all_volumes all_networks actual_name
  require_fresh_stack_identity
  if ! existing_containers="$(docker container ls --all \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.ID}}')"; then
    echo "could not inspect the fresh deploy Compose project" >&2
    return 1
  fi
  if ! existing_volumes="$(docker volume ls \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')"; then
    echo "could not inspect the fresh deploy PostgreSQL volume" >&2
    return 1
  fi
  if ! existing_networks="$(docker network ls \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')"; then
    echo "could not inspect the fresh deploy Compose network" >&2
    return 1
  fi
  if [[ -n "$existing_containers" || -n "$existing_volumes" || -n "$existing_networks" ]]; then
    echo "fresh deploy refuses an existing Compose project, PostgreSQL volume, or network" >&2
    return 2
  fi
  if ! all_containers="$(docker container ls --all --format '{{.Names}}')" \
    || ! all_volumes="$(docker volume ls --format '{{.Name}}')" \
    || ! all_networks="$(docker network ls --format '{{.Name}}')"; then
    echo "could not inspect unlabelled resources for a fresh deploy" >&2
    return 1
  fi
  while IFS= read -r actual_name; do
    [[ -n "$actual_name" && "$actual_name" == "$PROJECT-"* ]] || continue
    echo "fresh deploy refuses the existing project-scoped container ${actual_name}" >&2
    return 2
  done <<< "$all_containers"
  while IFS= read -r actual_name; do
    [[ -n "$actual_name" && ( "$actual_name" == "$PROJECT"_* || "$actual_name" == "$PROJECT-"* ) ]] || continue
    echo "fresh deploy refuses the existing project-scoped volume ${actual_name}" >&2
    return 2
  done <<< "$all_volumes"
  while IFS= read -r actual_name; do
    [[ -n "$actual_name" && ( "$actual_name" == "$PROJECT"_* || "$actual_name" == "$PROJECT-"* ) ]] || continue
    echo "fresh deploy refuses the existing project-scoped network ${actual_name}" >&2
    return 2
  done <<< "$all_networks"
}

fresh_stack_state_file_is_safe() {
  [[ "$FRESH_STACK_STATE_PATH" == /* && "$FRESH_STACK_STATE_PATH" != *:* \
    && "$FRESH_STACK_STATE_PATH" != *$'\n'* && "$FRESH_STACK_STATE_PATH" != */ ]] || {
    echo "PINVI_FRESH_STACK_STATE_PATH must be an absolute regular-file path" >&2
    return 2
  }
  local parent environment_name
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  parent="$(dirname -- "$FRESH_STACK_STATE_PATH")"
  [[ -d "$parent" && ! -L "$parent" ]] || {
    echo "fresh stack state parent must be an existing regular directory" >&2
    return 2
  }
  local parent_owner parent_mode
  parent_owner="$(stat -c '%u' -- "$parent")"
  parent_mode="$(stat -c '%a' -- "$parent")"
  if [[ "$environment_name" == staging || "$environment_name" == production ]]; then
    [[ "$parent_owner" == "0" ]] && (( (8#$parent_mode & 8#022) == 0 )) || {
      echo "staging/production fresh stack state parent must be root-owned and non-writable" >&2
      return 2
    }
  else
    [[ "$parent_owner" == "$(id -u)" ]] && (( (8#$parent_mode & 8#022) == 0 )) || {
      echo "fresh stack state parent must be owned by the current user and non-writable" >&2
      return 2
    }
  fi
  if [[ -e "$FRESH_STACK_STATE_PATH" || -L "$FRESH_STACK_STATE_PATH" ]]; then
    [[ -f "$FRESH_STACK_STATE_PATH" && ! -L "$FRESH_STACK_STATE_PATH" ]] || {
      echo "fresh stack state must be a regular non-symlink file" >&2
      return 2
    }
    local owner mode
    owner="$(stat -c '%u' -- "$FRESH_STACK_STATE_PATH")"
    mode="$(stat -c '%a' -- "$FRESH_STACK_STATE_PATH")"
    if [[ "$environment_name" == staging || "$environment_name" == production ]]; then
      [[ "$owner" == "0" && "$mode" == "600" ]] || {
        echo "staging/production fresh stack state must be root-owned mode 0600" >&2
        return 2
      }
    else
      [[ "$owner" == "$(id -u)" && "$mode" == "600" ]] || {
        echo "fresh stack state must be owned by the current user mode 0600" >&2
        return 2
      }
    fi
  fi
}

effective_compose_config_sha256() {
  compose config --format json | python3 -c '
import json
import sys

config = json.load(sys.stdin)
archive_root = sys.argv[1] if len(sys.argv) > 1 else ""

def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str) and archive_root:
        if value == archive_root:
            return "${PINVI_PROVENANCE_ARCHIVE_ROOT}"
        prefix = archive_root + "/"
        if value.startswith(prefix):
            return "${PINVI_PROVENANCE_ARCHIVE_ROOT}/" + value[len(prefix):]
    return value

config = normalize(config)
print(json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
' "$PINVI_PROVENANCE_ARCHIVE_ROOT" | sha256sum | awk '{print $1}'
}

fresh_stack_runtime_image_proof() {
  pinvi_verify_runtime_image_provenance app-api app-web
  FRESH_STACK_API_IMAGE_ID="$(pinvi_attested_runtime_image_id app-api)"
  FRESH_STACK_WEB_IMAGE_ID="$(pinvi_attested_runtime_image_id app-web)"
  if [[ "$ENABLE_DAGSTER" != "0" ]]; then
    pinvi_verify_runtime_image_provenance app-dagster
    FRESH_STACK_DAGSTER_IMAGE_ID="$(pinvi_attested_runtime_image_id app-dagster)"
  else
    FRESH_STACK_DAGSTER_IMAGE_ID="none"
  fi
  [[ "$FRESH_STACK_API_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ \
    && "$FRESH_STACK_WEB_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ \
    && ( "$FRESH_STACK_DAGSTER_IMAGE_ID" == "none" \
      || "$FRESH_STACK_DAGSTER_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ) ]]
}

write_fresh_stack_state() {
  fresh_stack_state_file_is_safe || return $?
  local source_revision environment_name source_path source_sha256 compose_sha256 tmp_path
  source_revision="${PINVI_SOURCE_REVISION:-}"
  [[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || {
    echo "fresh stack state requires the resolved Pinvi source revision" >&2
    return 2
  }
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  if ! capture_fresh_stack_migration_proof; then
    echo "migration succeeded but the fresh stack database proof could not be sealed" >&2
    return 1
  fi
  source_path="$(compose_env_source_file)"
  if [[ -n "$source_path" ]]; then
    source_sha256="$(sha256sum -- "$source_path" | awk '{print $1}')"
  else
    source_path="none"
    source_sha256="none"
  fi
  compose_sha256="$(sha256sum -- "$CANONICAL_COMPOSE_FILE" | awk '{print $1}')"
  [[ "$FRESH_STACK_EFFECTIVE_COMPOSE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "fresh stack state requires the effective Compose configuration proof" >&2
    return 1
  }
  tmp_path="$(mktemp "$(dirname -- "$FRESH_STACK_STATE_PATH")/.fresh-stack.XXXXXX")"
  if ! {
    printf 'version=3\n'
    printf 'project=%s\n' "$PROJECT"
    printf 'environment=%s\n' "$environment_name"
    printf 'root_dir=%s\n' "$ROOT_DIR"
    printf 'source_revision=%s\n' "$source_revision"
    printf 'compose_sha256=%s\n' "$compose_sha256"
    printf 'effective_compose_sha256=%s\n' "$FRESH_STACK_EFFECTIVE_COMPOSE_SHA256"
    printf 'environment_source_path=%s\n' "$source_path"
    printf 'environment_source_sha256=%s\n' "$source_sha256"
    printf 'db_container_id=%s\n' "$FRESH_STACK_DB_CONTAINER_ID"
    printf 'db_volume_name=%s\n' "$FRESH_STACK_DB_VOLUME_NAME"
    printf 'db_system_identifier=%s\n' "$FRESH_STACK_DB_SYSTEM_IDENTIFIER"
    printf 'alembic_version=%s\n' "$FRESH_STACK_ALEMBIC_VERSION"
    printf 'api_image_id=%s\n' "$FRESH_STACK_API_IMAGE_ID"
    printf 'web_image_id=%s\n' "$FRESH_STACK_WEB_IMAGE_ID"
    printf 'dagster_image_id=%s\n' "$FRESH_STACK_DAGSTER_IMAGE_ID"
    printf 'migration_receipt_sha256=%s\n' "$FRESH_STACK_MIGRATION_RECEIPT_SHA256"
  } >"$tmp_path"; then
    rm -f -- "$tmp_path"
    return 1
  fi
  chmod 600 -- "$tmp_path"
  if ! mv -f -- "$tmp_path" "$FRESH_STACK_STATE_PATH"; then
    rm -f -- "$tmp_path"
    return 1
  fi
  fresh_stack_state_file_is_safe
}

fresh_stack_migration_receipt_sha256() {
  local environment_name
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  printf 'pinvi-fresh-migration/v3\nproject=%s\nenvironment=%s\nroot_dir=%s\nsource_revision=%s\ncompose_sha256=%s\neffective_compose_sha256=%s\nenvironment_source_sha256=%s\ndb_container_id=%s\ndb_volume_name=%s\ndb_system_identifier=%s\nalembic_version=%s\napi_image_id=%s\nweb_image_id=%s\ndagster_image_id=%s\n' \
    "$PROJECT" "$environment_name" "$ROOT_DIR" "${PINVI_SOURCE_REVISION:-}" \
    "$FRESH_STACK_COMPOSE_SHA256" "$FRESH_STACK_EFFECTIVE_COMPOSE_SHA256" \
    "$FRESH_STACK_ENVIRONMENT_SOURCE_SHA256" \
    "$FRESH_STACK_DB_CONTAINER_ID" "$FRESH_STACK_DB_VOLUME_NAME" \
    "$FRESH_STACK_DB_SYSTEM_IDENTIFIER" "$FRESH_STACK_ALEMBIC_VERSION" \
    "$FRESH_STACK_API_IMAGE_ID" "$FRESH_STACK_WEB_IMAGE_ID" "$FRESH_STACK_DAGSTER_IMAGE_ID" \
    | sha256sum | awk '{print $1}'
}

capture_fresh_stack_migration_proof() {
  local environment_name source_path db_container_ids db_container_id db_volume_name
  local owner_user db_system_identifier alembic_version
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  if ! fresh_stack_runtime_image_proof; then
    echo "fresh deploy runtime image provenance could not be sealed" >&2
    return 1
  fi
  FRESH_STACK_COMPOSE_SHA256="$(sha256sum -- "$CANONICAL_COMPOSE_FILE" | awk '{print $1}')"
  if ! FRESH_STACK_EFFECTIVE_COMPOSE_SHA256="$(effective_compose_config_sha256)"; then
    echo "could not resolve the effective canonical Compose configuration" >&2
    return 1
  fi
  [[ "$FRESH_STACK_EFFECTIVE_COMPOSE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "effective canonical Compose configuration digest is invalid" >&2
    return 1
  }
  source_path="$(compose_env_source_file)"
  if [[ -n "$source_path" ]]; then
    FRESH_STACK_ENVIRONMENT_SOURCE_SHA256="$(sha256sum -- "$source_path" | awk '{print $1}')"
  else
    FRESH_STACK_ENVIRONMENT_SOURCE_SHA256="none"
  fi
  if ! db_container_ids="$(docker container ls --all \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter 'label=com.docker.compose.service=app-postgres' --format '{{.ID}}')"; then
    echo "could not inspect the fresh deploy PostgreSQL container" >&2
    return 1
  fi
  if [[ "$(printf '%s\n' "$db_container_ids" | sed '/^$/d' | wc -l)" != "1" ]]; then
    echo "fresh deploy requires exactly one project-scoped PostgreSQL container" >&2
    return 2
  fi
  db_container_id="$(printf '%s\n' "$db_container_ids" | sed '/^$/d')"
  if [[ "$(docker container inspect --format '{{.State.Running}}' "$db_container_id")" != "true" ]]; then
    echo "fresh deploy requires the migrated PostgreSQL container to be running" >&2
    return 2
  fi
  if ! db_volume_name="$(docker container inspect --format \
    '{{range .Mounts}}{{if and (eq .Destination "/var/lib/postgresql/data") (eq .Type "volume")}}{{.Name}}{{end}}{{end}}' \
    "$db_container_id")"; then
    echo "could not inspect the fresh deploy PostgreSQL volume" >&2
    return 1
  fi
  [[ -n "$db_volume_name" ]] || {
    echo "fresh deploy requires a named PostgreSQL data volume" >&2
    return 2
  }
  owner_user="$(compose_env_value PINVI_DB_OWNER_USER pinvi_owner)"
  [[ "$owner_user" =~ ^[a-z_][a-z0-9_]*$ ]] || {
    echo "fresh deploy PostgreSQL owner name is invalid" >&2
    return 2
  }
  if ! db_system_identifier="$(docker exec "$db_container_id" psql -U "$owner_user" -d pinvi -Atqc \
    'SELECT system_identifier FROM pg_control_system();' | tr -d '[:space:]')"; then
    echo "could not read the migrated PostgreSQL system identifier" >&2
    return 1
  fi
  if ! alembic_version="$(docker exec "$db_container_id" psql -U "$owner_user" -d pinvi -Atqc \
    "SELECT string_agg(version_num, ',' ORDER BY version_num) FROM app.alembic_version;" | tr -d '[:space:]')"; then
    echo "could not read the migrated Alembic revision" >&2
    return 1
  fi
  [[ "$db_system_identifier" =~ ^[0-9]+$ && "$alembic_version" == "20260824_0101" ]] || {
    echo "fresh deploy requires the canonical 0101 Alembic revision and a PostgreSQL identity" >&2
    return 2
  }
  FRESH_STACK_DB_CONTAINER_ID="$db_container_id"
  FRESH_STACK_DB_VOLUME_NAME="$db_volume_name"
  FRESH_STACK_DB_SYSTEM_IDENTIFIER="$db_system_identifier"
  FRESH_STACK_ALEMBIC_VERSION="$alembic_version"
  if ! FRESH_STACK_MIGRATION_RECEIPT_SHA256="$(fresh_stack_migration_receipt_sha256)"; then
    echo "could not compute the fresh migration receipt" >&2
    return 1
  fi
  [[ "$FRESH_STACK_MIGRATION_RECEIPT_SHA256" =~ ^[0-9a-f]{64}$ ]]
}

require_reusable_fresh_stack_contract() {
  local state_version="" state_project="" state_environment="" state_root_dir="" state_revision=""
  local state_compose_sha256="" state_environment_source_path="" state_environment_source_sha256=""
  local state_effective_compose_sha256=""
  local state_db_container_id="" state_db_volume_name="" state_db_system_identifier=""
  local state_alembic_version="" state_api_image_id="" state_web_image_id=""
  local state_dagster_image_id="" state_migration_receipt_sha256=""
  local environment_name source_path compose_sha256 source_sha256 effective_compose_sha256
  local key value seen_keys='|' existing_containers existing_volumes existing_networks db_containers rustfs_containers
  require_fresh_stack_identity
  fresh_stack_state_file_is_safe || return $?
  [[ -f "$FRESH_STACK_STATE_PATH" ]] || {
    echo "standalone up/dagster requires a successful migrate state for this fresh stack" >&2
    return 2
  }
  while IFS='=' read -r key value; do
    [[ -n "$key" ]] || {
      echo "fresh stack state contains an empty field" >&2
      return 2
    }
    [[ "$seen_keys" != *"|$key|"* ]] || {
      echo "fresh stack state contains a duplicate field" >&2
      return 2
    }
    seen_keys+="$key|"
    case "$key" in
      version) state_version="$value" ;;
      project) state_project="$value" ;;
      environment) state_environment="$value" ;;
      root_dir) state_root_dir="$value" ;;
      source_revision) state_revision="$value" ;;
      compose_sha256) state_compose_sha256="$value" ;;
      effective_compose_sha256) state_effective_compose_sha256="$value" ;;
      environment_source_path) state_environment_source_path="$value" ;;
      environment_source_sha256) state_environment_source_sha256="$value" ;;
      db_container_id) state_db_container_id="$value" ;;
      db_volume_name) state_db_volume_name="$value" ;;
      db_system_identifier) state_db_system_identifier="$value" ;;
      alembic_version) state_alembic_version="$value" ;;
      api_image_id) state_api_image_id="$value" ;;
      web_image_id) state_web_image_id="$value" ;;
      dagster_image_id) state_dagster_image_id="$value" ;;
      migration_receipt_sha256) state_migration_receipt_sha256="$value" ;;
      *) echo "fresh stack state contains an unknown field" >&2; return 2 ;;
    esac
  done < "$FRESH_STACK_STATE_PATH"
  if ! environment_name="$(resolved_environment)"; then
    return 2
  fi
  source_path="$(compose_env_source_file)"
  if [[ -n "$source_path" ]]; then
    source_sha256="$(sha256sum -- "$source_path" | awk '{print $1}')"
  else
    source_path="none"
    source_sha256="none"
  fi
  compose_sha256="$(sha256sum -- "$CANONICAL_COMPOSE_FILE" | awk '{print $1}')"
  if ! effective_compose_sha256="$(effective_compose_config_sha256)"; then
    return 1
  fi
  [[ "$seen_keys" == *"|version|"* && "$seen_keys" == *"|project|"* \
    && "$seen_keys" == *"|environment|"* && "$seen_keys" == *"|root_dir|"* \
    && "$seen_keys" == *"|source_revision|"* \
    && "$seen_keys" == *"|compose_sha256|"* \
    && "$seen_keys" == *"|effective_compose_sha256|"* \
    && "$seen_keys" == *"|environment_source_path|"* \
    && "$seen_keys" == *"|environment_source_sha256|"* \
    && "$seen_keys" == *"|db_container_id|"* && "$seen_keys" == *"|db_volume_name|"* \
    && "$seen_keys" == *"|db_system_identifier|"* && "$seen_keys" == *"|alembic_version|"* \
    && "$seen_keys" == *"|api_image_id|"* && "$seen_keys" == *"|web_image_id|"* \
    && "$seen_keys" == *"|dagster_image_id|"* \
    && "$seen_keys" == *"|migration_receipt_sha256|"* \
    && "$state_version" == "3" && "$state_project" == "$PROJECT" \
    && "$state_environment" == "$environment_name" \
    && "$state_root_dir" == "$ROOT_DIR" \
    && "$state_revision" == "${PINVI_SOURCE_REVISION:-}" \
    && "$state_compose_sha256" == "$compose_sha256" \
    && "$state_effective_compose_sha256" == "$effective_compose_sha256" \
    && "$state_environment_source_path" == "$source_path" \
    && "$state_environment_source_sha256" == "$source_sha256" \
    && "$state_db_container_id" =~ ^[0-9a-f]{12,64}$ \
    && "$state_db_volume_name" != "" \
    && "$state_db_system_identifier" =~ ^[0-9]+$ \
    && "$state_alembic_version" == "20260824_0101" \
    && "$state_api_image_id" =~ ^sha256:[0-9a-f]{64}$ \
    && "$state_web_image_id" =~ ^sha256:[0-9a-f]{64}$ \
    && ( "$state_dagster_image_id" == "none" \
      || "$state_dagster_image_id" =~ ^sha256:[0-9a-f]{64}$ ) \
    && "$state_migration_receipt_sha256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "fresh stack state does not match the requested project, environment, source, or migration proof" >&2
    return 2
  }
  if ! existing_containers="$(docker container ls --all \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.ID}}')" \
    || ! existing_volumes="$(docker volume ls \
      --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')" \
    || ! existing_networks="$(docker network ls \
      --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')"; then
    echo "could not inspect the reusable fresh deploy Compose project" >&2
    return 1
  fi
  [[ -n "$existing_containers" && -n "$existing_volumes" && -n "$existing_networks" ]] || {
    echo "reusable fresh deploy requires the migrated Compose project, PostgreSQL volume, and network" >&2
    return 2
  }
  if ! require_reusable_fresh_stack_resource_shape; then
    return 1
  fi
  if ! db_containers="$(docker container ls --all \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter 'label=com.docker.compose.service=app-postgres' --format '{{.ID}}')" \
    || ! rustfs_containers="$(docker container ls --all \
      --filter "label=com.docker.compose.project=${PROJECT}" \
      --filter 'label=com.docker.compose.service=app-rustfs' --format '{{.ID}}')"; then
    echo "could not inspect reusable fresh deploy database dependencies" >&2
    return 1
  fi
  [[ "$(printf '%s\n' "$db_containers" | sed '/^$/d' | wc -l)" == "1" \
    && "$(printf '%s\n' "$rustfs_containers" | sed '/^$/d' | wc -l)" == "1" ]] || {
    echo "reusable fresh deploy requires the migrated app-postgres and app-rustfs services" >&2
    return 2
  }
  if ! capture_fresh_stack_migration_proof; then
    return 1
  fi
  [[ "$FRESH_STACK_DB_CONTAINER_ID" == "$state_db_container_id" \
    && "$FRESH_STACK_DB_VOLUME_NAME" == "$state_db_volume_name" \
    && "$FRESH_STACK_DB_SYSTEM_IDENTIFIER" == "$state_db_system_identifier" \
    && "$FRESH_STACK_ALEMBIC_VERSION" == "$state_alembic_version" \
    && "$FRESH_STACK_API_IMAGE_ID" == "$state_api_image_id" \
    && "$FRESH_STACK_WEB_IMAGE_ID" == "$state_web_image_id" \
    && "$FRESH_STACK_DAGSTER_IMAGE_ID" == "$state_dagster_image_id" \
    && "$FRESH_STACK_MIGRATION_RECEIPT_SHA256" == "$state_migration_receipt_sha256" ]] || {
    echo "fresh stack database identity or migration proof no longer matches the sealed state" >&2
    return 2
  }
}

require_reusable_fresh_stack_resource_shape() {
  local project_containers service container_count
  local postgres_count=0 rustfs_count=0 rustfs_init_count=0 api_count=0 web_count=0 dagster_count=0
  local container_id project_volumes volume project_networks network
  if ! project_containers="$(docker container ls --all \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.ID}}')"; then
    echo "could not inspect reusable fresh deploy containers" >&2
    return 1
  fi
  while IFS= read -r container_id; do
    [[ -n "$container_id" ]] || continue
    if ! service="$(docker container inspect --format \
      '{{ index .Config.Labels "com.docker.compose.service" }}' "$container_id")"; then
      echo "could not inspect reusable fresh deploy service labels" >&2
      return 1
    fi
    case "$service" in
      app-postgres) ((postgres_count+=1)) ;;
      app-rustfs) ((rustfs_count+=1)) ;;
      app-rustfs-init) ((rustfs_init_count+=1)) ;;
      app-api) ((api_count+=1)) ;;
      app-web) ((web_count+=1)) ;;
      app-dagster) ((dagster_count+=1)) ;;
      *)
        echo "reusable fresh deploy refuses unexpected Compose service: ${service:-<missing>}" >&2
        return 2
        ;;
    esac
  done <<< "$project_containers"
  [[ "$postgres_count" == "1" && "$rustfs_count" == "1" \
    && "$rustfs_init_count" -le 1 \
    && "$api_count" == "$web_count" \
    && "$api_count" -le 1 && "$dagster_count" -le 1 ]] || {
    echo "reusable fresh deploy requires one database/object store and at most one runtime per service" >&2
    return 2
  }
  if ! project_volumes="$(docker volume ls \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')"; then
    echo "could not inspect reusable fresh deploy volumes" >&2
    return 1
  fi
  while IFS= read -r volume; do
    [[ -n "$volume" ]] || continue
    case "$volume" in
      "${PROJECT}_app-postgres"|"${PROJECT}_app-dagster") ;;
      *)
        echo "reusable fresh deploy refuses unexpected project volume: ${volume}" >&2
        return 2
        ;;
    esac
  done <<< "$project_volumes"
  if ! project_networks="$(docker network ls \
    --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Name}}')"; then
    echo "could not inspect reusable fresh deploy networks" >&2
    return 1
  fi
  [[ "$(printf '%s\n' "$project_networks" | sed '/^$/d' | wc -l)" == "1" \
    && "$(printf '%s\n' "$project_networks" | sed '/^$/d')" == "${PROJECT}_default" ]] || {
    echo "reusable fresh deploy requires exactly the canonical project network" >&2
    return 2
  }
}

require_fresh_stack_identity() {
  [[ "$DEPLOY_MANAGER_UNAVAILABLE" == "1" ]] || {
    echo "fresh deploy requires explicit PINVI_DOCKER_MANAGER_UNAVAILABLE=1" >&2
    return 2
  }
  [[ "$DEPLOY_FRESH_STACK" == "1" ]] || {
    echo "deploy-node deploy requires PINVI_DEPLOY_FRESH_STACK=1" >&2
    return 2
  }
  [[ -n "${PINVI_DOCKER_PROJECT:-}" && "$PROJECT" != "pinvi-app" \
    && "$PROJECT" =~ ^pinvi-[a-z0-9][a-z0-9-]*$ ]] || {
    echo "fresh deploy requires an explicit isolated PINVI_DOCKER_PROJECT" >&2
    return 2
  }
  require_n150_execution_host
  require_canonical_compose_file
  require_isolated_database_endpoint
}

assert_host_ports_available_before_migration() {
  require_command ss
  local port listeners container_ids container_id actual_project
  for port in "$API_PORT" "$WEB_PORT" "$RUSTFS_PORT" "$RUSTFS_CONSOLE_PORT" \
    "$DAGSTER_PORT" "$CADVISOR_PORT" "$PROMETHEUS_PORT" "$GRAFANA_PORT"; do
    if ! listeners="$(ss -H -ltn "sport = :${port}" 2>/dev/null)"; then
      echo "could not inspect host port ${port}; refusing migration" >&2
      return 1
    fi
    [[ -n "$listeners" ]] || continue
    if ! container_ids="$(docker ps --filter "publish=${port}" --format '{{.ID}}')"; then
      echo "could not inspect containers publishing host port ${port}; refusing migration" >&2
      return 1
    fi
    if [[ -z "$container_ids" ]]; then
      echo "host port ${port} is occupied by a non-project listener; refusing migration" >&2
      return 2
    fi
    while IFS= read -r container_id; do
      [[ -n "$container_id" ]] || continue
      if ! actual_project="$(docker container inspect --format \
        '{{ index .Config.Labels "com.docker.compose.project" }}' "$container_id")"; then
        echo "could not inspect the host port ${port} container; refusing migration" >&2
        return 1
      fi
      if [[ "$actual_project" != "$PROJECT" ]]; then
        echo "host port ${port} is occupied by another Compose project; refusing migration" >&2
        return 2
      fi
    done <<< "$container_ids"
  done
}

pull_images() {
  pinvi_prepare_api_image_provenance
  log "pulling app images"
  compose pull app-api app-web
  if dagster_rollout_enabled; then
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
  if dagster_rollout_enabled; then
    compose --profile etl build app-dagster
  fi
  if dagster_rollout_enabled; then
    pinvi_verify_runtime_image_provenance app-api app-web app-dagster
  else
    pinvi_verify_runtime_image_provenance app-api app-web
  fi
}

runtime_dagster_is_running() {
  local -a container_ids=()
  if ! pinvi_runtime_container_ids_into_array container_ids app-dagster running; then
    return 1
  fi
  (( ${#container_ids[@]} > 0 ))
}

dagster_rollout_enabled() {
  [[ "$ENABLE_DAGSTER" != "0" ]] && return 0
  local -a container_ids=()
  if ! pinvi_runtime_container_ids_into_array container_ids app-dagster running; then
    echo "runtime Dagster discovery failed; refusing to continue with Dagster disabled" >&2
    exit 1
  fi
  (( ${#container_ids[@]} > 0 ))
}

runtime_writer_container_id() {
  local service="$1"
  pinvi_runtime_container_ids "$service" running
}

runtime_capture_predeploy_container_ids() {
  RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
  if ! pinvi_runtime_container_ids_into_array RUNTIME_PREDEPLOY_API_CONTAINER_IDS app-api; then
    return 1
  fi
  if ! pinvi_runtime_container_ids_into_array RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS app-web; then
    return 1
  fi
  if ! pinvi_runtime_container_ids_into_array RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS app-dagster; then
    return 1
  fi
  runtime_capture_predeploy_stopped_container_ids
}

runtime_capture_predeploy_stopped_container_ids() {
  local service container_id running
  for service in app-api app-web app-dagster; do
    case "$service" in
      app-api) for container_id in "${RUNTIME_PREDEPLOY_API_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          return 1
        fi
        if [[ "$running" != "true" ]]; then
          RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS+=("$container_id")
        fi
      done ;;
      app-web) for container_id in "${RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          return 1
        fi
        if [[ "$running" != "true" ]]; then
          RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS+=("$container_id")
        fi
      done ;;
      app-dagster) for container_id in "${RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          return 1
        fi
        if [[ "$running" != "true" ]]; then
          RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS+=("$container_id")
        fi
      done ;;
    esac
  done
}

runtime_id_was_existing() {
  local service="$1"
  local container_id="$2"
  local old_id
  case "$service" in
    app-api) for old_id in "${RUNTIME_PREDEPLOY_API_CONTAINER_IDS[@]}"; do [[ "$old_id" == "$container_id" ]] && return 0; done ;;
    app-web) for old_id in "${RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS[@]}"; do [[ "$old_id" == "$container_id" ]] && return 0; done ;;
    app-dagster) for old_id in "${RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS[@]}"; do [[ "$old_id" == "$container_id" ]] && return 0; done ;;
  esac
  return 1
}

runtime_stop_reused_predeploy_stopped_writers() {
  local service container_id running stop_failed="0"
  for service in app-api app-web app-dagster; do
    case "$service" in
      app-api) for container_id in "${RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          stop_failed="1"
        elif [[ "$running" == "true" ]] && ! docker stop "$container_id" >/dev/null; then
          stop_failed="1"
        fi
      done ;;
      app-web) for container_id in "${RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          stop_failed="1"
        elif [[ "$running" == "true" ]] && ! docker stop "$container_id" >/dev/null; then
          stop_failed="1"
        fi
      done ;;
      app-dagster) for container_id in "${RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS[@]}"; do
        if ! running="$(docker container inspect --format '{{.State.Running}}' "$container_id")"; then
          stop_failed="1"
        elif [[ "$running" == "true" ]] && ! docker stop "$container_id" >/dev/null; then
          stop_failed="1"
        fi
      done ;;
    esac
  done
  [[ "$stop_failed" == "0" ]]
}

runtime_record_new_container_ids() {
  local service="$1"
  local container_id
  local -a container_ids=()
  case "$service" in
    app-api) RUNTIME_NEW_API_CONTAINER_IDS=() ;;
    app-web) RUNTIME_NEW_WEB_CONTAINER_IDS=() ;;
    app-dagster) RUNTIME_NEW_DAGSTER_CONTAINER_IDS=() ;;
    *) return 2 ;;
  esac
  if ! pinvi_runtime_container_ids_into_array container_ids "$service"; then
    return 1
  fi
  for container_id in "${container_ids[@]}"; do
    [[ -n "$container_id" ]] || continue
    if ! runtime_id_was_existing "$service" "$container_id"; then
      case "$service" in
        app-api) RUNTIME_NEW_API_CONTAINER_IDS+=("$container_id") ;;
        app-web) RUNTIME_NEW_WEB_CONTAINER_IDS+=("$container_id") ;;
        app-dagster) RUNTIME_NEW_DAGSTER_CONTAINER_IDS+=("$container_id") ;;
      esac
    fi
  done
}

runtime_new_container_ids() {
  local service="$1"
  local container_id
  case "$service" in
    app-api) for container_id in "${RUNTIME_NEW_API_CONTAINER_IDS[@]}"; do printf '%s\n' "$container_id"; done ;;
    app-web) for container_id in "${RUNTIME_NEW_WEB_CONTAINER_IDS[@]}"; do printf '%s\n' "$container_id"; done ;;
    app-dagster) for container_id in "${RUNTIME_NEW_DAGSTER_CONTAINER_IDS[@]}"; do printf '%s\n' "$container_id"; done ;;
  esac
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

runtime_writer_container_name() {
  local container_id="$1"
  docker container inspect --format '{{.Name}}' "$container_id" | sed 's#^/##'
}

runtime_snapshot_preflight() {
  local service stale_snapshot_ids
  for service in app-api app-web app-dagster; do
    if ! stale_snapshot_ids="$(pinvi_runtime_predeploy_snapshot_ids "$service")"; then
      echo "pre-deploy ${service} snapshot discovery failed; refusing runtime mutation" >&2
      return 1
    fi
    if [[ -n "$stale_snapshot_ids" ]]; then
      echo "pre-deploy ${service} snapshot already exists; refusing stale rollback artifact" >&2
      return 2
    fi
  done
  [[ "$RUNTIME_DEPLOY_PRESERVE" == "1" ]] || return 0
  if (( ${#RUNTIME_PREDEPLOY_API_CONTAINER_IDS[@]} > 0 \
    || ${#RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS[@]} > 0 \
    || ${#RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS[@]} > 0 )); then
    echo "in-place runtime snapshot is disabled; use the manager pinned rebuild for an existing runtime" >&2
    return 2
  fi
  local service container_id container_name backup_name
  for service in app-api app-web app-dagster; do
    case "$service" in
      app-api) container_id="$RUNTIME_API_CONTAINER_ID" ;;
      app-web) container_id="$RUNTIME_WEB_CONTAINER_ID" ;;
      app-dagster) container_id="$RUNTIME_DAGSTER_CONTAINER_ID" ;;
    esac
    [[ -n "$container_id" ]] || continue
    if ! container_name="$(runtime_writer_container_name "$container_id")"; then
      return 1
    fi
    backup_name="${container_name}.pinvi-predeploy"
    if docker container inspect "$backup_name" >/dev/null 2>&1; then
      echo "pre-deploy ${service} snapshot name already exists: ${backup_name}" >&2
      return 1
    fi
    case "$service" in
      app-api) RUNTIME_API_CONTAINER_NAME="$container_name"; RUNTIME_API_BACKUP_NAME="$backup_name" ;;
      app-web) RUNTIME_WEB_CONTAINER_NAME="$container_name"; RUNTIME_WEB_BACKUP_NAME="$backup_name" ;;
      app-dagster) RUNTIME_DAGSTER_CONTAINER_NAME="$container_name"; RUNTIME_DAGSTER_BACKUP_NAME="$backup_name" ;;
    esac
  done
}

runtime_update_snapshot_renamed_flag() {
  if [[ "$RUNTIME_API_SNAPSHOT_RENAMED" == "1" || "$RUNTIME_WEB_SNAPSHOT_RENAMED" == "1" \
    || "$RUNTIME_DAGSTER_SNAPSHOT_RENAMED" == "1" ]]; then
    RUNTIME_SNAPSHOT_RENAMED="1"
  else
    RUNTIME_SNAPSHOT_RENAMED="0"
  fi
}

runtime_snapshot_matches_captured_writer() {
  local service="$1"
  local backup_name="$2"
  local expected_id expected_image actual_id actual_image actual_project actual_service metadata
  case "$service" in
    app-api) expected_id="$RUNTIME_API_CONTAINER_ID"; expected_image="$RUNTIME_API_IMAGE_ID" ;;
    app-web) expected_id="$RUNTIME_WEB_CONTAINER_ID"; expected_image="$RUNTIME_WEB_IMAGE_ID" ;;
    app-dagster) expected_id="$RUNTIME_DAGSTER_CONTAINER_ID"; expected_image="$RUNTIME_DAGSTER_IMAGE_ID" ;;
    *) return 2 ;;
  esac
  if ! metadata="$(docker container inspect --format \
    '{{.Id}}|{{.Image}}|{{ index .Config.Labels "com.docker.compose.project" }}|{{ index .Config.Labels "com.docker.compose.service" }}' \
    "$backup_name")"; then
    return 1
  fi
  IFS='|' read -r actual_id actual_image actual_project actual_service <<< "$metadata"
  if [[ "$actual_id" != "$expected_id" || "$actual_image" != "$expected_image" \
    || "$actual_project" != "$PROJECT" || "$actual_service" != "$service" ]]; then
    echo "pre-deploy ${service} snapshot identity drifted; refusing name restoration" >&2
    return 1
  fi
}

restore_runtime_snapshot_name() {
  local service="$1"
  local renamed backup_name container_name
  case "$service" in
    app-api)
      renamed="$RUNTIME_API_SNAPSHOT_RENAMED"
      backup_name="$RUNTIME_API_BACKUP_NAME"
      container_name="$RUNTIME_API_CONTAINER_NAME"
      ;;
    app-web)
      renamed="$RUNTIME_WEB_SNAPSHOT_RENAMED"
      backup_name="$RUNTIME_WEB_BACKUP_NAME"
      container_name="$RUNTIME_WEB_CONTAINER_NAME"
      ;;
    app-dagster)
      renamed="$RUNTIME_DAGSTER_SNAPSHOT_RENAMED"
      backup_name="$RUNTIME_DAGSTER_BACKUP_NAME"
      container_name="$RUNTIME_DAGSTER_CONTAINER_NAME"
      ;;
    *) return 2 ;;
  esac
  [[ "$renamed" == "1" ]] || return 0
  if ! docker container inspect "$backup_name" >/dev/null 2>&1; then
    echo "pre-deploy ${service} snapshot disappeared before name restoration: ${backup_name}" >&2
    return 1
  fi
  if ! runtime_snapshot_matches_captured_writer "$service" "$backup_name"; then
    return 1
  fi
  if ! docker rename "$backup_name" "$container_name"; then
    echo "pre-deploy ${service} snapshot could not be renamed back: ${backup_name}" >&2
    return 1
  fi
  case "$service" in
    app-api) RUNTIME_API_SNAPSHOT_RENAMED="0" ;;
    app-web) RUNTIME_WEB_SNAPSHOT_RENAMED="0" ;;
    app-dagster) RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0" ;;
  esac
  runtime_update_snapshot_renamed_flag
}

restore_runtime_snapshot_names() {
  local restore_failed="0"
  local service
  for service in app-api app-web app-dagster; do
    if ! restore_runtime_snapshot_name "$service"; then
      restore_failed="1"
    fi
  done
  runtime_update_snapshot_renamed_flag
  [[ "$restore_failed" == "0" ]]
}

remove_recorded_new_runtime_writers() {
  local service container_id removal_failed="0"
  local -a container_ids=()
  for service in app-api app-web app-dagster; do
    mapfile -t container_ids < <(runtime_new_container_ids "$service")
    for container_id in "${container_ids[@]}"; do
      [[ -n "$container_id" ]] || continue
      if ! docker rm -f "$container_id" >/dev/null; then
        removal_failed="1"
      fi
    done
  done
  [[ "$removal_failed" == "0" ]]
}

contain_unverified_runtime_writers() {
  local containment_failed="0"
  # discovery가 실패한 뒤에는 이름/label을 다시 추론해 삭제하지 않는다. 대신 Compose가
  # 관리하는 writer 세 개를 중지해 검증되지 않은 새 runtime이 요청을 받지 못하게 한다.
  if ! compose stop app-web; then
    containment_failed="1"
  fi
  if ! compose stop app-api; then
    containment_failed="1"
  fi
  if ! compose --profile etl stop app-dagster; then
    containment_failed="1"
  fi
  [[ "$containment_failed" == "0" ]]
}

remove_new_runtime_writers() {
  local containment_failed="0"
  local removal_failed="0"
  if [[ "$RUNTIME_CONTAINER_DISCOVERY_FAILED" == "1" ]]; then
    log "runtime container discovery failed; containing managed writers before rollback"
    if ! contain_unverified_runtime_writers; then
      containment_failed="1"
    fi
    # 이 invocation이 이미 기록한 ID만 제거한다. discovery로 새 ID를 추론하지 않는다.
    if ! remove_recorded_new_runtime_writers; then
      removal_failed="1"
    fi
    if [[ "$containment_failed" != "0" || "$removal_failed" != "0" ]]; then
      log "runtime containment is incomplete; manual recovery is required before any snapshot restore"
    fi
    return 1
  fi
  remove_recorded_new_runtime_writers
}

preserve_runtime_writers() {
  local api_name="" web_name="" dagster_name=""
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]]; then
    if ! api_name="$(runtime_writer_container_name "$RUNTIME_API_CONTAINER_ID")"; then
      return 1
    fi
    RUNTIME_API_CONTAINER_NAME="$api_name"
    RUNTIME_API_BACKUP_NAME="${api_name}.pinvi-predeploy"
    if docker container inspect "$RUNTIME_API_BACKUP_NAME" >/dev/null 2>&1; then
      echo "pre-deploy API snapshot name already exists: $RUNTIME_API_BACKUP_NAME" >&2
      return 1
    fi
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]]; then
    if ! web_name="$(runtime_writer_container_name "$RUNTIME_WEB_CONTAINER_ID")"; then
      return 1
    fi
    RUNTIME_WEB_CONTAINER_NAME="$web_name"
    RUNTIME_WEB_BACKUP_NAME="${web_name}.pinvi-predeploy"
    if docker container inspect "$RUNTIME_WEB_BACKUP_NAME" >/dev/null 2>&1; then
      echo "pre-deploy Web snapshot name already exists: $RUNTIME_WEB_BACKUP_NAME" >&2
      return 1
    fi
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    if ! dagster_name="$(runtime_writer_container_name "$RUNTIME_DAGSTER_CONTAINER_ID")"; then
      return 1
    fi
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
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]]; then
    RUNTIME_API_SNAPSHOT_RENAMED="1"
    runtime_update_snapshot_renamed_flag
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]] && ! docker rename \
    "$RUNTIME_WEB_CONTAINER_ID" "$RUNTIME_WEB_BACKUP_NAME"; then
    if ! restore_runtime_snapshot_names; then
      echo "runtime snapshot name rollback failed after Web rename failure" >&2
    fi
    return 1
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]]; then
    RUNTIME_WEB_SNAPSHOT_RENAMED="1"
    runtime_update_snapshot_renamed_flag
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]] && ! docker rename \
    "$RUNTIME_DAGSTER_CONTAINER_ID" "$RUNTIME_DAGSTER_BACKUP_NAME"; then
    if ! restore_runtime_snapshot_names; then
      echo "runtime snapshot name rollback failed after Dagster rename failure" >&2
    fi
    return 1
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    RUNTIME_DAGSTER_SNAPSHOT_RENAMED="1"
    runtime_update_snapshot_renamed_flag
  fi
}

rollback_preserved_runtime_writers() {
  local rollback_failed="0"
  if ! runtime_stop_reused_predeploy_stopped_writers; then
    rollback_failed="1"
  fi
  if [[ "$RUNTIME_NEW_WRITERS_STARTED" == "1" ]] && ! remove_new_runtime_writers; then
    # Discovery/containment failure 뒤에는 현재 runtime을 다시 추론하거나 snapshot을 되살리지
    # 않는다. 기록한 ID의 cleanup은 위에서 끝냈으며, 남은 상태는 수동 복구 전까지 검증되지 않는다.
    return 1
  fi
  if [[ "$rollback_failed" != "0" ]]; then
    return 1
  fi
  if ! restore_runtime_snapshot_names; then
    rollback_failed="1"
  fi
  if [[ "$rollback_failed" == "0" ]] && ! restore_runtime_writers_without_rollback; then
    rollback_failed="1"
  fi
  if [[ "$rollback_failed" == "0" ]]; then
    RUNTIME_DEPLOY_PRESERVE="0"
    RUNTIME_NEW_WRITERS_STARTED="0"
    RUNTIME_SNAPSHOT_RENAMED="0"
    RUNTIME_NEW_API_CONTAINER_IDS=()
    RUNTIME_NEW_WEB_CONTAINER_IDS=()
    RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
    RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
    RUNTIME_CONTAINER_DISCOVERY_FAILED="0"
  fi
  [[ "$rollback_failed" == "0" ]]
}

disarm_preserved_runtime_writers_after_rollout() {
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
  RUNTIME_NEW_WRITERS_STARTED="0"
  RUNTIME_SNAPSHOT_RENAMED="0"
  RUNTIME_NEW_API_CONTAINER_IDS=()
  RUNTIME_NEW_WEB_CONTAINER_IDS=()
  RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
  RUNTIME_API_SNAPSHOT_RENAMED="0"
  RUNTIME_WEB_SNAPSHOT_RENAMED="0"
  RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0"
  RUNTIME_CONTAINER_DISCOVERY_FAILED="0"
  RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
}

drain_runtime_writers() {
  local drain_failed="0"
  local api_container_id api_image_id web_container_id web_image_id
  local dagster_container_id dagster_image_id
  if ! runtime_capture_predeploy_container_ids; then
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
  RUNTIME_API_CONTAINER_NAME=""
  RUNTIME_WEB_CONTAINER_NAME=""
  RUNTIME_DAGSTER_CONTAINER_NAME=""
  RUNTIME_API_BACKUP_NAME=""
  RUNTIME_WEB_BACKUP_NAME=""
  RUNTIME_DAGSTER_BACKUP_NAME=""
  RUNTIME_NEW_WRITERS_STARTED="0"
  RUNTIME_SNAPSHOT_RENAMED="0"
  RUNTIME_NEW_API_CONTAINER_IDS=()
  RUNTIME_NEW_WEB_CONTAINER_IDS=()
  RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
  RUNTIME_API_SNAPSHOT_RENAMED="0"
  RUNTIME_WEB_SNAPSHOT_RENAMED="0"
  RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0"
  if ! api_container_id="$(runtime_writer_container_id app-api)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    drain_failed="1"
  elif [[ -n "$api_container_id" ]]; then
    if [[ "$api_container_id" == *$'\n'* ]]; then
      drain_failed="1"
    elif ! api_image_id="$(docker container inspect --format '{{.Image}}' "$api_container_id")"; then
      drain_failed="1"
    fi
  fi
  if ! web_container_id="$(runtime_writer_container_id app-web)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    drain_failed="1"
  elif [[ -n "$web_container_id" ]]; then
    if [[ "$web_container_id" == *$'\n'* ]]; then
      drain_failed="1"
    elif ! web_image_id="$(docker container inspect --format '{{.Image}}' "$web_container_id")"; then
      drain_failed="1"
    fi
  fi
  # 이미 실행 중인 Dagster는 현재 호출의 enable flag와 무관하게 writer이므로 drain한다.
  if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
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
  if ! runtime_snapshot_preflight; then
    drain_failed="1"
  fi
  [[ "$drain_failed" == "0" ]] || return 1
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
  RUNTIME_API_CONTAINER_NAME=""
  RUNTIME_WEB_CONTAINER_NAME=""
  RUNTIME_DAGSTER_CONTAINER_NAME=""
  RUNTIME_API_BACKUP_NAME=""
  RUNTIME_WEB_BACKUP_NAME=""
  RUNTIME_DAGSTER_BACKUP_NAME=""
  RUNTIME_NEW_WRITERS_STARTED="0"
  RUNTIME_SNAPSHOT_RENAMED="0"
  RUNTIME_NEW_API_CONTAINER_IDS=()
  RUNTIME_NEW_WEB_CONTAINER_IDS=()
  RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
  RUNTIME_API_SNAPSHOT_RENAMED="0"
  RUNTIME_WEB_SNAPSHOT_RENAMED="0"
  RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0"
  RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
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
  elif [[ "$RUNTIME_NEW_WRITERS_STARTED" == "1" ]]; then
    if ! remove_new_runtime_writers; then
      cleanup_failed="1"
      log "new runtime writer cleanup failed during process exit"
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
    local legacy_database_url
    legacy_database_url="$(compose_env_value PINVI_LEGACY_REBASELINE_DATABASE_URL "")"
    [[ -n "$legacy_database_url" ]] || {
      echo "PINVI_LEGACY_REBASELINE_DATABASE_URL is required for the legacy wrapper" >&2
      return 2
    }
    legacy_args+=( -e "PINVI_DATABASE_URL=$legacy_database_url" )
  fi
  if [[ "$legacy_rebaseline" == "1" ]]; then
    compose "${profile_args[@]}" run --rm --no-deps \
      --user "$runner_user" \
      -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE="$credential_file" \
      -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_SHA256="$BOOTSTRAP_ADMIN_CREDENTIAL_SHA256" \
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
    -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_SHA256="$BOOTSTRAP_ADMIN_CREDENTIAL_SHA256" \
    -v "$credential_file:$credential_file:ro" \
    "${legacy_args[@]}" \
    "$service" pinvi-admin-bootstrap
}

validate_bootstrap_admin_credential_file() {
  local credential_file="$1"
  local legacy_rebaseline="$2"
  local service="app-migrator"
  local runner_user="$(id -u):$(id -g)"
  local profile_args=()
  local legacy_args=()
  if [[ "$legacy_rebaseline" == "1" ]]; then
    service="app-legacy-rebaseline-migrator"
    runner_user="0:0"
    profile_args=(--profile legacy-rebaseline)
    local legacy_database_url
    legacy_database_url="$(compose_env_value PINVI_LEGACY_REBASELINE_DATABASE_URL "")"
    [[ -n "$legacy_database_url" ]] || {
      echo "PINVI_LEGACY_REBASELINE_DATABASE_URL is required for the legacy wrapper" >&2
      return 2
    }
    legacy_args=( -e "PINVI_DATABASE_URL=$legacy_database_url" )
  fi
  local validation_output
  local validation_sha
  if ! validation_output="$(compose "${profile_args[@]}" run --rm --no-deps \
    --user "$runner_user" \
    -e PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE="$credential_file" \
    -v "$credential_file:$credential_file:ro" \
    "${legacy_args[@]}" \
    "$service" pinvi-admin-bootstrap validate-credential 2>&1)"; then
    return 1
  fi
  if ! validation_sha="$(printf '%s\n' "$validation_output" | bootstrap_credential_binding_from_validation_output)"; then
    return 1
  fi
  if [[ ! "$validation_sha" =~ ^[0-9a-f]{64}$ ]]; then
    return 1
  fi
  BOOTSTRAP_ADMIN_CREDENTIAL_SHA256="$validation_sha"
}

bootstrap_credential_binding_from_validation_output() {
  python3 -c '
import json
import sys

for line in reversed(sys.stdin.read().splitlines()):
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        continue
    value = payload.get("credential_binding_sha256") if isinstance(payload, dict) else None
    if isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value):
        print(value)
        raise SystemExit(0)
raise SystemExit(1)
'
}

reject_explicit_migrator_database_url() {
  if [[ -n "${PINVI_MIGRATOR_DATABASE_URL:-}" ]]; then
    echo "PINVI_MIGRATOR_DATABASE_URL is unsupported; use PINVI_MIGRATOR_DB_USER and PINVI_MIGRATOR_DB_PASSWORD" >&2
    exit 2
  fi
}

migrate_under_lifecycle_lock() {
  if ! assert_host_ports_available_before_migration; then
    log "host-port preflight failed before migration"
    return 1
  fi
  pinvi_verify_runtime_image_provenance app-api
  if [[ "$RUNTIME_WRITERS_DRAINED" != "1" ]] && ! runtime_snapshot_preflight; then
    log "stale pre-deploy snapshot preflight failed before migration"
    return 1
  fi
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
  if ! validate_bootstrap_admin_credential_file "$credential_file" "$legacy_rebaseline"; then
    log "bootstrap admin credential validation failed before any migration"
    return 1
  fi
  if [[ "$RUNTIME_WRITERS_DRAINED" != "1" ]] && ! drain_runtime_writers; then
    log "runtime writer drain failed"
    restore_runtime_writers || log "runtime writer restoration failed"
    return 1
  fi
  log "starting database dependencies and runtime DB role"
  if ! compose up -d app-postgres app-rustfs app-rustfs-init; then
    log "database dependency startup failed"
    restore_runtime_writers || log "runtime writer restoration failed"
    return 1
  fi
  if ! assert_host_ports_available_before_migration; then
    log "host-port preflight failed at the migration boundary"
    restore_runtime_writers || log "runtime writer restoration failed"
    return 1
  fi
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
  if ! assert_host_ports_available_before_migration; then
    log "host-port preflight failed immediately before migration"
    seal_migrator_login "$legacy_rebaseline" || \
      log "pre-migration port failure could not be followed by a sealing run"
    restore_runtime_writers || log "runtime writer restoration failed"
    return 1
  fi
  log "running Pinvi admin bootstrap"
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
  restore_runtime_writers || log "runtime writer restoration failed"
  return 1
}

fresh_stack_contract_failure() {
  release_migrator_lifecycle_lock
  return 1
}

migrate() {
  reject_explicit_migrator_database_url
  pinvi_prepare_api_image_provenance require-immutable
  assert_host_ports_available_before_migration
  acquire_migrator_lifecycle_lock
  if ! require_fresh_stack_contract; then
    fresh_stack_contract_failure
  fi
  # EXIT handler가 실패 시 writer 복구와 lifecycle lock 해제를 담당한다. 조건문
  # 안에서 호출하면 Bash가 함수 내부의 errexit을 끄므로 migration 본문은 직접 호출한다.
  migrate_under_lifecycle_lock
  if ! write_fresh_stack_state; then
    echo "migration succeeded but the fresh stack continuation state could not be sealed" >&2
    release_migrator_lifecycle_lock
    return 1
  fi
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

dagster_up_under_lifecycle_lock() {
  if ! assert_host_ports_available_before_migration; then
    log "host-port preflight failed immediately before Dagster start"
    return 1
  fi
  pinvi_verify_runtime_image_provenance app-dagster
  log "starting Dagster webserver (port ${DAGSTER_PORT})"
  if ! compose --profile etl up -d app-dagster; then
    runtime_record_new_container_ids app-dagster
    return 1
  fi
  runtime_record_new_container_ids app-dagster
  pinvi_verify_running_dagster
  wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster"
  local dagster_container_id
  if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  wait_for_container_health "$dagster_container_id" "Dagster container"
}

prepare_standalone_dagster_writer() {
  local dagster_container_id dagster_image_id
  if ! runtime_capture_predeploy_container_ids; then
    return 1
  fi
  if ! runtime_snapshot_preflight; then
    return 1
  fi
  if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  [[ -n "$dagster_container_id" && "$dagster_container_id" != *$'\n'* ]] || return 0
  if ! dagster_image_id="$(docker container inspect --format '{{.Image}}' "$dagster_container_id")"; then
    return 1
  fi
  RUNTIME_DAGSTER_CONTAINER_ID="$dagster_container_id"
  RUNTIME_DAGSTER_IMAGE_ID="$dagster_image_id"
  RUNTIME_DAGSTER_WAS_RUNNING="1"
  if ! compose --profile etl stop app-dagster; then
    return 1
  fi
  preserve_runtime_writers
}

up_under_lifecycle_lock() {
  local api_container_id web_container_id
  if [[ "$ENABLE_DAGSTER" != "0" || "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    pinvi_verify_runtime_image_provenance app-api app-web app-dagster
  else
    pinvi_verify_runtime_image_provenance app-api app-web
  fi
  log "starting API + Web"
  RUNTIME_NEW_WRITERS_STARTED="1"
  if ! compose up -d app-api app-web; then
    runtime_record_new_container_ids app-api
    runtime_record_new_container_ids app-web
    return 1
  fi
  runtime_record_new_container_ids app-api
  runtime_record_new_container_ids app-web
  pinvi_verify_running_app
  if [[ "$ENABLE_DAGSTER" != "0" || "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    dagster_up_under_lifecycle_lock
  fi
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" "M05 worker"
  if ! api_container_id="$(runtime_writer_container_id app-api)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  [[ -n "$api_container_id" && "$api_container_id" != *$'\n'* ]] || {
    echo "running API container could not be identified" >&2
    return 1
  }
  wait_for_container_health "$api_container_id" "API container"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  if ! web_container_id="$(runtime_writer_container_id app-web)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  [[ -n "$web_container_id" && "$web_container_id" != *$'\n'* ]] || {
    echo "running Web container could not be identified" >&2
    return 1
  }
  wait_for_container_health "$web_container_id" "Web container"
  if [[ "$ENABLE_DAGSTER" != "0" || "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster final"
    if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
      RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
      return 1
    fi
    wait_for_container_health "$dagster_container_id" "Dagster final container"
  fi
}

up() {
  pinvi_prepare_api_image_provenance require-immutable
  assert_host_ports_available_before_migration
  acquire_migrator_lifecycle_lock
  if ! require_reusable_fresh_stack_contract; then
    fresh_stack_contract_failure
  fi
  RUNTIME_DEPLOY_PRESERVE="1"
  if ! drain_runtime_writers; then
    log "runtime writer drain failed"
    return 1
  fi
  up_under_lifecycle_lock
  finalize_preserved_runtime_writers
  release_migrator_lifecycle_lock
}

dagster_up() {
  pinvi_prepare_api_image_provenance require-immutable
  assert_host_ports_available_before_migration
  acquire_migrator_lifecycle_lock
  if ! require_reusable_fresh_stack_contract; then
    fresh_stack_contract_failure
  fi
  RUNTIME_DEPLOY_PRESERVE="1"
  prepare_standalone_dagster_writer
  RUNTIME_NEW_WRITERS_STARTED="1"
  dagster_up_under_lifecycle_lock
  finalize_preserved_runtime_writers
  release_migrator_lifecycle_lock
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

smoke() {
  local api_container_id dagster_container_id
  if dagster_rollout_enabled; then
    pinvi_verify_runtime_image_provenance app-api app-web app-dagster
  else
    pinvi_verify_runtime_image_provenance app-api app-web
  fi
  pinvi_verify_running_app
  wait_for_url "http://127.0.0.1:${RUSTFS_PORT}/health/live" "RustFS"
  wait_for_url "http://127.0.0.1:${API_PORT}/health" "API"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/feature-reference-reconciliation" "M05 worker"
  wait_for_url "http://127.0.0.1:${API_PORT}/health/db" "API DB"
  if ! api_container_id="$(runtime_writer_container_id app-api)"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  wait_for_container_health "$api_container_id" "API container"
  wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"
  if [[ "$ENABLE_DAGSTER" != "0" || "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster"
    if ! dagster_container_id="$(runtime_writer_container_id app-dagster)"; then
      RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
      return 1
    fi
    wait_for_container_health "$dagster_container_id" "Dagster container"
  fi
  log "smoke passed"
}

finalize_preserved_runtime_writers() {
  local cleanup_failed="0"
  if [[ "$RUNTIME_API_WAS_RUNNING" == "1" ]]; then
    if ! docker rm "$RUNTIME_API_CONTAINER_ID" >/dev/null; then
      log "pre-deploy API snapshot could not be removed"
      cleanup_failed="1"
    fi
  fi
  if [[ "$RUNTIME_WEB_WAS_RUNNING" == "1" ]]; then
    if ! docker rm "$RUNTIME_WEB_CONTAINER_ID" >/dev/null; then
      log "pre-deploy Web snapshot could not be removed"
      cleanup_failed="1"
    fi
  fi
  if [[ "$RUNTIME_DAGSTER_WAS_RUNNING" == "1" ]]; then
    if ! docker rm "$RUNTIME_DAGSTER_CONTAINER_ID" >/dev/null; then
      log "pre-deploy Dagster snapshot could not be removed"
      cleanup_failed="1"
    fi
  fi
  if [[ "$cleanup_failed" != "0" ]]; then
    log "pre-deploy snapshot cleanup failed; keeping healthy new writers and remaining snapshots for manual cleanup"
    disarm_preserved_runtime_writers_after_rollout
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
  RUNTIME_DEPLOY_PRESERVE="0"
  RUNTIME_API_CONTAINER_NAME=""
  RUNTIME_WEB_CONTAINER_NAME=""
  RUNTIME_DAGSTER_CONTAINER_NAME=""
  RUNTIME_API_BACKUP_NAME=""
  RUNTIME_WEB_BACKUP_NAME=""
  RUNTIME_DAGSTER_BACKUP_NAME=""
  RUNTIME_NEW_WRITERS_STARTED="0"
  RUNTIME_SNAPSHOT_RENAMED="0"
  RUNTIME_NEW_API_CONTAINER_IDS=()
  RUNTIME_NEW_WEB_CONTAINER_IDS=()
  RUNTIME_NEW_DAGSTER_CONTAINER_IDS=()
  RUNTIME_API_SNAPSHOT_RENAMED="0"
  RUNTIME_WEB_SNAPSHOT_RENAMED="0"
  RUNTIME_DAGSTER_SNAPSHOT_RENAMED="0"
  RUNTIME_PREDEPLOY_API_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_API_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_WEB_STOPPED_CONTAINER_IDS=()
  RUNTIME_PREDEPLOY_DAGSTER_STOPPED_CONTAINER_IDS=()
}

status() {
  compose ps
}

deploy() {
  acquire_migrator_lifecycle_lock
  if ! require_fresh_stack_contract; then
    fresh_stack_contract_failure
  fi
  build_images
  reject_explicit_migrator_database_url
  assert_host_ports_available_before_migration
  RUNTIME_DEPLOY_PRESERVE="1"
  if ! drain_runtime_writers; then
    log "runtime writer drain failed"
    return 1
  fi
  migrate_under_lifecycle_lock
  if ! write_fresh_stack_state; then
    echo "migration succeeded but the fresh stack continuation state could not be sealed" >&2
    return 1
  fi
  if ! require_reusable_fresh_stack_contract; then
    echo "fresh stack continuation changed between migration and runtime startup" >&2
    return 1
  fi
  up_under_lifecycle_lock
  smoke
  finalize_preserved_runtime_writers
  release_migrator_lifecycle_lock
  status
}

main() {
  cd "$ROOT_DIR"
  trap 'restore_runtime_writers_on_exit "$?"' EXIT
  case "${1:-}" in
    deploy|build|pull|migrate|up|dagster|smoke)
      require_node_mutation_environment
      require_canonical_compose_file
      ;;
  esac
  preflight
  case "${1:-}" in
    deploy|build|pull|migrate|up|dagster|smoke)
      require_n150_execution_host
      ;;
  esac
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
