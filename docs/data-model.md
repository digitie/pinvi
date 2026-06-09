# data-model.md — TripMate `app` 도메인 데이터 모델

본 문서는 TripMate가 소유하는 `app` schema의 도메인 모델이다. 지도 feature
도메인(`feature` schema)은 `python-krtour-map`이 소유하며 본 문서 범위 밖이다.

`feature` schema의 데이터 모델은 `python-krtour-map`의 `docs/data-model.md` 참고.

> **감사 후속 (2026-06-06, `docs/audit/2026-06-06-doc-impl-audit.md`)**:
> ADR-029에 따라 사용자 대면 추천 여행은 `curated_trip_plans` 계열로 분리했고,
> `notice_plans`는 운영 공지 전용으로 남긴다. DEC-05 사용자 제안 큐는 T-177에서
> `feature_suggestions`로 실체화했다. `security_incidents`와 누락 `users` 컬럼 문서
> 정합은 T-138, `trip_day_pois` 예산/currency 정합은 T-140에서 반영했다.

## 1. 큰 그림

```
┌──────────────────────────────────────────────────────────────────┐
│ app schema (TripMate 소유)                                        │
│                                                                  │
│  app.users                                                       │
│   ├── app.user_oauth_identities  (kakao/naver/google/email)      │
│   ├── app.user_sessions                                          │
│   └── app.user_email_verifications                               │
│                                                                  │
│  app.trips                                                       │
│   ├── app.trip_days                                              │
│   │    └── app.trip_day_pois  (POI 첨부 — feature_id reference)  │
│   │         └── app.trip_poi_rise_sets  (KASI 위치별 해·달 출몰시각) │
│   ├── app.trip_companions                                        │
│   └── app.trip_share_links                                       │
│                                                                  │
│  app.attachments  (RustFS 메타 — Trip/POI/사용자 첨부)            │
│                                                                  │
│  app.curated_trip_plans  (Admin 추천 여행 템플릿)                 │
│   ├── app.curated_plan_pois                                      │
│   └── app.curated_plan_attachments                               │
│                                                                  │
│  app.notice_plans  (Admin이 운영하는 공지)                       │
│   └── app.notice_plan_audiences                                  │
│                                                                  │
│  app.feature_suggestions  (사용자 feature 제안 큐)                │
│                                                                  │
│  app.admin_audit_logs                                            │
│                                                                  │
│  app.import_jobs  (Dagster job/run 영속화 — ops와 분리)          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼ feature_id (외부 schema reference)
┌──────────────────────────────────────────────────────────────────┐
│ feature schema (python-krtour-map 소유)                          │
│   feature.features, feature.source_records, ...                  │
└──────────────────────────────────────────────────────────────────┘
```

`app.trip_day_pois.feature_id`는 `feature.features.feature_id`를 가리키지만,
**외래키 제약은 두지 않는다** (schema 책임 분리 — 라이브러리 schema가 우선
변경되면 TripMate의 제약이 깨질 수 있음). 정합성은 응용 레이어에서 처리.

## 2. 엔티티 카탈로그

### 2.1 사용자 / 인증

#### `app.users`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `user_id` | `uuid` (PK) | `gen_random_uuid()` |
| `email` | `varchar(320)` UNIQUE NOT NULL | 가입/로그인 email |
| `password_hash` | `varchar(255)` | Argon2id hash. OAuth-only 계정은 null 가능 |
| `nickname` | `varchar(80)` | 표시 이름 |
| `avatar_url` | `varchar(1024)` | RustFS 또는 OAuth 공급자 URL |
| `avatar_kind` | `varchar(16)` | `default` 등 avatar source |
| `gender` | `varchar(16)` | `demographic_use` 동의 시에만 저장 |
| `birth_year_month` | `varchar(6)` | YYYYMM. `demographic_use` 동의 시에만 저장 |
| `residence_sigungu_code` | `varchar(5)` | 거주 시군구. `demographic_use` 동의 시에만 저장 |
| `status` | `varchar(32)` | `pending_verification` / `pending_profile` / `active` / `disabled` / `deleted` |
| `roles` | `varchar(16)[]` | `user` / `admin` / `operator` / `cpo` (SPEC V8 M-14). 기본 `['user']` |
| `email_verified_at` | `timestamptz` | null이면 미인증 |
| `email_status` | `varchar(16)` | `active` / `bounced` / `complained` |
| `access_token_version` | `integer` NOT NULL DEFAULT 0 | access JWT `token_version` claim 검증. 비밀번호 재설정 등 전체 세션 무효화 시 증가 |
| `is_active` | `boolean` | 서버 로그인 가능 여부 |
| `deleted_at` | `timestamptz` | soft delete 시각 |
| `created_at` | `timestamptz` NOT NULL DEFAULT now() | KST aware는 응용에서 변환 |
| `updated_at` | `timestamptz` NOT NULL DEFAULT now() | trigger |

