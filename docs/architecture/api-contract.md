# API 계약 — 응답 / 에러 / Pagination / 버전

본 문서는 TripMate HTTP API의 계약 표준. `docs/api/common.md`의 디테일을 본 문서가
요약. AI agent가 구현 시작 전 빠르게 확인.

## 1. 응답 형식

```jsonc
// 성공
{
  "data": { /* resource or list */ },
  "meta": {
    "cursor": "...",       // cursor pagination
    "has_more": true,
    "total": 100,          // Admin 일부
    "version": 42          // optimistic lock 대상
  }
}

// 실패
{
  "error": {
    "code": "EMAIL_NOT_VERIFIED",
    "message": "이메일 인증이 필요합니다.",
    "details": { /* field-level validation 등 */ }
  }
}
```

- `meta`는 필요 시만
- `message`는 한국어 (사용자 가시), `code`는 머신용
- `details`는 `VALIDATION_ERROR`에 자세히 (필드별 배열)

## 2. 표준 에러 코드

| Code | HTTP | 의미 |
|------|------|------|
| `AUTH_INVALID_CREDENTIALS` | 401 | 로그인 실패 (enumeration 차단) |
| `EMAIL_NOT_VERIFIED` | 401 | 미인증 로그인 |
| `EMAIL_ALREADY_USED` | 409 | 가입 시 중복 |
| `TOKEN_EXPIRED` | 401 | access/refresh 만료 |
| `TOKEN_INVALID` | 401 | 서명 불일치 |
| `PERMISSION_DENIED` | 403 | RBAC 거부. Admin은 404 변환 가능 |
| `RESOURCE_NOT_FOUND` | 404 | 단일 리소스 없음 |
| `VERSION_CONFLICT` | 409 | `If-Match` 불일치 |
| `RATE_LIMITED` | 429 | SlowAPI 한도 |
| `VALIDATION_ERROR` | 422 | Pydantic 검증 |
| `INTERNAL_ERROR` | 500 | 예외 (Sentry) |
| `SERVICE_UNAVAILABLE` | 503 | 외부 의존 실패 |

도메인별 추가:

- `auth`: `OAUTH_PROVIDER_DISABLED`, `OAUTH_STATE_EXPIRED`, `ACCOUNT_LINK_REQUIRED`,
  `EMAIL_UNVERIFIED_PROVIDER`, ...
- `trips`: `TRIPS_OWNED` (탈퇴 시), `TRIP_NOT_FOUND`, `INVALID_DAY_RANGE`, ...
- `pois`: `SORT_ORDER_CONFLICT`, `FEATURE_NOT_LINKED`, ...
- `notice_plans`: `NOTICE_PLAN_NOT_PUBLISHED`, `COPY_TARGET_INVALID`, ...
- `storage`: `MIME_NOT_ALLOWED`, `FILE_TOO_LARGE`, `BUCKET_UNAVAILABLE`, ...
- `admin`: `CANNOT_MODIFY_SELF`, `REASON_REQUIRED`, ...

## 3. Pagination

### 3.1 Cursor 기반 (기본)

```http
GET /trips?limit=20&cursor=<base64>
```

```jsonc
{
  "data": [...],
  "meta": { "cursor": "next-token", "has_more": true }
}
```

cursor는 base64로 JSON. 클라이언트는 분석 X.

### 3.2 Page/Limit (Admin)

```http
GET /admin/users?page=3&limit=100
```

`limit`: 50 / 100 / 200 / 500.

## 4. Optimistic Lock

PATCH 요청에 `If-Match: <version>` 헤더 필수:

```http
PATCH /trips/<id>
If-Match: 42
```

- 불일치 → `409 VERSION_CONFLICT` + 현재 row 반환
- 성공 시 `version + 1`

## 5. 인증 헤더

기본 cookie:

- `tripmate_access` (JWT, 15분)
- `tripmate_refresh` (opaque, 7일)

대안 Bearer:

```http
Authorization: Bearer <jwt>
```

## 6. 시간 / 좌표

- 모든 timestamp ISO 8601 + offset (`+09:00`)
- 좌표 lon-lat 순서, EPSG:4326
- 사용자 위치는 정밀도 4자리

자세히는 `docs/conventions/geospatial.md`.

## 7. URL prefix / 버전

- v1.0 단계: `/<resource>` (prefix 없음)
- v2 도입 시: `/v1/<resource>`, `/v2/<resource>` 결정 ADR
- Deprecation: `Deprecation` + `Sunset` HTTP 헤더

## 8. 응답 헤더

| 헤더 | 의미 |
|------|------|
| `X-Request-Id` | request 추적 (모든 응답) |
| `If-Match` (요청) / `ETag` (응답) | optimistic lock |
| `Retry-After` (429) | rate limit |
| `Deprecation`, `Sunset` (옵션) | 폐기 예정 |
| `Cache-Control` | public 응답만 |

## 9. CORS / 보안 헤더

`docs/api/common.md` §10, §11 참고. HTTPS / HSTS / CSP / X-Frame-Options /
Permissions-Policy 모두 활성.

## 10. AI agent 체크리스트

새 endpoint 구현 시:

- [ ] 본 문서 응답 형식 준수
- [ ] 표준 에러 코드 우선 사용 (도메인별 추가는 본 문서 §2에 등록)
- [ ] pagination 필요 시 cursor 기본
- [ ] PATCH는 `If-Match` 필수
- [ ] HTTP status code 표준 (200/201/204/4xx/5xx)
- [ ] `X-Request-Id` 자동 처리 확인 (미들웨어)
- [ ] Pydantic + Zod 양쪽 schema 동기
