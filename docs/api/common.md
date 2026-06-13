# API 공통 규약

본 문서는 Pinvi HTTP API의 공통 규약을 정의한다. 모든 endpoint 문서는 본 문서를
참조하고, 본 규약에서 벗어나면 그 endpoint 문서에 명시한다.

> **정본 규약 (ADR-030, 2026-06-06 확정)** — 외부 API는 다음을 단일 정본으로 한다.
> 현재 per-domain 문서/코드에 혼재하는 변형은 T-123/T-124/T-126에서 본 규약으로
> 정렬한다(감사 `docs/audit/2026-06-06-doc-impl-audit.md` §3).
> - **URL 버전 prefix**: `/v1` 노출(라우터가 이미 `api/v1`). 예: `GET /v1/trips`.
> - **list 응답**: `{"data": [...], "meta": {...}}` (data는 **배열 직접**). 단건은
>   `{"data": {...}}`. `data.items`/`data.<plural>`/`data.rows` 변형은 폐기.
> - **페이지네이션**: 사용자 대면 list는 **cursor**. Admin/S3 continuation은 예외로
>   각 문서에 명문.
> - **좌표**: `{"lon": .., "lat": ..}` (lng-first, 6자리). WebSocket 포함
>   전 구간 동일. `[lng,lat]`/`{lat,lng}`/평면/GeoJSON 변형 폐기.
> - **datetime**: ISO 8601 `+09:00`(KST). admin 포함 통일.
> - **id 필드**: `<entity>_id`. 현재 사용자 객체는 `data.user`.
> - **생성 status**: 영속 리소스 생성 시 `201`, 그 외 `200`.
> - **에러**: 본 문서 표준 taxonomy만. 누락 코드는 등록 또는 표준 코드로 대체.

## 1. Base URL / 환경별

| 환경 | URL |
|------|-----|
| 로컬 dev | `http://localhost:12801` |
| 로컬 dev (Docker smoke) | `http://127.0.0.1:12801` |
| 스테이징 | TBD (Sprint 6) |
| 운영 | `https://pinviapi.digitie.mywire.org` |

웹 origin:

| 환경 | URL |
|------|-----|
| 로컬 dev | `http://localhost:12805` |
| 로컬 dev (Docker smoke) | `http://127.0.0.1:12805` |
| 운영 | `https://pinvi.digitie.mywire.org` |

OpenAPI 자동 생성: `<base>/docs` (FastAPI), `<base>/redoc`.

## 2. 응답 형식

### 2.1 성공

```jsonc
{
  "data": { /* resource or list */ },
  "meta": {
    "cursor": "...",      // pagination 시
    "has_more": true,     // pagination 시
    "total": 100,         // Admin 일부에서만
    "version": 42         // optimistic lock 대상
  }
}
```

`meta`는 필요 없으면 생략. 단일 리소스 응답은 `data`에 객체, 목록은 배열.

### 2.2 실패

```jsonc
{
  "error": {
    "code": "EMAIL_NOT_VERIFIED",
    "message": "이메일 인증이 필요합니다.",
    "details": { /* validation errors per field, optional */ }
  }
}
```

`message`는 한국어. `code`는 머신 읽기용 (대문자 + 언더스코어). `details`는
`VALIDATION_ERROR`에서 필드별 에러 배열 형태로 사용.

### 2.3 표준 에러 코드

