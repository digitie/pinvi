# postgres-schema.md — `app` schema 골격

본 문서는 `pinvi` PostgreSQL 데이터베이스의 `app` schema DDL 골격이다. 실제
DDL은 Alembic migration이 박는다 (코드 작성 단계 진입 후 `apps/api/alembic/
versions/...`).

다른 schema:

- `feature`, `provider_sync` — `kor-travel-map` 소유. 그쪽 저장소의
  `docs/postgres-schema.md` 참고.
- `ops` — Dagster run/event storage. Dagster가 자체 관리. Pinvi는 `app.import_jobs`
  로 도메인 관점의 메타만 둔다.
- `x_extension` — PostGIS / pg_trgm / pgcrypto.

SPEC V8 cross-reference: spec/v8/01-data.md §2 (Pinvi가 박는 항목 매핑).

## 1. 부트스트랩

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS x_extension;

CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm  SCHEMA x_extension;

-- 접속 시 search_path
ALTER ROLE pinvi SET search_path TO public, x_extension;

-- updated_at trigger (공통)
CREATE OR REPLACE FUNCTION app.touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;
```

## 2. 사용자 / 인증

### 2.1 `app.users`

```sql
CREATE TABLE app.users (
  user_id                 uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  email                   varchar(320) NOT NULL,
  password_hash           varchar(255),
  nickname                varchar(80),
  avatar_url              varchar(1024),
  avatar_kind             varchar(16) NOT NULL DEFAULT 'default',
  gender                  varchar(16),
  birth_year_month        varchar(6),
  residence_sigungu_code  varchar(5),
  status                  varchar(32) NOT NULL DEFAULT 'pending_verification',
  roles                   varchar(16)[] NOT NULL DEFAULT ARRAY['user']::varchar[],
  email_verified_at       timestamptz,
  email_status            varchar(16) NOT NULL DEFAULT 'active',
  access_token_version    integer NOT NULL DEFAULT 0,
  is_active               boolean NOT NULL DEFAULT true,
  deleted_at              timestamptz,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_users_status CHECK (
    status IN ('pending_verification', 'pending_profile', 'active', 'disabled', 'deleted')
  ),
  CONSTRAINT ck_users_email_status CHECK (email_status IN ('active', 'bounced', 'complained')),
  CONSTRAINT ck_users_gender CHECK (
    gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'no_answer')
  ),
  CONSTRAINT ck_users_access_token_version_nonnegative CHECK (access_token_version >= 0)
);

CREATE UNIQUE INDEX uq_users_email ON app.users (email);
CREATE INDEX ix_users_status ON app.users (status);

CREATE TRIGGER trg_users_touch_updated_at
BEFORE UPDATE ON app.users
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

### 2.2 `app.user_oauth_identities`

```sql
CREATE TABLE app.user_oauth_identities (
  identity_id      uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  provider         varchar(32) NOT NULL,
  provider_user_id varchar(255) NOT NULL,
  provider_email   varchar(320),
  provider_email_verified boolean,
  display_name_snapshot varchar(120),
  linked_at        timestamptz NOT NULL DEFAULT now(),
  last_login_at    timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_oauth_identities_provider_subject UNIQUE (provider, provider_user_id),
  CONSTRAINT uq_user_oauth_identities_user_provider UNIQUE (user_id, provider),
  CONSTRAINT ck_user_oauth_identities_provider CHECK (provider IN ('google', 'naver', 'kakao'))
);
```

### 2.3 `app.user_sessions`

```sql
CREATE TABLE app.user_sessions (
  session_id          uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  session_token_hash  varchar(128) NOT NULL UNIQUE,
  expires_at          timestamptz NOT NULL,
  revoked_at          timestamptz,
  user_agent          varchar(512),
  ip_address          inet,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_sessions_active_idx
  ON app.user_sessions (user_id, expires_at)
  WHERE revoked_at IS NULL;
```

`access_token_version`은 access JWT의 `token_version` claim과 비교한다. 비밀번호 재설정
등 전체 세션 무효화 이벤트에서 증가하며, 이전 access JWT는 만료 시간 전이라도 거부된다.

`session_token_hash`는 refresh token 원문이 아닌 SHA-256 hash다. refresh 성공 시 기존
row의 `revoked_at`을 채우고 새 row를 발급한다. 회전 처리는 기존 row를 잠가 같은 refresh
token 동시 재사용이 새 session을 둘 이상 만들지 못하게 한다.

### 2.4 `app.user_email_verifications`

```sql
CREATE TABLE app.user_email_verifications (
  verification_id uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  token_hash      varchar(128) NOT NULL UNIQUE,
  purpose         varchar(32) NOT NULL DEFAULT 'signup',
  expires_at      timestamptz NOT NULL,
  used_at         timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_user_email_verifications_purpose CHECK (
    purpose IN ('signup', 'password_reset', 'email_change')
  )
);
```

