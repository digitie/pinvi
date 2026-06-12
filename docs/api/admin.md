# Admin API (`/admin/*`)

Admin 콘솔의 모든 endpoint. 13개 페이지 인덱스는 [`docs/spec/v8/04-admin.md`](../spec/v8/04-admin.md).
RBAC 상세는 [`docs/architecture/admin-rbac.md`](../architecture/admin-rbac.md) (작성 예정).
공통 규약 [`common.md`](./common.md).

## 1. 인증 / 권한

- 사용자와 동일한 cookie 인증 (`tripmate_access`, `tripmate_refresh`)
- 권한 검사는 `app.users.roles` 배열에 `admin` / `operator` / `cpo` 포함 여부
- 미권한 사용자 → **`404 Not Found`** (존재 자체 숨김 — `403` 대신)
- 모든 mutating 액션은 `app.admin_audit_log`에 자동 기록 (`prev_hash` unique +
  advisory lock 기반 chain)
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
| `GET /admin/pois` / `{poi_id}` | 여행 POI 검색 / 상세 (`feature_link_broken_at` 필터) | 3 |
| `PATCH /admin/pois/{poi_id}/link-status` | POI feature 연결 상태 로컬 표시 | 3 |
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
| `GET /admin/feature-requests` | 사용자 feature 제안 검토 큐 (§8.4) | 8 |
| `POST /admin/feature-requests/{id}/approve\|reject` | 검토 → krtour `/v1/admin/features*` 릴레이 | 8 |
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
| `GET /admin/backup/snapshots` | `app` schema backup snapshot 목록 | 5 |
| `POST /admin/backup/snapshot` | 수동 backup snapshot 생성 + audit | 5 |
| `GET/POST /admin/mcp-tokens` / `{token_id}/revoke` | MCP 토큰 검색 / 대리 발급 / 강제 회수 | 6 |
| `GET /admin/rustfs/objects` / `DELETE` | RustFS 객체 관리 | 2 |
| `POST /admin/seed/*` | dev/staging seed 시나리오 (운영 차단) | 3 |
| `POST /admin/reset` | DB reset (dev/staging only) | 3 |

## 3. 대시보드

### 3.1 `GET /admin/stats/overview`

TripMate app schema에서 계산 가능한 지표만 즉시 반환한다. `features_by_kind`와
`etl_last_24h`는 krtour-map admin/ops 및 Dagster 요약 API가 결선될 때까지 빈 값/0값이다.

응답 200:

```jsonc
{
  "data": {
    "users_total": 1234,
    "users_24h": 42,
    "users_pending_verification": 18,
    "trips_total": 567,
    "trips_active": 234,
    "pois_total": 789,
    "email_queue_pending": 3,
    "api_calls_24h": 91,
    "api_calls_failed_24h": 2,
    "features_by_kind": {},
    "etl_last_24h": { "success": 0, "failed": 0 }
  }
}
```

권한: `admin` / `operator`.

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
- `access_reason` body 또는 `X-Access-Reason` 헤더 (위험 액션 시). PII 원본 조회처럼
  자유 텍스트 사유가 필요한 액션은 URL과 header에 남기지 않고 JSON body만 허용한다.
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
      { "schema": "app", "table_name": "curated_trip_plans", "owner": "tripmate", "row_count": 42 },
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
GET /admin/datasets/curated_trip_plans/rows?search=부산&sort_by=updated_at&sort_dir=desc&limit=100&filter.is_published=true
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

### 6.0 `GET /admin/users`

```http
GET /admin/users?q=kim&status_filter=active&page=1&limit=50
```

- `q`: 이메일 / 닉네임 부분 일치, `user_id` UUID 정확 일치
- `status_filter`: `pending_verification` / `pending_profile` / `active` / `disabled`
- 목록 응답은 항상 `email_masked`만 제공하고 원본 이메일은 포함하지 않는다.

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
- 응답 200: 갱신된 user + 최근 audit

### 6.4 PII 마스킹

`GET /admin/users` 목록 응답:

- `email_masked`: `a***@gmail.com`
- `nickname`: 그대로
- `birth_year_month`: 그대로 (선택 동의 받은 경우만)
- `residence_sigungu_code`: 그대로 (선택 동의 받은 경우만)

상세 `GET /admin/users/{user_id}`:

