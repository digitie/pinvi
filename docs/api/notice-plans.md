# Notice Plan API (`/notice-plans/*`, `/admin/notice-plans/*`)

Admin이 작성한 **추천 여행 plan** 사용자 조회 + 사용자 trip으로 copy + Admin CRUD.
도메인 상세는 [`docs/architecture/notice-plans.md`](../architecture/notice-plans.md).
공통 규약 [`common.md`](./common.md).

> **혼동 주의**: 본 문서의 "notice plan" ≠ SPEC V8 D-10 "notice feature"
> (지도 위 공지·자연현상). 두 도메인은 별개. 자세히는 ADR-013.

## 1. 사용자 API

### 1.1 `GET /notice-plans`

published 추천 plan 목록.

```http
GET /notice-plans?category=recommended&page=1&limit=20
Cookie: tripmate_access=...
```

```jsonc
{
  "data": {
    "items": [
      {
        "notice_plan_id": "uuid",
        "slug": "busan-2-night-3-day",
        "title": "부산 2박 3일",
        "category": "recommended",
        "summary": "...",
        "source_name": "한국관광공사 추천",
        "destination": "부산",
        "starts_on": "2026-06-01",
        "ends_on": "2026-06-03",
        "cover_attachment": { /* image attachment */ },
        "poi_count": 8,
        "updated_at": "..."
      }
    ]
  },
  "meta": { "page": 1, "limit": 20, "total": 42 }
}
```

`is_published = true AND deleted_at IS NULL`만. category 필터 옵션.

### 1.2 `GET /notice-plans/{plan_id}`

상세 — POI 목록 + 첨부 포함.

```jsonc
{
  "data": {
    "notice_plan_id": "uuid",
    "slug": "...",
    "title": "...",
    "category": "...",
    "summary": "...",
    "source_name": "...",
    "destination": "...",
    "starts_on": "...",
    "ends_on": "...",
    "is_published": true,
    "version": 3,
    "attachments": [
      {
        "attachment_id": "uuid",
        "storage_key": "...",
        "content_type": "image/jpeg",
        "role": "image",
        "sort_order": 0
      }
    ],
    "pois": [
      {
        "id": "uuid",
        "day_index": 1,
        "sort_order": "a1",
        "feature_id": "f_2611000000_p_...",
        "feature_snapshot": { "name": "광안리 해수욕장", "coord": [129.118, 35.155], "category": "해수욕장", "marker_color": "P-07" },
        "memo": "일출 명소",
        "budget": null,
        "user_url": null,
        "attachments": [/* ... */]
      }
    ]
  }
}
```

`feature_snapshot`은 적재 시점 캐시. 최신 feature 정보는 클라이언트가 `feature_id`로
`GET /features/{id}` 호출하면 됨 (옵션).

### 1.3 `POST /notice-plans/{plan_id}/copy`

```http
POST /notice-plans/{plan_id}/copy
Content-Type: application/json
Cookie: tripmate_access=...

{
  "target_trip_id": null,            // null이면 새 trip 생성
  "trip_title": "부산 여행 (내가 추가)",  // null이면 notice title 사용
  "trip_start_date": "2026-07-15",   // null이면 notice 기간 사용 또는 미정
  "trip_end_date": "2026-07-17",
  "poi_ids": ["uuid", "uuid", ...]   // 가져올 POI subset (전체면 비움 또는 모든 ID)
}
```

응답 201:

```jsonc
{
  "data": {
    "trip_id": "uuid",
    "created_trip": true,                 // 새로 만들었나
    "copied_poi_ids": ["uuid", ...],      // 새로 생성된 trip_pois IDs
    "skipped_poi_ids": [],                // 라이브러리 feature 없어서 skip한 IDs (옵션)
    "copied_attachment_count": 5
  }
}
```

서버 처리:

1. notice plan + 선택 POI 로드 + 권한 검증 (published or admin)
2. target_trip_id null → 새 trip 생성
3. target_trip_id 채워짐 → owner / editor 권한 검증
4. 필요한 `trip_days` 생성 (`day_index`)
5. notice_pois → `trip_day_pois`로 INSERT (`sort_order`는 새 trip이면 그대로,
   기존 trip이면 마지막 + LexoRank append)
6. `plan_poi_attachments` 복사 (`source_attachment_id` 설정, `storage_key` 동일)
7. RustFS object는 **복사 안 함** (같은 object 참조)

