# API 공통 규약

본 문서는 Pinvi HTTP API의 공통 규약을 정의한다. 모든 endpoint 문서는 본 문서를
참조하고, 본 규약에서 벗어나면 그 endpoint 문서에 명시한다.

> **정본 규약 (ADR-030, 2026-06-06 확정)** — 외부 API는 다음을 단일 정본으로 한다.
> 현재 per-domain 문서/코드에 혼재하는 변형은 T-123/T-124/T-126에서 본 규약으로
> 정렬한다(감사 `docs/audit/2026-06-06-doc-impl-audit.md` §3).
>
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

| 환경                    | URL                             |
| ----------------------- | ------------------------------- |
| 로컬 dev                | `http://localhost:12801`        |
| 로컬 dev (Docker smoke) | `http://127.0.0.1:12801`        |
| 스테이징                | TBD (Sprint 6)                  |
| 운영                    | `https://pinvi-api.example.com` |

웹 origin:

| 환경                    | URL                         |
| ----------------------- | --------------------------- |
| 로컬 dev                | `http://localhost:12805`    |
| 로컬 dev (Docker smoke) | `http://127.0.0.1:12805`    |
| 운영                    | `https://pinvi.example.com` |

OpenAPI 자동 생성: `<base>/docs` (FastAPI), `<base>/redoc`.

## 2. 응답 형식

### 2.1 성공

```jsonc
{
  "data": {
    /* resource or list */
  },
  "meta": {
    "cursor": "...", // pagination 시
    "has_more": true, // pagination 시
    "total": 100, // Admin 일부에서만
    "version": 42, // optimistic lock 대상
  },
}
```

`meta`는 필요 없으면 생략. 단일 리소스 응답은 `data`에 객체, 목록은 배열.

### 2.2 실패

```jsonc
{
  "error": {
    "code": "EMAIL_NOT_VERIFIED",
    "message": "이메일 인증이 필요합니다.",
    "details": {
      /* validation errors per field, optional */
    },
  },
}
```

`message`는 한국어. `code`는 머신 읽기용 (대문자 + 언더스코어). `details`는
`VALIDATION_ERROR`에서 필드별 에러 배열 형태로 사용.

### 2.3 표준 에러 코드

| Code                       | HTTP | 상황                                                            |
| -------------------------- | ---- | --------------------------------------------------------------- |
| `AUTH_INVALID_CREDENTIALS` | 401  | 이메일/비밀번호 불일치                                          |
| `EMAIL_NOT_VERIFIED`       | 401  | 미인증 상태 로그인 시도. body에 `verification_email_dispatched` |
| `EMAIL_ALREADY_USED`       | 409  | 가입 시 이메일 중복                                             |
| `TOKEN_EXPIRED`            | 401  | access/refresh 만료                                             |
| `TOKEN_INVALID`            | 401  | 서명 불일치/위변조                                              |
| `PERMISSION_DENIED`        | 403  | RBAC 거부. Admin은 의도적으로 404로 변환 가능                   |
| `RESOURCE_NOT_FOUND`       | 404  | 단일 리소스 없음                                                |
| `VERSION_CONFLICT`         | 409  | optimistic lock `If-Match` 불일치                               |
| `RATE_LIMITED`             | 429  | SlowAPI 한도 초과                                               |
| `VALIDATION_ERROR`         | 422  | Pydantic 검증 실패. `details`에 필드별                          |
| `INTERNAL_ERROR`           | 500  | 처리 중 예외 (Sentry로 전달)                                    |
| `SERVICE_UNAVAILABLE`      | 503  | 외부 의존 (Resend/RustFS) 실패                                  |

도메인별 추가 코드는 각 API 문서에 명시.

## 3. 인증

### 3.1 Cookie 기반 (사용자 + Admin)

| Cookie          | 용도                    | 속성                                 |
| --------------- | ----------------------- | ------------------------------------ |
| `pinvi_access`  | JWT access              | HttpOnly, Secure, SameSite=Lax, 15분 |
| `pinvi_refresh` | refresh handle (opaque) | HttpOnly, Secure, SameSite=Lax, 7일  |

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
  "data": [
    /* ... */
  ],
  "meta": {
    "cursor": "next-cursor-token",
    "has_more": true,
  },
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
  "data": [
    /* ... */
  ],
  "meta": {
    "page": 3,
    "limit": 100,
    "total": 287,
    "total_pages": 3,
  },
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

