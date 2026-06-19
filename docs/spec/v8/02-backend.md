# SPEC V8 #2 — 백엔드 · 인증 · API (Pinvi 적용 노트)

원본: `spec_v8_2_backend.docx` (B 라이브러리 / C 스택 / F 권한 / G 회원가입 / H API).

## 1. 스택 채택 (C장)

| 계층 | 채택 | 비고 |
|------|------|------|
| API 서버 | FastAPI + Uvicorn | async I/O, OpenAPI 자동 |
| ORM | SQLAlchemy 2 async + GeoAlchemy2 | Pinvi `app` schema만 매핑 |
| 마이그레이션 | Alembic | `apps/api/alembic/versions/...` (app schema 한정) |
| 실시간 동기화 | FastAPI WebSocket | 단일 프로세스. 수평 확장은 v2 (Redis Streams) |
| 작업 큐 | Dagster + PostgreSQL 단발 SKIP LOCKED | Redis 없음 |
| 캐시 | PostgreSQL UNLOGGED + `functools.lru_cache` | 외부 API 응답 |
| 인증 | JWT (access 15m + refresh 7d) + OAuth2 (Google) | refresh는 httpOnly cookie |
| 파일 저장소 | RustFS (S3 호환, ARM64 공식 이미지) | MinIO 마이그레이션 가능 |
| 이메일 | Resend + React Email + Webhook | 도메인 인증 필수 |

`apps/api` 구조 (Sprint 1 진입 PR로 박음):

```
apps/api/
├── pyproject.toml
├── alembic/
├── app/
│   ├── main.py              # FastAPI entry
│   ├── core/
│   │   ├── config.py        # pydantic-settings
│   │   ├── security.py      # JWT, Argon2
│   │   ├── sentry.py
│   │   ├── logging.py       # structlog
│   │   └── deps.py
│   ├── middleware/
│   │   ├── request_id.py
│   │   ├── location_audit.py    # O-3
│   │   └── admin_audit.py       # O-6
│   ├── api/v1/
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── trips.py
│   │   ├── pois.py
│   │   ├── features.py      # 라이브러리 경유 read
│   │   ├── admin/
│   │   └── ws.py
│   ├── models/              # app schema만
│   ├── schemas/             # Pydantic
│   ├── services/
│   ├── repositories/        # app schema raw SQL
│   ├── clients/
│   │   └── kor_travel_map.py    # kor-travel-map OpenAPI HTTP client
│   └── webhooks/
│       └── resend.py
└── tests/{unit,integration,e2e}/
```

## 2. 라이브러리 의존 (B-1)

| 라이브러리 | Pinvi 사용처 |
|-----------|----------------|
| `kor-travel-map` | 라이브러리 본체 (모든 feature read/write) |
| `python-kraddr-base` | 좌표/주소/카테고리 base 타입 — DTO/응답에 사용 |
| `kor-travel-geo` | 주소 검색/지오코딩 — `app.users.sigungu_code` 검증 등 |
| `python-vworld-api` | (라이브러리 경유) — 직접 호출 안 함 |
| `python-visitkorea-api` 등 모든 provider client | Dagster asset이 라이브러리 client에 주입 |

**wrapper 금지**: SPEC V8 R-1 + ADR-005. Pinvi에 `KorTravelMapGateway` /
`KmaWrapper` 같은 어댑터 클래스 만들지 않는다.

## 3. 권한 / 공유 (F장)

### 3.1 권한 매트릭스

| 권한 | 관리자 | 리더 | 동반자 | 공유링크 | 비로그인 |
|------|-------|-----|-------|---------|---------|
| 여행 보기 | ✓ | ✓ | ✓ | 토큰 시 | ✗ |
| 여행 메타 편집 | ✓ | ✓ | ✓ | ✗ | ✗ |
| POI CRUD | ✓ | ✓ | ✓ | ✗ | ✗ |
| 여행 삭제 | ✓ | ✓ | ✗ | ✗ | ✗ |
| 리더 이관 | ✓ | ✓ | ✗ | ✗ | ✗ |
| 동반자 추가/제거 | ✓ | ✓ | ✗ | ✗ | ✗ |
| 공유 링크 발급/취소 | ✓ | ✓ | ✗ | ✗ | ✗ |
| Feature DB 편집 | ✓ | 요청만 | 요청만 | ✗ | ✗ |

(F-1) 동반자가 동반자 추가/공유 발급할 수 없음 — 단순화.

### 3.2 공유 토큰 (F-2)

