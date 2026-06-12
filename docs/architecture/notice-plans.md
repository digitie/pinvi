# Curated Trip Plan 도메인 — 추천 여행 + POI + 첨부

본 문서는 TripMate v2의 **추천/큐레이션 여행 plan** 도메인을 정의한다.
ADR-029에 따라 DB/ORM 정본 이름은 `curated_trip_plans` 계열이고, 기존 사용자 API
경로(`/notice-plans`)와 응답 필드(`notice_plan_id` 등)는 Sprint 4 호환을 위해
유지한다. `app.notice_plans`는 운영 공지(system notice) 전용이다.
ADR-036에 따라 curated trip plan은 **POI 묶음**이며, 각 POI의 `feature_id`는
nullable이다. 생성 소스는 TripMate 자체 큐레이션과 krtour-map `curated_features`
1:1 import가 모두 정식이다. 외부 연계(`tripmate-agent` 등)가 krtour feature를 알고
들어올 때만 feature-backed POI로 연결하고, 같은 plan에 해당 feature POI가 없으면
새로 만든다.

v1
(`apps/api/app/services/notice_plan.py`, `app/models/trip.py`,
`alembic/versions/20260521_0027_notice_plans.py`,
`20260522_0028_plan_poi_attachments.py`)에서 9개월간 운영한 자산을 v2로 가져온다.

## 1. 명명 정정 — 두 가지 "notice"

v1에서 같은 단어가 두 개의 별개 개념에 쓰여 혼동이 누적됐다. v2에서는 다음과 같이
분리·명시한다.

| 개념 | 어디에 있나 | 소유 | 약어 |
|------|-----------|------|------|
| 공지 / 자연현상 feature (사고·시설 통제·바다갈라짐·만조/간조) | `feature.notices` (혹은 `feature.features WHERE kind='notice'`) | `python-krtour-map` | **notice feature** |
| Admin이 작성한 추천 여행 plan (사용자가 자기 trip으로 copy 가능) | `app.curated_trip_plans` + `app.curated_plan_pois` | TripMate | **curated trip plan** |

본 문서는 후자(**curated trip plan**)를 다룬다. 전자는 SPEC V8 D-10 +
`docs/spec/v8/01-data.md` §3 (라이브러리 위임 — 7 Feature 중 `notice` kind).

## 2. 도메인 개요

추천 여행 plan은 **Admin이 운영하는 "이렇게 여행해 보세요" 콘텐츠**다.

- Admin/운영자/TripMate agent가 slug + 제목 + 카테고리 + 요약 + 출처 + 기간으로
  TripMate-native plan 작성
- krtour-map `curated_features` REST 계약이 확정되면 TripMate가 해당 정보를 조회해
  `curated_trip_plans` / `curated_plan_pois`로 1:1 복사
- POI를 day별로 sort_order에 따라 배치 — 사용자 trip과 동일한 구조
- POI는 `feature_id` 없이도 존재 가능. 단 외부/agent 연계가 feature를 제공하면
  `feature_id`로 기존 curated POI를 찾아 연결하고, 없으면 새 POI를 생성
- POI마다 memo / budget / custom marker 등 추천 정보
- 파일 첨부 (이미지 / 문서) — RustFS에 저장
- `is_published=true`인 plan을 일반 사용자가 listing/조회
- 사용자가 "내 trip으로 가져오기" → 선택한 POI를 자기 trip에 복사 (첨부도 함께)

권한:

- 작성/수정/삭제: Admin (`roles[]`에 `admin` 또는 `operator`)
- 조회: published만 일반 사용자, 모든 plan은 admin
- copy: 인증 사용자

## 3. DB 모델 (`app` schema)