| Code | HTTP | 상황 |
|------|------|------|
| `AUTH_INVALID_CREDENTIALS` | 401 | 이메일/비밀번호 불일치 |
| `EMAIL_NOT_VERIFIED` | 401 | 미인증 상태 로그인 시도. body에 `verification_email_dispatched` |
| `EMAIL_ALREADY_USED` | 409 | 가입 시 이메일 중복 |
| `TOKEN_EXPIRED` | 401 | access/refresh 만료 |
| `TOKEN_INVALID` | 401 | 서명 불일치/위변조 |
| `PERMISSION_DENIED` | 403 | RBAC 거부. Admin은 의도적으로 404로 변환 가능 |
| `RESOURCE_NOT_FOUND` | 404 | 단일 리소스 없음 |
| `VERSION_CONFLICT` | 409 | optimistic lock `If-Match` 불일치 |
| `RATE_LIMITED` | 429 | SlowAPI 한도 초과 |
| `VALIDATION_ERROR` | 422 | Pydantic 검증 실패. `details`에 필드별 |
| `INTERNAL_ERROR` | 500 | 처리 중 예외 (Sentry로 전달) |
| `SERVICE_UNAVAILABLE` | 503 | 외부 의존 (Resend/RustFS) 실패 |

도메인별 추가 코드는 각 API 문서에 명시.

## 3. 인증

### 3.1 Cookie 기반 (사용자 + Admin)

| Cookie | 용도 | 속성 |
|--------|------|------|
| `pinvi_access` | JWT access | HttpOnly, Secure, SameSite=Lax, 15분 |
| `pinvi_refresh` | refresh handle (opaque) | HttpOnly, Secure, SameSite=Lax, 7일 |

- DB에는 access 토큰을 저장하지 않음 (stateless JWT).
- `pinvi_refresh`는 `app.user_sessions`에 hash로만 저장
  (`session_token_hash`). DB row에 `revoked_at` 채우면 즉시 폐기.
- 로그아웃: 현재 refresh session `revoked_at=now()` + 클라이언트 cookie 삭제.
- refresh: 기존 refresh session `revoked_at=now()` + 새 refresh session row 발급
  (rotation).
- Admin은 동일 cookie 사용 (별도 admin 도메인 없음). 권한 검사는 서버 dependency.

### 3.2 OAuth state nonce

OAuth callback 시 CSRF 차단:

- `app.oauth_login_states.state_hash` (TTL 10분, `oauth_state_ttl_seconds`)
- nonce, PKCE code_verifier도 hash로만 저장

자세히는 `docs/integrations/social-login.md`.

### 3.3 Bearer 토큰 (선택)

CLI / 외부 도구가 access를 직접 사용하려면 `Authorization: Bearer <jwt>` 헤더.
브라우저는 cookie 우선.

## 4. 시간 / 좌표

### 4.1 시간

- DB: `timestamptz` (UTC 저장)
- 응용 변환: KST (`Asia/Seoul`) — Python `zoneinfo`
- 응답 JSON: ISO 8601 + offset, 예: `"2026-05-25T14:30:00+09:00"`
- 요청 입력: ISO 8601 (offset 포함 권장). offset 없으면 KST로 해석.

### 4.2 좌표

- 입력/응답: **`(longitude, latitude)`** 순서. EPSG:4326.
- 응답 단일 좌표: `{"lon": 127.0, "lat": 37.5}` 또는
  GeoJSON `{"type": "Point", "coordinates": [127.0, 37.5]}`.
- 응답 좌표 정밀도: 소수점 4자리 (~10m) — 사용자 위치(SPEC V8 O-3)는 4자리 제한,
  POI feature 좌표는 6자리 가능.
- bbox: `{"sw": [lng, lat], "ne": [lng, lat]}` 또는 query `sw_lng,sw_lat,ne_lng,ne_lat`.

### 4.3 위치 감사

좌표를 query/body에 받는 endpoint는 자동으로 `app.location_access_log`에 적재
(`docs/architecture/user-location.md`). 클라이언트가 별도 처리 X.

## 5. Pagination

### 5.1 cursor 기반 (기본)

```http
GET /trips?limit=20&cursor=eyJ1cGRhdGVkX2F0Ijoi...
```

```jsonc
{
  "data": [/* ... */],
  "meta": {
    "cursor": "next-cursor-token",
    "has_more": true
  }
}
```

- `cursor`는 opaque (base64로 JSON 인코딩). 클라이언트는 분석하지 않음.
- 마지막 페이지는 `has_more: false`, `cursor`는 생략 또는 `null`.
- `limit` 기본 20, 최대 100.

