#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/n150-live-catalog.sh [options] [-- <extra playwright args>]

Runs the live e2e catalog (apps/web/e2e-live, playwright.live-catalog.config.ts) against the
deployed PinVi web app from N150, through the official Playwright Docker runner
(scripts/n150-playwright-runner.sh). Results (html report, results.json, traces, shots) land in a
dated directory and a pass/fail/skip table per area is printed at the end.

Options:
  --project <name>   desktop | mobile | session (repeatable; default: desktop mobile).
                     `session` enables the ~13-min TRIP-046 (@slow) project.
  --area <area>      trip | search | nearby | weather | share | poi | notify | admin | core
                     (repeatable; default: all areas)
  --grep <regex>     Playwright --grep (case id such as 'TRIP-00[1-3]' or a title fragment)
  --list             List the selected cases and exit (no browser, no env file needed)
  --head             Use the current checkout HEAD as PINVI_LIVE_EXPECTED_REVISION
                     (the runner refuses a dirty/mismatched checkout either way)
  -h, --help

Environment (names only — values live in the root-only env file, never on the command line):
  PINVI_E2E_ENV_FILE               Root-only env file, default /root/.pinvi-e2e.env.
                                   Required keys: PLAYWRIGHT_BASE_URL, PINVI_E2E_USER_EMAIL,
                                   PINVI_E2E_USER_PASSWORD. See docs/runbooks/live-e2e-catalog.md
                                   for the optional keys (USER2, ADMIN, TELEGRAM, …).
  PINVI_E2E_RESULTS_ROOT           Where dated result dirs are created,
                                   default $HOME/pinvi-live-catalog-results.
  PINVI_LIVE_EXPECTED_REVISION     Full SHA the checkout must match (or pass --head).
  PINVI_PLAYWRIGHT_RUNNER_IMAGE    Digest-pinned Playwright image (default: the pin recorded in
                                   docs/runbooks/live-mutating-e2e.md).
USAGE
}

projects=()
areas=()
grep_expr=""
list_only="0"
use_head="0"
extra=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) projects+=("$2"); shift 2 ;;
    --area) areas+=("$2"); shift 2 ;;
    --grep) grep_expr="$2"; shift 2 ;;
    --list) list_only="1"; shift ;;
    --head) use_head="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; extra=("$@"); break ;;
    *) echo "error: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [[ ${#projects[@]} -eq 0 ]]; then
  projects=(desktop mobile)
fi
for p in "${projects[@]}"; do
  case "$p" in
    desktop|mobile|session) ;;
    *) echo "error: unknown project '$p' (desktop|mobile|session)" >&2; exit 2 ;;
  esac
done
for a in "${areas[@]}"; do
  case "$a" in
    trip|search|nearby|weather|share|poi|notify|admin|core) ;;
    *) echo "error: unknown area '$a'" >&2; exit 2 ;;
  esac
done

repo_root="${PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT:-}"
if [[ -z "$repo_root" ]]; then
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
repo_root="$(cd "$repo_root" && pwd)"
cd "$repo_root"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "error: run this on N150 (Linux)" >&2
  exit 1
fi

# ── env file (root-only). Re-exec through sudo when it is not readable by this user. ──
env_file="${PINVI_E2E_ENV_FILE:-/root/.pinvi-e2e.env}"
if [[ "$list_only" != "1" ]]; then
  if [[ ! -r "$env_file" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
      echo "env file $env_file is not readable — re-running with sudo (SUDO_USER keeps the result dir)" >&2
      exec sudo --preserve-env=PINVI_E2E_ENV_FILE,PINVI_E2E_RESULTS_ROOT,PINVI_LIVE_EXPECTED_REVISION,PINVI_PLAYWRIGHT_RUNNER_IMAGE,PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT,HOME "$0" "$@"
    fi
    echo "error: env file $env_file is missing or unreadable" >&2
    exit 1
  fi
  if [[ "$(stat -c '%a' "$env_file")" != "600" && "$(stat -c '%a' "$env_file")" != "400" ]]; then
    echo "error: $env_file must be mode 600 (or 400); it holds credentials" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  for name in PLAYWRIGHT_BASE_URL PINVI_E2E_USER_EMAIL PINVI_E2E_USER_PASSWORD; do
    if [[ -z "${!name:-}" ]]; then
      echo "error: $env_file must set $name" >&2
      exit 1
    fi
  done
  case "$PLAYWRIGHT_BASE_URL" in
    *localhost*|*127.0.0.1*)
      echo "error: PLAYWRIGHT_BASE_URL must be the deployed origin (#618: no localhost fallback)" >&2
      exit 1 ;;
  esac
fi

# ── checkout pin + runner image (same gate as the other live suites) ──
if [[ "$use_head" == "1" ]]; then
  PINVI_LIVE_EXPECTED_REVISION="$(git rev-parse --verify HEAD^{commit})"
  echo "note: PINVI_LIVE_EXPECTED_REVISION taken from HEAD (${PINVI_LIVE_EXPECTED_REVISION:0:12}) — not a release gate" >&2
fi
export PINVI_LIVE_EXPECTED_REVISION="${PINVI_LIVE_EXPECTED_REVISION:-}"
export PINVI_PLAYWRIGHT_RUNNER_IMAGE="${PINVI_PLAYWRIGHT_RUNNER_IMAGE:-mcr.microsoft.com/playwright:v1.64.1-noble@sha256:47b510dd9230bf0b9bfc9b20102241e577ea7a99334ab4c3ca19f19770e9b8ea}"

# ── playwright args ──
pw_args=()
for p in "${projects[@]}"; do
  pw_args+=(--project "$p")
  if [[ "$p" == "session" ]]; then
    export PINVI_E2E_SESSION=1
  fi
done
if [[ -n "$grep_expr" ]]; then
  pw_args+=(--grep "$grep_expr")
fi
for a in "${areas[@]}"; do
  pw_args+=("e2e-live/specs/$a/")
done
if [[ ${#extra[@]} -gt 0 ]]; then
  pw_args+=("${extra[@]}")
fi

if [[ "$list_only" == "1" ]]; then
  # Listing needs no browser and no credentials; use the checkout's own node_modules.
  exec npm -w @pinvi/web run test:e2e:live-catalog:list -- "${pw_args[@]}"
fi

# ── result dir (mounted into the container at the same absolute path) ──
results_root="${PINVI_E2E_RESULTS_ROOT:-${HOME}/pinvi-live-catalog-results}"
run_dir="${results_root}/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run_dir"
export PINVI_PLAYWRIGHT_RUNNER_OUTPUT_DIR="$run_dir"
export PINVI_E2E_OUTPUT_DIR="$run_dir"
export PINVI_LIVE_UI_E2E=1
echo "live catalog: projects=${projects[*]} areas=${areas[*]:-all} grep=${grep_expr:-none}"
echo "live catalog: results → $run_dir"

status=0
scripts/n150-playwright-runner.sh -- \
  npm -w @pinvi/web run test:e2e:live-catalog -- "${pw_args[@]}" || status=$?

if [[ -f "$run_dir/results.json" ]]; then
  node scripts/live-catalog-summary.mjs "$run_dir/results.json" || true
else
  echo "live catalog: no results.json in $run_dir (run aborted before the reporter wrote it)" >&2
fi
if [[ -n "${SUDO_USER:-}" && "$EUID" -eq 0 ]]; then
  chown -R "$SUDO_USER" "$run_dir" || true
fi
echo "live catalog: exit $status, report $run_dir/html/index.html"
exit "$status"
