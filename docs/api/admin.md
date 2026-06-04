# Admin API (`/admin/*`)

Admin 콘솔의 모든 endpoint. 13개 페이지 인덱스는 [`docs/spec/v8/04-admin.md`](../spec/v8/04-admin.md).
RBAC 상세는 [`docs/architecture/admin-rbac.md`](../architecture/admin-rbac.md) (작성 예정).
공통 규약 [`common.md`](./common.md).

## 1. 인증 / 권한

- 사용자와 동일한 cookie 인증 (`tripmate_access`, `tripmate_refresh`)
- 권한 검사는 `app.users.roles` 배열에 `admin` / `operator` / `cpo` 포함 여부
- 미권한 사용자 → **`404 Not Found`** (존재 자체 숨김 — `403` 대신)
- 모든 mutating 액션은 `app.admin_audit_log`에 자동 기록 (chain prev_hash/content_hash)
- 위험 액션은 `access_reason` 입력 강제 (request body 또는 별도 헤더)

자세히는 SPEC V8 M-4 / O-6.

## 2. 인덱스

| Path | 용도 | Sprint |
|------|------|--------|
| `GET /admin/stats/overview` | 대시보드 카드 8개 | 3 |
| `GET /admin/users` / `{user_id}` / `PATCH` | 사용자 목록 / 상세 / 편집 | 3 |
| `POST /admin/users/{id}/force-verify` | 강제 verify (디버그) | 3 |
| `POST /admin/users/{id}/resend-verify` | 인증 메일 재발송 | 3 |
| `POST /admin/users/{id}/disable` | 비활성화 (refresh 전부 revoke) | 3 |
| `GET /admin/trips` / `{trip_id}` | trip 목록 / 상세 | 3 |
| `GET /admin/features` | 라이브러리 feature 검색 (read-only) | 3 |
| `GET /admin/pois` | POI 검색 (`feature_link_broken_at` 필터) | 3 |
| `GET /admin/datasets` | dataset 카탈로그 | 3 |
| `GET /admin/datasets/{table_name}/rows` | row 조회 (검색/필터/정렬/page) | 3 |
| `GET/POST/PATCH/DELETE /admin/entities/{entity}[/{item_id}]` | 통합 엔티티 CRUD | 3 |
| `GET /admin/api-calls` | 외부 API 호출 로그 (`api_call_log`) | 3 |
| `GET /admin/emails` | 이메일 발송 큐 (`email_queue`) | 3 |
| `POST /admin/emails/{id}/resend` | 재발송 | 3 |
| `GET /admin/audit` | `admin_audit_log` (read-only, chain 검증) | 3 |
| `GET /admin/audit/location` | `location_access_log` (CPO 권한만) | 3 |
| `GET/POST /admin/notice-plans[/{plan_id}]` / `PATCH` / `DELETE` | Notice plan CRUD | 6 |
| `POST /admin/notice-plans/{plan_id}/pois[/reorder]` | Notice POI | 6 |
| `GET/POST/DELETE /admin/feature-requests[/{id}]` | 사용자 feature 요청 큐 | 6 |
| `POST /admin/feature-requests/{id}/approve` | 승인 → 라이브러리 적재 trigger | 6 |
| `GET/PUT /admin/category-mappings` | maki + 16색 매핑 | 6 |
| `GET /admin/etl/*` | Dagit reverse-proxy + 자체 요약 | 5 |
| `GET /admin/dedup-review` / `POST /admin/dedup-review/{id}/verdict` | Record Linkage 검토 큐 | 5 |
| `GET /admin/features/{id}/sources` | source_links | 5 |
| `GET /admin/features/{id}/overrides` | feature_overrides | 5 |
| `GET /admin/features/{id}/weather-values` | weather timeline | 5 |
| `GET /admin/provider-sync` / `POST {id}/{action}` | provider_sync_state 관리 | 5 |
| `GET /admin/integrity` / `POST /admin/integrity/{rule}/fix` | data_integrity_violations | 5 |
| `WS /admin/debug/logs` | Loki LogQL stream | 5 |
| `GET /admin/debug/request/{request_id}` | X-Request-Id 타임라인 | 5 |
| `GET /admin/rustfs/objects` / `DELETE` | RustFS 객체 관리 | 2 |
| `POST /admin/seed/*` | dev/staging seed 시나리오 (운영 차단) | 3 |
| `POST /admin/reset` | DB reset (dev/staging only) | 3 |

## 3. 대시보드

### 3.1 `GET /admin/stats/overview`

응답 200:

```jsonc
{
  "data": {
    "users_total": 1234,
    "users_24h": 42,
    "users_pending_verification": 18,
    "trips_total": 567,
    "trips_active": 234,
    "features_by_kind": { "place": 12345, "event": 234, "...": 0 },
    "pois_total": 789,
    "etl_last_24h": { "success": 12, "failed": 1 },
    "api_rate_limit_remaining": { "kma": 0.85, "visitkorea": 0.92 },
    "email_queue_pending": 3
  }
}
```