### 3.1 `app.curated_trip_plans`

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `curated_plan_id` | `uuid` (PK) | |
| `slug` | `text` | URL-safe, partial unique on `deleted_at IS NULL` |
| `title` | `text` NOT NULL | |
| `category` | `text` | 예: `recommended`, `themed`, `seasonal` |
| `summary` | `text` | nullable |
| `source_name` | `text` | "한국관광공사 추천 코스" 등 |
| `destination` | `text` | "부산", "강원" 등 자유 텍스트 |
| `starts_on` | `date` | nullable. 함께 채우거나 함께 비움 (CHECK) |
| `ends_on` | `date` | nullable |
| `is_published` | `boolean` NOT NULL DEFAULT false | |
| `created_by_admin_id` | `uuid` FK `app.users` | RESTRICT |
| `updated_by_admin_id` | `uuid` FK `app.users` | RESTRICT |
| `version` | `int` NOT NULL DEFAULT 1 | optimistic lock |
| `deleted_at` | `timestamptz` | soft delete |
| `created_at`, `updated_at` | `timestamptz` | |

인덱스:

- `uq_curated_trip_plans_slug_active` (partial `WHERE deleted_at IS NULL`)
- `ix_curated_trip_plans_published (is_published, updated_at)`
- `ix_curated_trip_plans_category (category, updated_at)`
- `ix_curated_trip_plans_created_by_admin`, `ix_curated_trip_plans_updated_by_admin`

CHECK:

- 기간은 둘 다 null이거나 둘 다 채워짐, `ends_on >= starts_on`

### 3.2 `app.curated_plan_pois`

추천 plan의 POI들. 구조가 `app.trip_pois`와 거의 동일.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `curated_poi_id` | `uuid` (PK) | |
| `curated_plan_id` | `uuid` FK | CASCADE |
| `day_index` | `int` NOT NULL DEFAULT 1 | |
| `sort_order` | `text COLLATE "C"` NOT NULL | LexoRank — SPEC V8 E-6 |
| `feature_id` | `text` | nullable. krtour `feature.features.feature_id` reference (FK 없음, ADR-003/036) |
| `map_feature_id` | `uuid` | v1 호환용 (라이브러리 UUID 시절 cursor — v2에서는 미사용 후보) |
| `snapshot` | `jsonb` | feature 캐시 (이름/좌표/카테고리) |
| `memo` | `text` | |
| `budget` | `numeric(12,2)` | |
| `currency` | `char(3)` NOT NULL DEFAULT 'KRW' | |
| `user_url` | `text` | 추천자가 참조할 외부 링크 |
| `custom_marker_color` | `text` | P-01~P-16 |
| `custom_marker_icon` | `text` | maki id |
| `version` | `int` NOT NULL DEFAULT 1 | |
| `deleted_at` | `timestamptz` | |
| `created_at`, `updated_at` | `timestamptz` | |

인덱스:

- UNIQUE `(curated_plan_id, day_index, sort_order COLLATE "C")`
- `(curated_plan_id, day_index)`, `(feature_id)` partial nullable lookup

정책:

- 사람이 만든 자유 POI는 `feature_id = null`일 수 있다.
- `tripmate-agent` 같은 외부 연계가 feature를 알고 있으면
  `ensure_plan_poi_for_feature()` 경로로 같은 plan의 기존 feature-backed POI를 재사용한다.
- 기존 POI가 없으면 새 `curated_plan_pois` row를 만들고 plan에 연결한다.
- krtour feature schema와 cross-schema FK는 만들지 않는다.

### 3.2.1 생성 소스와 krtour `curated_features` import

Curated trip plan의 생성 소스는 하나로 제한하지 않는다.

| 소스 | 설명 | 현재 상태 |
|------|------|----------|
| TripMate-native 큐레이션 | Admin/운영자/TripMate agent가 TripMate 안에서 직접 기획·작성한 추천 여행 plan | 현재 정본 흐름 |
| krtour `curated_features` import | TripMate가 krtour-map REST API로 curated feature 정보를 가져와 TripMate plan으로 1:1 복사 | REST 상세 계약 대기 |

krtour import가 붙으면 매핑은 다음 원칙을 따른다.

| krtour-map | TripMate |
|------------|----------|
| curated feature 1건 | `app.curated_trip_plans` 1건 |
| curated feature의 하위 항목/POI | `app.curated_plan_pois` 여러 건 |
| 하위 항목의 `feature_id` | `curated_plan_pois.feature_id`에 nullable 저장 |
| 하위 항목의 표시명/좌표/카테고리 snapshot | `curated_plan_pois.feature_snapshot` |
| 순서/일차 정보 | `day_index`, `sort_order` |

