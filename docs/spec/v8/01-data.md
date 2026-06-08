# SPEC V8 #1 — 데이터 모델 · DB · ETL (TripMate 적용 노트)

원본: `spec_v8_1_data.docx` (D장 데이터 모델 + E장 DDL + K장 ETL + L장 vworld 임포트).

> SPEC V8의 후속 메모 **O (2026-05-17)** 와 **Q/R (2026-05-20)** 는 본 도메인의
> 책임을 `python-krtour-map`으로 분리한다고 명시한다. 본 노트는 그 분리된
> 책임에 따라 TripMate가 무엇을 하고 무엇을 라이브러리에 위임하는지 정리한다.

## 1. 책임 분담

| 영역 | 본 저장소 | `python-krtour-map` | SPEC V8 출처 |
|------|-----------|---------------------|--------------|
| 7 Feature 모델(place/event/notice/price/weather/route/area) | — | ✓ | D-1 ~ D-13 |
| `feature_id` 생성 (`f_{bjd}_{kind[0]}_{sha1[:16]}`) | — | ✓ | D-2 |
| 트리(`parent_feature_id`) / sibling | — | ✓ | D-3 |
| `feature.detail` Pydantic 모델 | — | ✓ | D-4, D-8 ~ D-12 |
| `price_points` / `price_values` 시계열 | — | ✓ | D-5, E-3 |
| `WeatherValue` / `feature_weather_values` | — | ✓ | D-6, N(2026-05-16) |
| **POI** snapshot + sort_order | ✓ | — | D-7, E-3 |
| `bjd_lookup` (법정동코드 마스터) | — | ✓ | E-3, L장 (python-kraddr-geo) |
| `features.geom` GIST 인덱스 | — | ✓ | E-3 |
| Record Linkage (100m blocking / 0.45/0.35/0.20 / 0.85) | — | ✓ | D-14, K-4 |
| `dedup_review_queue` schema | — | ✓ | K-4 |
| vworld 법정동코드 임포트 본체 | — | ✓ (`python-kraddr-geo`) | L장 |
| vworld 임포트 트리거 UI | ✓ | — | L-3 |
| `app.trips` / `app.trip_days` / `app.trip_pois` | ✓ | — | E-3 |
| **POI sort_order COLLATE "C"** | ✓ | — | E-6 (Critical) |
| `app.users` / `app.user_consents` / `app.user_oauth_identities` | ✓ | — | E-2 |
| `app.location_access_log` audit chain | ✓ | — | O-3 |
| `app.admin_audit_log` audit chain | ✓ | — | O-6, M-14 |

## 2. TripMate가 직접 박는 항목

### 2.1 POI sort_order — Fractional Indexing + COLLATE "C" (E-6 Critical)

`app.trip_pois.sort_order TEXT COLLATE "C"`. JavaScript LexoRank와 PostgreSQL
`en_US.utf8` 정렬 결과가 다르면 시스템 마비 — `COLLATE "C"`로 ASCII 바이트 순서
강제.

- DDL: `docs/postgres-schema.md` §3.3
- 인덱스도 `(trip_id, day_index, sort_order COLLATE "C")` 명시
- Alembic: `op.alter_column(..., type_=sa.Text(collation="C"))`
- 로컬 DB가 C 로캘이면 테스트에서 안 잡힘 → CI는 `en_US.utf8` 로캘 컨테이너로 강제
- 운영 사고 사례로 ADR 후보 (ADR-NNN)

### 2.2 사용자 / 인증 / 동의 (E-2)

`app.users`:

- `email CITEXT UNIQUE`
- `password_hash` (Argon2id, 소셜-only면 NULL)
- `roles TEXT[]` (`user`/`admin`/`operator`/`cpo` — `is_admin` BOOLEAN 정정)
- `email_verified BOOLEAN` + `email_verified_at`
- 선택 정보: `gender`, `birth_yyyymm`, `sigungu_code` (동의 시에만)
- `status`: `pending_verification` / `pending_profile` / `active` / `disabled`

`app.user_email_verifications` (SPEC V8의 `email_verify_tokens`):