#### `app.user_oauth_identities`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `identity_id` | `uuid` (PK) | |
| `user_id` | `uuid` NOT NULL → `app.users` | ON DELETE CASCADE |
| `provider` | `varchar(32)` NOT NULL | 현재 활성은 `google`; `naver`/`kakao`는 미래 provider |
| `provider_user_id` | `varchar(255)` NOT NULL | 공급자 측 사용자 ID |
| `provider_email` | `varchar(320)` | nullable |
| `provider_email_verified` | `boolean` | provider가 확인한 email 여부 |
| `display_name_snapshot` | `varchar(120)` | provider 표시명 snapshot |
| `linked_at` | `timestamptz` NOT NULL | |
| `last_login_at` | `timestamptz` | |
| `created_at` | `timestamptz` NOT NULL | |
| `updated_at` | `timestamptz` NOT NULL | |
| UNIQUE | `(provider, provider_user_id)` | |
| UNIQUE | `(user_id, provider)` | 사용자별 provider 1개 |

#### `app.user_sessions`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `session_id` | `uuid` (PK) | `gen_random_uuid()` |
| `user_id` | `uuid` NOT NULL → `app.users` | |
| `session_token_hash` | `varchar(128)` UNIQUE NOT NULL | refresh token SHA-256 hash |
| `expires_at` | `timestamptz` NOT NULL | |
| `revoked_at` | `timestamptz` | nullable. refresh rotation/logout 시 기존 row 폐기. rotation은 기존 row lock 후 처리 |
| `user_agent` | `varchar(512)` | |
| `ip_address` | `inet` | |
| `created_at` | `timestamptz` NOT NULL | |
| `updated_at` | `timestamptz` NOT NULL | |

#### `app.user_email_verifications`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `verification_id` | `uuid` (PK) | |
| `user_id` | `uuid` NOT NULL → `app.users` | |
| `token_hash` | `varchar(128)` UNIQUE NOT NULL | verify/reset token hash |
| `purpose` | `varchar(32)` | `signup` / `email_change` / `password_reset` |
| `expires_at` | `timestamptz` NOT NULL | |
| `used_at` | `timestamptz` | nullable |
| `created_at` | `timestamptz` NOT NULL | |
| `updated_at` | `timestamptz` NOT NULL | |

#### `app.security_incidents`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `incident_id` | `uuid` (PK) | |
| `incident_type` | `varchar(64)` | `admin_export_anomaly`, `audit_chain_broken` 등 |
| `severity` | `varchar(16)` | `low` / `medium` / `high` / `critical` |
| `status` | `varchar(24)` | `open` / `acknowledged` / `resolved` / `false_positive` |
| `source` | `varchar(64)` | 감지 소스 |
| `summary` | `varchar(240)` | CPO 목록용 한 줄 설명 |
| `details` | `jsonb` | 원인/근거 payload |
| `affected_user_count` | `int` | 추정 영향 사용자 수 |
| `notification_required` | `boolean` | 정보주체 통지 필요 판정 |
| `assigned_cpo_user_id` | `uuid` → `app.users` | 담당 CPO, nullable |
| `request_id` | `uuid` | 관련 API request id, nullable |
| `detected_at` | `timestamptz` NOT NULL | 감지 시각 |
| `acknowledged_at` | `timestamptz` | CPO 확인 시각 |
| `resolved_at` | `timestamptz` | 종료 시각 |
| `notified_at` | `timestamptz` | 사용자 통지 시각 |
| `kisa_reported_at` | `timestamptz` | KISA 신고 시각 |
| `created_at` | `timestamptz` NOT NULL | |
| `updated_at` | `timestamptz` NOT NULL | |

