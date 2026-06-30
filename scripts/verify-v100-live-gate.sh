#!/usr/bin/env bash
# v1.0.0 E2E / live gate orchestrator (T-273).
#
# This script does not hide mutating guards. Each underlying suite still
# requires its own explicit opt-in env, and this wrapper requires
# PINVI_V100_LIVE_GATE=1 for any run action.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_PHASES="admin-live-list live-mutating-list"

usage() {
  cat <<'USAGE'
Usage:
  scripts/verify-v100-live-gate.sh plan [phase...]
  PINVI_V100_LIVE_GATE=1 scripts/verify-v100-live-gate.sh run [phase...]

Default phases:
  admin-live-list live-mutating-list

Phases:
  mock-e2e                 Run the mock Playwright E2E suite.
  admin-live-list          List Admin read-only live catalog.
  admin-live-smoke         Run Admin read-only live catalog with PINVI_ADMIN_LIVE_CASE_LIMIT.
  admin-live-full          Run full Admin read-only live catalog.
  live-mutating-list       List live mutating suite.
  trip-realtime-mutating   Run trip realtime mutating suite.
  backup-mutating          Run backup staging mutating suite.
  geofence                 Run scripts/verify-geofence.sh.
  mcp                      Run scripts/verify-mcp.sh.
  restore-staging          Run scripts/restore-staging-drill.sh with PINVI_V100_RESTORE_SNAPSHOT.
  perf                     Run tests/load/api_p95_latency.py.
  security                 Run tests/security/csp_cors_rate_limit.py.

Environment:
  PINVI_V100_LIVE_GATE=1              Required for run.
  PINVI_V100_GATE_PHASES              Space or comma separated phase list.
  PINVI_V100_GATE_N150_RUNNER=1       Wrap Playwright phases with scripts/n150-playwright-runner.sh.
  PINVI_V100_ADMIN_LIVE_CASE_LIMIT    Default 200 for admin-live-smoke.
  PINVI_ADMIN_LIVE_CASE_START         Optional 1-based Admin matrix start for resumed full catalog.
  PINVI_ADMIN_LIVE_CASE_END           Optional 1-based Admin matrix end for resumed full catalog.
  PINVI_V100_RESTORE_SNAPSHOT         Snapshot path for restore-staging.
  PINVI_V100_RESTORE_DOCKER_RUNNER=1  Run restore-staging inside a PostgreSQL Docker image.
  PINVI_V100_RESTORE_DOCKER_IMAGE     Default postgres:16-alpine.
  PINVI_V100_RESTORE_DOCKER_NETWORK   Optional docker --network value, e.g. container:<postgres>.
  PINVI_V100_PERF_PATHS               Default /health,/health/db.
  PINVI_V100_PERF_REQUESTS            Default 100.
  PINVI_V100_PERF_CONCURRENCY         Default 10.
  PINVI_V100_PERF_P95_MS              Default 500.
  PINVI_V100_PERF_MAX_ERROR_RATE      Default 0.01.
  PINVI_V100_REQUIRE_HSTS=1           Add --require-hsts to security phase.

Notes:
  - Run from Linux/N150 first. Use Windows only when the N150 Docker runner and
    host browser are both unavailable, and record the fallback reason.
  - Actual domains, credentials, tokens, and DB URLs must remain in local env files.
USAGE
}

split_phases() {
  local raw="$*"
  raw="${raw//,/ }"
  # shellcheck disable=SC2086
  printf '%s\n' $raw
}

phase_list() {
  if [[ "$#" -gt 0 ]]; then
    split_phases "$*"
  elif [[ -n "${PINVI_V100_GATE_PHASES:-}" ]]; then
    split_phases "${PINVI_V100_GATE_PHASES}"
  else
    split_phases "${DEFAULT_PHASES}"
  fi
}

run_cmd() {
  local label="$1"
  shift
  printf '\n[v100-live-gate] phase=%s\n' "${label}"
  "$@"
}

run_playwright() {
  local label="$1"
  shift
  if [[ "${PINVI_V100_GATE_N150_RUNNER:-0}" == "1" ]]; then
    run_cmd "${label}" "${ROOT_DIR}/scripts/n150-playwright-runner.sh" -- "$@"
  else
    run_cmd "${label}" "$@"
  fi
}

