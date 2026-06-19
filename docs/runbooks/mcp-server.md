# Pinvi MCP 외부 인터페이스 운영 (ADR-019)

> 아키텍처는 `docs/architecture/mcp-server.md`. 본 runbook은 토큰 관리 /
> 클라이언트 연결 / 모니터링 / 트러블슈팅.

## 1. 토큰 발급

### 1.1 사용자 본인

```
1. apps/web 로그인
2. /settings/mcp-tokens 진입
3. "새 토큰 발급" 클릭
4. 입력:
   - name (예: "Claude Desktop @ macbook")
   - scope: ☑ mcp:read (필수, 1차 한정)
   - expires_at: 30일 (default) / 1일 / 7일 / 무기한
5. "발급" → 원본 mcp_xxxx... 1회 노출 → 사용자가 복사
6. 다시 보려면 회수 후 재발급 필요
```

### 1.2 admin (사용자 대리)

`/admin/mcp-tokens`에서 admin role이 사용자 대리로 발급 가능 (사용자 동의 후
오프라인 발급 시나리오 — 운영 트러블슈팅용).

audit log에 `actor_user_id != owner_user_id` 기록.

### 1.3 HTTP API 정본

사용자 본인:

- `GET /users/me/mcp-tokens` — 내 토큰 목록(마스킹, `last_used_at`, 만료/회수 상태)
- `POST /users/me/mcp-tokens` — 토큰 발급(`name`, `expires_at`, `scopes=["mcp:read"]`)
- `DELETE /users/me/mcp-tokens/{token_id}` — 내 토큰 회수

Admin:

- `GET /admin/mcp-tokens` — 전체 토큰 검색(`user_id`, `q`, `status`)
- `POST /admin/mcp-tokens` — 사용자 대리 발급(`user_id`, `name`, `expires_at`,
  `access_reason`)
- `POST /admin/mcp-tokens/{token_id}/revoke` — 강제 회수(`access_reason`)

## 2. 클라이언트 등록

### 2.1 Claude Desktop (stdio)

`~/.claude.json`:

```json
{
  "mcpServers": {
    "pinvi": {
      "type": "stdio",
      "command": "/path/to/mcp-stdio-bridge.sh",
      "env": {
        "PINVI_MCP_URL": "https://pinvi-api.example.com/mcp/sse",
        "PINVI_MCP_TOKEN": "mcp_xxxx..."
      }
    }
  }
}
```

T-112 1차 구현은 SSE discovery와 HTTP tool-call 표면을 먼저 제공한다. stdio wrapper
(`apps/api/scripts/mcp-stdio-bridge.sh`)는 같은 토큰과 tool registry를 재사용하는 후속
작업에서 추가한다.

### 2.2 Claude Code (SSE 직접)

```json
{
  "mcpServers": {
    "pinvi": {
      "type": "sse",
      "url": "https://pinvi-api.example.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer mcp_xxxx..."
      }
    }
  }
}
```

### 2.3 사용자 자동화 (curl)

```bash
# SSE 스트림
curl -N -H "Authorization: Bearer mcp_xxxx..." \
  https://pinvi-api.example.com/mcp/sse

# tool 호출
curl -X POST -H "Authorization: Bearer mcp_xxxx..." \
  -H "Content-Type: application/json" \
  -d '{"arguments":{"bucket":"all","limit":20}}' \
  https://pinvi-api.example.com/mcp/tools/list_trips
```

## 3. 토큰 회수

### 3.1 사용자 본인

```
1. /settings/mcp-tokens
2. 회수할 토큰 옆 "회수" 버튼
3. 확인 → revoked_at 즉시 설정
4. 다음 호출부터 401
```

### 3.2 admin (긴급)

```
1. /admin/mcp-tokens 진입
2. 검색 (사용자 / 이름 / last_used_at)
3. "강제 회수" → 사유 입력 → admin_audit_log
```

긴급 시 (토큰 leak 의심) — 사용자 전체 토큰을 한 번에 회수:

```bash
# DB 직접
docker exec -it pinvi-postgres psql -U pinvi pinvi <<SQL
UPDATE app.mcp_tokens
   SET revoked_at = now()
 WHERE user_id = '<user_id>'
   AND revoked_at IS NULL;
SQL
```

## 4. 모니터링

### 4.1 Grafana 대시보드 (Sprint 5 이후)

`/admin/grafana` → "MCP 외부 인터페이스" 대시보드:

- 시간별 호출량 (line chart)
- tool별 분포 (bar chart)
- 에러율 (401 / 429 / 5xx)
- 활성 토큰 수
- 사용자별 호출 top 10
- 만료 7일 임박 토큰 수

### 4.2 알림

- 1분 동안 401이 30회 초과 → admin 알림 (Telegram)
- 1일 동안 한 토큰의 호출이 1만 초과 → admin 알림 (악용 의심)
- 1일 동안 unique IP가 5+ → admin 알림 (토큰 leak 의심)

## 5. tool 추가 / 변경

mutating tool 추가 (v1.1+) 전:

1. ADR-019-amend 박기 — 어느 tool / scope / 영향 범위
2. `apps/api/app/mcp/tools/<tool_name>.py` 추가
3. `apps/api/app/mcp/server.py` tools 목록 등록
4. 통합 테스트 + 보안 검토 (사용자 데이터 외 노출 금지)
5. UI에 새 scope 추가 (`McpTokenIssuer.tsx`)
6. 사용자 안내 (release notes)

## 6. 트러블슈팅

| 증상 | 원인 후보 | 해결 |
|------|----------|------|
| 클라이언트 401 (Token expired) | expires_at 경과 | 재발급 |
| 401 (Token revoked) | revoked_at 설정됨 | 재발급, 회수 사유 확인 |
| 429 Too Many Requests | rate limit (60/min) | backoff or 사용자 안내 |
| 404 tool not found | tool 명 오타 / version mismatch | tools list (`/mcp/sse`로 GET) |
| 500 internal | DB / 외부 HTTP 호출 실패 | request_id로 Loki 검색 |
| SSE 연결 끊김 | timeout / network | client 재연결 (exponential backoff) |

## 7. 보안 사고 대응

토큰 leak 의심 시:

1. 사용자 / admin 모두 즉시 회수
2. last_used_at + last_used_ip 추적 (admin_audit_log)
3. 의심 IP에서의 모든 호출 audit log 조회
4. 영향 받은 사용자 데이터 범위 평가 (read-only이지만)
5. 사용자 / CPO에게 통지 (PIPA)

## 8. 참조

- ADR-019 (본 정책)
- `docs/architecture/mcp-server.md` (아키텍처)
- ADR-017 + `docs/runbooks/codegraph-worktrees.md` (codegraph MCP — 운영 친숙도)
- SPRINT-6.md