### 2.2 여행 계획

#### `app.trips`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `trip_id` | `uuid` (PK) | |
| `owner_user_id` | `uuid` NOT NULL → `app.users` | |
| `title` | `text` NOT NULL | |
| `description` | `text` | nullable, markdown 허용 |
| `start_date` | `date` NOT NULL | |
| `end_date` | `date` NOT NULL | `>= start_date` |
| `region_hint` | `text` | 예: "부산", "강릉" |
| `primary_region_code` | `varchar(10)` | 선택. 지역 기반 알림/질의용 sido/sigungu/bjd code |
| `primary_region_source` | `varchar(16)` | `manual` / `poi_snapshot` / `geocoded` |
| `cover_attachment_id` | `uuid` → `app.attachments` | nullable |
| `visibility` | `text` | `private` / `unlisted` / `public` |
| `status` | `text` | `draft` / `planned` / `in_progress` / `completed` / `archived` |
| `created_at`, `updated_at` | `timestamptz` | |

`region_hint`는 사용자 표시용 자유텍스트이고, `primary_region_code`는 텔레그램 brief,
지역 날씨/유가 후보 질의처럼 구조화 지역 키가 필요한 흐름에서 사용한다. 사용자가
직접 입력하면 `manual`, POI `feature_snapshot`에서 보강되면 `poi_snapshot`이다.

#### `app.trip_days`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `day_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | ON DELETE CASCADE |
| `day_index` | `int` NOT NULL | 0 = 첫 날 |
| `date` | `date` | nullable (확정 전) |
| `title` | `text` | nullable |
| `note` | `text` | markdown |
| UNIQUE | `(trip_id, day_index)` | |

#### `app.trip_day_pois`

POI 첨부 — feature 도메인 `feature_id` reference + 사용자 메모. **순서는
LexoRank fractional indexing + COLLATE "C"** (SPEC V8 E-6 Critical).

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `attachment_id` | `uuid` (PK) | |
| `trip_id`, `day_index` | `uuid`, `int` → `app.trip_days` | 복합 FK |
| `sort_order` | `text COLLATE "C"` NOT NULL | LexoRank. JS ASCII와 PG 정렬을 맞추기 위해 C 콜레이션 강제 |
| `feature_id` | `text` NOT NULL | `feature.features.feature_id` 참조 (제약 없음) |
| `feature_snapshot` | `jsonb` | denormalized 캐시 (이름/좌표/카테고리) |
| `custom_marker_color` | `text` | P-01~P-16 (사용자 override) |
| `custom_marker_icon` | `text` | maki id (사용자 override) |
| `planned_arrival_at` | `timestamptz` | KST aware |
| `planned_departure_at` | `timestamptz` | |
| `user_note` | `text` | markdown |
| `budget_amount` | `numeric(12,2)` | 예상 비용. null 또는 0 이상 |
| `actual_amount` | `numeric(12,2)` | 실제 지출. null 또는 0 이상 |
| `currency` | `varchar(3)` | 대문자 3글자. 기본 `KRW` |
| `user_url` | `text` | 사용자 참고 URL |
| `version` | `int` | optimistic lock — `PATCH` 시 `If-Match` 헤더 (SPEC V8 J-2) |
| `created_at`, `updated_at` | `timestamptz` | |

`feature_snapshot`은 적재 시점의 정보를 보존하는 캐시 — 라이브러리 schema가
바뀌어도 UI 표시는 유지. 실제 최신 좌표/이름은 `feature_id`로 조회.

#### `app.trip_poi_rise_sets`

