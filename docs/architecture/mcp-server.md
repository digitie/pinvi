# TripMate MCP 외부 인터페이스 (ADR-019)

> Sprint 6 진입 후 본격 구현. 본 문서는 결정 / 컨트랙트 / 보안 / 모니터링을
> 박는다. AI agent는 본 문서만 보고 구현 가능해야 한다.

## 1. 목적

TripMate가 **MCP (Model Context Protocol) 서버를 외부로 노출**한다. 외부 AI
agent (Claude Code / Claude Desktop / Codex / Antigravity 등)가 사용자 본인의
trip / poi / feature / profile 데이터를 read-only로 조회할 수 있다.

**사용 시나리오**:
- 사용자가 Claude Desktop에 "내 부산 여행 일정 보여줘" → MCP tool `get_trip` 호출
- 사용자가 Codex CLI에 "다음 여행에 추가할 만한 한적한 카페 추천" →
  `search_features(q="한적 카페", bounds=내 trip 영역)` + `list_pois(trip_id)`
  조합
- 사용자가 본인의 자동화 스크립트에서 cron으로 `list_trips` polling

## 2. 트랜스포트

| 트랜스포트 | 사용처 | 엔드포인트 |
|----------|--------|----------|
| **stdio** | Claude Desktop (로컬) — `~/.claude.json`에 등록 | `codegraph install` 패턴과 동일하게 wrapper script 제공 |
| **SSE (Server-Sent Events)** | Claude Code remote / web client / 사용자 자동화 | `GET /mcp/sse` (Bearer 토큰) |

stdio wrapper는 `apps/api/scripts/mcp-stdio-bridge.sh` — 환경변수로 토큰을
받아 `/mcp/sse`로 프록시.

## 3. 인증

### 3.1 MCP 토큰

일반 `tripmate_access` cookie 토큰과 **분리된** 전용 토큰.

- **scope**: `mcp:read` (필수, 1차 구현 한정). 향후 `mcp:write`, `mcp:admin`
  scope 추가 가능 (ADR-019 amendment).
- **수명**: 기본 30일. 사용자가 발급 시 1일~무기한 선택.
- **저장**: `app.mcp_tokens` (Alembic migration Sprint 6) — `token_id`, `user_id`,
  `token_hash` (Argon2id), `scopes TEXT[]`, `name TEXT` (사용자가 부여),
  `expires_at`, `last_used_at`, `last_used_ip_hash`, `revoked_at`.
- **사용자 API**: `GET/POST /users/me/mcp-tokens`,
  `DELETE /users/me/mcp-tokens/{token_id}`.
- **Admin API**: `GET/POST /admin/mcp-tokens`,
  `POST /admin/mcp-tokens/{token_id}/revoke`.
- **발급 UI**: `/settings/mcp-tokens` (사용자 본인) / `/admin/mcp-tokens`
  (관리자 — 전체 / 대리 발급 / 강제 회수).
- **표시**: 발급 직후 1회만 원본 노출. 이후 `mcp_xxxx...xxxx` 마스킹.

### 3.2 호출 검증

```http
GET /mcp/sse
Authorization: Bearer mcp_<JWT>
```

1. JWT signature 검증 (`TRIPMATE_MCP_JWT_SECRET` — 일반 access 토큰과 별 secret)
2. `revoked_at IS NULL` 확인
3. `expires_at > now()` 확인
4. `scope` 일치 확인
5. `last_used_at` 갱신 + `api_call_log` 적재

### 3.3 Rate limit

- 사용자당 **60 calls/min**. 초과 시 429.
- 일 1만 calls 초과 시 admin 알림 (악용 의심).

## 4. Tools (1차 — 5개, 모두 read-only)

### 4.1 `list_trips`

```jsonc
{
  "name": "list_trips",
  "description": "사용자 본인의 trip 목록",
  "inputSchema": {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["draft", "planned", "in_progress", "completed", "archived"]
      },
      "limit": { "type": "integer", "default": 20, "maximum": 100 }
    }
  }
}
```

응답: `[{trip_id, title, status, start_date, end_date, day_count, poi_count}]`

### 4.2 `get_trip(trip_id)`

```jsonc
{
  "name": "get_trip",
  "description": "trip + day + POI 트리 전체",
  "inputSchema": {
    "type": "object",
    "properties": { "trip_id": { "type": "string", "format": "uuid" } },
    "required": ["trip_id"]
  }
}
```

응답: `{trip: {...}, days: [{day_index, date, pois: [{poi_id, label, feature_id, ...}]}]}`

### 4.3 `list_pois(trip_id, day_index?)`

trip 또는 trip의 특정 day의 POI만 필터.

### 4.4 `search_features(q, kind?, bounds?)`

krtour-map OpenAPI HTTP `GET /features/search`로 조회한다. 결과는 사용자 권한 /
동의 범위 내에서만 반환한다.

### 4.5 `get_user_profile`

본인 프로필 (마스킹 적용 — 이메일 / 전화는 일반 API와 동일 마스킹).

## 5. mutating tool은 v1.1 이후

본 ADR-019 1차는 **read-only만**. 사용자 UX 검증 + 보안 점검 후 v1.1에서
mutating tool 추가 (별 ADR-019-amend):

- `add_poi_to_trip(trip_id, feature_id, day_index)` — 새 POI 추가
- `optimize_day(trip_id, day_index)` — 일정 자동 최적화 (ADR Sprint 6)
- `update_trip(trip_id, ...)` — trip 메타 변경

mutating tool은 scope `mcp:write` 별 발급 필요.

## 6. 디렉토리 구조

```
apps/api/app/mcp/
├── __init__.py
├── server.py              # FastAPI sub-app 또는 별 ASGI
├── auth.py                # MCP 토큰 검증
├── tools/
│   ├── __init__.py
│   ├── list_trips.py
│   ├── get_trip.py
│   ├── list_pois.py
│   ├── search_features.py
│   └── get_user_profile.py
└── transport/
    ├── sse.py             # /mcp/sse
    └── stdio.py           # apps/api/scripts/mcp-stdio-bridge.sh wrapper

apps/web/app/
├── (app)/settings/mcp-tokens/page.tsx          # 사용자 본인
├── (admin)/admin/mcp-tokens/page.tsx           # admin
└── components/mcp/McpTokenIssuer.tsx
```

## 7. 모니터링

- 모든 MCP 호출 → `app.api_call_log` 적재
- 발급 / revoke → `app.admin_audit_log`
- Grafana 대시보드: 호출량 / 에러율 / 사용자별 분포 / 만료 임박 토큰
- 일 1만 calls 초과 / 1분 동안 429 30회 초과 → admin 알림 (Telegram 또는 email)

## 8. CSP / 도메인

- `connect-src 'self' https://tripmateapi.digitie.mywire.org` (SSE)
- 추가 도메인 노출은 없음 — 본 저장소의 기존 API 도메인 안.

## 9. 절대 금지

- mutating tool 1차 노출 금지 (ADR-019)
- 사용자 본인 데이터 외 노출 금지 (admin role도 본인 데이터만)
- MCP 토큰을 일반 cookie 토큰과 교차 사용 금지 (별 scope)
- 무인증 호출 허용 금지

## 10. 참조

- ADR-017 (codegraph MCP — 운영 친숙도)
- ADR-019 (본 결정)
- `docs/runbooks/mcp-server.md` — 운영 절차
- Anthropic MCP 표준: https://modelcontextprotocol.io/