### 2.5 `app.mcp_tokens` (Sprint 6)

```sql
CREATE TABLE app.mcp_tokens (
  token_id           uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  token_hash         varchar(255) NOT NULL UNIQUE,
  token_prefix       varchar(16) NOT NULL,
  token_suffix       varchar(12) NOT NULL,
  name               varchar(120) NOT NULL,
  scopes             varchar(32)[] NOT NULL DEFAULT ARRAY['mcp:read']::varchar[],
  expires_at         timestamptz,
  last_used_at       timestamptz,
  last_used_ip_hash  varchar(128),
  revoked_at         timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_mcp_tokens_scope_read_only CHECK (scopes <@ ARRAY['mcp:read']::varchar[])
);

CREATE INDEX ix_mcp_tokens_user_active
  ON app.mcp_tokens (user_id, expires_at)
  WHERE revoked_at IS NULL;

CREATE TRIGGER trg_mcp_tokens_touch_updated_at
BEFORE UPDATE ON app.mcp_tokens
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

원본 MCP 토큰은 발급 직후 1회만 표시하고 DB에는 Argon2id hash(`token_hash`)만 저장한다.
목록 마스킹용으로 원본 앞/뒤 일부만 `token_prefix` / `token_suffix`에 보존한다.
1차 외부 MCP는 read-only라 `mcp:read` scope만 허용한다(ADR-019).

## 3. 여행 계획

### 3.1 `app.trips`

```sql
CREATE TABLE app.trips (
  trip_id           uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  owner_user_id     uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  title             text NOT NULL,
  description       text,
  start_date        date NOT NULL,
  end_date          date NOT NULL,
  region_hint       text,
  primary_region_code varchar(10),
  primary_region_source varchar(16),
  cover_attachment_id uuid,
  visibility        text NOT NULL DEFAULT 'private',
  status            text NOT NULL DEFAULT 'draft',
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trips_dates_chk CHECK (end_date >= start_date),
  CONSTRAINT ck_trips_primary_region_code CHECK (
    primary_region_code IS NULL OR primary_region_code ~ '^[0-9]{2,10}$'
  ),
  CONSTRAINT ck_trips_primary_region_source CHECK (
    primary_region_source IS NULL OR primary_region_source IN ('manual', 'poi_snapshot', 'geocoded')
  ),
  CONSTRAINT ck_trips_primary_region_pair CHECK (
    (primary_region_code IS NULL AND primary_region_source IS NULL)
    OR (primary_region_code IS NOT NULL AND primary_region_source IS NOT NULL)
  ),
  CONSTRAINT trips_visibility_chk CHECK (visibility IN ('private', 'unlisted', 'public')),
  CONSTRAINT trips_status_chk CHECK (status IN ('draft', 'planned', 'in_progress', 'completed', 'archived'))
);

CREATE INDEX trips_owner_status_idx ON app.trips (owner_user_id, status, start_date DESC);
CREATE INDEX trips_public_idx ON app.trips (start_date DESC) WHERE visibility = 'public';
CREATE INDEX ix_trips_primary_region
  ON app.trips (primary_region_code)
  WHERE primary_region_code IS NOT NULL AND deleted_at IS NULL;

CREATE TRIGGER trips_touch_updated_at
BEFORE UPDATE ON app.trips
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

### 3.2 `app.trip_days`

```sql
CREATE TABLE app.trip_days (
  day_id    uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id   uuid NOT NULL REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  day_index int NOT NULL,
  date      date,
  title     text,
  note      text,
  UNIQUE (trip_id, day_index),
  CONSTRAINT trip_days_index_chk CHECK (day_index >= 0)
);

CREATE INDEX trip_days_trip_idx ON app.trip_days (trip_id, day_index);
```

### 3.3 `app.trip_day_pois`