병렬 쿼리로 한 번에. 일부 `feature` schema 카운트는 krtour-map ops/admin OpenAPI
(`/ops/metrics` 등)로 조회한다.

## 4. 통합 엔티티 CRUD (`/admin/entities/{entity}`)

SPEC V8 M-8 패턴. v1의 `admin_entity_crud.py` 이전.

`entity`: `users` | `features`(read-only) | `trips` | `pois` | `notice-plans` | `notice-pois` |
`category-mappings` | `feature-requests`.

### 4.1 `GET /admin/entities/{entity}`

```http
GET /admin/entities/users?q=email:gmail.com+-status:disabled&sort=-created_at&page=1&limit=100
```

검색 문법은 SPEC V8 M-9 — [`common.md`](./common.md) §7.

### 4.2 `POST /admin/entities/{entity}` (생성 가능 entity만)

- `users` — ✗ (가입 흐름 사용)
- `features` — ✗ (라이브러리에 요청)
- `trips` — ✗ (사용자 흐름)
- `notice-plans` / `notice-pois` / `category-mappings` / `feature-requests` — ✓

### 4.3 `PATCH /admin/entities/{entity}/{item_id}`

- `If-Match: <version>` 필수
- `access_reason` body 또는 `X-Access-Reason` 헤더 (위험 액션 시)
- `admin_audit_log` 자동 기록 (before/after diff)

### 4.4 `DELETE /admin/entities/{entity}/{item_id}`

| Entity | 동작 |
|--------|------|
| `users` | `status = 'deleted'`, `is_active = false` (soft, 30일 후 hard delete schedule) |
| `features` | (라이브러리에 요청 — `feature.status='hidden'`) |
| `trips` | `status = 'archived'`, `deleted_at = now()` (soft) |
| `pois` | hard delete |
| `notice-plans` | soft delete |
| `notice-pois` | soft delete |
| `category-mappings` | hard delete |
| `feature-requests` | hard delete (`status='rejected'` 권장) |

자기 자신 disable / admin 권한 박탈 차단 — `403 PERMISSION_DENIED`
(`details.reason: "cannot_modify_self"`).

## 5. Dataset 브라우저

v1 `admin_data_browser.py` 이전. krtour-map 소유 schema가 분리됐으므로 일부 dataset
은 krtour-map admin/ops OpenAPI 경유.

### 5.1 `GET /admin/datasets`

```jsonc
{
  "data": {
    "datasets": [
      { "schema": "app", "table_name": "notice_plans", "owner": "tripmate", "row_count": 42 },
      { "schema": "feature", "table_name": "features", "owner": "krtour-map", "row_count": 12345 },
      { "schema": "feature", "table_name": "source_records", "owner": "krtour-map", "row_count": 67890 },
      { "schema": "provider_sync", "table_name": "state", "owner": "krtour-map", "row_count": 12 }
    ]
  }
}
```

**제외**: `users`, `user_sessions`, `user_email_verifications`, `user_oauth_identities`,
`trips`, `trip_days`, `trip_day_pois`, `user_consents`, `location_access_log`,
`admin_audit_log`. PII / 보안 민감 테이블은 `/admin/entities/users`로만 접근.

### 5.2 `GET /admin/datasets/{table_name}/rows`

```http
GET /admin/datasets/notice_plans/rows?search=부산&sort_by=updated_at&sort_dir=desc&limit=100&filter.is_published=true
```

- `limit`: `50` / `100` / `200` / `500`
- 정렬: `sort_by` + `sort_dir` (`asc` / `desc`)
- 필드별 필터: `filter.<column>=<value>` (부분 일치 LIKE)
- 자유 텍스트 검색: `search=...` (텍스트 컬럼 OR ILIKE)
- 응답: `data.rows` 배열 + `meta.total` + `meta.has_more`

geometry는 `ST_AsText`로 직렬화. JSONB는 그대로 반환. krtour-map 소유 schema는
TripMate가 직접 table browse하지 않고 krtour-map admin/offline/ops OpenAPI로
조회한다.

## 6. 사용자 관리

### 6.1 `POST /admin/users/{user_id}/force-verify`

```http
POST /admin/users/<user_id>/force-verify
Content-Type: application/json
X-Access-Reason: "고객 문의 처리 (TICKET-1234)"

{}
```

- `users.email_verified_at = now()`, `status = 'pending_profile'`
- `admin_audit_log` + Resend webhook 없이 강제 진입 표시
- 응답 200: 갱신된 user

### 6.2 `POST /admin/users/{user_id}/resend-verify`

- 새 verify 토큰 발급 + Resend 발송
- 기존 verify 토큰 `used_at = now()`로 폐기

### 6.3 `POST /admin/users/{user_id}/disable`

- `users.status = 'disabled'`, `is_active = false`
- 모든 `user_sessions.revoked_at = now()`
- 응답 204

### 6.4 PII 마스킹

`GET /admin/entities/users` 목록 응답:

- `email`: `a***@gmail.com` (사유 입력 후 `?reveal=true&reason=...`로 원본 표시)
- `nickname`: 그대로
- `birth_year_month`: 그대로 (선택 동의 받은 경우만)
- `residence_sigungu_code`: 그대로 (선택 동의 받은 경우만)