### 5.2 page/limit 기반 (Admin 일부)

Admin 화면처럼 페이지 점프가 필요한 경우만:

```http
GET /admin/users?page=3&limit=100
```

```jsonc
{
  "data": [/* ... */],
  "meta": {
    "page": 3,
    "limit": 100,
    "total": 287,
    "total_pages": 3
  }
}
```

`limit`은 `50, 100, 200, 500` 중 선택 (Admin UI 표준).

## 6. Optimistic Lock — `If-Match`

POI / Trip / NoticePlan PATCH 요청은 `If-Match: <version>` 헤더 필수:

```http
PATCH /trips/{trip_id}/pois/{poi_id}
If-Match: 42
Content-Type: application/json

{"user_note": "..."}
```

- 서버: 현재 `version` ≠ `If-Match` → `409 VERSION_CONFLICT` (현재 row 반환)
- 클라이언트: "동반자 X가 변경했습니다. 새 값으로 갱신할까요?" 다이얼로그
- 성공 시 `version = version + 1`, WebSocket broadcast

## 7. 검색 / 필터 / 정렬 (Admin)

`/admin/{resource}` 목록 endpoint는 SPEC V8 M-9 검색 문법 사용:

```http
GET /admin/users?q=email:gmail.com+-status:disabled&sort=-created_at&page=1
```

자세히는 [admin.md](./admin.md) §검색.

## 8. Rate Limit

| 카테고리 | 한도 | 키 |
|---------|------|-----|
| 로그인 / 가입 / 재설정 / verify | 분당 5회 | IP + 이메일(JSON body에 이메일이 있으면 포함) |
| OAuth start / callback | 분당 10회 | IP |
| `/storage/upload-urls` | 분당 30회 | user_id |
| `/public/*` | 분당 60회 | IP |
| `/features/in-bounds` | 분당 60회 | user_id 또는 IP |
| `/features/search`, `/search` | 분당 60회 | user_id 또는 IP |
| `/trips/{id}/exports/*` | 분당 20회 | user_id |
| 그 외 인증 사용자 경로 | 분당 60회 | user_id 또는 token |
| 공유 토큰 접근 (`/trips/{id}/shared/{token}`) | 분당 60회 | token |

초과 시 `429 RATE_LIMITED` + `Retry-After` 헤더.

구현은 `RateLimitMiddleware`가 전역으로 적용한다(ADR-038/T-195). 기본
`PINVI_RATE_LIMIT_BACKEND=auto`는 `PINVI_ENVIRONMENT=production`/`staging`에서
Postgres fixed-window bucket(`app.rate_limit_buckets`), 그 외 로컬/테스트/smoke에서
process-local memory를 사용한다. 운영에서 worker/노드 간 한도 공유가 필요하므로 memory
backend를 강제하지 않는다.

IP key는 기본적으로 socket client IP를 사용한다. Cloudflare Tunnel/reverse proxy가 origin
직접 접근을 막고 실제 client IP를 보존하는 환경에서만
`PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP`처럼 명시한다. 저장 bucket key는
HMAC-SHA256으로 해시되며 원문 IP/email/token은 DB에 저장하지 않는다.

## 9. Webhook

| Path | 발신자 | 검증 |
|------|--------|------|
| `POST /webhooks/resend` | Resend | Svix 서명 (`svix-id` / `svix-timestamp` / `svix-signature`), secret 미설정 시 기본 `503`; 로컬 unsigned는 명시 opt-in 필요 |
| `POST /webhooks/oauth/{provider}/callback` | Google 활성, Naver/Kakao future provider | state + PKCE |
| (v2) `POST /webhooks/telegram/{trip_id}` | Telegram bot | HMAC |
| (v2) `POST /webhooks/gemini/job` | 사용자 키 호출 콜백 | idempotency_key |