POI 생성 시 `python-kasi-api`의 `rise_set.location`(`getLCRiseSetInfo`,
위치별 해달 출몰시각 정보조회)을 1회 호출한 결과를 POI 부속 정보로 저장한다.
재계산 schedule은 두지 않는다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `poi_id` | `uuid` (PK) → `app.trip_day_pois.attachment_id` | ON DELETE CASCADE |
| `locdate` | `date` | 조회 기준일 (`trip_days.date`) |
| `longitude`, `latitude` | `double precision` | 요청 좌표 snapshot |
| `sunrise_at`, `sunset_at` | `timestamptz` | 파싱 가능할 때 |
| `moonrise_at`, `moonset_at` | `timestamptz` | 파싱 가능할 때 |
| `status` | `text` | `pending_date` / `pending_coord` / `pending_fetch` / `success` / `failed` |
| `raw_payload` | `jsonb` | KASI 원문 payload |
| `error` | `jsonb` | 실패 시 redacted error |
| `fetched_at` | `timestamptz` | 마지막 호출 시각 |
| `created_at`, `updated_at` | `timestamptz` | |

#### `app.kasi_special_days`

Dagster `kasi_special_days_daily`가 하루 1회, 실행일 기준 과거 6개월부터 미래
18개월까지 KASI 특일 계열 dataset을 조회해 upsert한다. 별도 삭제는 없다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `special_day_id` | `uuid` (PK) | |
| `dataset` | `text` | `holidays` / `national_holidays` / `anniversaries` / `solar_terms_24` / `sundry_days` |
| `sol_date` | `date` | 양력 기준일 |
| `name` | `text` | 특일명 |
| `sequence` | `text` | provider sequence가 있으면 저장 |
| `is_holiday` | `bool` | 공휴일 여부를 알 수 있을 때 |
| `raw_payload` | `jsonb` | KASI 원문 payload |
| `fetched_at`, `created_at`, `updated_at` | `timestamptz` | |

#### `app.trip_companions`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `companion_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | |
| `user_id` | `uuid` → `app.users` | 가입 user 매칭 시 채움 |
| `invited_email` | `varchar(320)` | 미가입 초대 또는 초대 메일 수신 주소 |
| `invited_nickname` | `varchar(80)` | 초대 화면 표시명 |
| `role` | `text` | `co_owner` / `editor` / `viewer` |
| `invited_at` | `timestamptz` | |
| `joined_at` | `timestamptz` | |
| `created_at`, `updated_at` | `timestamptz` | |

`(trip_id, user_id)`와 `(trip_id, lower(invited_email))`는 partial unique index로
중복 초대를 막는다. 초대 API는 이메일로 기존 user를 매칭해 `user_id`와 `joined_at`을
즉시 채우고, `app.email_queue.template='trip_invite'` row를 적재한다.

#### `app.trip_share_links`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `share_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | |
| `token_hash` | `varchar(128)` UNIQUE NOT NULL | 원문 token은 응답 1회만 노출 |
| `created_by_user_id` | `uuid` NOT NULL → `app.users` | owner-only 발급 |
| `visibility` | `text` | `view_only` / `comment` / `edit` |
| `expires_at` | `timestamptz` | nullable |
| `revoked_at` | `timestamptz` | |
| `last_used_at` | `timestamptz` | |
| `created_at`, `updated_at` | `timestamptz` | |

`visibility='comment'`는 shared-token 보기에서 댓글 작성까지 허용하는 의미다. 로그인
사용자 댓글 API는 아래 `app.trip_comments`에 먼저 구현되어 있고, 비로그인
shared-token 댓글 라우트는 shared-token 조회 구현 시 같은 테이블로 연결한다.

#### `app.trip_comments`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `comment_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | ON DELETE CASCADE |
| `author_user_id` | `uuid` → `app.users` | 삭제 user 보존 위해 nullable |
| `body` | `text` NOT NULL | 1~2000자 |
| `target_type` | `text` | `trip` / `day` / `poi` |
| `target_id` | `uuid` | `target_type='poi'` 등일 때 선택 |
| `day_index` | `int` | `target_type='day'`일 때 선택 |
| `deleted_at` | `timestamptz` | soft delete |
| `created_at`, `updated_at` | `timestamptz` | |

### 2.3 파일 첨부