| 카테고리                                      | 한도      | 키                                            |
| --------------------------------------------- | --------- | --------------------------------------------- |
| 로그인 / 가입 / 재설정 / verify               | 분당 5회  | IP + 이메일(JSON body에 이메일이 있으면 포함) |
| OAuth start / callback                        | 분당 10회 | IP                                            |
| `/storage/upload-urls`                        | 분당 30회 | user_id                                       |
| `/public/*`                                   | 분당 60회 | IP                                            |
| `/features/in-bounds`, `/weather/markers-in-bounds` | 분당 60회 | user_id 또는 IP                         |
| `/features/search`, `/search`                 | 분당 60회 | user_id 또는 IP                               |
| `/trips/{id}/exports/*`                       | 분당 20회 | user_id                                       |
| 그 외 인증 사용자 경로                        | 분당 60회 | user_id 또는 token                            |
| 공유 토큰 접근 (`/trips/{id}/shared/{token}`) | 분당 60회 | token                                         |

초과 시 `429 RATE_LIMITED` + `Retry-After` 헤더. Admin `/admin/abuse`에서 생성한 active
`blocked` override는 `429 RATE_LIMIT_BLOCKED`, active `allowed` override는 TTL 동안 counter hit
우회로 적용된다(Postgres backend 한정).

구현은 `RateLimitMiddleware`가 전역으로 적용한다(ADR-038/T-195). 기본
`PINVI_RATE_LIMIT_BACKEND=auto`는 `PINVI_ENVIRONMENT=production`/`staging`에서
Postgres fixed-window bucket(`app.rate_limit_buckets`), 그 외 로컬/테스트/smoke에서
process-local memory를 사용한다. 운영에서 worker/노드 간 한도 공유가 필요하므로 memory
backend를 강제하지 않는다.

IP key는 기본적으로 socket client IP를 사용한다. Cloudflare Tunnel/reverse proxy가 origin
직접 접근을 막고 실제 client IP를 보존하는 환경에서만
`PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP`처럼 명시한다. 저장 bucket key는
HMAC-SHA256으로 해시되며 원문 IP/email/token은 DB에 저장하지 않는다.


### 사용자별 영구 상한(#653)

PINVI_RATE_LIMIT_USER_LIMIT_OVERRIDES는 canonical 사용자 UUID를 양의 정수 상한(최대 6000/분)에 대응시키는 JSON 객체이며 기본값은 빈 객체다. 예시는 다음과 같다(실제 UUID는 로컬 운영 구성에만 둔다).

    PINVI_RATE_LIMIT_USER_LIMIT_OVERRIDES={"00000000-0000-0000-0000-000000000101":600}

bool·문자열 숫자·실수·0·음수·UUID가 아닌 키와 비정규 UUID 표기는 시작 시 거부한다. 검증된 access JWT의 사용자 식별자에만 적용하며 인증 성공을 대신하지 않는다. 네 정책 authenticated_default·feature_search·storage_upload_urls·trip_exports 각각의 독립 한도를 대체한다. 낮은 값도 그대로 적용하며 전체 정책을 합친 하나의 공유 상한이 아니다. 기본 authenticated_default/feature_search60, storage30, export20, 로그인5와 그 밖의 정책은 비대상에게 그대로다.

대상 사용자는 유효한 blocked가 기존 allowed보다 먼저 적용된다(생성 순서 무관). allowed가 있어도 실제 counter를 증가시키고 상한에서429를 반환한다. 차단 해제는 해당 blocked를 정상 rollback하거나 만료시키며, 이미 소진한 counter는 새 window 전까지 유지한다. 비대상 사용자의 기존 최신 활성 override 선택 의미는 유지한다. 429의 limit·Retry-After와 관리자 limit/remaining/초과 집계는 실제 유효 상한이다. 무시된 allowed 행은 원문 metadata를 보존하되 bucket 상태는 observed이며 UI에서 허용 우회 미적용을 안내한다.

기존 identity/HMAC 산식은 유지한다. UUID 설정 membership은 비밀키 회전과 무관하지만 회전하면 counter hash와 기존 DB override hash 연결은 바뀐다. 기존 저장소 장애 정책도 유지하며 기본은 fail-closed다. fail_open을 명시하면 저장소 장애 시 상한을 건너뛸 수 있으므로 무조건적인 상한 보장으로 해석하지 않는다.

운영 Manager는 환경변수를 명시적으로 전달한다. Manager pinvi-api 전달선과 Pinvi fallback Compose 전달선이 모두 있어야 하며 .env 값만 추가해서는 충분하지 않다. 코드 전달선 변경과 운영 UUID 구성·기존 임시6건 해제는 별개다. 실제 운영 활성화·검증은 담당 Claude Code가 수행한다.

### 저장소 장애와 핸들러 오류의 경계(#684)

한도 저장소의 override 조회·counter hit 실패만 기존 fail-open/fail-closed 정책을 적용한다.
허용 후 핸들러 DB 오류나 응답 전송 오류를 한도 저장소503으로 바꾸거나 핸들러를 재실행하지 않는다.
저장소 장애 로그에는 예외 종류와 정책 이름만 남기며 SQL·파라미터 원문은 남기지 않는다.