```sql
CREATE TABLE app.trip_day_pois (
  attachment_id        uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id              uuid NOT NULL,
  day_index            int NOT NULL,
  sort_order           text COLLATE "C" NOT NULL,    -- SPEC V8 E-6 (Critical) — LexoRank
  feature_id           text,                          -- nullable. feature.features.feature_id 참조 (FK 없음)
  feature_link_broken_at timestamptz,
  feature_snapshot     jsonb NOT NULL DEFAULT '{}'::jsonb,
  custom_marker_color  text,                          -- 사용자 override (P-01..P-16)
  custom_marker_icon   text,                          -- 사용자 override (maki id)
  planned_arrival_at   timestamptz,
  planned_departure_at timestamptz,
  user_note            text,
  budget_amount        numeric(12,2),
  actual_amount        numeric(12,2),
  currency             varchar(3) NOT NULL DEFAULT 'KRW',
  user_url             text,
  added_by_user_id     uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  version              int NOT NULL DEFAULT 1,        -- optimistic lock (SPEC V8 J-2)
  deleted_at           timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_trip_day_pois_day
    FOREIGN KEY (trip_id, day_index) REFERENCES app.trip_days(trip_id, day_index) ON DELETE CASCADE,
  CONSTRAINT ck_trip_day_pois_budget_nonnegative
    CHECK (budget_amount IS NULL OR budget_amount >= 0),
  CONSTRAINT ck_trip_day_pois_actual_nonnegative
    CHECK (actual_amount IS NULL OR actual_amount >= 0),
  CONSTRAINT ck_trip_day_pois_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- 정렬·중복 방지: ASCII 바이트 순서 강제 (en_US.utf8 정렬과 다름)
CREATE UNIQUE INDEX uq_trip_day_pois_day_sort
  ON app.trip_day_pois (trip_id, day_index, sort_order COLLATE "C")
  WHERE deleted_at IS NULL;
CREATE INDEX ix_trip_day_pois_feature ON app.trip_day_pois (feature_id);
CREATE INDEX ix_trip_day_pois_trip_day ON app.trip_day_pois (trip_id, day_index);

CREATE TRIGGER trip_day_pois_touch_updated_at
BEFORE UPDATE ON app.trip_day_pois
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

### 3.3.1 `app.trip_poi_rise_sets`

```sql
CREATE TABLE app.trip_poi_rise_sets (
  poi_id       uuid PRIMARY KEY REFERENCES app.trip_day_pois(attachment_id) ON DELETE CASCADE,
  locdate      date,
  longitude    double precision,
  latitude     double precision,
  sunrise_at   timestamptz,
  sunset_at    timestamptz,
  moonrise_at  timestamptz,
  moonset_at   timestamptz,
  status       text NOT NULL DEFAULT 'pending_date',
  raw_payload  jsonb NOT NULL DEFAULT '{}'::jsonb,
  error        jsonb,
  fetched_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trip_poi_rise_sets_status_chk
    CHECK (status IN ('pending_date', 'pending_coord', 'pending_fetch', 'success', 'failed'))
);

CREATE INDEX trip_poi_rise_sets_locdate_idx ON app.trip_poi_rise_sets (locdate);

CREATE TRIGGER trip_poi_rise_sets_touch_updated_at
BEFORE UPDATE ON app.trip_poi_rise_sets
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

POI 생성 시 `python-kasi-api`의 위치별 해달 출몰시각 정보조회 결과를 1회 저장한다.
별도 주기 재조회는 없다.

### 3.4 `app.trip_companions`

```sql
CREATE TABLE app.trip_companions (
  companion_id     uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id          uuid NOT NULL REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  user_id          uuid REFERENCES app.users(user_id) ON DELETE SET NULL,
  invited_email    varchar(320),
  invited_nickname varchar(80),
  role             varchar(16) NOT NULL DEFAULT 'editor',
  invited_at       timestamptz NOT NULL DEFAULT now(),
  joined_at        timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_trip_companions_target CHECK ((user_id IS NOT NULL) OR (invited_email IS NOT NULL)),
  CONSTRAINT ck_trip_companions_role CHECK (role IN ('co_owner', 'editor', 'viewer'))
);

CREATE INDEX ix_trip_companions_trip ON app.trip_companions (trip_id);
CREATE INDEX ix_trip_companions_user ON app.trip_companions (user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_trip_companions_trip_user
  ON app.trip_companions (trip_id, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_trip_companions_trip_invited
  ON app.trip_companions (trip_id, lower(invited_email)) WHERE invited_email IS NOT NULL;
```

### 3.5 `app.trip_share_links`

```sql
CREATE TABLE app.trip_share_links (
  share_id           uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id            uuid NOT NULL REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  token_hash         varchar(128) NOT NULL UNIQUE,
  created_by_user_id uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  visibility         varchar(16) NOT NULL DEFAULT 'view_only',
  expires_at         timestamptz,
  revoked_at         timestamptz,
  last_used_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_trip_share_links_visibility CHECK (visibility IN ('view_only', 'comment', 'edit'))
);

CREATE INDEX ix_trip_share_links_trip_active
  ON app.trip_share_links (trip_id) WHERE revoked_at IS NULL;
```

`visibility='comment'`는 공유 보기에서 댓글 작성까지 허용하는 링크다. 현재 구현된
로그인 사용자 댓글 API는 `app.trip_comments`를 사용하며, 비로그인 shared-token 댓글
작성 라우트는 `GET /trips/{trip_id}/shared/{token}` 구현과 함께 연결한다.

