# DB 규약 (PostgreSQL / PostGIS / Alembic)

TripMate `app` schema 작업 규칙. v1 `skills/database-architect.ko.md` +
`docs/decisions/20260425-postgres-migration-constraints.md` 정리.

> **scope 주의**: `feature` / `provider_sync` schema는 `python-krtour-map` 소유
> (ADR-003). 본 규약은 TripMate `app` schema에만 적용.

## 1. 기본 원칙

- ORM 모델 / Alembic migration / 테스트 fixture가 같은 계약을 말해야 함
- `timestamptz` 저장 + KST 응용 변환
- 공간 컬럼은 SRID 명시 (`docs/conventions/geospatial.md`)
- 모든 코드 컬럼 (addr_code / provider_code / category_code)은 **문자열** —
  선행 0 보존
- raw vs serving 계층 분리 (TripMate는 주로 serving)
- raw provider 응답 long-term 저장 X
- secret을 DB / fixture / log에 평문 X

## 2. PostgreSQL 16 baseline

- PostgreSQL 16 + PostGIS 3.5
- `x_extension` schema에 extension 설치 (ADR-008)
- 로캘 `en_US.utf8` 운영 — `tripmate_db.col COLLATE "C"`은 명시 컬럼만

## 3. 명명 / 식별자

### 3.1 길이 / 명명

- 모든 identifier 63자 이하 (PostgreSQL limit)
- 실무 권장 40자 이하
- FK / index / unique / check 자동 생성 X — **명시적 이름 부여**

### 3.2 명명 규약

| 종류 | 패턴 | 예 |
|------|------|-----|
| Table | `<plural_snake>` | `users`, `trip_day_pois` |
| Column | `<snake>` | `email_verified_at`, `legal_dong_code` |
| PK | `pk_<table>` | `pk_users` |
| FK | `fk_<src_table>_<src_col>` (≤40자) | `fk_trip_day_pois_day_id` |
| Index | `ix_<table>_<col>[_<col>]` 또는 `idx_<table>_<short>` | `ix_users_email`, `idx_trip_day_pois_sort` |
| Unique | `uq_<table>_<col>[_<col>][_<scope>]` | `uq_notice_plans_slug_active` (partial) |
| Check | `ck_<table>_<short>` | `ck_trips_date_range_order` |
| Trigger | `trg_<table>_<event>` | `trg_users_touch_updated_at` |

### 3.3 짧은 alias 표

긴 테이블 이름은 별칭 — `docs/decisions/20260425-postgres-migration-constraints.md` mirror:

| Table | alias (≤6자) |
|-------|-------------|
| `trip_day_pois` | `tdp` |
| `notice_plans` | `npl` |
| `notice_pois` | `npo` |
| `plan_poi_attachments` | `ppa` |
| `user_oauth_identities` | `uoi` |
| `user_email_verifications` | `uev` |

예시: `fk_ppa_trip_id` (= `fk_plan_poi_attachments_trip_id`, 35자).

## 4. Alembic

### 4.1 파일 명명

`apps/api/alembic/versions/YYYYMMDD_NNNN_<short_slug>.py`

예: `20260601_0001_initial_app_schema.py`, `20260601_0002_trips.py`,
`20260601_0003_pois_collate_c.py`.

### 4.2 운영

```python
def upgrade():
    # 1) schema 생성 (CREATE TABLE / ALTER)
    op.create_table(
        "trips",
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ...
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.user_id"], name="fk_trips_owner_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trip_id", name="pk_trips"),
        sa.CheckConstraint("end_date >= start_date", name="ck_trips_date_range_order"),
    )
    op.create_index("ix_trips_owner_status", "trips", ["owner_user_id", "status", "start_date"])

def downgrade():
    op.drop_index("ix_trips_owner_status", "trips")
    op.drop_table("trips")
```

### 4.3 운영 검증

