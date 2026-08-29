#!/usr/bin/env bash
# shellcheck shell=bash

# 호출자가 ROOT_DIR와 compose() 함수를 정의한 뒤 source한다.

# 외부 환경이 내부 attestation 상태를 주입해 preflight를 우회하지 못하게 항상 초기화한다.
PINVI_PROVENANCE_PREPARED=0
PINVI_PROVENANCE_ENVIRONMENT=""
PINVI_PROVENANCE_ARCHIVE_ROOT=""
PINVI_PROVENANCE_ARCHIVE_COMPOSE_FILE=""
PINVI_PROVENANCE_ARCHIVE_COMPOSE_SHA256=""
PINVI_ATTESTED_API_IMAGE_ID=""
PINVI_ATTESTED_WEB_IMAGE_ID=""
PINVI_ATTESTED_DAGSTER_IMAGE_ID=""
PINVI_API_IMAGE_DIGEST=""
PINVI_WEB_IMAGE_DIGEST=""
PINVI_DAGSTER_IMAGE_DIGEST=""
PINVI_APP_BUILD_CONTEXT=""
PINVI_PROVENANCE_PY="$ROOT_DIR/scripts/api_image_provenance.py"
PINVI_ORIGINAL_COMPOSE_FILE="$COMPOSE_FILE"

pinvi_cleanup_api_build_context() {
  if [[ -n "$PINVI_PROVENANCE_ARCHIVE_ROOT" ]]; then
    chmod -R u+w -- "$PINVI_PROVENANCE_ARCHIVE_ROOT" 2>/dev/null || true
    rm -rf -- "$PINVI_PROVENANCE_ARCHIVE_ROOT"
    PINVI_PROVENANCE_ARCHIVE_ROOT=""
  fi
  PINVI_PROVENANCE_ARCHIVE_COMPOSE_FILE=""
  PINVI_PROVENANCE_ARCHIVE_COMPOSE_SHA256=""
  unset PINVI_API_BUILD_CONTEXT
  unset PINVI_APP_BUILD_CONTEXT
  unset PINVI_API_IMAGE_DIGEST
  unset PINVI_WEB_IMAGE_DIGEST
  unset PINVI_DAGSTER_IMAGE_DIGEST
  COMPOSE_FILE="$PINVI_ORIGINAL_COMPOSE_FILE"
  PINVI_PROVENANCE_PY="$ROOT_DIR/scripts/api_image_provenance.py"
}

pinvi_provenance_input_document() {
  local -a command
  command=(docker compose -f -)
  if [[ -f "$ENV_FILE" ]]; then
    command+=(--env-file "$ENV_FILE")
  fi
  command+=(config --format json)
  "${command[@]}" <<'YAML'
services:
  provenance:
    image: scratch
    environment:
      PINVI_ENVIRONMENT: ${PINVI_ENVIRONMENT:-smoke}
      PINVI_SOURCE_REVISION: ${PINVI_SOURCE_REVISION:-}
YAML
}

pinvi_read_provenance_input() {
  local name="$1"
  pinvi_provenance_input_document | \
    python3 "$PINVI_PROVENANCE_PY" compose-provenance-input --name "$name"
}