이 import는 TripMate-native 큐레이션을 대체하지 않는다. krtour `curated_features`는
추가 소스이며, TripMate가 자체적으로 직접 만든 추천 plan도 같은 테이블에 계속 저장한다.

REST 계약 확정 후 provenance가 필요하면 별도 migration으로 다음 후보 컬럼을 검토한다.

- plan: `source_system`, `source_curated_feature_id`, `source_curated_feature_version`,
  `source_imported_at`
- POI: `source_curated_feature_item_id`, `source_curated_feature_id`

계약이 확정되기 전에는 위 컬럼을 선행 확정하지 않는다. 그 전까지는 기존 `source_name`과
`feature_snapshot`만으로 표시 정보를 보존한다.

### 3.3 `app.curated_plan_attachments` — 단일 테이블 다중 대상

v1의 핵심 결정: **4개 대상(사용자 trip, 사용자 trip_poi, curated_plan, curated_poi)의
파일 첨부를 한 테이블에서 관리**.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `attachment_id` | `uuid` (PK) | |
| `trip_id` | `uuid` FK `app.trips` | CASCADE — 단일 대상 |
| `trip_poi_id` | `uuid` FK `app.trip_pois` (또는 `trip_day_pois`) | CASCADE |
| `curated_plan_id` | `uuid` FK `app.curated_trip_plans` | CASCADE |
| `curated_poi_id` | `uuid` FK `app.curated_plan_pois` | CASCADE |
| `source_attachment_id` | `uuid` self FK | SET NULL — notice → trip copy 시 원본 추적 |
| `bucket` | `text` NOT NULL | RustFS bucket (`tripmate-media` 기본) |
| `storage_key` | `text` NOT NULL | RustFS object key |
| `original_filename` | `text` NOT NULL | |
| `content_type` | `text` NOT NULL | |
| `byte_size` | `bigint` NOT NULL | `> 0` |
| `public_url` | `text` | public base URL 파생 |
| `checksum_sha256` | `text` | 클라이언트 옵션 |
| `role` | `text` NOT NULL DEFAULT 'attachment' | `attachment` / `image` / `document` / `reference` |
| `description` | `text` | |
| `sort_order` | `int` NOT NULL DEFAULT 0 | `>= 0` |
| `uploaded_by_user_id` | `uuid` FK `app.users` | |
| `deleted_at` | `timestamptz` | |
| `created_at`, `updated_at` | `timestamptz` | |

핵심 CHECK:

- `num_nonnulls(trip_id, trip_poi_id, curated_plan_id, curated_poi_id) = 1`
- `byte_size > 0`
- `sort_order >= 0`
- `role IN ('attachment', 'image', 'document', 'reference')`

인덱스: `(trip_id, sort_order)`, `(trip_poi_id, sort_order)`,
`(curated_plan_id, sort_order)`, `(curated_poi_id, sort_order)`,
`(source_attachment_id)`, `(bucket, storage_key)`.

## 4. API endpoint

### 4.1 일반 사용자

- `GET /notice-plans?category=...&page=&limit=` — published listing
- `GET /notice-plans/{plan_id}` — published 상세 (POI + 첨부 포함)
- `POST /notice-plans/{plan_id}/copy` — 사용자 trip으로 복사 (선택 POI ids,
  새 trip 생성 or 기존 trip에 추가)

### 4.2 Admin

- `GET /admin/notice-plans` — 모든 plan (filter: `is_published`, category, slug, 작성자)
- `POST /admin/notice-plans` — 생성
- `GET /admin/notice-plans/{plan_id}` — 상세
- `PATCH /admin/notice-plans/{plan_id}` — 메타 편집 (`If-Match: version`)
- `DELETE /admin/notice-plans/{plan_id}` — soft delete
- `POST /admin/notice-plans/{plan_id}/pois` — POI 추가
- `PATCH /admin/notice-plans/{plan_id}/pois/{poi_id}` — POI 편집
- `DELETE /admin/notice-plans/{plan_id}/pois/{poi_id}` — soft delete
- `POST /admin/notice-plans/{plan_id}/pois/reorder` — fractional indexing

### 4.3 첨부 (Storage)

공통:

- `POST /storage/upload-urls` — presigned PUT URL 발급 (목적/사이즈/MIME 검증)

