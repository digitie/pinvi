#!/usr/bin/env bash
# Start Pinvi local DEV services on fixed ports, bound to 127.0.0.1 (internal only).
#
# 정책 (ADR-047):
# - dev는 여기(이 worktree)에서 직접 실행한다. 기본 대상은 dev(별도 지시 없으면 dev).
# - 내부 주소 127.0.0.1로만 bind한다(외부/LAN 미노출).
# - 고정 포트가 이미 점유돼 있으면 새 포트로 바꾸지 않는다. 강제종료 여부를 사용자에게
#   묻고, 거부하면 기동을 중지한다. prod(ktdctl) 컨테이너가 같은 포트를 쓰는 경우도 동일.
# - prod는 이 스크립트가 아니라 kor-travel-docker-manager(ktdctl)로 올린다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="${ROOT}/.tmp/dev/pids"
LOG_DIR="${ROOT}/.tmp/dev/logs"

HOST="127.0.0.1"
API_PORT="${PINVI_API_DEV_PORT:-12801}"
WEB_PORT="${PINVI_WEB_DEV_PORT:-12805}"
DAGSTER_PORT="${PINVI_DAGSTER_DEV_PORT:-12802}"
# 비대화형에서 명시적으로 강제종료를 허용할 때만 1. 기본은 묻기/중지.
FORCE_KILL="${PINVI_DEV_FORCE_KILL:-0}"

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
export TMPDIR=/tmp
export TMP=/tmp
export TEMP=/tmp
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  . "${HOME}/.nvm/nvm.sh"
fi

mkdir -p "${PID_DIR}" "${LOG_DIR}"

port_pids() {
  local port="$1" pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -z "${pids}" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "${port}" 2>/dev/null || true)"
  fi
  echo "${pids}" | tr '\n' ' ' | tr -s ' '
}

# 고정 포트 점유 검사 — 점유 시 새 포트로 바꾸지 않고 사용자에게 강제종료를 묻는다.
ensure_ports_free_or_ask() {
  local occupied=() name port pids
  for entry in "api:${API_PORT}" "web:${WEB_PORT}" "dagster:${DAGSTER_PORT}"; do
    name="${entry%%:*}"
    port="${entry##*:}"
    pids="$(port_pids "${port}")"
    pids="${pids#"${pids%%[![:space:]]*}"}"
    pids="${pids%"${pids##*[![:space:]]}"}"
    if [[ -n "${pids}" ]]; then
      occupied+=("${name} :${port} (pid ${pids})")
    fi
  done

  if [[ ${#occupied[@]} -eq 0 ]]; then
    return 0
  fi

  echo "ERROR: 다음 고정 dev 포트가 이미 사용 중입니다 (새 포트로 바꾸지 않습니다):" >&2
  local o
  for o in "${occupied[@]}"; do
    echo "  - ${o}" >&2
  done
  echo "  prod(ktdctl) 컨테이너이거나 다른 dev 인스턴스일 수 있습니다." >&2

  local do_kill=0
  if [[ "${FORCE_KILL}" == "1" ]]; then
    do_kill=1
    echo "PINVI_DEV_FORCE_KILL=1 → 강제종료 진행." >&2
  elif [[ -t 0 ]]; then
    local ans=""
    printf '강제종료하고 같은 포트로 재기동할까요? [y/N] ' >&2
    read -r ans || ans=""
    case "${ans}" in
      [yY] | [yY][eE][sS]) do_kill=1 ;;
      *) do_kill=0 ;;
    esac
  else
    echo "비대화형(TTY 없음): 기본은 강제종료하지 않음." >&2
    echo "종료를 원하면 PINVI_DEV_FORCE_KILL=1 또는 'npm run dev:down' 후 재시도." >&2
  fi

  if [[ "${do_kill}" != "1" ]]; then
    echo "==> 강제종료하지 않음. dev 기동을 중지합니다." >&2
    exit 3
  fi

  echo "==> 사용자 승인 → 점유 프로세스를 종료하고 같은 포트로 재기동합니다."
  "${ROOT}/scripts/dev-down.sh"
}

ensure_ports_free_or_ask

require_linux_command() {
  local name="$1"
  local path

  path="$(command -v "${name}" 2>/dev/null || true)"
  if [[ -z "${path}" ]]; then
    echo "ERROR: ${name} not found in WSL PATH" >&2
    exit 1
  fi
  if [[ "${path}" == /mnt/c/* || "${path}" == *.exe || "${path}" == *.cmd ]]; then
    echo "ERROR: ${name} resolves to Windows shim: ${path}" >&2
    exit 1
  fi
}

require_linux_command uv
require_linux_command node
require_linux_command npm

start_service() {
  local name="$1"
  shift

  echo "==> starting ${name}: $*"
  (
    cd "${ROOT}"
    if command -v setsid >/dev/null 2>&1; then
      setsid "$@" >"${LOG_DIR}/${name}.log" 2>&1 &
    else
      nohup "$@" >"${LOG_DIR}/${name}.log" 2>&1 &
    fi
    echo "$!" >"${PID_DIR}/${name}.pid"
  )
}

start_service api \
  bash -lc "cd apps/api && uv run python -m uvicorn app.main:app --reload --host ${HOST} --port ${API_PORT}"

start_service web \
  env NEXT_PUBLIC_PINVI_API_URL="http://127.0.0.1:${API_PORT}" \
    NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED="${NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED:-0}" \
    NEXT_PUBLIC_VWORLD_API_KEY="${NEXT_PUBLIC_VWORLD_API_KEY:-}" \
    npm --workspace apps/web run dev -- --hostname "${HOST}"

start_service dagster \
  bash -lc "cd apps/etl && uv run dagster dev --host ${HOST} --port ${DAGSTER_PORT}"

echo "==> API     http://127.0.0.1:${API_PORT}"
echo "==> Web     http://127.0.0.1:${WEB_PORT}"
echo "==> Dagster http://127.0.0.1:${DAGSTER_PORT}"
echo "==> logs    ${LOG_DIR}"