### 3.6 `app.trip_comments`

```sql
CREATE TABLE app.trip_comments (
  comment_id     uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id        uuid NOT NULL REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  author_user_id uuid REFERENCES app.users(user_id) ON DELETE SET NULL,
  body           text NOT NULL,
  target_type    varchar(16) NOT NULL DEFAULT 'trip',
  target_id      uuid,
  day_index      int,
  deleted_at     timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_trip_comments_target_type CHECK (target_type IN ('trip', 'day', 'poi')),
  CONSTRAINT ck_trip_comments_body_len CHECK (length(body) BETWEEN 1 AND 2000)
);

CREATE INDEX ix_trip_comments_trip_created_at
  ON app.trip_comments (trip_id, created_at) WHERE deleted_at IS NULL;
CREATE INDEX ix_trip_comments_author
  ON app.trip_comments (author_user_id) WHERE author_user_id IS NOT NULL;

CREATE TRIGGER trip_comments_touch_updated_at
BEFORE UPDATE ON app.trip_comments
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

### 3.7 추천 여행 템플릿 (`curated_*`)

외부 API는 Sprint 4 호환을 위해 `/notice-plans` 경로와 `notice_plan_id` 응답 alias를
유지하지만, DB/ORM 정본은 ADR-029의 `curated_*` 이름이다.

```sql
CREATE TABLE app.curated_trip_plans (
  curated_plan_id     uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  slug                varchar(160) NOT NULL,
  title               varchar(200) NOT NULL,
  category            varchar(80) NOT NULL DEFAULT 'recommended',
  summary             text,
  source_name         varchar(200),
  destination         varchar(120),
  starts_on           date,
  ends_on             date,
  is_published        boolean NOT NULL DEFAULT false,
  created_by_admin_id uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  updated_by_admin_id uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  version             int NOT NULL DEFAULT 1,
  deleted_at          timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_curated_trip_plans_date_range CHECK (
    (starts_on IS NULL AND ends_on IS NULL)
    OR (starts_on IS NOT NULL AND ends_on IS NOT NULL AND ends_on >= starts_on)
  )
);

CREATE UNIQUE INDEX uq_curated_trip_plans_slug_active
  ON app.curated_trip_plans (slug)
  WHERE deleted_at IS NULL;
CREATE INDEX ix_curated_trip_plans_published
  ON app.curated_trip_plans (is_published, updated_at DESC);
CREATE INDEX ix_curated_trip_plans_category
  ON app.curated_trip_plans (category, updated_at DESC);

CREATE TRIGGER trg_curated_trip_plans_touch_updated_at
BEFORE UPDATE ON app.curated_trip_plans
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();

-- kor_travel_map curated_features 1:1 import를 붙일 때 출처 추적이 필요하면
-- source_system, source_curated_feature_id, source_curated_feature_version,
-- source_imported_at 같은 컬럼을 후속 migration으로 추가한다.
-- 현재 DDL은 Pinvi-native 큐레이션과 kor_travel_map import가 같은 테이블을 공유한다는
-- 정책만 반영하고, 상세 REST 계약 확정 전 source 컬럼을 선행 확정하지 않는다.

CREATE TABLE app.curated_plan_pois (
  curated_poi_id      uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  curated_plan_id     uuid NOT NULL REFERENCES app.curated_trip_plans(curated_plan_id) ON DELETE CASCADE,
  day_index           int NOT NULL DEFAULT 1,
  sort_order          text COLLATE "C" NOT NULL,
  feature_id          text,                           -- nullable. 외부 연계 시 feature-backed POI lookup
  feature_snapshot    jsonb NOT NULL DEFAULT '{}'::jsonb,
  memo                text,
  budget_amount       numeric(12,2),
  currency            varchar(3) NOT NULL DEFAULT 'KRW',
  user_url            text,
  custom_marker_color varchar(16),
  custom_marker_icon  varchar(64),
  version             int NOT NULL DEFAULT 1,
  deleted_at          timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_curated_plan_pois_day_index CHECK (day_index >= 1),
  CONSTRAINT ck_curated_plan_pois_budget_nonnegative CHECK (budget_amount IS NULL OR budget_amount >= 0),
  CONSTRAINT ck_curated_plan_pois_currency CHECK (currency ~ '^[A-Z]{3}$')
);

CREATE INDEX ix_curated_plan_pois_plan_day
  ON app.curated_plan_pois (curated_plan_id, day_index)
  WHERE deleted_at IS NULL;
CREATE INDEX ix_curated_plan_pois_feature
  ON app.curated_plan_pois (feature_id)
  WHERE deleted_at IS NULL AND feature_id IS NOT NULL;
