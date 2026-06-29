#!/usr/bin/env bash
# 한국 전용 geofencing — FastAPI fallback 스모크 검증 (ADR-018 / T-268, T-273 라이브 게이트용).
#
# 실행 중인 API origin에 대해 2차(FastAPI) 계층의 451/통과를 확인한다. Cloudflare 1차는
# KR 외 실 IP(또는 VPN)로 직접 요청해 별도 확인한다(docs/runbooks/korea-only.md §5).
#
# 전제: 대상 API가 PINVI_GEOFENCE_ENABLED=true로 기동 중. proxy secret/CIDR/mTLS 중 설정된
# trusted signal을 본 스크립트가 충족해야 country header가 신뢰된다(미충족 시 UNKNOWN→차단).
#
# env:
#   API_BASE                (선택) 기본 http://127.0.0.1:12801
#   GEOFENCE_COUNTRY_HEADER (선택) 기본 CF-IPCountry
#   GEOFENCE_PROXY_HEADER   (선택) 기본 X-Pinvi-Geofence-Proxy
#   GEOFENCE_PROXY_SECRET   (선택) PINVI_GEOFENCE_TRUSTED_PROXY_SECRET와 동일 값
#   HEALTH_PATH             (선택) 기본 /api/v1/healthz
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:12801}"
COUNTRY_HEADER="${GEOFENCE_COUNTRY_HEADER:-CF-IPCountry}"
PROXY_HEADER="${GEOFENCE_PROXY_HEADER:-X-Pinvi-Geofence-Proxy}"
PROXY_SECRET="${GEOFENCE_PROXY_SECRET:-}"
HEALTH_PATH="${HEALTH_PATH:-/api/v1/healthz}"

fail=0
proxy_args=()
[ -n "$PROXY_SECRET" ] && proxy_args=(-H "${PROXY_HEADER}: ${PROXY_SECRET}")

status() { # status <country> <path>
  curl -s -o /dev/null -w '%{http_code}' \
    -H "${COUNTRY_HEADER}: $1" "${proxy_args[@]}" "${API_BASE}$2"
}

check() { # check <label> <expected> <actual>
  if [ "$3" = "$2" ]; then
    echo "  PASS  $1 → $3"
  else
    echo "  FAIL  $1 → expected $2, got $3"
    fail=1
  fi
}

echo "[verify-geofence] target=$API_BASE country_header=$COUNTRY_HEADER secret=$([ -n "$PROXY_SECRET" ] && echo set || echo unset)"
check "KR 통과 (root)"        200 "$(status KR /api/v1/healthz)"
check "비KR 차단 (US, root)"  451 "$(status US /)"
check "헬스체크 bypass"       200 "$(status US "$HEALTH_PATH")"

if [ "$fail" -ne 0 ]; then
  echo "[verify-geofence] FAILED — geofence 동작이 기대와 다르다." >&2
  exit 1
fi
echo "[verify-geofence] OK"
