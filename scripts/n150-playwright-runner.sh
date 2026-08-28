#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/n150-playwright-runner.sh -- <command> [args...]

Runs a Playwright command in the official Playwright Docker image. The default
network is host so N150 tests can reach http://127.0.0.1:12805 from inside the
container.

Examples:
  PINVI_ADMIN_LIVE_E2E=1 \
  PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 \
  scripts/n150-playwright-runner.sh -- \
    npm -w @pinvi/web run test:e2e:admin-live -- --grep "UI login rejects malformed email" --workers=1

  PINVI_ADMIN_LIVE_E2E=1 PINVI_ADMIN_LIVE_CASE_LIMIT=200 \
  scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live

Environment:
  PINVI_PLAYWRIGHT_RUNNER_IMAGE        Override Docker image.
  PINVI_PLAYWRIGHT_RUNNER_NETWORK      Docker network, default: host.
  PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT    Repository root, default: script parent.
  PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI  Set to 1 to reuse the node_modules volume.
  PINVI_PLAYWRIGHT_RUNNER_VOLUME_PREFIX Named volume prefix, default: pinvi-playwright.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--" ]]; then
  shift
fi

if [[ "$#" -eq 0 ]]; then
  usage >&2
  exit 2
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "error: this runner must be launched from Linux/N150" >&2
  exit 1
fi

actual_arch="$(uname -m)"
actual_hostname="$(hostname -s 2>/dev/null || hostname)"
actual_os_version="$(sed -n 's/^VERSION_ID=//p' /etc/os-release 2>/dev/null | tr -d '"')"
if [[ "$actual_arch" != "x86_64" ]] \
  || [[ "$actual_hostname" != "n150" && "$actual_hostname" != "digitie-at-n150" ]] \
  || [[ "$actual_os_version" != "26.04" ]]; then
  echo "error: this runner must be launched on the N150 x86_64 host" >&2
  exit 1
fi

docker_bin="/usr/bin/docker"
if [[ ! -x "${docker_bin}" ]]; then
  echo "error: pinned /usr/bin/docker is required" >&2
  exit 1
fi

repo_root="${PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT:-}"
if [[ -z "$repo_root" ]]; then
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
repo_root="$(cd "$repo_root" && pwd)"
cd "$repo_root"

assert_exact_live_checkout() {
  local expected_revision="${PINVI_LIVE_EXPECTED_REVISION:-}"
  local actual_revision
  if [[ -z "$expected_revision" || ! "$expected_revision" =~ ^[0-9a-f]{40}$ ]]; then
    echo "error: live UI requires PINVI_LIVE_EXPECTED_REVISION as a full lowercase commit" >&2
    exit 1
  fi
  actual_revision="$(git rev-parse --verify HEAD^{commit})"
  if [[ "$actual_revision" != "$expected_revision" ]]; then
    echo "error: live UI checkout ${actual_revision} does not match expected ${expected_revision}" >&2
    exit 1
  fi
  if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
    echo "error: live UI checkout must be clean" >&2
    exit 1
  fi
}

is_digest_pinned_playwright_image() {
  [[ "$1" =~ ^mcr\.microsoft\.com/playwright(:[^@[:space:]]+)?@sha256:[0-9a-f]{64}$ ]]
}

live_ui_requested="0"
if [[ "${PINVI_ADMIN_LIVE_E2E:-0}" == "1" \
  || "${PINVI_LIVE_UI_E2E:-0}" == "1" \
  || "${PINVI_M04_LIVE_E2E:-0}" == "1" \
  || -n "${PINVI_M04_UI_VERIFICATION_ID:-}" \
  || -n "${PINVI_M05_UI_VERIFICATION_ID:-}" \
  || "${PINVI_M05_LIVE_E2E:-0}" == "1" \
  || "${PINVI_LIVE_MUTATING_E2E:-0}" == "1" \
  || "${PINVI_BACKUP_LIVE_MUTATING_E2E:-0}" == "1" \
  || "${PINVI_LIVE_FEATURE_RESOLUTION_E2E:-0}" == "1" \
  || "${PINVI_LIVE_ATTACHMENT_E2E:-0}" == "1" ]]; then
  live_ui_requested="1"
  assert_exact_live_checkout
fi

if ! command -v node >/dev/null 2>&1; then
  echo "error: node is required to resolve package-lock Playwright version" >&2
  exit 1
fi

playwright_version="${PINVI_PLAYWRIGHT_VERSION:-}"
if [[ -z "$playwright_version" ]]; then
  playwright_version="$(
    node -e "const p=require('./package-lock.json'); const pkg=p.packages && p.packages['node_modules/@playwright/test']; if (!pkg) process.exit(1); console.log(pkg.version)"
  )"
fi