## 9. Webhook

| Path                                       | 발신자                                   | 검증                                                                                                                       |
| ------------------------------------------ | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `POST /webhooks/resend`                    | Resend                                   | Svix 서명 (`svix-id` / `svix-timestamp` / `svix-signature`), secret 미설정 시 기본 `503`; 로컬 unsigned는 명시 opt-in 필요 |
| `POST /webhooks/oauth/{provider}/callback` | Google 활성, Naver/Kakao future provider | state + PKCE                                                                                                               |
| (v2) `POST /webhooks/telegram/{trip_id}`   | Telegram bot                             | HMAC                                                                                                                       |
| (v2) `POST /webhooks/gemini/job`           | 사용자 키 호출 콜백                      | idempotency_key                                                                                                            |

서명 검증 실패 시 `401`. Resend webhook secret이 없거나 잘못된 형식이면 기본
`503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다. 서명 없는 Resend webhook은
로컬성 환경에서 `PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED=true`를 명시한 경우에만 허용한다.
페이로드 raw는 `app.api_call_log`에 저장하지 않음(`hash`만).

## 10. CORS

| 환경         | 허용 Origin                                        |
| ------------ | -------------------------------------------------- |
| 로컬 dev     | `http://localhost:12805`, `http://127.0.0.1:12805` |
| Docker smoke | `http://127.0.0.1:12805`                           |
| 스테이징     | TBD                                                |
| 운영         | `https://pinvi.example.com`                        |

`Access-Control-Allow-Credentials: true` (cookie 전송).

운영 보안 처리:

- API `https://pinvi-api.example.com`는 CORS origin에 직접 추가하지 않는다.
  CORS 허용 origin은 브라우저가 로드된 웹 origin
  `https://pinvi.example.com`만 둔다.
- 운영 `PINVI_CORS_ALLOWED_ORIGINS`는 정확히
  `["https://pinvi.example.com"]`로 설정한다. wildcard(`*`) 금지.
- credential cookie를 쓰므로 `Access-Control-Allow-Credentials: true`와 wildcard
  origin을 함께 쓰면 안 된다.

## 11. CSP / 보안 헤더

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{nonce}'
; img-src 'self' data: https://api.vworld.kr https://...;
connect-src 'self' http://localhost:12801 https://pinvi-api.example.com
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

## 외부 호출 복원력과 관측 (#616·#621)

Map outer envelope는 필수 `data`/`meta`와 기존 타입·상태 의미를 검사하고 추가 키는
무시한다. 무시한 키는 위치·키 집합별 한 번 경고한다. 서명·인과 증명·immutable receipt의
exact 검사는 별도 보안 경계이므로 그대로 유지한다.

사용자 Map·geo·weather client는 worker별 독립 동시 호출 한도16을 가진다. Map weather와
transport는 기본 Map client 한도를 공유한다. 포화 시 기다리지 않고 기존 unavailable로
강등한다. timeout 등 전송 장애가 3회 연속 발생하면 회로를120초 열고 시험 호출 하나만
허용한다. 직접 weather의 endpoint/host·짧은 deadline 판단은 유지하며 이전 세대의 늦은
결과는 새 회로 상태에 반영하지 않는다. 로컬 포화·연결 풀 대기는 원격 장애로 세지 않는다.
별도 admin/curation/command client를 하나의 전역 Map cap으로 합친 것은 아니다.

