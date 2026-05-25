# data-model.md — TripMate `app` 도메인 데이터 모델

본 문서는 TripMate가 소유하는 `app` schema의 도메인 모델이다. 지도 feature
도메인(`feature` schema)은 `python-krtour-map`이 소유하며 본 문서 범위 밖이다.

`feature` schema의 데이터 모델은 `python-krtour-map`의 `docs/data-model.md` 참고.

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
│   ├── app.trip_companions                                        │
│   └── app.trip_share_links                                       │
│                                                                  │
│  app.attachments  (RustFS 메타 — Trip/POI/사용자 첨부)            │
│                                                                  │
│  app.notice_plans  (Admin이 운영하는 공지)                       │
│   └── app.notice_plan_audiences                                  │
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
| `email` | `text` UNIQUE NOT NULL | 정규화된 lowercase |
| `email_verified_at` | `timestamptz` | null이면 미인증 |
| `display_name` | `text` | nullable |
| `avatar_url` | `text` | RustFS 또는 OAuth 공급자 URL |
| `status` | `text` | `active` / `suspended` / `deleted` |
| `roles` | `text[]` | 예: `['admin', 'editor']`. 기본 `[]` |
| `created_at` | `timestamptz` NOT NULL DEFAULT now() | KST aware는 응용에서 변환 |
| `updated_at` | `timestamptz` NOT NULL DEFAULT now() | trigger |

#### `app.user_oauth_identities`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `identity_id` | `uuid` (PK) | |
| `user_id` | `uuid` NOT NULL → `app.users` | ON DELETE CASCADE |
| `provider` | `text` NOT NULL | `kakao` / `naver` / `google` |
| `provider_user_id` | `text` NOT NULL | 공급자 측 사용자 ID |
| `provider_email` | `text` | nullable |
| `linked_at` | `timestamptz` NOT NULL | |
| `last_login_at` | `timestamptz` | |
| UNIQUE | `(provider, provider_user_id)` | |

#### `app.user_sessions`

세션 모델은 ADR-010 결정 후 확정. 잠정안 (cookie session):

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `session_id` | `uuid` (PK) | secure random |
| `user_id` | `uuid` NOT NULL → `app.users` | |
| `created_at` | `timestamptz` NOT NULL | |
| `expires_at` | `timestamptz` NOT NULL | |
| `revoked_at` | `timestamptz` | nullable |
| `ip` | `inet` | |
| `user_agent` | `text` | |

#### `app.user_email_verifications`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `verification_id` | `uuid` (PK) | |
| `user_id` | `uuid` NOT NULL → `app.users` | |
| `token_hash` | `text` NOT NULL | bcrypt/argon2 |
| `email` | `text` NOT NULL | snapshot |
| `purpose` | `text` | `signup` / `email_change` / `reset_password` |
| `created_at` | `timestamptz` NOT NULL | |
| `expires_at` | `timestamptz` NOT NULL | |
| `used_at` | `timestamptz` | nullable |

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
| `cover_attachment_id` | `uuid` → `app.attachments` | nullable |
| `visibility` | `text` | `private` / `unlisted` / `public` |
| `status` | `text` | `draft` / `planned` / `in_progress` / `completed` / `archived` |
| `created_at`, `updated_at` | `timestamptz` | |

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

POI 첨부 — feature 도메인 `feature_id` reference + 사용자 메모.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `attachment_id` | `uuid` (PK) | |
| `day_id` | `uuid` NOT NULL → `app.trip_days` | |
| `position` | `int` NOT NULL | day 내 순서 (0부터) |
| `feature_id` | `text` NOT NULL | `feature.features.feature_id` 참조 (제약 없음) |
| `feature_snapshot` | `jsonb` | denormalized 캐시 (이름/좌표/카테고리) |
| `planned_arrival_at` | `timestamptz` | KST aware |
| `planned_departure_at` | `timestamptz` | |
| `user_note` | `text` | markdown |
| `created_at`, `updated_at` | `timestamptz` | |

`feature_snapshot`은 적재 시점의 정보를 보존하는 캐시 — 라이브러리 schema가
바뀌어도 UI 표시는 유지. 실제 최신 좌표/이름은 `feature_id`로 조회.

#### `app.trip_companions`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `companion_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | |
| `user_id` | `uuid` → `app.users` | nullable (외부 동행자) |
| `display_name` | `text` | external user일 때 사용 |
| `role` | `text` | `co_owner` / `editor` / `viewer` |
| `joined_at` | `timestamptz` | |

#### `app.trip_share_links`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `share_id` | `uuid` (PK) | |
| `trip_id` | `uuid` NOT NULL → `app.trips` | |
| `token` | `text` UNIQUE NOT NULL | URL-safe random |
| `visibility` | `text` | `view_only` / `comment` / `edit` |
| `expires_at` | `timestamptz` | nullable |
| `revoked_at` | `timestamptz` | |

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
| `linked_entity_kind` | `text` | `trip` / `trip_day` / `poi_attachment` / `user` / `notice_plan` |
| `linked_entity_id` | `uuid` | 카테고리에 따라 reference |
| `created_at` | `timestamptz` | |
| UNIQUE | `(bucket, object_key)` | |

`linked_entity_kind` + `linked_entity_id`는 폴리모픽 참조. 외래키 제약은 두지
않고 응용에서 검증. RustFS 버킷 분리 정책은 ADR-013.

### 2.4 공지 (Notice plan)

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

#### `app.admin_audit_logs`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `log_id` | `bigserial` (PK) | |
| `admin_user_id` | `uuid` → `app.users` | nullable (system) |
| `action` | `text` NOT NULL | `create` / `update` / `delete` / `login` / ... |
| `entity_kind` | `text` | `user` / `trip` / `notice_plan` / ... |
| `entity_id` | `text` | uuid 또는 자연키 |
| `before` | `jsonb` | nullable |
| `after` | `jsonb` | nullable |
| `ip` | `inet` | |
| `user_agent` | `text` | |
| `created_at` | `timestamptz` NOT NULL | |

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
단계 진입 후). `AsyncKrtourMapClient.features_by_ids(...)`로 batch 조회 후 join.

## 5. 인덱스 전략 (요약)

자세한 DDL/인덱스는 `postgres-schema.md`. 핵심:

- `app.users(email)` UNIQUE
- `app.user_sessions(user_id, expires_at)` partial WHERE `revoked_at IS NULL`
- `app.trips(owner_user_id, status, start_date)` 합성
- `app.trip_day_pois(day_id, position)` UNIQUE 합성
- `app.trip_day_pois(feature_id)` — feature schema join용 (B-tree)
- `app.attachments(linked_entity_kind, linked_entity_id)` 합성
- `app.notice_plans(status, starts_at)` 합성
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

## 8. 향후 확장 후보 (ADR 후보)

- ADR-NNN: 사용자 직접 입력 POI (feature가 없는 자유 메모) 모델
- ADR-NNN: 여행 일정 자동 생성 (Gemini integration)
- ADR-NNN: 동행자 공유 권한 모델 상세화 (ACL/RBAC)
- ADR-NNN: 사용자 활동 로그 (시간순 timeline view)