```bash
# 모델 메타데이터 확인만으로 끝내지 않음 — 실제 PostgreSQL/PostGIS에 적용
docker exec tripmate-postgres dropdb -U tripmate tripmate_migration_check
docker exec tripmate-postgres createdb -U tripmate tripmate_migration_check
TRIPMATE_DATABASE_URL='postgresql+psycopg://tripmate:changeme@localhost:55432/tripmate_migration_check' \
  uv run alembic upgrade head
```

### 4.4 BREAKING 변경

- 컬럼 rename: 새 컬럼 추가 → backfill → 라우터 dual-write → 삭제 (3 단계 PR)
- DROP TABLE: 데이터 마이그레이션 plan 명시 + 백업 후
- 마이그레이션 + 데이터 변환은 별 commit (1 PR이라도 분리)

### 4.5 데이터 마이그레이션

DDL과 backfill을 분리. 한 migration에 데이터 변환 섞지 X.

```python
# 좋은 예
# 0010_add_users_roles.py — DDL만
def upgrade():
    op.add_column("users", sa.Column("roles", postgresql.ARRAY(sa.Text()),
                                     server_default=sa.text("'{user}'::text[]")))

# 0011_backfill_user_roles.py — 데이터만
def upgrade():
    op.execute("UPDATE users SET roles = ARRAY['user', 'admin'] WHERE is_admin = true")
```

## 5. 공간 컬럼

- SRID 4326 (WGS84 lon-lat) — `geometry(Point, 4326)`
- `spatial_index=False`로 선언하고 Alembic에서 GiST 명시 생성:

```python
op.create_table(
    "places",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
)
op.create_index("ix_places_geom", "places", ["geom"], postgresql_using="gist")
```

- 좌표: `ST_MakePoint(lon, lat)` 순서 — 항상
- 자세히는 [geospatial.md](./geospatial.md)

> TripMate `app` schema에는 공간 컬럼이 적음 — feature schema에 위임. 본
> 규약은 app schema의 공간 컬럼 (있다면 `feature_snapshot.coord` JSONB) 또는
> 라이브러리 호출 결과 변환 시 적용.

## 6. JSONB

```python
sa.Column("feature_snapshot", postgresql.JSONB(astext_type=sa.Text()),
          nullable=False, server_default=sa.text("'{}'::jsonb"))
```

- 키는 snake_case
- 응용에서 Pydantic으로 파싱 (`.model_dump()` 결과 저장)
- JSONB 인덱스는 GIN (필요 시):

```python
op.create_index("ix_trip_day_pois_snapshot_gin", "trip_day_pois", ["feature_snapshot"],
                postgresql_using="gin")
```

## 7. Soft delete

- `deleted_at TIMESTAMPTZ NULL` 컬럼
- partial unique: `CREATE UNIQUE INDEX uq_x_y_active ON x (y) WHERE deleted_at IS NULL`
- 쿼리에서 `WHERE deleted_at IS NULL` 일관 적용
- Hard delete는 별 cleanup job (30일 후 등)

## 8. `updated_at` 자동 갱신

```python
op.execute("""
    CREATE OR REPLACE FUNCTION app.touch_updated_at()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      NEW.updated_at := now();
      RETURN NEW;
    END;
    $$;
""")

# trigger 부착
op.execute("""
    CREATE TRIGGER trg_trips_touch_updated_at
    BEFORE UPDATE ON trips
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
""")
```

## 9. Unique 정책

### 9.1 NULL 포함 unique

PostgreSQL 15+ `NULLS NOT DISTINCT`:

```sql
CREATE UNIQUE INDEX uq_trip_companions_invited_email
  ON trip_companions (trip_id, invited_email)
  WHERE invited_email IS NOT NULL
  NULLS NOT DISTINCT;
```

또는 partial:

```sql
CREATE UNIQUE INDEX uq_x ON x (a, b) WHERE c IS NOT NULL;
```

### 9.2 sort_order

SPEC V8 E-6 Critical:

