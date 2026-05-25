# POI API (`/trips/{trip_id}/pois/*`)

여행 day별 POI 첨부 CRUD + 순서 변경 (LexoRank fractional indexing).
공통 규약 [`common.md`](./common.md). Trip 권한은 [`trips.md`](./trips.md) §2.

## 1. 모델

- `app.trip_day_pois`:
  - `sort_order TEXT COLLATE "C"` — **SPEC V8 E-6 Critical** (LexoRank 정합성)
  - `feature_id TEXT` — 라이브러리 `feature.features.feature_id` reference (FK 없음)
  - `feature_snapshot JSONB` — 적재 시점 캐시 (이름/좌표/카테고리)
  - `custom_marker_color`, `custom_marker_icon` — 사용자 override
  - `version INTEGER` — optimistic lock (`If-Match`)
  - `planned_arrival_at`, `planned_departure_at` — KST aware

## 2. CRUD

### 2.1 `POST /trips/{trip_id}/pois`

```http
POST /trips/{trip_id}/pois
Content-Type: application/json

{
  "day_index": 2,
  "sort_order": "a3",                          // LexoRank
  "feature_id": "f_2611000000_p_abc123...",    // 라이브러리 feature_id
  "feature_snapshot": {
    "name": "부산타워",
    "coord": { "longitude": 129.0319, "latitude": 35.1009 },
    "category": "관광명소",
    "marker_color": "P-11",
    "marker_icon": "attraction"
  },
  "planned_arrival_at": "2026-06-02T14:00:00+09:00",
  "planned_departure_at": "2026-06-02T15:30:00+09:00",
  "user_note": "...",
  "custom_marker_color": "P-08",   // 선택
  "custom_marker_icon": null
}
```

- `feature_id`가 라이브러리에 없으면 (`AsyncKrtourMapClient.features_by_ids` 결과 empty)
  → `feature_link_broken_at` 채움 + 그래도 row 생성 (`feature_snapshot`으로 표시)
- `sort_order` 충돌 시 (`(day_index, sort_order COLLATE "C")` UNIQUE) → `409`

응답 201: 생성된 POI.

### 2.2 `PATCH /trips/{trip_id}/pois/{poi_id}`

```http
PATCH /trips/{trip_id}/pois/{poi_id}
If-Match: 3
Content-Type: application/json

{
  "user_note": "...",
  "custom_marker_color": "P-04",
  "planned_arrival_at": "..."
}
```

LWW 필드 단위 — `version + 1` + WebSocket broadcast (`poi.updated`).

### 2.3 `DELETE /trips/{trip_id}/pois/{poi_id}`

소프트 삭제 (`deleted_at = now()`) 또는 hard delete (정책 결정 — Sprint 2 ADR).

## 3. Reorder (D&D)

### 3.1 `POST /trips/{trip_id}/pois/reorder`

```http
POST /trips/{trip_id}/pois/reorder
Content-Type: application/json

{
  "poi_id": "uuid",
  "new_sort_order": "a2.5"        // LexoRank (a2 < a2.5 < a3)
}
```

또는 batch:

```jsonc
{
  "moves": [
    { "poi_id": "uuid-1", "new_sort_order": "b1" },
    { "poi_id": "uuid-2", "new_sort_order": "b2" }
  ]
}
```

응답 200: 갱신된 POI 목록 (snapshot 포함).

WebSocket broadcast: `poi.reordered` + `version`.

## 4. LexoRank 정합성 (SPEC V8 E-6 Critical)

- `sort_order TEXT COLLATE "C"` 필수 — JS LexoRank와 PG 정렬 일치
- 클라이언트 LexoRank 라이브러리: `@dnd-kit/sortable` + 자체 LexoRank helper
  (`packages/hooks/src/lexorank.ts`)
- 끼워넣기 예: `a1 < a2` 사이 → `a1.5` (또는 `a15`)
- 6자 이상 깊어지면 rebalance job (Dagster, 주 1회) — `sort_order`를 `a..z`
  단조 시퀀스로 재배치

## 5. feature_snapshot 동기화

라이브러리 `feature.features`가 갱신되면 POI snapshot을 다시 채울지 정책:

| 정책 | 동작 |
|------|------|
| **lazy** (기본) | UI 표시 시 라이브러리 호출. snapshot은 fallback |
| **eager** (선택) | Dagster job 일 1회 + `WHERE feature_id IN (...)` |
| **on-write** | POI write 시점 라이브러리 호출 → snapshot upsert |

v1.0은 **lazy**. Sprint 5에서 eager rebuild Dagster job 검토.

자세히는 `docs/architecture/feature-snapshot-sync.md` (작성 예정 시점에 참고).

## 6. 일괄 작업

### 6.1 `POST /trips/{trip_id}/pois/batch-add`

추천 plan에서 가져온 POI 여러 개 일괄 추가 (Notice plan copy 흐름).

```jsonc
{
  "day_index": 1,
  "pois": [
    { "feature_id": "...", "snapshot": {...}, "user_note": "...", "sort_order": "a1" },
    { "feature_id": "...", "snapshot": {...}, "user_note": "...", "sort_order": "a2" }
  ]
}
```

`POST /notice-plans/{plan_id}/copy`에서 내부적으로 사용 (직접 호출도 가능).

## 7. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/poi.py` Pydantic + `packages/schemas/src/poi.ts` Zod
- [ ] `apps/api/app/services/poi.py` 비즈니스 로직 (sort_order 검증 + 라이브러리 feature 검증)
- [ ] `apps/api/app/api/v1/pois.py` 라우터 (또는 `trips.py`에 합치기)
- [ ] LexoRank helper `packages/hooks/src/lexorank.ts` (또는 `packages/lexorank/`)
- [ ] `sort_order COLLATE "C"` Alembic + 로컬 PostGIS 통합 테스트
- [ ] WebSocket broadcast 트리거 (`poi.*`)
- [ ] feature_snapshot lazy join 패턴 통합 테스트