#### `app.attachments`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `attachment_id` | `uuid` (PK) | |
| `owner_user_id` | `uuid` NOT NULL → `app.users` | |
| `bucket` | `text` NOT NULL | `tripmate-app` 기본 |
| `object_key` | `text` NOT NULL | RustFS key |
| `mime_type` | `text` NOT NULL | |
| `byte_size` | `bigint` NOT NULL | |
| `display_name` | `text` | 원본 파일명 |
| `category` | `text` | `trip_cover` / `day_photo` / `poi_note` / `user_avatar` / `notice` |
| `linked_entity_kind` | `text` | `trip` / `trip_day` / `poi_attachment` / `user` / `curated_plan` / `notice` |
| `linked_entity_id` | `uuid` | 카테고리에 따라 reference |
| `created_at` | `timestamptz` | |
| UNIQUE | `(bucket, object_key)` | |

`linked_entity_kind` + `linked_entity_id`는 폴리모픽 참조. 외래키 제약은 두지
않고 응용에서 검증. RustFS 버킷 분리 정책은 ADR-013.

### 2.4 추천 여행 템플릿 (Curated trip plan)

외부 API 경로는 Sprint 4 호환을 위해 `/notice-plans`를 유지하지만, DB/ORM 정본은
ADR-029의 `curated_*` 이름이다. `app.notice_plans`는 아래 §2.5의 운영 공지 전용이다.

#### `app.curated_trip_plans`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `curated_plan_id` | `uuid` (PK) | |
| `slug` | `varchar(160)` NOT NULL | partial unique (`deleted_at IS NULL`) |
| `title` | `varchar(200)` NOT NULL | |
| `category` | `varchar(80)` | `recommended` 기본 |
| `summary` | `text` | |
| `source_name` | `varchar(200)` | |
| `destination` | `varchar(120)` | |
| `starts_on`, `ends_on` | `date` | 둘 다 null이거나 둘 다 채움 |
| `is_published` | `boolean` | published만 일반 사용자 노출 |
| `created_by_admin_id`, `updated_by_admin_id` | `uuid` → `app.users` | |
| `version` | `int` | optimistic lock |
| `deleted_at`, `created_at`, `updated_at` | `timestamptz` | |

#### `app.curated_plan_pois`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `curated_poi_id` | `uuid` (PK) | |
| `curated_plan_id` | `uuid` NOT NULL → `app.curated_trip_plans` | ON DELETE CASCADE |
| `day_index` | `int` | 1 이상 |
| `sort_order` | `text COLLATE "C"` | LexoRank |
| `feature_id` | `text` | krtour-map feature id 값 참조(FK 없음) |
| `feature_snapshot` | `jsonb` | 적재 시점 캐시 |
| `memo` | `text` | |
| `budget_amount` | `numeric(12,2)` | 0 이상 |
| `currency` | `varchar(3)` | ISO 4217 |
| `user_url` | `text` | |
| `custom_marker_color`, `custom_marker_icon` | `text` | |
| `version`, `deleted_at`, `created_at`, `updated_at` | | |

#### `app.curated_plan_attachments`

`trip` / `trip_poi` / `curated_plan` / `curated_poi` 중 정확히 하나를 가리키는
RustFS 메타 테이블이다. curated → trip copy 시 새 row의 `source_attachment_id`에
원본 row를 남기고 RustFS object 자체는 복사하지 않는다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `attachment_id` | `uuid` (PK) | |
| `trip_id` | `uuid` → `app.trips` | 선택 |
| `trip_poi_id` | `uuid` → `app.trip_day_pois.attachment_id` | 선택 |
| `curated_plan_id` | `uuid` → `app.curated_trip_plans` | 선택 |
| `curated_poi_id` | `uuid` → `app.curated_plan_pois` | 선택 |
| `source_attachment_id` | `uuid` → `app.curated_plan_attachments` | copy 원본 |
| `bucket`, `storage_key`, `original_filename`, `content_type` | `text` | RustFS 메타 |
| `byte_size` | `bigint` | 0보다 큼 |
| `role` | `varchar(40)` | `attachment` / `image` / `document` / `reference` |
| `description`, `sort_order`, `uploaded_by_user_id` | | |
| `deleted_at`, `created_at`, `updated_at` | `timestamptz` | |

