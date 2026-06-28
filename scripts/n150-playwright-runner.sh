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

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required" >&2
  exit 1
fi

repo_root="${PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT:-}"
if [[ -z "$repo_root" ]]; then
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
repo_root="$(cd "$repo_root" && pwd)"
cd "$repo_root"

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

docker_args=(
  run
  --rm
  --ipc=host
  --network "$network"
  -e HOME=/tmp/pinvi-playwright-home
  -e npm_config_cache=/tmp/.npm
  -e PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
  -e PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI="$skip_npm_ci"
)

while IFS='=' read -r name _; do
  case "$name" in
    PINVI_PLAYWRIGHT_RUNNER_* | PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD | PLAYWRIGHT_BROWSERS_PATH)
      ;;
    PINVI_* | NEXT_PUBLIC_* | PLAYWRIGHT_* | CI | DEBUG)
      docker_args+=(--env "$name")
      ;;
  esac
done < <(env)

docker_args+=(
  -v "$repo_root:/work"
  -v "${volume_prefix}-node-modules:/work/node_modules"
  -v "${volume_prefix}-npm-cache:/tmp/.npm"
  -v "${volume_prefix}-test-results:/work/apps/web/test-results"
  -v "${volume_prefix}-playwright-report:/work/apps/web/playwright-report"
  -w /work
  "$image"
  bash
  -lc
  'set -euo pipefail
if [[ "${PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI:-0}" != "1" ]]; then
  npm ci --no-audit --no-fund
fi
exec "$@"'
  bash
  "$@"
)

echo "playwright_runner_image=$image"
echo "playwright_runner_network=$network"
exec docker "${docker_args[@]}"