pinvi_materialize_api_build_context() {
  case "$PINVI_PROVENANCE_ENVIRONMENT" in
    isolated|staging|production) ;;
    *) return 0 ;;
  esac
  if [[ -n "$PINVI_PROVENANCE_ARCHIVE_ROOT" ]]; then
    return 0
  fi

  local command
  for command in git tar mktemp realpath; do
    if ! command -v "$command" >/dev/null 2>&1; then
      echo "api image provenance preflight failed: ${command} not found" >&2
      return 127
    fi
  done

  local archive_root context_root
  umask 077
  archive_root="$(mktemp -d "${TMPDIR:-/tmp}/pinvi-api-build.XXXXXXXX")"
  context_root="$archive_root/context"
  mkdir -m 0700 "$context_root"
  if ! git -C "$ROOT_DIR" archive --format=tar "$PINVI_SOURCE_REVISION" | \
    tar -xf - -C "$context_root"; then
    rm -rf -- "$archive_root"
    return 2
  fi
  local relative control_file
  if [[ -e "$context_root/.git" ]]; then
    rm -rf -- "$archive_root"
    echo "api image provenance preflight failed: immutable archive is incomplete" >&2
    return 2
  fi
  for relative in \
    apps/api/Dockerfile \
    apps/web/Dockerfile \
    apps/etl/Dockerfile \
    infra/docker-compose.app.yml \
    scripts/api_image_provenance.py \
    scripts/validate-image-provenance.sh; do
    control_file="$context_root/$relative"
    if [[ \
      ! -f "$control_file" || \
      -L "$control_file" || \
      "$(realpath -e -- "$control_file" 2>/dev/null || true)" != "$control_file" \
    ]]; then
      rm -rf -- "$archive_root"
      echo "api image provenance preflight failed: immutable control file is not canonical" >&2
      return 2
    fi
  done

  PINVI_PROVENANCE_ARCHIVE_ROOT="$archive_root"
  PINVI_PROVENANCE_ARCHIVE_COMPOSE_FILE="$context_root/infra/docker-compose.app.yml"
  PINVI_PROVENANCE_ARCHIVE_COMPOSE_SHA256="$(sha256sum -- "$PINVI_PROVENANCE_ARCHIVE_COMPOSE_FILE" | awk '{print $1}')"
  export PINVI_API_BUILD_CONTEXT="$context_root"
  export PINVI_APP_BUILD_CONTEXT="$context_root"
  COMPOSE_FILE="$context_root/infra/docker-compose.app.yml"
  PINVI_PROVENANCE_PY="$context_root/scripts/api_image_provenance.py"

  if ! compose config --format json | \
    python3 "$PINVI_PROVENANCE_PY" verify-compose-build \
      --context-root "$context_root" \
      --expected-environment "$PINVI_PROVENANCE_ENVIRONMENT" \
      --expected-revision "$PINVI_SOURCE_REVISION"; then
    pinvi_cleanup_api_build_context
    return 2
  fi
  chmod -R a-w -- "$archive_root"
}

pinvi_prepare_api_image_provenance() {
  local requirement="${1:-}"
  if [[ -n "$requirement" && "$requirement" != "require-immutable" ]]; then
    echo "api image provenance preflight failed: unknown provenance requirement" >&2
    return 2
  fi
  if [[ "$PINVI_PROVENANCE_PREPARED" == "1" ]]; then
    if [[ "$requirement" == "require-immutable" ]]; then
      case "$PINVI_PROVENANCE_ENVIRONMENT" in
        staging|production) ;;
        *)
          echo "api image provenance preflight failed: deploy entry requires staging or production" >&2
          return 2
          ;;
      esac
    fi
    return 0
  fi

  local provenance_document compose_environment requested revision
  local -a resolve_args
  provenance_document="$(pinvi_provenance_input_document)"
  compose_environment="$(
    printf '%s\n' "$provenance_document" | \
      python3 "$PINVI_PROVENANCE_PY" compose-provenance-input --name PINVI_ENVIRONMENT
  )"
  requested="$(
    printf '%s\n' "$provenance_document" | \
      python3 "$PINVI_PROVENANCE_PY" compose-provenance-input --name PINVI_SOURCE_REVISION
  )"
  if [[ "$requirement" == "require-immutable" ]]; then
    case "$compose_environment" in
      staging|production) ;;
      *)
        echo "api image provenance preflight failed: deploy entry requires staging or production" >&2
        return 2
        ;;
    esac
  fi
  resolve_args=(
    resolve
    --environment "$compose_environment"
    --repo-root "$ROOT_DIR"
  )
  if [[ -n "$requested" ]]; then
    resolve_args+=(--requested "$requested")
  fi
  revision="$(python3 "$PINVI_PROVENANCE_PY" "${resolve_args[@]}")"

  export PINVI_SOURCE_REVISION="$revision"
  PINVI_PROVENANCE_ENVIRONMENT="$compose_environment"
  export PINVI_ENVIRONMENT="$PINVI_PROVENANCE_ENVIRONMENT"
  pinvi_materialize_api_build_context
  local resolved_environment resolved_revision
  resolved_environment="$({ compose config --format json; } | \
    python3 "$PINVI_PROVENANCE_PY" compose-environment)"
  resolved_revision="$({ compose config --format json; } | \
    python3 "$PINVI_PROVENANCE_PY" compose-requested-revision)"
  if [[ \
    "$resolved_environment" != "$PINVI_PROVENANCE_ENVIRONMENT" || \
    "$resolved_revision" != "$PINVI_SOURCE_REVISION" \
  ]]; then
    echo "api image provenance preflight failed: resolved Compose provenance drifted" >&2
    pinvi_cleanup_api_build_context
    return 2
  fi
  PINVI_PROVENANCE_PREPARED=1
}