### 2.5 공지 (Notice plan)

#### `app.notice_plans`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `notice_id` | `uuid` (PK) | |
| `title` | `text` NOT NULL | |
| `body` | `text` NOT NULL | markdown |
| `category` | `text` | `general` / `maintenance` / `event` / `incident` |
| `priority` | `int` NOT NULL DEFAULT 0 | 큰 수가 더 우선 |
| `starts_at` | `timestamptz` NOT NULL | |
| `ends_at` | `timestamptz` | nullable |
| `status` | `text` | `draft` / `scheduled` / `active` / `archived` |
| `created_by` | `uuid` NOT NULL → `app.users` | admin |
| `created_at`, `updated_at` | `timestamptz` | |

#### `app.notice_plan_audiences`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `audience_id` | `uuid` (PK) | |
| `notice_id` | `uuid` NOT NULL → `app.notice_plans` | ON DELETE CASCADE |
| `audience_kind` | `text` | `all` / `role` / `user` / `region` |
| `audience_value` | `text` | role 이름, user_id, 시도/시군구 코드 |

### 2.5 운영 / 로그

#### `app.admin_audit_log`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `log_id` | `bigserial` (PK) | |
| `actor_user_id` | `uuid` → `app.users` | |
| `action` | `varchar(64)` NOT NULL | `user.force_verify` / `trip.update_status` / ... |
| `resource_type` | `varchar(64)` NOT NULL | `user` / `trip` / `poi` / `backup` / ... |
| `resource_id` | `varchar(128)` | uuid 또는 자연키 |
| `before_state`, `after_state` | `jsonb` | nullable |
| `access_reason` | `text` | 위험 액션 사유 |
| `target_pii_fields` | `varchar(64)[]` | 접근한 PII 필드 |
| `ip_hash` | `varchar(64)` NOT NULL | SHA-256(IP) |
| `user_agent` | `text` | |
| `request_id` | `uuid` NOT NULL | |
| `prev_hash` | `varchar(64)` NOT NULL UNIQUE | chain fork 차단 |
| `content_hash` | `varchar(64)` NOT NULL | |
| `occurred_at` | `timestamptz` NOT NULL | |

#### `app.import_jobs`

Dagster run을 영속화하는 ops 보조 테이블. Dagster 자체 storage(`ops` schema)와
분리해서 TripMate 도메인 관점의 메타를 둔다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `job_id` | `uuid` (PK) | Dagster run_id mapping |
| `kind` | `text` | `feature_event_festivals` / `feature_place_rest_areas` / ... |
| `state` | `text` | `queued` / `running` / `success` / `failed` |
| `started_at` | `timestamptz` | |
| `ended_at` | `timestamptz` | |
| `payload` | `jsonb` | 입력 파라미터 |
| `result` | `jsonb` | 산출 메타 |
| `error` | `jsonb` | 실패 시 |

## 3. 좌표 / 시간 정책

- 모든 `timestamptz` 컬럼은 UTC 저장 + KST(`Asia/Seoul`)로 응용에서 변환.
- 좌표는 본 schema에 갖지 않는다 — POI 첨부는 `feature_id`로 참조. 좌표가 필요하면
  `feature.features`에서 조회.
- 단, 사용자가 직접 입력한 좌표(아직 feature가 없는 자유 메모 POI)는 `app` 도메인
  확장이 필요할 수 있다 — ADR로 결정 (제안 ADR-017).

## 4. UI 모델 / API 응답

응용 레이어는 `app` 도메인 모델과 `feature` 도메인 모델을 join해서 사용자에게
보여준다. 백엔드 응답 셰입은 다음 패턴:

```jsonc
{
  "trip": {
    "trip_id": "...",
    "title": "...",
    "days": [
      {
        "day_id": "...",
        "date": "2026-06-01",
        "pois": [
          {
            "attachment_id": "...",
            "feature_id": "f_2611000000_p_...",
            "feature": {
              // python-krtour-map에서 join해 가져온 최신 정보
              "name": "...",
              "category": "...",
              "coord": [lon, lat]
            },
            "feature_snapshot": { /* 적재 시점의 cache (백업) */ },
            "user_note": "..."
          }
        ]
      }
    ]
  }
}
```