- 기본 마스킹. `?reveal=true`는 legacy misuse로 보고 `422`로 거부한다.
- 상세 응답은 `recent_audit` 최근 10건을 포함한다.

원본 이메일 조회:

```http
POST /admin/users/<user_id>/reveal-pii
Content-Type: application/json

{ "access_reason": "고객 문의 확인" }
```

- 응답 200: 원본 이메일 포함 상세 + `email_revealed=true`.
- `admin_audit_log`에 `action = "user.reveal_pii"`,
  `target_pii_fields = ["email"]`, `access_reason` 기록.
- 사유는 URL query/header가 아닌 JSON body로만 전달한다.

## 7. 여행계획 관리

### 7.1 `GET /admin/trips`

```http
GET /admin/trips?q=busan&status_filter=planned&visibility_filter=private&page=1&limit=50
```

- 권한: `admin` / `operator`
- `q`: 제목 / 지역 힌트 / `primary_region_code` / owner 이메일 부분 일치,
  `trip_id` 또는 `owner_user_id` UUID 정확 일치
- `status_filter`: `draft` / `planned` / `in_progress` / `completed` / `archived`
- `visibility_filter`: `private` / `unlisted` / `public`
- `owner_user_id`: 특정 소유자 UUID
- 목록 응답은 owner 이메일 원본을 포함하지 않고 `owner_email_masked`만 제공한다.
- 각 row는 `day_count`, `poi_count`, `companion_count`, `share_link_count`를 포함한다.
- 각 row는 `region_hint`와 함께 구조화 지역 키
  `primary_region_code`/`primary_region_source`를 포함한다.

### 7.2 `GET /admin/trips/{trip_id}`

- 권한: `admin` / `operator`
- 기본 여행 필드 + `description`
- `companions`: 초대 이메일은 `invited_email_masked`로만 제공
- `share_links`: token 원문/해시는 반환하지 않고 share row metadata만 제공
- `recent_audit`: 해당 trip의 최근 `admin_audit_log` 10건

### 7.3 `PATCH /admin/trips/{trip_id}/status`

```http
PATCH /admin/trips/<trip_id>/status
Content-Type: application/json

{
  "status": "archived",
  "access_reason": "운영 정책 위반 처리"
}
```

- 권한: `admin`
- `access_reason` 필수
- `trips.status`를 변경하고 `version`을 1 증가시킨다.
- `admin_audit_log`에 `action = "trip.update_status"`를 기록한다.

## 8. POI 관리

POI Admin은 TripMate 소유 `app.trip_day_pois` 첨부 행만 관리한다. `feature_id`
재연결이나 feature 원천 데이터 수정은 krtour-map OpenAPI client 준비 후 별도 작업으로
진행한다.

### 8.1 `GET /admin/pois`

```http
GET /admin/pois?q=haeundae&has_broken_link=false&page=1&limit=50
```

- 권한: `admin` / `operator`
- `q`: `feature_id`, `feature_snapshot` JSON, trip 제목, owner 이메일 부분 일치,
  `attachment_id` / `trip_id` / `owner_user_id` UUID 정확 일치
- `trip_id`: 특정 여행 UUID
- `has_broken_link`: `true`면 `feature_link_broken_at IS NOT NULL`, `false`면 정상
  연결 표시 행만 조회
- 목록 응답은 owner 이메일 원본을 포함하지 않고 `owner_email_masked`만 제공한다.

응답 row:

```jsonc
{
  "attachment_id": "uuid",
  "trip_id": "uuid",
  "trip_title": "부산 가족 여행",
  "owner_user_id": "uuid",
  "owner_email_masked": "o***@example.com",
  "day_index": 1,
  "sort_order": "a0",
  "feature_id": "place-haeundae",
  "feature_label": "해운대 해수욕장",
  "feature_link_broken_at": null,
  "version": 1,
  "created_at": "2026-06-06T10:00:00+09:00",
  "updated_at": "2026-06-06T11:00:00+09:00"
}
```

### 8.2 `GET /admin/pois/{poi_id}`

- 권한: `admin` / `operator`
- 목록 row + `added_by_email_masked`, `feature_snapshot`, marker override, 예정 시각,
  메모, 예산/실사용 금액, 사용자 URL, 최근 `admin_audit_log` 10건을 반환한다.
- owner / added_by 이메일은 항상 마스킹한다.

### 8.3 `PATCH /admin/pois/{poi_id}/link-status`