상세 `GET /admin/entities/users/{user_id}`:

- 기본 마스킹. `?reveal=true` + `X-Access-Reason` 헤더 → 원본 + `admin_audit_log`에
  `target_pii_fields = ["email", "phone", ...]` 기록

## 7. 위치 감사 로그 (CPO 권한)

### 7.1 `GET /admin/audit/location`

```http
GET /admin/audit/location?user_id=<uid>&from=2026-05-01&to=2026-05-31&limit=100
```

- `cpo` 역할만 SELECT
- content_hash chain 자동 검증 — 깨진 row가 있으면 응답 헤더 `X-Chain-Broken: true`
  + Sentry alert
- 응답에는 좌표 정밀도 4자리로 mask (raw 6자리 표시는 별도 endpoint, 더 강한 사유 검증)

## 8. Notice Plan 관리

자세히는 [`notice-plans.md`](./notice-plans.md) Admin 섹션.

## 9. ETL / Record Linkage / 데이터 일관성

SPEC V8 M-10 ~ M-11.

### 9.1 `GET /admin/dedup-review`

라이브러리 `dedup_review_queue` 호출.

```jsonc
{
  "data": {
    "items": [
      {
        "id": "uuid",
        "a_feature_id": "f_...",
        "b_feature_id": "f_...",
        "score": 0.78,
        "candidate_a": { /* feature snapshot */ },
        "candidate_b": { /* feature snapshot */ }
      }
    ]
  }
}
```

### 9.2 `POST /admin/dedup-review/{id}/verdict`

```jsonc
{ "verdict": "merge_a_into_b" | "merge_b_into_a" | "not_same" | "uncertain", "reason": "..." }
```

krtour-map dedup verdict는 krtour-map admin OpenAPI로 callback한다.

### 9.3 `GET /admin/provider-sync`

```jsonc
{
  "data": {
    "items": [
      {
        "provider": "python-visitkorea-api",
        "dataset_key": "search_festival",
        "sync_scope": "rolling_12m",
        "cursor": "2026-05-25T10:00:00Z",
        "last_success_at": "...",
        "last_attempt_at": "...",
        "next_run_after": "...",
        "last_error": null
      }
    ]
  }
}
```

### 9.4 `POST /admin/provider-sync/{id}/{action}`

`action`: `pause` | `resume` | `retry` | `reset_cursor`.

### 9.5 `GET /admin/integrity`

`app.data_integrity_violations` + 라이브러리 자체 violations 합쳐 표시.

## 10. 디버그 콘솔

### 10.1 `WS /admin/debug/logs`

Loki LogQL을 백엔드에서 호출 → WebSocket으로 push.

```jsonc
// 클라이언트 → 서버 첫 메시지
{ "type": "subscribe", "query": "{service=\"fastapi\", level=\"error\"} |= \"trip_id=abc\"" }

// 서버 → 클라이언트
{ "type": "log", "ts": "...", "service": "...", "level": "ERROR", "msg": "...", "extra": {...} }
{ "type": "subscribed", "stream_id": "..." }
{ "type": "error", "message": "LogQL syntax error" }
```

### 10.2 `GET /admin/debug/request/{request_id}`

X-Request-Id 기반 단일 요청 타임라인. structlog 로그 + Sentry transaction +
`app.api_call_log` row 합쳐 보여줌.

## 11. Seed / Reset (dev/staging only)

### 11.1 `POST /admin/seed/scenarios/{scenario_key}`

`scenario_key`: SPEC V8 M-13 8 시나리오 키 (`new_user_first_trip` 등).

운영 환경에서는 라우트 자체 비활성 (`ENABLE_SEED` 환경변수 false → router include
안 함). 404.

### 11.2 `POST /admin/reset`

```jsonc
{ "confirm": "RESET", "admin_password": "..." }
```

- dev/staging에서만 라우트 등록
- DB 전체 reset (`alembic downgrade base` → `upgrade head`)
- 라이브러리 schema는 별도 reset endpoint (`POST /admin/krtour-map/reset`)
- 자동으로 `new_user_first_trip` 시나리오 적용

## 12. AI agent 구현 체크리스트

- [ ] `apps/api/app/api/v1/admin/__init__.py` 라우터 분기
- [ ] `apps/api/app/api/v1/admin/{users,trips,features,pois,datasets,entities,audit,etl,dedup,integrity,debug,seed,reset,rustfs}.py`
- [ ] `apps/api/app/services/admin/{entity_browser,entity_crud,audit_chain,seed_scenarios,reset}.py`
- [ ] `apps/api/app/middleware/admin_audit.py` (chain prev_hash + content_hash)
- [ ] `apps/api/app/middleware/rbac.py` (`roles` 검사 + 404 변환)
- [ ] 통합 테스트 + RBAC 거부 e2e + chain 검증
- [ ] 운영 환경 `ENABLE_SEED=false` 시 seed/reset 라우트 404 확인
