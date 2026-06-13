# 정규화 패턴

1NF~BCNF 일반 정규화 + denormalization 패턴 + Pinvi 도메인 적용 가이드.
v1 `skills/normalization-patterns.ko.md` 정리.

## 1. 정규형 요약

| Form | 핵심 룰 |
|------|---------|
| **1NF** | atomic 값. 다중 값 컬럼 X (배열은 케이스별) |
| **2NF** | composite PK에 부분 의존 X |
| **3NF** | 비 PK → 비 PK 전이 의존 X |
| **BCNF** | 모든 determinant가 candidate key |

## 2. Pinvi 적용

### 2.1 1NF

- `users.email` — atomic 문자열 ✓
- `users.roles TEXT[]` — array, 단 값 자체는 atomic ✓
- "phone_number_list TEXT" — comma-separated 금지 ✗ → 별 테이블 또는 JSONB

### 2.2 2NF

- `user_consents (user_id, consent_type, version)` composite PK
- `agreed_at`, `withdrawn_at`는 모든 PK에 의존 ✓
- `consent_label` (예: "이용약관")은 `consent_type`에만 의존 → 별 테이블 또는 enum 처리

### 2.3 3NF

- `users.residence_sigungu_code` → `sigungu_name` 전이 X — `sigungu_name`는 별 테이블 (또는 라이브러리)
- 컬럼 갱신 시점이 다른 columns 분리

### 2.4 BCNF

대부분 도메인에서 3NF로 충분. notice plan / poi처럼 명백한 multi-entity는
이미 분리.

## 3. Denormalization 패턴

| 패턴 | 용도 | 예 |
|------|------|----|
| 파생 컬럼 | 자주 계산되는 값 캐시 | `trips.poi_count` (옵션) |
| 중복 컬럼 | join 회피 | `trip_pois.feature_snapshot.coord` |
| 사전 조인 테이블 | 복잡한 view | `area_feature_counts` (라이브러리) |
| 히스토리 스냅샷 | 시점 데이터 보존 | `trip_pois.feature_snapshot` |
| 카운터 컬럼 | aggregate 없이 빠른 조회 | `notice_plans.poi_count` (cron 갱신) |
| JSON/JSONB | 가변 shape | `trip_pois.feature_snapshot`, `gemini_research_runs.result_sections` |

원칙:

- 정규화 우선 → 측정된 병목에만 denorm
- denorm 컬럼은 trigger / 응용 / cron으로 동기 유지 정책 명시
- snapshot은 의도적 — 라이브러리 변경 시 UI 무결성 위해 (`docs/api/pois.md` §5)

## 4. 공통 컬럼

모든 테이블 표준:

| 컬럼 | 비고 |
|------|------|
| `<x>_id UUID PRIMARY KEY DEFAULT gen_random_uuid()` | natural key 없는 경우 |
| `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` | trigger 자동 갱신 |
| `deleted_at TIMESTAMPTZ NULL` | soft delete (필요 시) |
| `version INTEGER NOT NULL DEFAULT 1` | optimistic lock 필요 시 |

## 5. 다국어 (v2)

- locale별 컬럼 X (`name_ko`, `name_en`, ...)
- 별 translation 테이블:

  ```sql
  CREATE TABLE app.category_translations (
    category_key TEXT NOT NULL REFERENCES app.category_mappings(category_key),
    locale       VARCHAR(8) NOT NULL,    -- 'ko', 'en', 'ja'
    display_name TEXT NOT NULL,
    PRIMARY KEY (category_key, locale)
  );
  ```

- v1.0은 ko 만 (next-intl 메시지 카탈로그 분리)

## 6. 폴리모픽 1:N

`curated_plan_attachments`처럼 한 row가 4 대상 중 1 가리키는 경우:

```sql
CHECK (num_nonnulls(trip_id, trip_poi_id, curated_plan_id, curated_poi_id) = 1)
```

장점:

- 단일 테이블 — 첨부 로직 일관
- 검색 단순 (`WHERE curated_plan_id = ...`)

단점:

- FK는 4개 모두 ON DELETE CASCADE — 동작 일관성 보장

대안:

- 별 테이블 (`trip_attachments`, `trip_poi_attachments`, ...) — 작은 도메인이면 OK
- 본 저장소는 단일 테이블 채택 (v1 호환)

## 7. 시계열 (시계열 데이터)

라이브러리 `feature.weather_values` / `price_values`처럼:

```sql
CREATE TABLE feature.price_values (
  feature_id   TEXT NOT NULL,
  item_key     TEXT NOT NULL,
  observed_at  TIMESTAMPTZ NOT NULL,
  value        NUMERIC(12, 2) NOT NULL,
  PRIMARY KEY (feature_id, item_key, observed_at)
);

CREATE INDEX ix_price_values_observed_brin ON feature.price_values USING brin (observed_at);
```

BRIN 인덱스 — 대량 append-only 시계열에 적합.

Pinvi `app` schema에는 시계열 거의 없음 (notification outbox 정도).

## 8. AI agent 체크리스트

새 테이블 설계 시:

- [ ] 1NF: atomic 값 / multi-value 제거
- [ ] 2NF / 3NF / BCNF 점검
- [ ] PK / FK / unique / check 명시 이름
- [ ] 공통 컬럼 (`*_id`, `created_at`, `updated_at`)
- [ ] 시계열이면 BRIN index
- [ ] 폴리모픽 1:N이면 CHECK `num_nonnulls = 1`
- [ ] 다국어 컬럼 추가 X — 별 translation 테이블
- [ ] Snapshot / denorm 필요한지 검토 → 동기 정책 명시
- [ ] `docs/data-model.md` + `docs/postgres-schema.md` 갱신