```http
PATCH /admin/pois/<poi_id>/link-status
Content-Type: application/json

{
  "broken": true,
  "access_reason": "feature_id 점검 결과 끊김"
}
```

- 권한: `admin`
- `access_reason` 필수
- `broken = true`면 `feature_link_broken_at`을 현재 시각으로 설정하고, `false`면
  `NULL`로 되돌린다.
- 실제 값이 바뀐 경우 `trip_day_pois.version`을 1 증가시킨다.
- `admin_audit_log`에 `action = "poi.update_link_status"`를 기록한다.

### 8.4 사용자 feature 제안 검토 큐 (T-179)

사용자 제안(`app.feature_suggestions`, T-177)을 Admin이 검토해 승인/거절한다. 승인 시
krtour `/v1/admin/features*` change API(전송 client = T-180, `:12301 /v1/admin/*`)로 전달한다.
**TripMate는 신규 수신 API를 만들지 않고 krtour 기존 change API를 전송 구간으로 쓴다**
(krtour ADR-051). `apps/api/app/api/v1/admin/feature_requests.py`.

```
GET    /admin/feature-requests?status=pending&page=&limit=     # admin/operator, 이메일 마스킹, FIFO
POST   /admin/feature-requests/{request_id}/approve            # admin
POST   /admin/feature-requests/{request_id}/reject             # admin
```

- **approve** (`access_reason` 필수 + audit): `suggestion_type`별 분기 —
  - `new_place` → krtour `POST /v1/admin/features` (`category`(8자리 코드)/`marker_color`/
    `marker_icon`은 사용자 제안에 없어 **Admin이 검토하며 body로 채운다** — 누락 시 422).
  - `correction` → `PATCH /v1/admin/features/{target_feature_id}` (override 일부).
  - `closure` → `DELETE /v1/admin/features/{target_feature_id}` (soft).
  - krtour 호출을 **먼저** 하고 성공 시에만 commit한다(실패 시 제안 `pending` 유지 → 재시도).
    반환 `feature_id`/`request_id`/state를 `krtour_ref`에 저장하고 상태를 `applied`면 `added`,
    그 외(require_review 큐 적재)면 `approved`로 둔다. `idempotency_key = request_id`,
    출처 태깅 `operator = tripmate-admin:{admin_id}`(익명, D-11).
- **reject**: krtour 호출 없이 `status = rejected` + audit.
- **§7 미확정**(krtour T-217c): review_mode/idempotency/출처태깅/admin인증/closure 합의는 문서화된
  기본값으로 진행하며 확정 시 조정한다.

## 9. API 호출 로그

### 9.1 `GET /admin/api-calls`

```http
GET /admin/api-calls?provider=kma&status_code=200&error_class=Timeout&limit=100
```

- 권한: `admin` / `operator`
- `app.api_call_log`를 `occurred_at DESC, log_id DESC`로 반환한다.
- 필터: `provider`, `status_code`, `error_class`, `limit(1~500)`
- 응답 row: `log_id`, `provider`, `endpoint`, `status_code`, `latency_ms`,
  `error_class`, `error_message`, `request_id`, `occurred_at`

## 10. 위치 감사 로그 (CPO 권한)

### 10.1 `GET /admin/audit/location`

```http
GET /admin/audit/location?user_id=<uid>&from=2026-05-01&to=2026-05-31&limit=100
```

- `cpo` 역할만 SELECT
- content_hash chain 자동 검증 — 깨진 row가 있으면 응답 헤더 `X-Chain-Broken: true`
  + Sentry alert
- 응답에는 좌표 정밀도 4자리로 mask (raw 6자리 표시는 별도 endpoint, 더 강한 사유 검증)

## 11. 상태 강등 / 후속 결선

- `/admin/features`: feature read/edit는 `python-krtour-map` admin API 기준으로 결선한다.
  TripMate가 feature 정규화·저장 책임을 가져오지 않는다.
- `/admin/etl`: Dagster/Dagit reverse proxy와 자체 요약은 Sprint 5 결선.
- `/admin/seed`, `/admin/reset`: dev/staging 전용 안전장치(운영 라우트 미등록, 확인 키워드,
  audit)가 들어갈 때까지 운영 기능으로 취급하지 않는다.

## 12. Notice Plan 관리

자세히는 [`notice-plans.md`](./notice-plans.md) Admin 섹션.