image="${PINVI_PLAYWRIGHT_RUNNER_IMAGE:-mcr.microsoft.com/playwright:v${playwright_version}-noble}"
network="${PINVI_PLAYWRIGHT_RUNNER_NETWORK:-host}"
skip_npm_ci="${PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI:-0}"
volume_prefix="${PINVI_PLAYWRIGHT_RUNNER_VOLUME_PREFIX:-pinvi-playwright}"
evidence_owner="$(id -u):$(id -g)"
generic_live_requested="0"
if [[ "${PINVI_LIVE_MUTATING_E2E:-0}" == "1" \
  || "${PINVI_BACKUP_LIVE_MUTATING_E2E:-0}" == "1" \
  || "${PINVI_LIVE_FEATURE_RESOLUTION_E2E:-0}" == "1" \
  || "${PINVI_LIVE_ATTACHMENT_E2E:-0}" == "1" ]]; then
  generic_live_requested="1"
fi
if [[ "$live_ui_requested" == "1" || "$generic_live_requested" == "1" ]]; then
  if ! is_digest_pinned_playwright_image "$image"; then
    echo "error: every live UI phase requires an official digest-pinned Playwright image" >&2
    exit 1
  fi
  if [[ "$network" != "host" || "$skip_npm_ci" != "0" ]]; then
    echo "error: every live UI phase requires host networking and a fresh npm ci" >&2
    exit 1
  fi
fi
if [[ "$generic_live_requested" == "1" ]]; then
  if [[ "${PINVI_LIVE_MUTATING_E2E:-0}" == "1" \
    || "${PINVI_LIVE_FEATURE_RESOLUTION_E2E:-0}" == "1" \
    || "${PINVI_LIVE_ATTACHMENT_E2E:-0}" == "1" ]]; then
    if [[ -z "${PINVI_LIVE_WEB_URL:-}" || -z "${PINVI_LIVE_API_URL:-}" \
      || -z "${PINVI_LIVE_EMAIL:-}" || -z "${PINVI_LIVE_PASSWORD:-}" ]]; then
      echo "error: generic live UI requires PINVI_LIVE_WEB_URL, PINVI_LIVE_API_URL, PINVI_LIVE_EMAIL, and PINVI_LIVE_PASSWORD" >&2
      exit 1
    fi
  fi
  if [[ "${PINVI_BACKUP_LIVE_MUTATING_E2E:-0}" == "1" ]]; then
    if [[ "${PINVI_BACKUP_LIVE_STAGING:-0}" != "1" ]]; then
      echo "error: backup live mutation requires PINVI_BACKUP_LIVE_STAGING=1" >&2
      exit 1
    fi
    if [[ -z "${PINVI_LIVE_WEB_URL:-${PINVI_ADMIN_LIVE_WEB_URL:-}}" \
      || ( -z "${PINVI_BACKUP_LIVE_EMAIL:-${PINVI_ADMIN_LIVE_EMAIL:-}}" \
        && -z "${PINVI_BACKUP_LIVE_STORAGE_STATE:-${PINVI_ADMIN_LIVE_STORAGE_STATE:-}}" ) \
      || ( -z "${PINVI_BACKUP_LIVE_PASSWORD:-${PINVI_ADMIN_LIVE_PASSWORD:-}}" \
        && -z "${PINVI_BACKUP_LIVE_STORAGE_STATE:-${PINVI_ADMIN_LIVE_STORAGE_STATE:-}}" ) ]]; then
      echo "error: backup live mutation requires an explicit web URL and admin credential or storage state" >&2
      exit 1
    fi
  fi
fi
evidence_dir="${PINVI_M05_UI_EVIDENCE_DIR:-${PINVI_M04_UI_EVIDENCE_DIR:-}}"
if [[ -n "${PINVI_M04_UI_EVIDENCE_DIR:-}" && -n "${PINVI_M05_UI_EVIDENCE_DIR:-}" ]]; then
  echo "error: only one M04/M05 UI evidence directory may be mounted per runner invocation" >&2
  exit 1
fi
if [[ -n "${PINVI_M04_UI_VERIFICATION_ID:-}" && -n "${PINVI_M05_UI_VERIFICATION_ID:-}" ]]; then
  echo "error: M04 and M05 attested UI runs cannot share one runner invocation" >&2
  exit 1
