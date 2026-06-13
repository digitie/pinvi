#!/usr/bin/env bash
# Non-secret operational preflight for Pinvi nodes.

set -euo pipefail

ROOT_DIR="${PINVI_ROOT_DIR:-/opt/pinvi}"
COMPOSE_FILE="${PINVI_COMPOSE_FILE:-infra/docker-compose.app.yml}"
PROJECT="${PINVI_DOCKER_PROJECT:-pinvi-app}"
NODE_NAME="${PINVI_NODE_NAME:-$(hostname)}"
EXPECTED_ARCH="${PINVI_EXPECTED_ARCH:-}"
EXPECTED_OS_VERSION="${PINVI_EXPECTED_OS_VERSION:-}"
API_PORT="${PINVI_API_PORT:-12801}"
WEB_PORT="${PINVI_WEB_PORT:-12805}"
RUSTFS_PORT="${PINVI_RUSTFS_PORT:-12101}"

section() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    printf 'OK %s: %s\n' "$1" "$(command -v "$1")"
  else
    warn "$1 not found"
  fi
}

check_url() {
  local label="$1"
  local url="$2"
  if curl -fsS "$url" >/dev/null 2>&1; then
    printf 'OK %s: %s\n' "$label" "$url"
  else
    warn "${label} unavailable: ${url}"
  fi
}

masked_env() {
  local name="$1"
  if grep -qE "^${name}=" .env 2>/dev/null; then
    printf 'OK %s=***\n' "$name"
  else
    warn "${name} missing from .env"
  fi
}

section "Node"
printf 'name=%s\n' "$NODE_NAME"
actual_arch="$(uname -m)"
printf 'arch=%s\n' "$actual_arch"
if [[ -n "$EXPECTED_ARCH" && "$actual_arch" != "$EXPECTED_ARCH" ]]; then
  warn "expected arch ${EXPECTED_ARCH}, got ${actual_arch}"
fi
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  printf 'os=%s %s\n' "${NAME:-unknown}" "${VERSION_ID:-unknown}"
  if [[ -n "$EXPECTED_OS_VERSION" && "${VERSION_ID:-}" != "$EXPECTED_OS_VERSION" ]]; then
    warn "expected OS version ${EXPECTED_OS_VERSION}, got ${VERSION_ID:-unknown}"
  fi
fi

section "Commands"
check_command docker
check_command curl
check_command git
check_command rsync
if docker compose version >/dev/null 2>&1; then
  docker compose version
else
  warn "docker compose plugin not available"
fi

section "Storage"
if mount | grep -q ' /mnt/nvme '; then
  printf 'OK /mnt/nvme mounted\n'
else
  warn "/mnt/nvme is not mounted"
fi
df -h /mnt/nvme 2>/dev/null || true

section "Repository"
if [[ -d "$ROOT_DIR" ]]; then
  cd "$ROOT_DIR"
  printf 'root=%s\n' "$ROOT_DIR"
else
  warn "root directory missing: ${ROOT_DIR}"
  exit 2
fi
[[ -f "$COMPOSE_FILE" ]] && printf 'OK compose=%s\n' "$COMPOSE_FILE" || warn "compose file missing"
[[ -f .env ]] && printf 'OK .env exists\n' || warn ".env missing"

section "Required environment names"
for name in \
  PINVI_ENVIRONMENT \
  PINVI_DATABASE_URL \
  PINVI_JWT_SECRET_KEY \
  PINVI_CORS_ALLOWED_ORIGINS \
  PINVI_RATE_LIMIT_BACKEND \
  PINVI_API_IMAGE \
  PINVI_WEB_IMAGE \
  NEXT_PUBLIC_PINVI_API_URL
do
  masked_env "$name"
done

section "Compose"
if [[ -f "$COMPOSE_FILE" ]]; then
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" ps || true
fi

section "Local health"
check_url "api" "http://127.0.0.1:${API_PORT}/health"
check_url "api-db" "http://127.0.0.1:${API_PORT}/health/db"
check_url "web" "http://127.0.0.1:${WEB_PORT}/"
check_url "rustfs" "http://127.0.0.1:${RUSTFS_PORT}/health/live"
