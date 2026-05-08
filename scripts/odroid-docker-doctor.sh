#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/infra/docker-compose.yml")

cd "${ROOT_DIR}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "FAIL: ODROID/WSL2 기준 스크립트는 Linux에서 실행합니다." >&2
  exit 1
fi

echo "kernel: $(uname -srm)"
echo "arch: $(uname -m)"
if [[ "$(uname -m)" != "aarch64" && "$(uname -m)" != "arm64" ]]; then
  echo "WARN: ODROID M1S 기준 arch는 aarch64/arm64입니다. 현재는 개발/WSL 환경일 수 있습니다." >&2
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "os: ${PRETTY_NAME:-unknown}"
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" != "24.04" ]]; then
    echo "WARN: 기준 OS는 Ubuntu 24.04입니다. 현재 VERSION_ID=${VERSION_ID:-unknown}" >&2
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker 명령을 찾지 못했습니다." >&2
  exit 1
fi
docker --version

if ! docker compose version >/dev/null 2>&1; then
  echo "FAIL: docker compose plugin을 찾지 못했습니다." >&2
  exit 1
fi
docker compose version

if [[ ! -f .env ]]; then
  echo "FAIL: .env 파일이 없습니다. 운영 비밀값은 서버 로컬 .env에만 저장하세요." >&2
  exit 1
fi

missing_env=()
for key in TRIPMATE_DATA_GO_SERVICE_KEY TRIPMATE_OPINET_API_KEY TRIPMATE_EXPRESSWAY_API_KEY; do
  if ! grep -Eq "^${key}=.+" .env; then
    missing_env+=("${key}")
  fi
done
if (( ${#missing_env[@]} > 0 )); then
  printf 'FAIL: .env에 필수 값이 없습니다: %s\n' "${missing_env[*]}" >&2
  exit 1
fi

mkdir -p .tmp/dagster-downloads .tmp/dagster-logs .tmp/etl-soak .tmp/backups dataset

echo "disk:"
df -h . .tmp dataset

echo "compose services:"
"${COMPOSE[@]}" config --services

echo "docker status:"
docker info --format 'ServerVersion={{.ServerVersion}} CgroupDriver={{.CgroupDriver}} OSType={{.OSType}} Architecture={{.Architecture}}'

echo "ODROID Docker doctor passed"