## 13. ETL / Record Linkage / 데이터 일관성

SPEC V8 M-10 ~ M-11.

### 13.1 `GET /admin/dedup-review`

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

### 13.2 `POST /admin/dedup-review/{id}/verdict`

```jsonc
{ "verdict": "merge_a_into_b" | "merge_b_into_a" | "not_same" | "uncertain", "reason": "..." }
```

krtour-map dedup verdict는 krtour-map admin OpenAPI로 callback한다.

### 13.3 `GET /admin/provider-sync`

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

### 13.4 `POST /admin/provider-sync/{id}/{action}`

`action`: `pause` | `resume` | `retry` | `reset_cursor`.

### 13.5 `GET /admin/integrity`

`app.data_integrity_violations` + 라이브러리 자체 violations 합쳐 표시.

## 14. 디버그 콘솔

### 14.1 `WS /admin/debug/logs`

Loki LogQL을 백엔드에서 호출 → WebSocket으로 push.

```jsonc
// 클라이언트 → 서버 첫 메시지
{ "type": "subscribe", "query": "{service=\"fastapi\", level=\"error\"} |= \"trip_id=abc\"" }

// 서버 → 클라이언트
{ "type": "log", "ts": "...", "service": "...", "level": "ERROR", "msg": "...", "extra": {...} }
{ "type": "subscribed", "stream_id": "..." }
{ "type": "error", "message": "LogQL syntax error" }
```

### 14.2 `GET /admin/debug/request/{request_id}`

X-Request-Id 기반 단일 요청 타임라인. structlog 로그 + Sentry transaction +
`app.api_call_log` row 합쳐 보여줌.

## 15. Backup / Restore

ADR-022 범위. 본 API는 TripMate 소유 `app` schema backup snapshot과 동일 DB
schema-swap restore만 다룬다. `feature` / `provider_sync` schema는
`python-krtour-map` 책임이다.

### 15.1 `GET /admin/backup/snapshots`

```http
GET /admin/backup/snapshots?limit=50
```

- 권한: `admin` / `operator` / `cpo`
- 저장 위치: `TRIPMATE_BACKUP_DIR`의 `*.dump`
- `.sha256` 파일이 있으면 `status="verified"`, 없으면 `status="available"`

응답 200:

```jsonc
{
  "data": [
    {
      "snapshot_id": "tripmate-app-20260606-003000",
      "filename": "tripmate-app-20260606-003000.dump",
      "path": "/var/lib/tripmate/backups/tripmate-app-20260606-003000.dump",
      "size_bytes": 2097152,
      "checksum_sha256": "b...",
      "status": "verified",
      "created_at": "2026-06-06T00:30:00Z"
    }
  ]
}
```

### 15.2 `POST /admin/backup/snapshot`

```http
POST /admin/backup/snapshot
Content-Type: application/json

{ "access_reason": "배포 전 수동 snapshot" }
```

- 권한: `admin`
- 동작: `TRIPMATE_BACKUP_SCRIPT_PATH`를 subprocess로 실행하고 `BACKUP_FILE=...`
  출력 또는 새 dump 파일을 snapshot으로 인식한다.
- audit: `app.admin_audit_log`에 `action="backup.snapshot"` 기록
- 실패: `503 SERVICE_UNAVAILABLE`, `error.code="BACKUP_FAILED"`

응답 201: `GET /admin/backup/snapshots` 항목과 동일한 snapshot 객체.

### 15.3 `POST /admin/backup/restore-hotswap`

```http
POST /admin/backup/restore-hotswap
Content-Type: application/json

{
  "snapshot_id": "tripmate-app-20260606-003000",
  "access_reason": "운영 복구 훈련",
  "confirm_schema_swap": true
}
```