```python
sa.Column("sort_order", sa.Text(collation="C"), nullable=False)
# UNIQUE는 partial 또는 (day_id, sort_order COLLATE "C")
```

자세히는 `docs/data-model.md` §2.3 + `docs/api/pois.md`.

## 10. 외래키 / 인덱스

- 모든 FK는 같은 컬럼에 index 자동 생성 안 됨 → 명시:
  ```python
  op.create_index("ix_trip_day_pois_day_id", "trip_day_pois", ["day_id"])
  ```
- ON DELETE는 명시 (`CASCADE` / `SET NULL` / `RESTRICT`)
- cross-schema FK 금지 (`app` → `feature` — ADR-003)
- 자기 참조 FK는 self-FK 명시 (예: `plan_poi_attachments.source_attachment_id`)

## 11. CHECK / NOT NULL

- NOT NULL을 가능한 한 많이
- enum 같은 값은 CHECK:
  ```python
  sa.CheckConstraint(
      "status IN ('active', 'pending_verification', 'pending_profile', 'disabled', 'deleted')",
      name="ck_users_status"
  )
  ```
- 단일 대상 다중 컬럼 중 정확히 하나:
  ```python
  sa.CheckConstraint(
      "num_nonnulls(trip_id, trip_poi_id, notice_plan_id, notice_poi_id) = 1",
      name="ck_plan_poi_attachments_single_target"
  )
  ```

## 12. Postgres extension

- 모두 `x_extension` schema (ADR-008)
- `search_path = 'public, x_extension'` (connect_args)

```python
op.execute("CREATE SCHEMA IF NOT EXISTS x_extension")
op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension")
op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA x_extension")
op.execute("CREATE EXTENSION IF NOT EXISTS postgis SCHEMA x_extension")
```

## 13. ETL / 보존 / Privacy

- raw provider 응답 본 `app` schema에 저장 X (라이브러리 `source_records`로)
- PII 보존 정책 (`docs/compliance/pipa.md` §2)
- 보존 만료 cleanup은 Dagster job (`docs/runbooks/etl.md` §10)

## 14. 권한 / 보안

- DB 사용자 `tripmate`: `app`, `ops`, `feature`, `provider_sync` 모두 CRUD
- 단 `feature`/`provider_sync` schema DDL은 `python-krtour-map` Alembic만
- 운영 read-only 사용자 `tripmate_ro` 별도 (BI / 모니터링)
- 비밀번호 / 토큰 hash 컬럼은 평문 저장 절대 X (Argon2 / bcrypt)
- `admin_audit_log`는 append-only (DELETE 거부 trigger 또는 권한 분리)

## 15. 자주 묻는 패턴

| 패턴 | 예 |
|------|-----|
| optimistic lock | `version INTEGER NOT NULL DEFAULT 1` + `If-Match` 헤더 |
| audit chain | `prev_hash CHAR(64) + content_hash CHAR(64)` + trigger 또는 응용 |
| 시계열 (가격/날씨) | BRIN(observed_at) + (feature_id, item_key, observed_at) PK — 라이브러리 |
| 큐 (email_queue) | `status` enum + `SKIP LOCKED` |
| 폴리모픽 1:N | 4 FK 중 1 NOT NULL CHECK |

## 16. AI agent 체크리스트

새 schema 변경 시:

- [ ] FK / index / unique / check 모두 명시 이름
- [ ] 모든 timestamp는 `timestamptz`
- [ ] `updated_at` trigger 부착 (필요 시)
- [ ] 코드 컬럼 (legal_dong_code 등)은 TEXT
- [ ] enum 컬럼은 CHECK 제약
- [ ] cross-schema FK 안 만들었나 (`app` → `feature` 금지)
- [ ] `uv run alembic upgrade head` 실 PostGIS 검증
- [ ] `apps/api/tests/integration/test_migration_contract.py` 갱신
- [ ] `docs/postgres-schema.md` 본문 갱신
- [ ] `docs/data-model.md` cross-ref 추가