fi
if [[ -n "$evidence_dir" ]]; then
  if [[ "$evidence_dir" != /* || ! -d "$evidence_dir" ]]; then
    echo "error: M04/M05 UI evidence directory must be an existing absolute directory" >&2
    exit 1
  fi
fi

if [[ "${PINVI_M04_LIVE_E2E:-}" == "1" || -n "${PINVI_M04_UI_VERIFICATION_ID:-}" ]]; then
  expected_m04_image="${PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_REF:-}"
  if [[ "$image" != "$expected_m04_image" ]] || ! is_digest_pinned_playwright_image "$image"; then
    echo "error: M04 live UI requires the attested immutable Playwright image" >&2
    exit 1
  fi
  if [[ "$network" != "host" || "$skip_npm_ci" != "0" ]]; then
    echo "error: M04 live UI requires host networking and a fresh npm ci" >&2
    exit 1
  fi
  required_m04_env=(
    PINVI_M04_LIVE_E2E
    PINVI_M04_LIVE_FEATURE_REQUEST_ID
    PINVI_M04_UI_API_URL
    PINVI_M04_UI_EVIDENCE_DIR
    PINVI_M04_UI_VERIFICATION_ID
    PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_ID
    PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_REF
    PINVI_SOURCE_REVISION
    PINVI_LIVE_WEB_URL
  )
  for name in "${required_m04_env[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      echo "error: M04 live UI requires ${name}" >&2
      exit 1
    fi
  done
  if [[ "${PINVI_M04_LIVE_E2E}" != "1" ]]; then
    echo "error: M04 live UI requires PINVI_M04_LIVE_E2E=1" >&2
    exit 1
  fi
  if [[ -z "${PINVI_M04_LIVE_STORAGE_STATE:-}" && ( -z "${PINVI_M04_LIVE_EMAIL:-}" || -z "${PINVI_M04_LIVE_PASSWORD:-}" ) ]]; then
    echo "error: M04 live UI requires admin credentials or storage state" >&2
    exit 1
  fi
fi

if [[ -n "${PINVI_M05_UI_VERIFICATION_ID:-}" ]]; then
  expected_m05_image="${PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF:-}"
  if [[ "$image" != "$expected_m05_image" ]] || ! is_digest_pinned_playwright_image "$image"; then
    echo "error: M05 live UI requires the attested immutable Playwright image" >&2
    exit 1
  fi
  if [[ "$network" != "host" || "$skip_npm_ci" != "0" ]]; then
    echo "error: M05 live UI requires host networking and a fresh npm ci" >&2
    exit 1
  fi
fi

docker_args=(
  run
  --rm
  --ipc=host
  --network "$network"
  -e "PINVI_PLAYWRIGHT_RUNNER_EVIDENCE_OWNER=$evidence_owner"
  -e HOME=/tmp/pinvi-playwright-home
  -e npm_config_cache=/tmp/.npm
  -e PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
  -e PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI="$skip_npm_ci"
)

allowed_env_names=(
  CI
  DEBUG
  NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED
  PLAYWRIGHT_BASE_URL
  PINVI_ADMIN_LIVE_AUTH_REFRESH_MS
  PINVI_ADMIN_LIVE_CASE_ATTEMPTS
  PINVI_ADMIN_LIVE_CASE_END
  PINVI_ADMIN_LIVE_CASE_LIMIT
  PINVI_ADMIN_LIVE_CASE_START
  PINVI_ADMIN_LIVE_E2E
  PINVI_ADMIN_LIVE_EMAIL
  PINVI_ADMIN_LIVE_LOGIN_ATTEMPTS
  PINVI_ADMIN_LIVE_PASSWORD
  PINVI_ADMIN_LIVE_RETRY_BACKOFF_MS
  PINVI_ADMIN_LIVE_STORAGE_STATE
  PINVI_ADMIN_LIVE_TEST_TIMEOUT_MS
  PINVI_ADMIN_LIVE_THROTTLE_MS
  PINVI_ADMIN_LIVE_WEB_URL
  PINVI_ADMIN_LIVE_WORKERS
  PINVI_BACKUP_LIVE_EMAIL
  PINVI_BACKUP_LIVE_MUTATING_E2E
  PINVI_BACKUP_LIVE_PASSWORD
  PINVI_BACKUP_LIVE_REASON_PREFIX
  PINVI_BACKUP_LIVE_STAGING
  PINVI_BACKUP_LIVE_STORAGE_STATE
  PINVI_BACKUP_LIVE_THROTTLE_MS
  PINVI_LIVE_API_URL
  PINVI_LIVE_ATTACHMENT_E2E
  PINVI_LIVE_EMAIL
  PINVI_LIVE_FEATURE_CACHE_REVALIDATION
  PINVI_LIVE_FEATURE_CACHE_WAIT_MS
  PINVI_LIVE_FEATURE_RESOLUTION_E2E
  PINVI_LIVE_FOUND_FEATURE_ID
  PINVI_LIVE_FOUND_FEATURE_LAT
  PINVI_LIVE_FOUND_FEATURE_LON
  PINVI_LIVE_FOUND_FEATURE_NAME
  PINVI_LIVE_MAP_PROXY_PORT
  PINVI_LIVE_MAP_UPSTREAM_PORT
  PINVI_LIVE_MISSING_FEATURE_ID
  PINVI_LIVE_MUTATING_E2E
  PINVI_LIVE_PASSWORD
  PINVI_LIVE_RETIRED_FEATURE_ID
  PINVI_LIVE_SCREENSHOT_DIR
  PINVI_LIVE_SUPPRESSED_FEATURE_ID
  PINVI_LIVE_TRIP_PREFIX
  PINVI_LIVE_UI_E2E
  PINVI_LIVE_WEB_URL
  PINVI_LIVE_EXPECTED_REVISION
  PINVI_LIVE_WEATHER_DATE
  PINVI_LIVE_WEATHER_FEATURE_ID
  PINVI_LIVE_WEATHER_FEATURE_LAT
  PINVI_LIVE_WEATHER_FEATURE_LON
  PINVI_LIVE_WEATHER_FEATURE_NAME
  PINVI_LIVE_WEATHER_NO_DATA_FEATURE_ID
  PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LAT
  PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LON
  PINVI_LIVE_WEATHER_NO_DATA_FEATURE_NAME
  PINVI_M04_LIVE_EMAIL
  PINVI_M04_LIVE_E2E
  PINVI_M04_LIVE_FEATURE_REQUEST_ID
  PINVI_M04_LIVE_PASSWORD
  PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_ID
  PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_REF
  PINVI_M04_LIVE_REASON
  PINVI_M04_LIVE_STORAGE_STATE
  PINVI_M04_UI_API_URL
  PINVI_M04_UI_EVIDENCE_DIR
  PINVI_M04_UI_VERIFICATION_ID
  PINVI_M05_LIVE_EMAIL
  PINVI_M05_LIVE_E2E
  PINVI_M05_LIVE_EVENT_ID
  PINVI_M05_LIVE_IMPACT_COUNT
  PINVI_M05_LIVE_OLD_FEATURE_ID
  PINVI_M05_LIVE_PASSWORD
  PINVI_M05_LIVE_REPLACEMENT_FEATURE_ID
  PINVI_M05_LIVE_STORAGE_STATE
  PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_ID
  PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF
  PINVI_M05_UI_API_URL
  PINVI_M05_UI_EVIDENCE_DIR
  PINVI_M05_UI_VERIFICATION_ID
  PINVI_SOURCE_REVISION
)
for name in "${allowed_env_names[@]}"; do
  if [[ -v "${name}" ]]; then
    docker_args+=(--env "${name}")
  fi
done

docker_args+=(
  -v "$repo_root:/work"
  -v "${volume_prefix}-node-modules:/work/node_modules"
  -v "${volume_prefix}-npm-cache:/tmp/.npm"
  # live runner가 실패해도 trace/report가 named volume이나 clean checkout에 남지 않는다.
  # M04/M05 증거는 아래 별도 evidence directory의 fixed marker만 허용한다.
  --tmpfs /work/apps/web/test-results:rw,noexec,nosuid,size=64m
  --tmpfs /work/apps/web/playwright-report:rw,noexec,nosuid,size=64m
)
if [[ -n "$evidence_dir" ]]; then
  docker_args+=( -v "$evidence_dir:$evidence_dir" )
fi
docker_args+=(
  -w /work
  "$image"
  bash
  -lc
  'set -euo pipefail
if [[ "${PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI:-0}" != "1" ]]; then
  npm ci --no-audit --no-fund
fi
test_status=0
"$@" || test_status=$?

# Docker runner는 기본 root로 실행된다. smoke attestation은 호출자 소유 0700
# evidence directory를 다시 읽어야 하므로, attested marker 하나만 host caller로
# 되돌린다. staging/production runner가 root라면 root:root 소유가 그대로 유지된다.
marker_path=""
if [[ -n "${PINVI_M04_UI_VERIFICATION_ID:-}" && -n "${PINVI_M04_UI_EVIDENCE_DIR:-}" ]]; then
  marker_path="${PINVI_M04_UI_EVIDENCE_DIR}/m04-ui-run.json"
elif [[ -n "${PINVI_M05_UI_VERIFICATION_ID:-}" && -n "${PINVI_M05_UI_EVIDENCE_DIR:-}" ]]; then
  marker_path="${PINVI_M05_UI_EVIDENCE_DIR}/ui-run.json"
fi
if [[ -n "$marker_path" && -e "$marker_path" ]]; then
  if [[ ! -f "$marker_path" || -L "$marker_path" ]]; then
    echo "error: attested UI evidence marker must be a regular non-symlink file" >&2
    exit 1
  fi
  chown "$PINVI_PLAYWRIGHT_RUNNER_EVIDENCE_OWNER" "$marker_path"
  chmod 600 "$marker_path"
fi
exit "$test_status"'
  bash
  "$@"
)

echo "playwright_runner_image=$image"
echo "playwright_runner_network=$network"
exec "${docker_bin}" "${docker_args[@]}"