CREATE UNIQUE INDEX uq_curated_plan_pois_plan_day_sort
  ON app.curated_plan_pois (curated_plan_id, day_index, sort_order COLLATE "C")
  WHERE deleted_at IS NULL;

-- kor_travel_map curated_features 하위 item과의 대응이 필요하면
-- source_curated_feature_id/source_curated_feature_item_id를 후속 migration으로 추가한다.
-- feature_id는 계속 nullable이다. kor_travel_map item이 feature를 제공하지 않거나
-- Pinvi-native 자유 POI이면 NULL로 둔다.

CREATE TABLE app.curated_plan_attachments (
  attachment_id        uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  trip_id              uuid REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  trip_poi_id          uuid REFERENCES app.trip_day_pois(attachment_id) ON DELETE CASCADE,
  curated_plan_id      uuid REFERENCES app.curated_trip_plans(curated_plan_id) ON DELETE CASCADE,
  curated_poi_id       uuid REFERENCES app.curated_plan_pois(curated_poi_id) ON DELETE CASCADE,
  source_attachment_id uuid REFERENCES app.curated_plan_attachments(attachment_id) ON DELETE SET NULL,
  bucket               varchar(80) NOT NULL,
  storage_key          varchar(1024) NOT NULL,
  original_filename    varchar(255) NOT NULL,
  content_type         varchar(255) NOT NULL,
  byte_size            bigint NOT NULL,
  public_url           text,
  checksum_sha256      varchar(64),
  role                 varchar(40) NOT NULL DEFAULT 'attachment',
  description          text,
  sort_order           int NOT NULL DEFAULT 0,
  uploaded_by_user_id  uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  deleted_at           timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_curated_plan_attachments_single_target
    CHECK (num_nonnulls(trip_id, trip_poi_id, curated_plan_id, curated_poi_id) = 1),
  CONSTRAINT ck_curated_plan_attachments_role
    CHECK (role IN ('attachment', 'image', 'document', 'reference')),
  CONSTRAINT ck_curated_plan_attachments_byte_size CHECK (byte_size > 0),
  CONSTRAINT ck_curated_plan_attachments_sort_order CHECK (sort_order >= 0)
);

CREATE INDEX ix_curated_plan_attachments_trip
  ON app.curated_plan_attachments (trip_id, sort_order)
  WHERE trip_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX ix_curated_plan_attachments_trip_poi
  ON app.curated_plan_attachments (trip_poi_id, sort_order)
  WHERE trip_poi_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX ix_curated_plan_attachments_curated_plan
  ON app.curated_plan_attachments (curated_plan_id, sort_order)
  WHERE curated_plan_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX ix_curated_plan_attachments_curated_poi
  ON app.curated_plan_attachments (curated_poi_id, sort_order)
  WHERE curated_poi_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX ix_curated_plan_attachments_storage_key
  ON app.curated_plan_attachments (bucket, storage_key);
```

### 3.8 `app.data_integrity_violations`

Pinvi app-owned `/admin/integrity` persisted source다. `kor-travel-map` consistency issue는
별도 OpenAPI source로만 조회하며, 이 table에 복제하지 않는다.

```sql
CREATE TABLE app.data_integrity_violations (
  id           bigserial PRIMARY KEY,
  rule_key     varchar(120) NOT NULL,
  entity_kind  varchar(80) NOT NULL,
  entity_id    text NOT NULL,
  severity     varchar(16) NOT NULL DEFAULT 'warning'
    CHECK (severity IN ('info', 'warning', 'error', 'critical')),
  message      text NOT NULL,
  details      jsonb NOT NULL DEFAULT '{}'::jsonb,
  status       varchar(16) NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'acknowledged', 'resolved', 'ignored')),
  detected_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at  timestamptz,
  auto_fixable boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_data_integrity_violations_status_severity_detected
  ON app.data_integrity_violations (status, severity, detected_at);
CREATE INDEX ix_data_integrity_violations_entity
  ON app.data_integrity_violations (entity_kind, entity_id);
CREATE UNIQUE INDEX uq_data_integrity_violations_active_rule_entity
  ON app.data_integrity_violations (rule_key, entity_kind, entity_id)
  WHERE status IN ('open', 'acknowledged') AND resolved_at IS NULL;
```

## 4. 첨부

### 4.1 `app.attachments`

```sql
CREATE TABLE app.attachments (
  attachment_id      uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  owner_user_id      uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  bucket             text NOT NULL,
  object_key         text NOT NULL,
  mime_type          text NOT NULL,
  byte_size          bigint NOT NULL CHECK (byte_size >= 0),
  display_name       text,
  category           text,
  linked_entity_kind text,
  linked_entity_id   uuid,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (bucket, object_key)
);