사용자 여행 첨부:

- `GET/POST /trips/{trip_id}/attachments[/{attachment_id}]`
- `GET/POST /trips/{trip_id}/pois/{poi_id}/attachments[/{attachment_id}]`

관리자 공지 첨부:

- `GET/POST /admin/notice-plans/{plan_id}/attachments[/{attachment_id}]`
- `GET/POST /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments[/{attachment_id}]`

관리자 RustFS 객체 직접 관리:

- `GET /admin/rustfs/objects?prefix=&limit=`
- `DELETE /admin/rustfs/objects?key=`

## 5. Copy 흐름 (사용자 가져오기)

```
사용자가 /notice-plans/{plan_id} 페이지에서 [내 trip으로 가져오기]
  ↓
POST /notice-plans/{plan_id}/copy
body: {
  target_trip_id?: UUID,        // null이면 새 trip 생성
  poi_ids: [UUID, ...]          // 가져올 POI subset
}
  ↓
서버:
  1. curated trip plan + 선택 POI 로드
  2. target_trip_id null → 새 trip 생성 (제목=notice.title, 기간=notice 기간 또는 사용자 입력)
  3. target_trip_id 채워짐 → 권한 검사 (소유자 또는 동반자 editor+)
  4. 필요한 trip_days 생성
  5. curated_plan_pois를 trip_pois로 INSERT
     - sort_order: 새 trip이면 그대로, 기존 trip이면 마지막 + 다음 LexoRank
     - feature_id: 있으면 그대로, 없으면 null 유지(snapshot만)
  6. curated_plan_attachments도 복사 (source_attachment_id에 원본 ref)
     - RustFS object는 복사하지 않음 — 같은 object_key 공유 (CDN 캐시 효율)
  7. 응답: { trip_id, created_trip: bool, copied_poi_ids: [...] }
```

핵심:

- **RustFS object는 복사하지 않음** — source object 그대로 참조. `source_attachment_id`로
  원본 추적
- 일반 첨부 `DELETE`는 row soft delete만, object 자체 삭제는 admin RustFS endpoint
- 큐레이션 첨부가 여러 사용자 trip에 copy되어 있을 수 있으므로 object 즉시 삭제 금지

## 6. RustFS 설정 (v1 정합)

| 환경변수 | 비고 |
|---------|------|
| `TRIPMATE_RUSTFS_ENDPOINT_URL` | 내부 API endpoint (FastAPI ↔ RustFS) |
| `TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL` | 브라우저 presigned PUT (보통 reverse proxy 경로) |
| `TRIPMATE_RUSTFS_BUCKET` | `tripmate-media` 기본 |
| `TRIPMATE_RUSTFS_ACCESS_KEY_ID` | |
| `TRIPMATE_RUSTFS_SECRET_ACCESS_KEY` | |

object key 패턴: `user-uploads/{purpose}/{user_id}/yyyy/mm/{uuid}.{ext}`.

presigned PUT: `AWS4-HMAC-SHA256` + `UNSIGNED-PAYLOAD`.

관리자 ListObjectsV2 / DeleteObject 호환.

`python-krtour-map`이 RustFS feature media에 같은 컨테이너를 쓰면 endpoint/keys를
공유. 두 compose가 동시에 12101/12105을 점유하지 않도록 한 쪽만 실행 (v1
운영 노트).

## 7. SPEC V8 정합

| SPEC V8 항목 | 본 문서 |
|------|---------|
| D-10 notice feature (공지·자연현상) | 본 문서와 **별개 개념** (라이브러리 소유). 본 §1 표 참고 |
| H-3 Trip API + POI 첨부 | 본 §4 |
| M-2 `/admin/notice-plans` (잠재 페이지) | 본 §4.2 (Admin 페이지 — Sprint 6에서 박음) |
| O-6 admin_audit_log | curated trip plan 변경 시 자동 기록 (POST/PATCH/DELETE) |

## 8. Sprint 매핑

