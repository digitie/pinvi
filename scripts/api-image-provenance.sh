#!/usr/bin/env bash
# shellcheck shell=bash

# 호출자가 ROOT_DIR와 compose() 함수를 정의한 뒤 source한다.

# 외부 환경이 내부 attestation 상태를 주입해 preflight를 우회하지 못하게 항상 초기화한다.
PINVI_PROVENANCE_PREPARED=0
PINVI_PROVENANCE_ENVIRONMENT=""
PINVI_PROVENANCE_ARCHIVE_ROOT=""
PINVI_ATTESTED_API_IMAGE_ID=""
PINVI_PROVENANCE_PY="$ROOT_DIR/scripts/api_image_provenance.py"
PINVI_ORIGINAL_COMPOSE_FILE="$COMPOSE_FILE"

pinvi_cleanup_api_build_context() {
  if [[ -n "$PINVI_PROVENANCE_ARCHIVE_ROOT" ]]; then
    chmod -R u+w -- "$PINVI_PROVENANCE_ARCHIVE_ROOT" 2>/dev/null || true
    rm -rf -- "$PINVI_PROVENANCE_ARCHIVE_ROOT"
    PINVI_PROVENANCE_ARCHIVE_ROOT=""
  fi
  unset PINVI_API_BUILD_CONTEXT
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
    staging|production) ;;
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
    infra/docker-compose.app.yml \
    scripts/api_image_provenance.py; do
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
  export PINVI_API_BUILD_CONTEXT="$context_root"
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
  pinvi_prepare_api_image_provenance

  local image_reference image_id actual_revision actual_environment
  if [[ -n "$PINVI_ATTESTED_API_IMAGE_ID" ]]; then
    image_id="$PINVI_ATTESTED_API_IMAGE_ID"
  else
    image_reference="$({ compose config --format json; } | \
      python3 "$PINVI_PROVENANCE_PY" compose-image-reference)"
    image_id="$(docker image inspect --format '{{.Id}}' "$image_reference")"
    if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "api image provenance preflight failed: app-api image ID is not canonical" >&2
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
  PINVI_ATTESTED_API_IMAGE_ID="$image_id"
  export PINVI_API_IMAGE="$image_id"
}

pinvi_verify_running_api_image_id() {
  if [[ -z "$PINVI_ATTESTED_API_IMAGE_ID" ]]; then
    echo "api image provenance preflight failed: API image is not attested" >&2
    return 2
  fi

  local container_id running_image_id
  local -a container_ids
  mapfile -t container_ids < <(compose ps -q app-api | sed '/^[[:space:]]*$/d')
  if (( ${#container_ids[@]} != 1 )); then
    echo "api image provenance preflight failed: app-api container must resolve exactly once" >&2
    return 2
  fi
  container_id="${container_ids[0]}"
  running_image_id="$(docker container inspect --format '{{.Image}}' "$container_id")"
  if [[ "$running_image_id" != "$PINVI_ATTESTED_API_IMAGE_ID" ]]; then
    echo "api image provenance preflight failed: running API image ID drifted" >&2
    return 2
  fi
}

pinvi_verify_or_remove_running_app() {
  local verification_status
  local -a container_ids remaining_ids
  mapfile -t container_ids < <(
    compose ps -aq app-api app-web | sed '/^[[:space:]]*$/d' | sort -u
  )
  if pinvi_verify_running_api_image_id; then
    return 0
  else
    verification_status="$?"
  fi

  # 검증되지 않은 API를 Web이 계속 노출하지 않도록 이 project의 app pair를 모두 제거한다.
  compose stop app-web app-api >/dev/null 2>&1 || true
  if (( ${#container_ids[@]} > 0 )); then
    docker container rm -f "${container_ids[@]}" >/dev/null 2>&1 || true
  fi
  mapfile -t remaining_ids < <(
    compose ps -aq app-api app-web | sed '/^[[:space:]]*$/d' | sort -u
  )
  if (( ${#remaining_ids[@]} > 0 )); then
    echo "api image provenance preflight failed: unverified app container remains" >&2
    return 2
  fi
  return "$verification_status"
}