CREATE INDEX attachments_owner_idx ON app.attachments (owner_user_id, created_at DESC);
CREATE INDEX attachments_linked_idx ON app.attachments (linked_entity_kind, linked_entity_id)
  WHERE linked_entity_kind IS NOT NULL;
```

## 5. 공지 (Notice plan)

### 5.1 `app.notice_plans`

```sql
CREATE TABLE app.notice_plans (
  notice_id   uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  title       text NOT NULL,
  body        text NOT NULL,
  category    text NOT NULL DEFAULT 'general',
  priority    int  NOT NULL DEFAULT 0,
  starts_at   timestamptz NOT NULL,
  ends_at     timestamptz,
  status      text NOT NULL DEFAULT 'draft',
  created_by  uuid NOT NULL REFERENCES app.users(user_id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT notice_plans_status_chk CHECK (status IN ('draft', 'scheduled', 'active', 'archived')),
  CONSTRAINT notice_plans_dates_chk CHECK (ends_at IS NULL OR ends_at >= starts_at)
);

CREATE INDEX notice_plans_active_idx ON app.notice_plans (status, starts_at DESC);

CREATE TRIGGER notice_plans_touch_updated_at
BEFORE UPDATE ON app.notice_plans
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

### 5.2 `app.notice_plan_audiences`

```sql
CREATE TABLE app.notice_plan_audiences (
  audience_id    uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  notice_id      uuid NOT NULL REFERENCES app.notice_plans(notice_id) ON DELETE CASCADE,
  audience_kind  text NOT NULL,
  audience_value text,
  CONSTRAINT notice_plan_audiences_kind_chk CHECK (audience_kind IN ('all', 'role', 'user', 'region'))
);

CREATE INDEX notice_plan_audiences_notice_idx ON app.notice_plan_audiences (notice_id);
```

### 5.3 `app.feature_suggestions`

```sql
CREATE TABLE app.feature_suggestions (
  request_id           uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  requester_user_id    uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  type                 varchar(16) NOT NULL DEFAULT 'new_place',
  target_feature_id    text,
  kind                 varchar(16) NOT NULL,
  name                 varchar(200) NOT NULL,
  lng                  numeric(9,6) NOT NULL,
  lat                  numeric(8,6) NOT NULL,
  categories           varchar(80)[] NOT NULL DEFAULT ARRAY[]::varchar[],
  note                 text,
  status               varchar(16) NOT NULL DEFAULT 'pending',
  reviewed_by_admin_id uuid REFERENCES app.users(user_id) ON DELETE SET NULL,
  kor_travel_map_ref           jsonb,
  resolved_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_feature_suggestions_type
    CHECK (type IN ('new_place', 'correction', 'closure')),
  CONSTRAINT ck_feature_suggestions_status
    CHECK (status IN ('pending', 'approved', 'rejected', 'added', 'duplicate')),
  CONSTRAINT ck_feature_suggestions_kind
    CHECK (kind IN ('place', 'event', 'notice', 'price', 'weather', 'route', 'area')),
  CONSTRAINT ck_feature_suggestions_korea_coord
    CHECK (lng >= 124.0 AND lng <= 132.0 AND lat >= 33.0 AND lat <= 43.0),
  CONSTRAINT ck_feature_suggestions_name CHECK (char_length(name) BETWEEN 1 AND 200),
  CONSTRAINT ck_feature_suggestions_note CHECK (note IS NULL OR char_length(note) <= 2000)
);

CREATE INDEX ix_feature_suggestions_requester_created_at
  ON app.feature_suggestions (requester_user_id, created_at);
CREATE INDEX ix_feature_suggestions_status_created_at
  ON app.feature_suggestions (status, created_at);
CREATE UNIQUE INDEX ux_feature_suggestions_user_pending_dedup
  ON app.feature_suggestions (requester_user_id, kind, lower(name), lng, lat)
  WHERE status = 'pending';

CREATE TRIGGER trg_feature_suggestions_touch_updated_at
BEFORE UPDATE ON app.feature_suggestions
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

사용자 `POST /features/requests`는 이 테이블에만 적재하고 kor-travel-map을 직접 호출하지
않는다. Admin 검사/승인 후 kor_travel_map feature change API로 반영하는 단계는 T-179에서 연결한다.

## 6. 운영 / 로그

### 6.1 `app.admin_audit_log`

```sql
CREATE TABLE app.admin_audit_log (
  log_id            bigserial PRIMARY KEY,
  actor_user_id     uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  action            varchar(64) NOT NULL,
  resource_type     varchar(64) NOT NULL,
  resource_id       varchar(128),
  before_state      jsonb,
  after_state       jsonb,
  access_reason     text,
  target_pii_fields varchar(64)[],
  ip_hash           varchar(64) NOT NULL,
  user_agent        varchar(512),
  request_id        uuid NOT NULL,
  prev_hash         varchar(64) NOT NULL UNIQUE,
  content_hash      varchar(64) NOT NULL,
  occurred_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_admin_audit_log_occurred
  ON app.admin_audit_log USING brin (occurred_at);
CREATE INDEX ix_admin_audit_log_resource
  ON app.admin_audit_log (resource_type, resource_id, occurred_at DESC);
```

`append_admin_audit()`는 마지막 row 조회 전 PostgreSQL transaction-level advisory lock을
잡아 head를 직렬화한다. `prev_hash` unique constraint는 같은 head에서 두 row가 갈라지는
fork를 DB 차원에서 차단한다.

### 6.2 `app.import_jobs`

```sql
CREATE TABLE app.import_jobs (
  job_id      uuid PRIMARY KEY,                -- Dagster run_id mapping
  kind        text NOT NULL,
  state       text NOT NULL DEFAULT 'queued',
  started_at  timestamptz,
  ended_at    timestamptz,
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
  result      jsonb NOT NULL DEFAULT '{}'::jsonb,
  error       jsonb,
  CONSTRAINT import_jobs_state_chk CHECK (state IN ('queued', 'running', 'success', 'failed'))
);

CREATE INDEX import_jobs_kind_state_idx ON app.import_jobs (kind, state);
CREATE INDEX import_jobs_started_idx ON app.import_jobs (started_at DESC) WHERE started_at IS NOT NULL;
```

### 6.3 `app.kasi_special_days`

```sql
CREATE TABLE app.kasi_special_days (
  special_day_id uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  dataset        text NOT NULL,
  sol_date       date NOT NULL,
  name           text NOT NULL,
  sequence       text,
  is_holiday     boolean,
  raw_payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  fetched_at     timestamptz NOT NULL DEFAULT now(),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT kasi_special_days_dataset_chk CHECK (
    dataset IN ('holidays', 'national_holidays', 'anniversaries', 'solar_terms_24', 'sundry_days')
  )
);

CREATE UNIQUE INDEX kasi_special_days_source_uk
  ON app.kasi_special_days (dataset, sol_date, (coalesce(sequence, '')), name);
CREATE INDEX kasi_special_days_date_idx ON app.kasi_special_days (sol_date);

CREATE TRIGGER kasi_special_days_touch_updated_at
BEFORE UPDATE ON app.kasi_special_days
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

Dagster가 하루 1회 실행일 기준 과거 6개월부터 미래 18개월까지 upsert한다. 별도
삭제는 없다.

## 7. 권한 / 보안

### 7.1 `app.security_incidents`

```sql
CREATE TABLE app.security_incidents (
  incident_id            uuid PRIMARY KEY DEFAULT x_extension.gen_random_uuid(),
  incident_type          varchar(64) NOT NULL,
  severity               varchar(16) NOT NULL,
  status                 varchar(32) NOT NULL DEFAULT 'detected',
  source                 varchar(64),
  summary                varchar(240) NOT NULL,
  details                jsonb NOT NULL DEFAULT '{}'::jsonb,
  affected_user_count    int NOT NULL DEFAULT 0,
  notification_required  boolean NOT NULL DEFAULT false,
  assigned_cpo_user_id   uuid REFERENCES app.users(user_id) ON DELETE SET NULL,
  request_id             uuid,
  detected_at            timestamptz NOT NULL DEFAULT now(),
  cpo_review_due_at      timestamptz NOT NULL DEFAULT now() + interval '30 minutes',
  external_report_due_at timestamptz NOT NULL DEFAULT now() + interval '72 hours',
  cpo_notified_at        timestamptz,
  acknowledged_at        timestamptz,
  notification_decision_at timestamptz,
  resolved_at            timestamptz,
  notified_at            timestamptz,
  kisa_reported_at       timestamptz,
  notification_payload_hash varchar(64),
  external_report_receipt_ref varchar(160),
  evidence_attachment_id uuid,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_security_incidents_severity_allowed CHECK (
    severity IN ('low', 'medium', 'high', 'critical')
  ),
  CONSTRAINT ck_security_incidents_status_allowed CHECK (
    status IN ('detected', 'triage', 'notification_decision', 'reported', 'closed')
  )
);

CREATE INDEX ix_security_incidents_status_detected_at
  ON app.security_incidents (status, detected_at);
CREATE INDEX ix_security_incidents_severity_detected_at
  ON app.security_incidents (severity, detected_at);
CREATE INDEX ix_security_incidents_external_report_due_at
  ON app.security_incidents (external_report_due_at)
  WHERE status <> 'closed';

CREATE TRIGGER trg_security_incidents_touch_updated_at
BEFORE UPDATE ON app.security_incidents
FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
```

PIPA 침해 가능성 감지와 CPO workflow 상태를 저장한다. `/admin/incidents`는 incident
생성, CPO 30분 review, 정보주체 통지 payload hash, 개인정보보호위원회/KISA 72시간 신고
접수번호, 종결 증거를 이 테이블과 `admin_audit_log`에 남긴다. 이상 IP/admin bulk export/
audit chain 깨짐 같은 자동 트리거는 후속 security review/abuse surface에서 확장한다.

### 7.2 운영 권한

- DB 사용자 `pinvi`는 `app`, `ops`, `feature`, `provider_sync` schema에 모두
  CRUD. 단 `feature`, `provider_sync`의 DDL은 `kor-travel-map` Alembic으로만 실행.
- 운영에서는 별도 read-only 사용자 `pinvi_ro`를 두어 BI/모니터링에 사용.
- 패스워드/토큰 hash 컬럼은 절대 평문 저장 금지 (argon2/bcrypt).
- `app.admin_audit_log`는 append-only — DELETE 막는 trigger 또는 권한 분리.

### 7.3 `app.rate_limit_buckets`

HTTP 공통 rate-limit의 운영/staging shared counter다(ADR-038). 원문 IP/email/token은
저장하지 않고 정책명+식별자를 HMAC-SHA256한 bucket hash만 저장한다.

```sql
CREATE TABLE app.rate_limit_buckets (
  bucket_hash  varchar(64) NOT NULL,
  window_start timestamptz NOT NULL,
  limit_name   varchar(80) NOT NULL,
  count        integer NOT NULL DEFAULT 0,
  expires_at   timestamptz NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_rate_limit_buckets PRIMARY KEY (bucket_hash, window_start),
  CONSTRAINT ck_rate_limit_buckets_count_nonnegative CHECK (count >= 0)
);

CREATE INDEX ix_rate_limit_buckets_expires_at
  ON app.rate_limit_buckets (expires_at);
```

`RateLimitMiddleware`가 요청마다 atomic upsert로 `count`를 증가시키고, 만료 bucket은
opportunistic cleanup으로 제거한다. 로컬 개발/테스트/smoke는 기본 memory backend를
사용해 이 테이블에 쓰지 않는다.

## 8. 데이터 보존 / GDPR / 탈퇴

- `app.users.status = 'deleted'`일 때 PII 마스킹 잡 schedule (Dagster):
  - `email` → `deleted-<user_id>@example.invalid`
  - `nickname` → `null`
  - `avatar_url` → `null`
  - 관련 세션 / verification token 일괄 `revoked_at = now()`.
- `app.attachments`는 RustFS 객체와 함께 hard-delete (사용자 명시 요청 시).
- 로그(`admin_audit_logs`)는 90일 보관 후 cold storage 이전 (운영 ADR로 결정).

## 9. 마이그레이션 운영

- 두 Alembic이 같은 DB를 친다 — 실행 순서:
  1. `kor-travel-map alembic upgrade head` (feature/provider_sync)
  2. `pinvi alembic upgrade head` (app/ops)
- 충돌 가능 항목: schema 이름 / 확장 설치 / 함수 정의.
- 가능한 한 본 schema에서 `feature` schema 객체를 참조하지 않는다 (FK 없음).
- backfill은 별도 Dagster job으로 분리 — DDL migration에 데이터 변환 섞지 않음.

## 10. v1 → v2 마이그레이션 매핑

v1의 `apps/api/alembic/versions/`에서 v2로 그대로 가져올 항목:

| v1 migration                               | v2 ADR                    | 비고                                                         |
| ------------------------------------------ | ------------------------- | ------------------------------------------------------------ |
| 0001 initial_core (user/session/trip 기본) | T-105 (대기)              | 컬럼 정렬은 본 §2~§3 골격 사용                               |
| 0023 widen mid-term weather summary        | (`kor-travel-map`에 이관) | feature schema 소유                                          |
| 0024 library spec v3 schema                | (`kor-travel-map`에 이관) | feature schema                                               |
| 0025 provider_source_weather_state         | (`kor-travel-map`에 이관) | provider_sync                                                |
| 0026 outdoor_feature_profiles              | (`kor-travel-map`에 이관) | feature schema                                               |
| 0027 notice_plans                          | T-102 (대기)              | system notice는 본 §5 골격 사용                              |
| 0028 plan_poi_attachments                  | T-137 완료                | 추천 여행 첨부는 본 §3.7의 `curated_plan_attachments`로 개명 |

자세한 매핑은 v2 코드 작성 단계에서 ADR로 박는다.
