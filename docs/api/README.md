# TripMate HTTP API 문서

본 디렉토리는 TripMate `apps/api`가 제공하는 HTTP endpoint의 계약을 박는다.
**v1.0 출시 전까지 본 문서가 단일 진실 — 실제 코드 구현 시 이 문서가 우선**한다.

## 1. 인덱스

| 파일 | 범위 | Sprint |
|------|------|--------|
| [auth.md](./auth.md) | 이메일 가입/로그인/verify/refresh + Google/Naver/Kakao OAuth | 1~2 |
| [users.md](./users.md) | 프로필/동의/탈퇴/avatar/OAuth 연결 | 1~2 |
| [trips.md](./trips.md) | Trip CRUD + 동반자 + 공유 토큰 + items | 2 |
| [pois.md](./pois.md) | POI CRUD + reorder (fractional indexing) | 2 |
| [features.md](./features.md) | 라이브러리 feature read (in-bounds / nearby / weather) | 4 |
| [notice-plans.md](./notice-plans.md) | 추천 plan listing + copy + Admin CRUD | 2/4/6 |
| [storage.md](./storage.md) | presigned PUT + 첨부 등록 + RustFS 관리 | 2 |
| [admin.md](./admin.md) | Admin 엔티티 CRUD + dataset 브라우저 | 3 |
| [health.md](./health.md) | `/health`, `/health/db` | 1 |
| [public.md](./public.md) | 비로그인 listing (beach/festival map markers) | 4 |
| [regions.md](./regions.md) | 행정구역 boundary 조회 (라이브러리 경유) | 4 |
| [websocket.md](./websocket.md) | `WS /ws/trips/{trip_id}` 채널 | 5 |
| [common.md](./common.md) | 응답 형식, 에러 코드, pagination, 인증 헤더, 시간/좌표 | 1~ |

## 2. 공통 규약

자세히는 [common.md](./common.md). 핵심:

- **Base URL**: 개발 `http://localhost:9021`, Docker smoke `http://127.0.0.1:9021`,
  운영 `https://tripmateapi.digitie.mywire.org`.
- **OpenAPI**: FastAPI 자동 생성 `http://localhost:9021/docs`.
- **응답 형식**:

  ```jsonc
  // 성공
  { "data": { ... }, "meta": { "cursor": "...", "has_more": true } }
  // 실패
  { "error": { "code": "EMAIL_NOT_VERIFIED", "message": "...", "details": { ... } } }
  ```

- **에러 코드 표준**: `AUTH_INVALID_CREDENTIALS`, `EMAIL_NOT_VERIFIED`,
  `EMAIL_ALREADY_USED`, `TOKEN_EXPIRED`, `TOKEN_INVALID`, `PERMISSION_DENIED`,
  `RESOURCE_NOT_FOUND`, `VERSION_CONFLICT`, `RATE_LIMITED`, `VALIDATION_ERROR`,
  `INTERNAL_ERROR`, 그 외 도메인별.
- **인증**: httpOnly cookie (`tripmate_access`, `tripmate_refresh`) — JWT 15분 /
  refresh 7일. 자세히는 `docs/integrations/social-login.md` + `docs/spec/v8/02-backend.md`.
- **CSRF**: `SameSite=Lax` cookie + state nonce (OAuth). 별도 CSRF 토큰 없음.
- **Rate limit**: SlowAPI. 로그인/가입/재설정은 IP+이메일 기준 분당 5회.
- **시간**: UTC 저장 → KST(`Asia/Seoul`) 응용 변환. 응답 JSON은 ISO 8601 + offset.
- **좌표**: 입력/응답 모두 `(longitude, latitude)` 순서. EPSG:4326.
- **Pagination**: cursor 기반 (`meta.cursor` + `meta.has_more`). page/limit는 Admin 일부에만.
- **버전 관리**: URL prefix는 v1.0 단계 `/` 또는 `/v1` (Sprint 1에서 ADR로 확정).
- **응답 `X-Request-Id`**: 모든 응답에 헤더 포함. `app.location_access_log` /
  `admin_audit_log` chain 추적용.

## 3. 책임 경계

- 모든 endpoint는 **TripMate가 소유**. URL/응답 셰입은 본 저장소 단일 진실.
- 응답 데이터 일부가 `python-krtour-map`의 `feature.*` schema에서 오면, TripMate
  서비스 레이어가 krtour-map OpenAPI HTTP 계약을 통해 가져와 TripMate 응답 셰입으로
  변환한다. provider/feature 도메인 wrapper class는 금지하고, HTTP client는
  transport 역할만 한다(ADR-026).

## 4. AI agent 작업 가이드

본 API를 구현할 때 (코드 작성 단계 진입 후):

1. **읽는 순서**: `common.md` → 해당 도메인 (예: `auth.md`) → `docs/data-model.md` →
   `docs/postgres-schema.md` → 해당 Sprint plan
2. **Zod schema는 공용 패키지**: `packages/schemas/src/<domain>.ts` 작성 → API
   응답/요청 모두 `packages/schemas`의 schema로 parse. (자세히는
   `docs/architecture/frontend.md`)
3. **Pydantic vs Zod**: 백엔드는 Pydantic v2 (`apps/api/app/schemas/`), 프론트는
   Zod (`packages/schemas/src/`). 둘 다 동일 계약 — 본 API 문서가 그 계약.
4. **테스트 패턴**: `apps/api/tests/integration/test_<route>.py` httpx ASGI 직접
   호출. PostGIS는 testcontainers. 자세히는 `docs/conventions/testing.md`.
5. **새 endpoint 추가**: 본 디렉토리에 endpoint 추가 또는 새 파일 생성 → Pydantic
   schema → Zod schema → 서비스 → 라우터 → 테스트 → `docs/journal.md`.

## 5. 변경 정책

- 응답 셰입 변경은 **BREAKING** 후보 — 반드시 ADR + CHANGELOG + OpenAPI export 갱신.
- 신규 endpoint 추가는 본 README 인덱스 + 도메인 파일에 추가.
- 에러 코드 추가는 `common.md` 표준 목록에도 추가.
- Webhook (`/webhooks/*`)은 별도 디렉토리 또는 `common.md` §webhooks에.

## 6. 관련 문서

- `docs/architecture.md` — 전체 의존 방향
- `docs/spec/v8/02-backend.md` — 외부 SPEC 적용 노트
- `docs/krtour-map-integration.md` — krtour-map OpenAPI HTTP 호출 패턴
- `docs/data-model.md` — DB 모델
- `docs/conventions/coding-style.md` — Python/TS 규칙