- `token_hash CHAR(64)` (실제 토큰은 클라이언트에만, DB는 해시만)
- `purpose`: `signup` / `password_reset` / `email_change`
- `expires_at` / `used_at`

`app.user_consents`:

- 복합 PK `(user_id, consent_type, version)`
- `consent_type`: `tos` / `privacy` / `lbs_tos` / `location_collection` /
  `marketing` / `demographic_use`
- `agreed_at` / `withdrawn_at`

`app.user_sessions` (refresh 토큰):

- `revoked_at IS NULL`인 row의 `(user_id, expires_at)` partial index
- IP / User-Agent 저장 (소송/감사 추적용)

### 2.3 여행 / POI (E-3)

- `app.trips` (leader_id, fuel_types text[], visibility)
- `app.trip_members` (가입 전 invited_email + 가입 후 user_id) — `app.trip_companions`로 명명 통일 권장
- `app.trip_days` (composite PK `(trip_id, day_index)`)
- `app.trip_pois`:
  - `feature_id TEXT` (라이브러리 schema reference, FK 없음 — ADR-003)
  - `feature_link_broken_at TIMESTAMPTZ` (라이브러리 feature 삭제 시 표시)
  - `feature_snapshot JSONB` (D-7의 `PoiSnapshot`)
  - `custom_marker_color` / `custom_marker_icon` (사용자 override)
  - `sort_order TEXT COLLATE "C"` (E-6)
  - `version INTEGER` (optimistic lock)
- `app.trip_share_links` (256bit 토큰)

### 2.4 위치 감사 로그 (O-3)

`app.location_access_log`:

- `content_hash` chain (`prev_hash` 컬럼 명시 추가 — SPEC V8 O-9)
- 6개월 retention (Dagster job)
- CPO 권한만 SELECT (RBAC)
- 자세히는 `docs/spec/v8/00-infrastructure.md` §3.3

### 2.5 Admin 감사 로그 (O-6, M-14)

`app.admin_audit_log`:

- `actor_user_id`, `action`, `resource_type`, `resource_id`
- `before` / `after` JSONB diff
- `access_reason` (위험 액션 시 강제)
- `target_pii_fields TEXT[]` (접근한 PII 필드)
- `prev_hash` / `content_hash` chain (`prev_hash` unique + advisory lock으로 head 직렬화)
- append-only (DELETE 차단 trigger 또는 권한 분리)

### 2.6 Admin 보조 테이블 (M-6)

`app.email_queue`:

- `to_email`, `template`, `payload JSONB`
- `status`: `pending` / `sent` / `delivered` / `bounced` / `complained` / `failed`
- `resend_id` (Resend ID — Resend 대시보드 deep link)
- `bounce_type` (`hard` / `soft`)

`app.api_call_log`:

- `provider` (`python-kma-api` 등 canonical name)
- `endpoint`, `status`, `latency_ms`, `error`
- BRIN(occurred_at) + (provider, occurred_at DESC)
- TripMate가 호출하는 외부 API의 호출 로그 — 라이브러리는 라이브러리 측에서
  별도 로그 (양쪽 결합 안 함)

`app.import_jobs`:

- Dagster run을 영속화하는 도메인 메타
- (`docs/data-model.md` §2.5)

`app.data_integrity_violations`:

- `/admin/integrity` 페이지 1차 소스
- `app` schema 룰 위반 추적 (feature schema는 라이브러리가 별도 관리)

`app.feature_requests`:

- 사용자가 "feature 추가 요청" → Admin 큐 → 승인 시 라이브러리에 적재 요청

`app.category_mappings`:

- 외부 카테고리 ↔ 내부 카테고리 매핑 (UI 표시용)
- 라이브러리의 카테고리 마스터 위에 사용자별 override

## 3. `python-krtour-map`에 위임하는 항목

### 3.1 7 Feature

`feature.features`:

- `feature_id TEXT PRIMARY KEY`
- `kind`: place / event / notice / price / weather / route / area
- `name`, `bjd_code`, `coord` (POINT 4326), `geom` (route LINESTRING, area POLYGON)
- `urls JSONB` (homepage/sns1/sns2/review_naver/review_kakao/review_google)
- `marker_icon` (maki 아이콘 id), `marker_color` (P-01 ~ P-16)
- `parent_feature_id`, `sibling_group_id`
- `detail JSONB` (kind+category별 Pydantic 모델)
- `raw_refs JSONB` ([{source_type, source_id, fetched_at}])
- `status`, `deleted_at`

본 저장소는 `feature_id`로 reference만. DDL은 라이브러리 alembic.

### 3.2 보관 정책 (D-13)

라이브러리가 Dagster job으로 일 1회 정리:

- `place` — 무기한 (폐업은 `status='inactive'`)
- `event` — `event_period.end + 20년`
- `notice` — `valid_period.end + 1년` (없으면 `start + 1년`)
- `price (value)` — `price_points.retention_days` (카테고리별, 기본 10년)
- `weather` — 여행 참조 0건이 되면 즉시 (TripMate가 trigger)
- `route`/`area` — 무기한 (`status='inactive'`로 hide)

### 3.3 Record Linkage (D-14, K-4)

- Blocking: 같은 `bjd_code` + `kind` + `ST_DWithin(coord, 100m)`
- Scoring: 명칭(Jaro-Winkler, 0.45) + 공간(Haversine 비선형, 0.35) + 카테고리(Jaccard, 0.20)
- 자동 병합 ≥ 0.85, 수동 큐 0.65 ~ 0.85
- `dedup_review_queue` — TripMate Admin `/admin/dedup-review` UI에서 호출

### 3.4 provider sync (Q-3 ~ R-2)

`provider_sync_state(provider, dataset_key, sync_scope)`:

- `cursor`, `last_success_at`, `last_error`, `last_full_scan_at`
- VisitKorea modifiedtime 증분, KMA 시간축, KHOA 30분 갱신

TripMate Admin `/admin/provider-sync`에서 재시도/일시정지/재개 (M-15).

## 4. Sprint 매핑

| SPEC V8 항목 | Sprint | 본 저장소 산출물 |
|------|--------|------------------|
| `app.users` + email verify (E-2, G-3) | Sprint 1 | `apps/api/alembic/versions/0001_initial_app.py` |
| `app.user_consents` + 4 분리 동의 (G-5) | Sprint 2 | `apps/api/app/services/consent.py` |
| `app.trips` + `trip_days` (E-3) | Sprint 2 | `apps/api/alembic/.../0002_trips.py` |
| `app.trip_pois` + COLLATE "C" (E-6) | Sprint 2 | `apps/api/alembic/.../0003_pois.py` |
| `app.location_access_log` chain (O-3) | Sprint 2 | `apps/api/app/middleware/location_audit.py` |
| `app.admin_audit_log` chain (M-14) | Sprint 3 | `apps/api/app/middleware/admin_audit.py` |
| `app.email_queue` (M-6) | Sprint 1 | DDL + worker (Sprint 2) |
| `app.api_call_log` (M-6) | Sprint 2 | httpx middleware |
| `app.import_jobs` (M-6) | Sprint 5 | Dagster sensor |
| `app.feature_requests` (H-6) | Sprint 3 | Admin 페이지 |
| `app.category_mappings` (M-2) | Sprint 3 | Admin 페이지 |
| 라이브러리 `feature.*` 사용 (모든 read API) | Sprint 4 | `apps/api/app/etl_bridge/krtour_map.py` |
| vworld 임포트 trigger UI (L-3) | Sprint 5 | Admin `/admin/etl/vworld-import` |
| Record Linkage 검토 큐 UI (K-4) | Sprint 5 | Admin `/admin/dedup-review` |

## 5. 관련 문서

- `docs/data-model.md` (본 저장소 `app` 도메인 상세)
- `docs/postgres-schema.md` (DDL 골격)
- `docs/krtour-map-integration.md` (krtour-map OpenAPI HTTP 패턴)
- `docs/decisions.md` ADR-003 (schema 책임 분담)
- `docs/spec/v8/02-backend.md` (API 측 매핑)
- `python-krtour-map`의 `docs/data-model.md`, `docs/postgres-schema.md`