| 항목 | Sprint | 산출물 |
|------|--------|--------|
| `app.curated_trip_plans` + `curated_plan_pois` Alembic | Sprint 2 | `apps/api/alembic/versions/20260602_0005_notice_plans_and_attachments.py` + T-137 rename |
| `app.curated_plan_attachments` (단일 테이블 4 대상) | Sprint 2 | `apps/api/alembic/versions/20260607_0011_curated_trip_plans.py` |
| 사용자 `GET /notice-plans`, `/copy` | Sprint 4 | `apps/api/app/api/v1/notice_plans.py` |
| Admin `/admin/notice-plans/*` | Sprint 6 | `apps/api/app/api/v1/admin/notice_plans.py` + UI |
| `POST /storage/upload-urls` presigned PUT | Sprint 2 | `apps/api/app/api/v1/storage.py` |
| 사용자 UI: notice plan 카드 + 가져오기 다이얼로그 | Sprint 4 | `apps/web/app/(app)/notice-plans/...` |
| Admin UI: notice plan 작성기 | Sprint 6 | `apps/web/app/admin/notice-plans/...` |

## 9. v1 → v2 이전 매핑

v1 자산:

- `apps/api/alembic/versions/20260521_0027_notice_plans.py`
- `apps/api/alembic/versions/20260522_0028_plan_poi_attachments.py`
- `apps/api/app/models/curated_plan.py` (`CuratedTripPlan`, `CuratedPlanPoi`)
- `apps/api/app/models/attachment.py` (`CuratedPlanAttachment`)
- `apps/api/app/schemas/notice.py` (Pydantic)
- `apps/api/app/services/notice_plan.py` (copy 흐름)
- `apps/api/app/services/plan_poi_attachment.py` (첨부)
- `apps/api/app/api/routes/notice.py` (사용자 + admin 라우터)
- `apps/api/tests/test_notice_plans_api.py`
- `docs/architecture/plan-poi-attachments.md`

v2 이전 절차 (Sprint 2 진입 시):

1. v1 코드 cherry-pick 하지 않고 **본 문서 + SPEC V8 +
   `docs/postgres-schema.md` 기준으로 재작성** — schema 정합성과 import-linter
   계약 준수 위해.
2. v1의 `map_feature_id UUID` 컬럼은 v2에서 제거 후보. 라이브러리의 `feature_id
   TEXT`만 reference.
3. v1의 `trip_pois`에서 `position INT` → v2 `trip_day_pois.sort_order TEXT
   COLLATE "C"` (SPEC V8 E-6) 변경 반영.
4. v1 테스트는 `apps/api/tests/integration/test_notice_plans_api.py`로 이전 시
   ASGI 직접 호출 패턴 사용.

## 10. UI 가이드

사용자 listing 화면:

- `/notice-plans` (또는 메인 페이지의 한 섹션) — 카테고리 탭 + 카드 그리드
- 카드: 대표 이미지 (첫 image attachment) + 제목 + 출처 + 기간 + POI 수
- 클릭 → 상세 페이지: 지도 + day별 POI 리스트 + 각 POI의 memo/budget/첨부

가져오기 다이얼로그:

```
[추천 여행: 부산 2박 3일 — KTO]
┌─ 가져올 POI 선택 (3/8 선택됨) ────────────────┐
│ ☑ Day 1                                        │
│   ☑ 광안리 해수욕장                            │
│   ☑ 자갈치 시장                                │
│   ☐ 부산타워                                   │
│ ☑ Day 2                                        │
│   ☑ 감천문화마을                               │
│   ☐ ...                                       │
│                                                │
│ 가져올 곳:                                     │
│   ● 새 여행 만들기 (제목: 부산 2박 3일)        │
│   ○ 기존 여행 선택: [드롭다운]                │
│                                                │
│           [취소] [가져오기]                    │
└────────────────────────────────────────────────┘
```

가져오기 후 토스트: "3개 POI를 새 여행에 추가했습니다" + [여행 보기] 버튼.

## 11. 관련 문서

- `docs/data-model.md` §2 (사용자 도메인 — Trip / POI)
- `docs/postgres-schema.md` (DDL 골격)
- `docs/spec/v8/01-data.md` §3 (라이브러리 위임 — 공지 feature)
- `docs/spec/v8/04-admin.md` (Admin notice plan UI 위치)
- `docs/architecture/frontend.md` (UI 컴포넌트 — Sprint 4/6)