에러:

- `403 PERMISSION_DENIED` — target_trip_id가 사용자 trip이 아님
- `404 RESOURCE_NOT_FOUND` — notice plan published=false
- `422 VALIDATION_ERROR` — poi_ids에 존재하지 않는 ID
- `409 VERSION_CONFLICT` — target_trip 동시 편집 충돌

## 2. Admin API

### 2.1 `GET /admin/notice-plans`

```http
GET /admin/notice-plans?q=is_published:true+category:seasonal&page=1
```

- 모든 plan (published, draft, archived)
- 검색 문법 SPEC V8 M-9

### 2.2 `POST /admin/notice-plans`

```http
POST /admin/notice-plans
Content-Type: application/json

{
  "slug": "busan-summer-2026",
  "title": "...",
  "category": "seasonal",
  "summary": "...",
  "source_name": "한국관광공사",
  "destination": "부산",
  "starts_on": "2026-07-01",
  "ends_on": "2026-08-31",
  "is_published": false
}
```

생성 후 POI는 별도 endpoint로 추가.

### 2.3 `PATCH /admin/notice-plans/{plan_id}`

```http
PATCH /admin/notice-plans/{plan_id}
If-Match: 3
Content-Type: application/json

{ "is_published": true, "summary": "..." }
```

`updated_by_admin_id` 자동 기록 + `admin_audit_log` chain.

### 2.4 `DELETE /admin/notice-plans/{plan_id}`

`deleted_at = now()`. 단 슬러그는 partial unique index 덕에 같은 slug 재사용
가능.

### 2.5 POI 추가 / 편집 / 순서 변경

```http
POST /admin/notice-plans/{plan_id}/pois
PATCH /admin/notice-plans/{plan_id}/pois/{poi_id}
DELETE /admin/notice-plans/{plan_id}/pois/{poi_id}
POST /admin/notice-plans/{plan_id}/pois/reorder
```

body 셰입은 [`pois.md`](./pois.md)와 거의 동일 (`notice_plan_id` 자동 채움,
trip 권한 검사 대신 admin 권한 검사).

### 2.6 첨부

```http
GET /admin/notice-plans/{plan_id}/attachments
POST /admin/notice-plans/{plan_id}/attachments
DELETE /admin/notice-plans/{plan_id}/attachments/{attachment_id}

GET /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments
POST /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments
DELETE /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments/{attachment_id}
```

자세히는 [`storage.md`](./storage.md).

## 3. 권한 매트릭스

| 액션 | 인증 사용자 | admin | operator | cpo |
|------|------------|-------|----------|-----|
| `GET /notice-plans` (published) | ✓ | ✓ | ✓ | ✓ |
| `GET /notice-plans/{id}` (published) | ✓ | ✓ | ✓ | ✓ |
| `POST /notice-plans/{id}/copy` | ✓ | ✓ | ✓ | ✓ |
| `GET /admin/notice-plans` (all) | ✗ | ✓ | ✓ | ✓ |
| `POST /admin/notice-plans` | ✗ | ✓ | ✓ | ✗ |
| `PATCH /admin/notice-plans/{id}` | ✗ | ✓ | ✓ | ✗ |
| `DELETE /admin/notice-plans/{id}` | ✗ | ✓ | ✗ | ✗ |
| `POST /admin/notice-plans/{id}/pois` | ✗ | ✓ | ✓ | ✗ |
| `*/attachments` (admin) | ✗ | ✓ | ✓ | ✗ |

## 4. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/notice.py` Pydantic + `packages/schemas/src/notice-plan.ts` Zod
- [ ] `apps/api/app/services/notice_plan.py` (v1 로직 재작성, schema 정합성 보장)
- [ ] `apps/api/app/api/v1/notice_plans.py` (사용자 endpoint)
- [ ] `apps/api/app/api/v1/admin/notice_plans.py` (Admin endpoint)
- [ ] 통합 테스트 `apps/api/tests/integration/test_notice_plans_api.py`
- [ ] copy 흐름 — RustFS object 비복사 + `source_attachment_id` 추적 검증
- [ ] LexoRank append 로직 (notice → 기존 trip 합치기)
- [ ] `feature_id` 라이브러리에 없을 때 fallback 동작 (`feature_link_broken_at`)
- [ ] `docs/architecture/notice-plans.md` cross-ref 업데이트