응답 빌더는 `apps/api/app/services/trip_view_builder.py`에 둔다 (코드 작성
단계 진입 후). krtour-map `POST /tripmate/features/batch`로 batch 조회 후 join.

## 5. 인덱스 전략 (요약)

자세한 DDL/인덱스는 `postgres-schema.md`. 핵심:

- `app.users(email)` UNIQUE
- `app.user_sessions(user_id, expires_at)` partial WHERE `revoked_at IS NULL`
- `app.trips(owner_user_id, status, start_date)` 합성
- `app.trip_day_pois(day_id, position)` UNIQUE 합성
- `app.trip_day_pois(feature_id)` — feature schema join용 (B-tree)
- `app.attachments(linked_entity_kind, linked_entity_id)` 합성
- `app.curated_trip_plans(is_published, updated_at)` 합성
- `app.curated_plan_pois(curated_plan_id, day_index)` 합성
- `app.notice_plans(status, starts_at)` 합성
- `app.feature_suggestions(requester_user_id, created_at)` 합성
- `app.feature_suggestions(status, created_at)` 합성
- `app.feature_suggestions(requester_user_id, kind, lower(name), lng, lat)` partial UNIQUE
  WHERE `status='pending'` — 사용자 pending 중복 방지
- `app.admin_audit_logs(created_at)` BRIN (대량 append)

## 6. 마이그레이션 정책

- 본 schema의 Alembic은 `apps/api/alembic/versions/...`에서 관리.
- 파일명 규약: `YYYYMMDD_NNNN_<short_slug>.py` (v1 패턴 유지).
- Down migration은 비어 있어도 무방하나 schema 추가/변경은 가능하면 작성.
- DDL과 backfill을 분리 — 한 migration에 데이터 변환을 섞지 않는다.

## 7. 의존 다이어그램 (외부 schema)

```
app schema (TripMate)
  └─ feature schema (python-krtour-map)
       └─ source_records → provider_sync (python-krtour-map)
```

`app`은 `feature`를 컬럼 값(`feature_id`)으로만 참조한다. 외래키 없음. join은
응용에서 처리.

## 8. SPEC V8 추가 테이블 (`app` schema)

SPEC V8 #4 M-6, M-14 + #0 O장에서 도입한 추가 테이블. 자세한 DDL은
`postgres-schema.md`.

### 8.1 `app.user_consents`

4 분리 동의 + 철회 (SPEC V8 G-5):

| 컬럼 | 비고 |
|------|------|
| `user_id` (FK + PK) | |
| `consent_type` (PK) | `tos` / `privacy` / `lbs_tos` / `location_collection` / `marketing` / `demographic_use` |
| `version` (PK) | 약관 버전 |
| `agreed_at` | |
| `withdrawn_at` | 철회 시. 위치 동의 철회 → 위치 기록 즉시 삭제 + 위치 기능 비활성 |

### 8.2 `app.location_access_log` (위치정보법 O-3)

`content_hash` chain:

| 컬럼 | 비고 |
|------|------|
| `id` (PK, bigserial) | |
| `user_id` | |
| `occurred_at` | |
| `endpoint`, `purpose` | 호출 컨텍스트 |
| `lat`, `lng` | 호출 시 사용자 좌표 (있을 때만) |
| `request_id` | X-Request-Id 매칭 |
| `ip_hash` | SHA-256(IP) — 원본 IP 직접 저장 X |
| `prev_hash`, `content_hash` | 직전 row content_hash + 현재 row 표현 → SHA-256 → chain |

- 6개월 retention (Dagster job)
- CPO 권한만 SELECT (`roles` 검사 + RBAC dependency)

### 8.3 `app.email_queue` (SPEC V8 M-6 / G-6)

Resend 통합:

| 컬럼 | 비고 |
|------|------|
| `id` (uuid) | |
| `to_email` | CITEXT |
| `template` | `verify` / `reset` / `invite` / `system` / `share_link` 등 |
| `payload` | jsonb — react-email props |
| `status` | `pending` / `sent` / `delivered` / `bounced` / `complained` / `failed` |
| `resend_id` | Resend 측 이메일 ID — Resend 대시보드 deep link |
| `bounce_type` | `hard` / `soft` |
| `attempts`, `last_error` | |

### 8.4 `app.api_call_log` (SPEC V8 M-6)

외부 API 호출 로그:

| 컬럼 | 비고 |
|------|------|
| `provider` | `python-kma-api` 등 canonical 이름 |
| `endpoint`, `status`, `latency_ms`, `error` | |
| `occurred_at` | BRIN index + `(provider, occurred_at DESC)` |

### 8.5 `app.feature_suggestions` (SPEC V8 H-6 / DEC-05)

사용자 feature 추가/정정/폐쇄 제안 큐. TripMate `app` schema가 소유하고,
`POST /features/requests`는 krtour-map을 직접 호출하지 않는다. Admin 검사/승인 후
krtour-map feature change API로 반영하는 흐름은 T-179에서 연결한다.

| 컬럼 | 비고 |
|------|------|
| `request_id` (uuid PK) | |
| `requester_user_id` | `app.users` FK. 제안 소유자 |
| `type` | `new_place` / `correction` / `closure` |
| `target_feature_id` | 기존 feature 정정/폐쇄 대상. FK 없음 |
| `kind` | `place` / `event` / `notice` / `price` / `weather` / `route` / `area` |
| `name`, `lng`, `lat`, `categories`, `note` | 사용자 입력 제안 내용 |
| `status` | `pending` / `approved` / `rejected` / `added` / `duplicate` |
| `reviewed_by_admin_id` | Admin 처리자. nullable |
| `krtour_ref` | 승인 후 krtour `feature_id`/`request_id`/state 참조 payload |
| `resolved_at` | 종료 시각 |

pending 상태에서는 같은 사용자·kind·정규화 이름·소수 6자리 좌표 조합을 중복 등록하지
않는다. API 레이어는 사용자당 24시간 20건 rate-limit을 적용한다.

### 8.6 `app.category_mappings` (SPEC V8 I-6 / M-2)

카테고리 → maki 아이콘 + 16색 매핑:

| 컬럼 | 비고 |
|------|------|
| `category_key` (PK) | 라이브러리 마스터 카테고리 |
| `maki_icon` | |
| `marker_color` | `P-01` ~ `P-16` |
| `display_name_ko` | |
| `updated_by`, `updated_at` | Admin 편집 audit |

### 8.7 `app.data_integrity_violations` (SPEC V8 M-11)

`/admin/integrity` 1차 소스:

| 컬럼 | 비고 |
|------|------|
| `id` (bigserial PK) | |
| `rule_key` | `orphan_poi`, `sort_order_duplicate`, ... |
| `entity_kind`, `entity_id` | |
| `details` | jsonb |
| `detected_at`, `resolved_at` | |
| `auto_fixable` | bool |

### 8.8 `app.admin_audit_log` (보강)

SPEC V8 O-6 / M-14에 따라 컬럼 추가:

| 추가 컬럼 | 비고 |
|------|------|
| `access_reason` | 위험 액션 시 강제 입력 |
| `target_pii_fields` | text[] — 접근한 PII 필드 목록 |
| `prev_hash`, `content_hash` | chain (audit log chain 깨짐 → 즉시 CPO 알림). `prev_hash`는 unique이며 append 경로는 advisory lock으로 head를 직렬화 |

## 9. 향후 확장 후보 (ADR 후보)

- ADR-NNN: 사용자 직접 입력 POI (feature가 없는 자유 메모) 모델
- ADR-NNN: 여행 일정 자동 생성 (Gemini integration)
- ADR-NNN: 동행자 공유 권한 모델 상세화 (ACL/RBAC)
- ADR-NNN: 사용자 활동 로그 (시간순 timeline view)
- ADR-NNN: GPX 업로드 (route feature 사용자 생성)