- 권한: `admin`
- 동작: `TRIPMATE_RESTORE_HOTSWAP_SCRIPT_PATH`를 subprocess로 실행한다.
  기본 스크립트는 `TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 custom dump를
  `app_restore_<ts>`로 remap restore하고, 검증 후 `app` → `app_previous_<ts>`,
  `app_restore_<ts>` → `app` schema rename을 수행한다.
- `TRIPMATE_RESTORE_DRAIN_COMMAND`가 있으면 switch 전 write drain 단계에서 실행한다.
  없으면 `TRIPMATE_RESTORE_ALLOW_NO_DRAIN=1`일 때만 drain을 skip할 수 있다.
- audit: 성공 시 `action="backup.restore_hotswap"`, 실패 시
  `action="backup.restore_hotswap_failed"` 기록
- 실패: snapshot 없음 `404 BACKUP_SNAPSHOT_NOT_FOUND`, 스크립트 실패
  `503 BACKUP_FAILED`, `confirm_schema_swap=false`는 `422 VALIDATION_ERROR`

응답 200:

```jsonc
{
  "data": {
    "restore_id": "20260608093000",
    "snapshot_id": "tripmate-app-20260606-003000",
    "snapshot_path": "/var/lib/tripmate/backups/tripmate-app-20260606-003000.dump",
    "restore_schema": "app_restore_20260608093000",
    "previous_schema": "app_previous_20260608093000",
    "status": "succeeded",
    "phases": [
      { "name": "preparing", "status": "success", "message": "snapshot verified" },
      { "name": "restoring", "status": "success", "message": "restored" },
      { "name": "validating", "status": "success", "message": "validated" },
      { "name": "draining", "status": "success", "message": "drained" },
      { "name": "switching", "status": "success", "message": "schema-swap completed" }
    ],
    "started_at": "2026-06-08T09:30:00Z",
    "completed_at": "2026-06-08T09:31:00Z"
  }
}
```

단순 restore는 API가 아니라 `scripts/restore-db.sh`와
[`docs/runbooks/backup-restore.md`](../runbooks/backup-restore.md) 절차로 수행한다.

## 16. MCP 토큰 관리 (ADR-019, Sprint 6)

### 16.1 `GET /admin/mcp-tokens`

```http
GET /admin/mcp-tokens?user_id=<uuid>&status=active&q=Claude
```

- 권한: `admin` / `operator` / `cpo`
- `status`: `active` | `expired` | `revoked`
- 응답은 토큰 원문 없이 마스킹 값과 metadata만 반환한다.

### 16.2 `POST /admin/mcp-tokens`

```jsonc
{
  "user_id": "uuid",
  "name": "사용자 대리 발급",
  "expires_at": "2026-07-07T00:00:00Z",
  "access_reason": "고객 지원 요청"
}
```

- 권한: `admin`
- `scopes`는 1차 구현에서 `["mcp:read"]`만 허용한다.
- `app.admin_audit_log`에 `action="mcp_token.issue"` 기록.
- 응답은 발급 직후 1회만 `token` 원문을 포함한다.

### 16.3 `POST /admin/mcp-tokens/{token_id}/revoke`

```jsonc
{ "access_reason": "토큰 유출 의심" }
```

- 권한: `admin`
- `revoked_at = now()` 설정.
- `app.admin_audit_log`에 `action="mcp_token.revoke"` 기록.

## 17. Seed / Reset (dev/staging only)

### 17.1 `POST /admin/seed/scenarios/{scenario_key}`

`scenario_key`: SPEC V8 M-13 8 시나리오 키 (`new_user_first_trip` 등).

운영 환경에서는 라우트 자체 비활성 (`ENABLE_SEED` 환경변수 false → router include
안 함). 404.

### 17.2 `POST /admin/reset`

```jsonc
{ "confirm": "RESET", "admin_password": "..." }
```

- dev/staging에서만 라우트 등록
- DB 전체 reset (`alembic downgrade base` → `upgrade head`)
- 라이브러리 schema는 별도 reset endpoint (`POST /admin/krtour-map/reset`)
- 자동으로 `new_user_first_trip` 시나리오 적용

## 18. AI agent 구현 체크리스트

- [ ] `apps/api/app/api/v1/admin/__init__.py` 라우터 분기
- [ ] `apps/api/app/api/v1/admin/{users,trips,features,pois,datasets,entities,audit,etl,dedup,integrity,debug,backup,seed,reset,rustfs}.py`
- [ ] `apps/api/app/services/admin/{entity_browser,entity_crud,audit_chain,seed_scenarios,reset}.py`
- [ ] `apps/api/app/middleware/admin_audit.py` (chain prev_hash + content_hash)
- [ ] `apps/api/app/middleware/rbac.py` (`roles` 검사 + 404 변환)
- [ ] 통합 테스트 + RBAC 거부 e2e + chain 검증
- [ ] 운영 환경 `ENABLE_SEED=false` 시 seed/reset 라우트 404 확인