- `CHAR(43)` URL-safe base64, 256bit 엔트로피
- 기본 만료 30일 (사용자가 변경 가능)
- revoke 즉시 차단
- URL: `https://pinvi.example.com/trips/{trip_id}/share/{token}`
- rate limit: 토큰당 분당 60회 (스크래핑 방지)

### 3.3 소셜 로그인 매칭 (F-3, G-4)

Google OAuth `email_verified` 신뢰 신호 사용. 안전 매칭:

```
email_verified == false → 거부
└─ 같은 email user 있고 verified=true → 자동 연결
└─ 같은 email user 있고 verified=false → 거부 ("기존 가입 인증 먼저")
└─ 없음 → 신규 user (verified=true, google_sub=sub)
```

연결 해제: 비밀번호 설정돼 있을 때만 허용 (소셜-only는 로그인 수단 사라짐).

## 4. 회원가입 / 인증 (G장)

### 4.1 상태 머신

`Anonymous → PendingEmailVerification → PendingProfileCompletion → Active`

(G-1) 모든 가입 경로 동일 상태 머신.

### 4.2 4 분리 동의 (G-5)

- (필수) 이용약관 / 개인정보 처리방침 / 위치기반서비스 이용약관 / 위치정보 수집·이용
- (선택) 성별·생년월 통계·추천 / 거주지 추천 / 마케팅 이메일

위치 동의 철회 → 위치 기록 즉시 삭제 + 위치 기능 비활성.

### 4.3 Resend 이메일 (G-6)

- 도메인 인증 필수: SPF / DKIM / DMARC
- From: `Pinvi <noreply@send.pinvi.example>` (서브도메인 분리)
- 백엔드: `services/email_service.py` + `email_queue` 테이블 + worker
- 템플릿: react-email (`emails/*.tsx`) — 빌드 시 정적 HTML export → 백엔드 변수 치환
- Webhook (`/webhooks/resend`): Svix 서명 검증 → `email.delivered` /
  `email.bounced` / `email.complained` 처리
- 영구 bounce → `users.email_status='bounced'` + 발송 차단
- 스팸 신고 → 즉시 차단 + audit log

템플릿 종류: `verify_email`, `reset_password`, `trip_invite`,
`share_link_notice`, `password_changed`, `weekly_digest`(v2).

## 5. API 명세 (H장)

OpenAPI 자동 생성. 핵심 엔드포인트:

### 5.1 인증 (H-1)

`POST /auth/signup` / `GET /auth/verify-email` / `POST /auth/login` /
`POST /auth/refresh` / `POST /auth/logout` /
`POST /auth/password/reset-request` / `POST /auth/password/reset` /
`GET /auth/oauth/google` / `GET /auth/oauth/google/callback`

미인증 로그인 시 `401 EMAIL_NOT_VERIFIED` + 재발송 옵션.

### 5.2 사용자 (H-2)

`GET /users/me` / `POST /users/profile/complete` / `PATCH /users/me` /
`GET /users/me/consents` / `POST /users/me/consents/withdraw` /
`POST /users/me/avatar` / `POST /users/me/oauth/google/disconnect` /
`DELETE /users/me`

회원 탈퇴 시 리더인 여행 있으면 `410` + 이관 안내.

### 5.3 여행 / POI (H-3)

`GET/POST /trips` / `GET/PATCH/DELETE /trips/{id}` / `POST /trips/{id}/copy` /
`POST/DELETE /trips/{id}/members[/{key}]` /
`POST/DELETE /trips/{id}/share-tokens[/{token}]` /
`GET /trips/{id}/shared/{token}` /
`GET /trips/{id}/exports/{print-data,gpx,pdf}` /
`POST/PATCH/DELETE /trips/{id}/pois[/{poi_id}]` /
`POST /trips/{id}/pois/reorder`

POI 편집은 `If-Match: version` (optimistic lock, J-2).

### 5.4 Feature / 지도 (H-4)

- `GET /features/in-bounds?bounds=&zoom=&kinds[]=` — viewport 쿼리 + zoom별 클러스터 (I-4)
- `GET /features/{id}` — kor-travel-map OpenAPI 호출
- `GET /features/{id}/weather` — `WeatherCard` (KMA 시간축 + sources 배열, R-4)
- `GET /features/nearby?lat=&lng=&radius_m=` — 주변
- `GET /features/search?q=` — 장소 feature 검색 (kor-travel-map HTTP)
- `POST /features/requests` — 사용자 요청 → Admin 큐 (`app.feature_suggestions`, kor_travel_map 직접 호출 X)
- `GET /features/requests/{id}` — 본인 요청 상태 조회
- `GET /search?q=` — 통합 검색 (2자 이상, T-129)