pinvi_verify_api_image_provenance() {
  pinvi_verify_runtime_image_provenance app-api
}

pinvi_attested_runtime_image_id() {
  case "$1" in
    app-api) printf '%s\n' "$PINVI_ATTESTED_API_IMAGE_ID" ;;
    app-web) printf '%s\n' "$PINVI_ATTESTED_WEB_IMAGE_ID" ;;
    app-dagster) printf '%s\n' "$PINVI_ATTESTED_DAGSTER_IMAGE_ID" ;;
    *) return 2 ;;
  esac
}

pinvi_bind_attested_runtime_image_id() {
  local service="$1"
  local image_id="$2"
  case "$service" in
    app-api)
      PINVI_ATTESTED_API_IMAGE_ID="$image_id"
      PINVI_API_IMAGE_DIGEST="$image_id"
      export PINVI_API_IMAGE_DIGEST
      export PINVI_API_IMAGE="$image_id"
      ;;
    app-web)
      PINVI_ATTESTED_WEB_IMAGE_ID="$image_id"
      PINVI_WEB_IMAGE_DIGEST="$image_id"
      export PINVI_WEB_IMAGE_DIGEST
      export PINVI_WEB_IMAGE="$image_id"
      ;;
    app-dagster)
      PINVI_ATTESTED_DAGSTER_IMAGE_ID="$image_id"
      PINVI_DAGSTER_IMAGE_DIGEST="$image_id"
      export PINVI_DAGSTER_IMAGE_DIGEST
      export PINVI_DAGSTER_IMAGE="$image_id"
      ;;
    *) return 2 ;;
  esac
}

pinvi_verify_runtime_image_provenance() {
  pinvi_prepare_api_image_provenance

  if (( $# == 0 )); then
    echo "api image provenance preflight failed: runtime service를 지정해야 합니다" >&2
    return 2
  fi

  local service image_reference image_id actual_revision actual_environment
  local -a config_profile_args=()
  for service in "$@"; do
    case "$service" in
      app-api|app-web|app-dagster) ;;
      *)
        echo "api image provenance preflight failed: attestation 대상 runtime service가 아닙니다" >&2
        return 2
        ;;
    esac
    if [[ "$service" == "app-dagster" ]]; then
      config_profile_args=(--profile etl)
    else
      config_profile_args=()
    fi
    image_id="$(pinvi_attested_runtime_image_id "$service")"
    if [[ -n "$image_id" ]]; then
      :
    else
      image_reference="$({ compose "${config_profile_args[@]}" config --format json; } | \
        python3 "$PINVI_PROVENANCE_PY" compose-image-reference --service "$service")"
      image_id="$(docker image inspect --format '{{.Id}}' "$image_reference")"
      if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
        echo "api image provenance preflight failed: ${service} image ID가 canonical 값이 아닙니다" >&2
        return 2
      fi
    fi
    actual_revision="$(
      docker image inspect \
        --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
        "$image_id"
    )"
    actual_environment="$(
      docker image inspect \
        --format '{{ index .Config.Labels "io.pinvi.build.environment" }}' \
        "$image_id"
    )"
    python3 "$PINVI_PROVENANCE_PY" verify-label \
      --expected-revision "$PINVI_SOURCE_REVISION" \
      --actual-revision "$actual_revision" \
      --expected-environment "$PINVI_PROVENANCE_ENVIRONMENT" \
      --actual-environment "$actual_environment"
    pinvi_bind_attested_runtime_image_id "$service" "$image_id"
  done
}