run_restore_staging() {
  local snapshot="$1"
  if [[ "${PINVI_V100_RESTORE_DOCKER_RUNNER:-0}" != "1" ]]; then
    run_cmd "restore-staging" "${ROOT_DIR}/scripts/restore-staging-drill.sh" run "${snapshot}"
    return
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is required when PINVI_V100_RESTORE_DOCKER_RUNNER=1" >&2
    exit 127
  fi
  if [[ ! -f "${snapshot}" ]]; then
    echo "error: restore snapshot not found: ${snapshot}" >&2
    exit 2
  fi

  local snapshot_dir
  local snapshot_file
  snapshot_dir="$(cd "$(dirname "${snapshot}")" && pwd)"
  snapshot_file="$(basename "${snapshot}")"

  local -a docker_args=(
    run
    --rm
    -v "${ROOT_DIR}:/workspace:ro"
    -v "${snapshot_dir}:/snapshot:ro"
    -w /workspace
  )
  if [[ -n "${PINVI_V100_RESTORE_DOCKER_NETWORK:-}" ]]; then
    docker_args+=(--network "${PINVI_V100_RESTORE_DOCKER_NETWORK}")
  fi

  local -a passthrough_env=(
    PINVI_RESTORE_STAGING_DATABASE_URL
    PINVI_RESTORE_DRILL_SCHEMA
    PINVI_BACKUP_SCHEMA
    PINVI_RESTORE_DRILL_JOBS
    PINVI_RESTORE_JOBS
    PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL
    PINVI_RESTORE_DRILL_ALLOW_NON_STAGING
  )
  local name
  for name in "${passthrough_env[@]}"; do
    if [[ -n "${!name:-}" ]]; then
      docker_args+=(-e "${name}")
    fi
  done

  run_cmd "restore-staging" docker "${docker_args[@]}" \
    "${PINVI_V100_RESTORE_DOCKER_IMAGE:-postgres:16-alpine}" \
    bash scripts/restore-staging-drill.sh run "/snapshot/${snapshot_file}"
}

require_run_guard() {
  if [[ "${PINVI_V100_LIVE_GATE:-0}" != "1" ]]; then
    echo "error: PINVI_V100_LIVE_GATE=1 is required for run" >&2
    exit 2
  fi
}

run_phase() {
  local phase="$1"
  case "${phase}" in
    mock-e2e)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e
      ;;
    admin-live-list)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e:admin-live:list
      ;;
    admin-live-smoke)
      run_playwright "${phase}" env \
        PINVI_ADMIN_LIVE_CASE_LIMIT="${PINVI_V100_ADMIN_LIVE_CASE_LIMIT:-200}" \
        npm -w @pinvi/web run test:e2e:admin-live
      ;;
    admin-live-full)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e:admin-live
      ;;
    live-mutating-list)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e:live-mutating:list
      ;;
    trip-realtime-mutating)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e:live-mutating -- \
        trip-realtime-live-mutating.live.ts --workers=1
      ;;
    backup-mutating)
      run_playwright "${phase}" npm -w @pinvi/web run test:e2e:live-mutating -- \
        admin-backup-live-mutating.live.ts --workers=1
      ;;
    geofence)
      run_cmd "${phase}" "${ROOT_DIR}/scripts/verify-geofence.sh"
      ;;
    mcp)
      run_cmd "${phase}" "${ROOT_DIR}/scripts/verify-mcp.sh"
      ;;
    restore-staging)
      : "${PINVI_V100_RESTORE_SNAPSHOT:?PINVI_V100_RESTORE_SNAPSHOT is required}"
      run_restore_staging "${PINVI_V100_RESTORE_SNAPSHOT}"
      ;;
    perf)
      run_cmd "${phase}" "${PYTHON_BIN}" "${ROOT_DIR}/tests/load/api_p95_latency.py" \
        --paths "${PINVI_V100_PERF_PATHS:-/health,/health/db}" \
        --requests "${PINVI_V100_PERF_REQUESTS:-100}" \
        --concurrency "${PINVI_V100_PERF_CONCURRENCY:-10}" \
        --p95-ms-threshold "${PINVI_V100_PERF_P95_MS:-500}" \
        --max-error-rate "${PINVI_V100_PERF_MAX_ERROR_RATE:-0.01}"
      ;;
    security)
      local -a security_args=()
      if [[ "${PINVI_V100_REQUIRE_HSTS:-0}" == "1" ]]; then
        security_args+=(--require-hsts)
      fi
      run_cmd "${phase}" "${PYTHON_BIN}" "${ROOT_DIR}/tests/security/csp_cors_rate_limit.py" \
        "${security_args[@]}"
      ;;
    *)
      echo "error: unknown phase '${phase}'" >&2
      usage >&2
      exit 2
      ;;
  esac
}

action="${1:-plan}"
if [[ "$#" -gt 0 ]]; then
  shift
fi

case "${action}" in
  -h | --help | help)
    usage
    ;;
  plan)
    echo "[v100-live-gate] phases:"
    phase_list "$@" | sed 's/^/  - /'
    ;;
  run)
    require_run_guard
    cd "${ROOT_DIR}"
    while IFS= read -r phase; do
      [[ -z "${phase}" ]] && continue
      run_phase "${phase}"
    done < <(phase_list "$@")
    ;;
  *)
    echo "error: unknown action '${action}'" >&2
    usage >&2
    exit 2
    ;;
esac