kor-travel-map OpenAPI 호출 패턴은 `docs/kor-travel-map-integration.md`.

### 5.5 WebSocket (H-5)

`WS /ws/trips/{trip_id}?token=<jwt>` — 권한 없으면 close 4403.

이벤트:

- `poi.created` / `poi.updated` / `poi.deleted` / `poi.reordered`
- `day.created` / `day.updated` / `day.deleted`
- `trip.updated` / `trip.member_changed` / `presence.update` / `ping` / `error`

`version`(단조증가), `actor_user_id`(자기 이벤트는 클라이언트가 무시) 포함.

### 5.6 Admin (H-6, M장)

13개 페이지 — 자세히는 `docs/spec/v8/04-admin.md`.

### 5.7 응답 형식 (H-7)

```jsonc
// 성공
{ "data": { ... }, "meta": { "cursor": "...", "has_more": true } }

// 실패
{ "error": { "code": "EMAIL_NOT_VERIFIED", "message": "...", "details": { ... } } }
```

에러 코드: `AUTH_INVALID_CREDENTIALS`, `EMAIL_NOT_VERIFIED`,
`EMAIL_ALREADY_USED`, `TOKEN_EXPIRED`, `TOKEN_INVALID`, `PERMISSION_DENIED`,
`RESOURCE_NOT_FOUND`, `VERSION_CONFLICT`, `RATE_LIMITED`, `VALIDATION_ERROR`,
`INTERNAL_ERROR`.

## 6. 일정 자동 최적화 (H-8)

`POST /trips/{id}/days/{day_index}/optimize`:

- POI ≤ 10: PostGIS 직선 거리 (1초 내)
- POI 11 ~ 20: 카카오 모빌리티 길찾기 API (cache TTL 1시간) — 3 ~ 5초
- POI > 20: "분할 권장" 안내 + 직선 거리
- OR-Tools (Routing + Simulated Annealing, 5초 limit)
- 응답: `{ reordered_pois, total_distance_km, total_duration_min }`
- 클라이언트가 미리보기 → "적용" 클릭 시 sort_order 재배치 + WebSocket broadcast

`GET /trips/{id}/days/{day_index}/distance-matrix` — POI 간 거리 행렬 (UI 라벨).

## 7. Sprint 매핑

| SPEC V8 항목 | Sprint | 본 저장소 산출물 |
|------|--------|------------------|
| FastAPI scaffolding (C) | Sprint 1 | `apps/api/app/main.py` + `core/config.py` |
| Argon2id + JWT (G-3) | Sprint 1 | `apps/api/app/core/security.py` |
| `/auth/signup` + verify (G-3, H-1) | Sprint 1 | `apps/api/app/api/v1/auth.py` |
| Resend 통합 + `email_queue` worker (G-6, M-6) | Sprint 2 | `apps/api/app/services/email_service.py` |
| 4 분리 동의 (G-5) | Sprint 2 | `apps/api/app/services/consent.py` |
| Google OAuth + 안전 매칭 (G-4, F-3) | Sprint 2 | `apps/api/app/services/oauth_google.py` |
| 위치 감사 미들웨어 (O-3) | Sprint 2 | `apps/api/app/middleware/location_audit.py` |
| Trip CRUD + 공유 토큰 (H-3, F-2) | Sprint 2 | `apps/api/app/api/v1/trips.py` |
| POI CRUD + optimistic lock (H-3, J-2) | Sprint 2 | `apps/api/app/api/v1/pois.py` |
| Feature read (H-4) | Sprint 4 | `apps/api/app/api/v1/features.py` |
| Admin H-6 (`api_call_log`, `feature_suggestions` 등) | Sprint 3 | `apps/api/app/api/v1/admin/` |
| Webhook Resend (G-6) | Sprint 2 | `apps/api/app/webhooks/resend.py` |
| WebSocket (H-5, J-1) | Sprint 5 | `apps/api/app/api/v1/ws.py` |
| OR-Tools 일정 최적화 (H-8) | Sprint 6 | `apps/api/app/services/route_optimizer.py` |

## 8. 관련 문서

- `docs/architecture.md` §2 백엔드 의존 방향
- `docs/kor-travel-map-integration.md` (kor-travel-map OpenAPI HTTP)
- `docs/spec/v8/00-infrastructure.md` (Sentry/Loki/Argon2)
- `docs/spec/v8/01-data.md` (DB schema)
- `docs/spec/v8/03-frontend.md` (WebSocket 클라이언트 쌍)
- `docs/spec/v8/04-admin.md` (Admin API)