# A stopped pre-deploy container keeps Compose's project/service labels so that
# it can be restored with its original image. It is excluded from active-runtime
# IDs and cleanup; the explicit preflight helper below still discovers stale
# snapshots so a failed rollout cannot silently reconcile or delete the rollback
# artifact together with the newly created container.
pinvi_runtime_container_ids() {
  local service="$1"
  local project="${PROJECT:-pinvi-app}"
  local -a list_args=()
  local raw_containers
  if [[ "${2:-all}" == "all" ]]; then
    list_args=(--all)
  fi
  if ! raw_containers="$(docker container ls --no-trunc "${list_args[@]}" \
    --filter "label=com.docker.compose.project=${project}" \
    --filter "label=com.docker.compose.service=${service}" \
    --format '{{.ID}} {{.Names}}')"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  awk '$2 !~ /\.pinvi-predeploy$/ {print $1}' <<< "$raw_containers"
}

pinvi_runtime_predeploy_snapshot_ids() {
  local service="$1"
  local project="${PROJECT:-pinvi-app}"
  local raw_containers
  if ! raw_containers="$(docker container ls --no-trunc --all \
    --filter "label=com.docker.compose.project=${project}" \
    --filter "label=com.docker.compose.service=${service}" \
    --format '{{.ID}} {{.Names}}')"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  awk '$2 ~ /\.pinvi-predeploy$/ {print $1}' <<< "$raw_containers"
}

pinvi_runtime_container_ids_into_array() {
  local array_name="$1"
  shift
  local ids=""
  local -n output_array="$array_name"
  if ! ids="$(pinvi_runtime_container_ids "$@")"; then
    RUNTIME_CONTAINER_DISCOVERY_FAILED="1"
    return 1
  fi
  output_array=()
  if [[ -n "$ids" ]]; then
    mapfile -t output_array <<< "$ids"
  fi
}

pinvi_verify_running_runtime_image_id() {
  local service="$1"
  local image_id container_id running_image_id
  local -a container_ids
  image_id="$(pinvi_attested_runtime_image_id "$service")"
  if [[ -z "$image_id" ]]; then
    echo "api image provenance preflight failed: ${service} image is not attested" >&2
    return 2
  fi

  if ! pinvi_runtime_container_ids_into_array container_ids "$service" running; then
    echo "api image provenance preflight failed: ${service} container discovery failed" >&2
    return 2
  fi
  if (( ${#container_ids[@]} != 1 )); then
    echo "api image provenance preflight failed: ${service} container must resolve exactly once" >&2
    return 2
  fi
  container_id="${container_ids[0]}"
  running_image_id="$(docker container inspect --format '{{.Image}}' "$container_id")"
  if [[ "$running_image_id" != "$image_id" ]]; then
    echo "api image provenance preflight failed: running ${service} image ID drifted" >&2
    return 2
  fi
}

pinvi_verify_running_api_image_id() {
  pinvi_verify_running_runtime_image_id app-api
}

pinvi_verify_running_app() {
  local verification_status
  if pinvi_verify_running_runtime_image_id app-api && \
    pinvi_verify_running_runtime_image_id app-web; then
    return 0
  else
    verification_status="$?"
  fi

  # Container removal belongs to the caller's invocation-scoped rollback. Do
  # not delete every stopped container sharing the Compose service label here.
  echo "api image provenance preflight failed: running app image is not attested" >&2
  return "$verification_status"
}

pinvi_verify_running_dagster() {
  local verification_status
  if pinvi_verify_running_runtime_image_id app-dagster; then
    return 0
  else
    verification_status="$?"
  fi

  # See pinvi_verify_running_app: rollback must be limited to this invocation.
  echo "api image provenance preflight failed: running Dagster image is not attested" >&2
  return "$verification_status"
}