Map 회로는 표면별로 따로 센다(#702): viewport(`in-bounds`·`nearby`), 그 밖 feature
(검색·상세·batch·공개 표면), transport. weather 표면은 자기 회로만 세고 Map 회로에는 닿지
않는다. 한 표면의 timeout이 다른 표면을 120초 끊지 않는다. 재시도는 연결 단계 오류
(연결 실패·응답 없는 끊김)와 5xx에만 하고 `ReadTimeout`은 다시 보내지 않는다 — Map이
처리 중인 무거운 질의를 겹쳐 쌓지 않는다. 멱등 GET이 재사용 연결의 끊김으로 실패하면
재시도 없는 표면에서도 새 연결로 한 번 더 보낸다. pooled 연결은 3초 뒤 버린다(Map uvicorn
keep-alive 5초보다 짧게). 실패 경고(`kor_travel_map.unavailable`)는 method·path·예외 클래스·
전송 횟수만 남긴다(query·header 제외).

HTTP 오류 공개 계약은 그대로다. Map·geo의 포화/열린 회로는 공개503의
`FEATURE_SERVICE_UNAVAILABLE`/`GEOCODING_SERVICE_UNAVAILABLE`로 투영하고 내부 code나
예외 문자열을 응답하지 않는다. rate limit은 기존429·Retry-After·저장소503·fail-open
정책을 유지한다. Postgres backend의 override 결정과 atomic counter 증가는 하나의
statement를 쓰며, 만료 bucket 정리는 요청과 독립된60초 주기 task가 transaction당
최대1000행씩 `SKIP LOCKED`로 처리한다. full batch이면같은전체주기5초예산안에서
추가batch를drain하며, 연결생성OSError/ConnectionRefusedError뒤에는다음주기에복구한다.
취소는계속전파하고driver close오류가외부취소를덮어도종료의도를유지한다.

`api_call_log`는 감사/업무 outbox와 달리 손실 허용 관측이다. session factory마다 메모리
큐 하나(대기1024행 + 전송 중 최대100행)를 쓰고0.25초/최대100행으로 배치한다. 요청은
DB 저장을 기다리지 않는다. flush는2초, 종료 drain은3초 상한이며 실패/포화/종료 손실은
`pinvi_api_call_log_rows_total{outcome=...}`, 대기는 `pinvi_api_call_log_queued`로 집계한다.
성공 여부를 확인하기 전 응답을 반환하므로 관리자 조회에 짧은 지연이나 누락이 있을 수 있다.

`ApiCallLoggingClient`를 사용하는 provider factory는 timeout·연결 실패·body read 실패·취소도
기록하고 원래 예외를 유지한다. endpoint는 공통 redaction을 적용하고 임의 예외 문자열은
저장하지 않는다. 기록의 `occurred_at`은 enqueue 시각이다. API runtime·관리자 TCP/UDS probe·독립 CLI의 생성부도 같은 client로 연결했다.
Dagster bounded reader는 기존 response-hook 금지 규칙을 유지하고 request tracker와
stream 종료 관측을 사용한다. streaming 응답은 헤더가 아니라 EOF/실패/취소/조기 종료에서
한 번 기록한다. 독립 CLI는 client 종료 뒤, DB engine dispose 전에 bounded drain한다.
Telegram의 전체 deadline이 전송을 먼저 취소하면 실제 전송 예외는 CancelledError이며,
공개 network_error 변환과 사용자 직접 취소의 재전파는 기존대로 유지한다.
별도 ETL 패키지는 API ORM에 의존하지 않으며 기존 resource timeout·Dagster retry/metadata를
유지한다.

DB 기본값은 `PINVI_DATABASE_POOL_SIZE=10`, `PINVI_DATABASE_MAX_OVERFLOW=0`,
`PINVI_DATABASE_POOL_TIMEOUT_SECONDS=5`이다. 대기 metric
`pinvi_api_db_pool_wait_seconds{outcome=acquired|timeout|cancelled|error}`는 실제 queue
acquisition을 측정하고 새 연결 생성 시간도 포함한다. SQL 실행·pre-ping 시간은 포함하지
않는다. worker가 늘면 이 한도가 worker 수만큼 곱해진다. 운영 설정 전달·부하 검증과
edge HTTP/2·worker 증설은 별도 운영 담당 범위다.

직접 weather `/resolve`는 요청에서 기다리지 않는다. 같은 좌표의 유효한 직접 캐시만
읽고, 미스는 별도 세션·별도 context의 배경 해석을 예약해 즉시 빈 카드/trip unavailable로
반환한다. feature별 single-flight와 최신 좌표 예약 병합, 실행2·대기128·음성 캐시128/30초를
사용한다. resolve만 read45초를 쓰며 전체 반경 HTTP 해석은140초 상한이다. 요청 deadline이나
인증 context는 배경 작업에 상속하지 않는다. 종료 시 worker를 취소·회수한 뒤 client를 닫는다.
음성 캐시는 반경 없음과 실패를 구분하고 TTL 뒤 재시도한다. 좌표/Map/로컬 캐시 삭제 뒤
늦은 결과는 optimistic version 검사로 거부한다. 외부 Map feature 삭제 여부는 Pinvi가
캐시 행만으로 추정하지 않는다.

직접 카드 예산은 `PINVI_KOR_TRAVEL_WEATHER_REQUEST_BUDGET_SECONDS` 기본4초,
관리자는 `PINVI_KOR_TRAVEL_WEATHER_ADMIN_REQUEST_BUDGET_SECONDS` 기본10초를 쓴다.
긴 resolve read override는 다른 동시 호출의 timeout을 바꾸지 않는다. 느린5xx는 기본 read와
호출별 read 중 짧은 값의 절반을 이미 썼으면 재시도하지 않으며, 빠른5xx·연결 재시도는
유지한다. deadline 회로의 의미 있는 원격 예산은 실제 connect/header 전송 시작부터 계산해
로컬 연결 풀 대기를 원격 장애 시간으로 세지 않는다.

#621의 운영 flag 적용·edge HTTP/2·실제 운영 latency/부하 및 worker 증설은 Claude Code
소유다. WSL 소유 fixture 검증은 운영 검증을 대신하지 않으며 #621은 자동 종료하지 않는다.