서명 검증 실패 시 `401`. Resend webhook secret이 없거나 잘못된 형식이면 기본
`503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다. 서명 없는 Resend webhook은
로컬성 환경에서 `PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED=true`를 명시한 경우에만 허용한다.
페이로드 raw는 `app.api_call_log`에 저장하지 않음(`hash`만).

## 10. CORS

| 환경 | 허용 Origin |
|------|------------|
| 로컬 dev | `http://localhost:12805`, `http://127.0.0.1:12805` |
| Docker smoke | `http://127.0.0.1:12805` |
| 스테이징 | TBD |
| 운영 | `https://pinvi.digitie.mywire.org` |

`Access-Control-Allow-Credentials: true` (cookie 전송).

운영 보안 처리:

- API `https://pinviapi.digitie.mywire.org`는 CORS origin에 직접 추가하지 않는다.
  CORS 허용 origin은 브라우저가 로드된 웹 origin
  `https://pinvi.digitie.mywire.org`만 둔다.
- 운영 `PINVI_CORS_ALLOWED_ORIGINS`는 정확히
  `["https://pinvi.digitie.mywire.org"]`로 설정한다. wildcard(`*`) 금지.
- credential cookie를 쓰므로 `Access-Control-Allow-Credentials: true`와 wildcard
  origin을 함께 쓰면 안 된다.

## 11. CSP / 보안 헤더

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{nonce}'
  ; img-src 'self' data: https://api.vworld.kr https://...;
  connect-src 'self' http://localhost:12801 https://pinviapi.digitie.mywire.org
  https://api.resend.com https://api.vworld.kr`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(self)` (위치 권한 origin)
- `X-Frame-Options: DENY` (Admin Dagit 임베드 예외는 별도)

운영에서는 TLS 종단 이후에도 앱이 `PINVI_ENVIRONMENT=production`을 받아야 한다.
이 값이 production이면 인증 cookie는 `Secure`로 설정된다. reverse proxy /
Cloudflare Tunnel 구성에서 `X-Forwarded-Proto=https`를 보존하고, HTTP 직접 접근은
HTTPS로 redirect한다.

## 12. 로깅 / 추적

- 모든 요청에 `X-Request-Id` UUID 생성 (요청 헤더에 있으면 그대로 사용)
- structlog 미들웨어가 `request_id`, `user_id`, `path`, `method`, `status`,
  `latency_ms`를 자동 로깅
- 위치 좌표 / 비밀번호 / 토큰은 `before_send` PII 마스킹 (Sentry / Loki 양쪽)
- Admin debug `/admin/debug/request/{id}` 페이지에서 추적

## 13. 버전 관리

- 본 v1.0 단계: URL prefix는 `/` (예: `/auth/login`). 향후 v2 도입 시 `/v1`,
  `/v2` 분기 ADR로 결정.
- 응답 셰입 BREAKING은 ADR + CHANGELOG. Deprecation 경로는 `Deprecation`,
  `Sunset` HTTP 헤더 사용.

## 14. AI agent를 위한 구현 체크리스트

새 endpoint를 구현할 때:

- [ ] 본 문서 + 해당 도메인 API 문서 + `docs/data-model.md` 확인
- [ ] Pydantic schema (`apps/api/app/schemas/`) + Zod schema (`packages/schemas/`)
      두 곳에 동일 정의
- [ ] 서비스 (`apps/api/app/services/`)에 비즈니스 로직 (라우터에 직접 박지 X)
- [ ] 라우터 (`apps/api/app/api/v1/`) + dependency (인증/RBAC)
- [ ] 미들웨어 자동 적용 확인 (request_id, location_audit, api_call_log,
      admin_audit if admin route)
- [ ] 통합 테스트 `apps/api/tests/integration/test_<route>.py`
- [ ] OpenAPI export (코드 작성 단계 진입 후 자동) — 변경 시 `.github/workflows/openapi.yml`에서 drift 검사
- [ ] 관련 문서 갱신: 본 API 문서 + `docs/journal.md` + (도메인 변경 시)
      `docs/data-model.md`
