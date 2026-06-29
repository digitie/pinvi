#!/usr/bin/env bash
# MCP 외부 인터페이스 운영 실증 (ADR-019 / T-266, T-273 라이브 게이트).
#
# 발급된 MCP 토큰으로 read-only tool 호출 성공을 확인한다(Claude Code/Desktop 클라이언트
# 등록 전/후 점검). 통합 테스트는 apps/api/tests/integration/test_mcp_tokens_api.py
# (test_mcp_read_only_tool_scenario)가 CI에서 동일 흐름을 자동 검증한다.
#
# env:
#   API_BASE   (선택) 기본 http://127.0.0.1:12801
#   MCP_TOKEN  (필수) mcp_... 토큰 (/users/me/mcp-tokens 또는 /admin/mcp-tokens 발급)
#   SEARCH_Q   (선택) search_features 질의, 기본 "서울"
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:12801}"
: "${MCP_TOKEN:?MCP_TOKEN is required (mcp_... 발급 토큰)}"
SEARCH_Q="${SEARCH_Q:-서울}"
auth="Authorization: Bearer ${MCP_TOKEN}"
body="$(mktemp)"
trap 'rm -f "$body"' EXIT
fail=0

req() { # req METHOD PATH [json] → echoes http_code, writes body to $body
  if [ "$1" = "GET" ]; then
    curl -s -o "$body" -w '%{http_code}' -H "$auth" "${API_BASE}$2"
  else
    curl -s -o "$body" -w '%{http_code}' -X "$1" -H "$auth" \
      -H 'Content-Type: application/json' -d "${3:-{}}" "${API_BASE}$2"
  fi
}

check() { # check LABEL EXPECTED ACTUAL [needle]
  if [ "$3" != "$2" ]; then echo "  FAIL  $1 → HTTP $3 (want $2)"; fail=1; return; fi
  if [ -n "${4:-}" ] && ! grep -q "$4" "$body"; then
    echo "  FAIL  $1 → 200이나 본문에 '$4' 없음"; fail=1; return; fi
  echo "  PASS  $1"
}

echo "[verify-mcp] target=$API_BASE"
check "GET /mcp/tools" 200 "$(req GET /mcp/tools)" 'list_trips'
check "POST list_trips" 200 \
  "$(req POST /mcp/tools/list_trips '{"arguments":{"bucket":"all"}}')" '"result"'
check "POST search_features" 200 \
  "$(req POST /mcp/tools/search_features "{\"arguments\":{\"q\":\"${SEARCH_Q}\"}}")" '"items"'

if [ "$fail" -ne 0 ]; then
  echo "[verify-mcp] FAILED — MCP 동작이 기대와 다르다(토큰/feature 서비스/권한 확인)." >&2
  exit 1
fi
echo "[verify-mcp] OK"
