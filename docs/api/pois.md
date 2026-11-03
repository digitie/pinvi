# POI API (`/trips/{trip_id}/pois/*`)

여행 day별 POI 첨부 CRUD + 순서 변경 (LexoRank fractional indexing).
공통 규약 [`common.md`](./common.md). Trip 권한은 [`trips.md`](./trips.md) §2.

## 1. 모델

- `app.trip_day_pois`:
  - `sort_order TEXT COLLATE "C"` — **SPEC V8 E-6 Critical** (LexoRank 정합성)
  - `feature_id TEXT` — nullable. 라이브러리 `feature.features.feature_id` reference (FK 없음)
  - `feature_snapshot JSONB` — 적재 시점 캐시 (이름/좌표/카테고리)
  - `custom_marker_color`, `custom_marker_icon` — 사용자 override
  - `version INTEGER` — optimistic lock (`If-Match`)
  - `planned_arrival_at`, `planned_departure_at` — KST aware
  - `budget_amount`, `actual_amount`, `currency` — 사용자 예상/실제 지출. 금액은 0 이상,
    `currency`는 대문자 3글자(기본 `KRW`)
  - `user_url` — 사용자가 저장한 참고 URL
- `app.trip_poi_rise_sets`:
  - POI 생성 시 `python-kasi-api` 위치별 해달 출몰시각 정보조회 결과를 1회 저장
  - `rise_set` 응답 선택 필드의 원천. 날짜/좌표가 없으면 pending 상태

## 2. CRUD

### 2.1 `POST /trips/{trip_id}/pois`

```http
POST /trips/{trip_id}/pois
Content-Type: application/json

{
  "day_index": 2,
  "sort_order": "a3",                          // LexoRank
  "feature_id": "f_2611000000_p_abc123...",    // nullable. 라이브러리 feature_id
  "feature_snapshot": {
    "name": "부산타워",
    "coord": { "lon": 129.0319, "lat": 35.1009 },
    "category": "관광명소",
    "marker_color": "P-11",
    "marker_icon": "attraction"
  },
  "planned_arrival_at": "2026-06-02T14:00:00+09:00",
  "planned_departure_at": "2026-06-02T15:30:00+09:00",
  "user_note": "...",
  "budget_amount": "12000.00",
  "actual_amount": null,
  "currency": "KRW",
  "user_url": "https://example.com/menu",
  "custom_marker_color": "P-08",   // 선택
  "custom_marker_icon": null
}
```

- `feature_id`가 없으면 자유 POI로 저장하고 `feature_snapshot`만 표시용으로 사용한다.
- `feature_id`가 있는데 kor-travel-map batch 조회 결과에 없으면
  → `feature_link_broken_at` 채움 + 그래도 row 생성 (`feature_snapshot`으로 표시)
- 좌표와 방문일(`trip_days.date`)이 있으면 POI 생성 후 Dagster/KASI job을 enqueue해
  `rise_set.location`(`getLCRiseSetInfo`) 결과를 1회 저장한다. API는 먼저
  `app.trip_poi_rise_sets.status='pending_fetch'` row를 만들고, Dagster one-shot job이
  실제 KASI 호출을 처리한다. 생성 응답 시점에는 `rise_set.status`가 `pending_date` /
  `pending_coord` / `pending_fetch`일 수 있다. row가 없으면 `rise_set`은 `null`이다.
- POI 날짜/좌표가 이후 변경되어도 `rise_set`은 자동 재조회하지 않는다. 저장된 값은
  생성 당시 snapshot 기준이며, refresh action은 후속 PR에서 별도 추가한다.
- `sort_order` 충돌 시 (`(day_index, sort_order COLLATE "C")` UNIQUE) → `409`

응답 201: 생성된 POI. 선택 필드:

```jsonc
{
  "rise_set": {
    "status": "success",
    "locdate": "2026-06-02",
    "sunrise_at": "2026-06-02T05:10:00+09:00",
    "sunset_at": "2026-06-02T19:39:00+09:00",
    "moonrise_at": "...",
    "moonset_at": "...",
    "fetched_at": "2026-06-01T21:00:00Z",
    "updated_at": "2026-06-01T21:00:00Z",
  },
}
```

### 2.2 `PATCH /trips/{trip_id}/pois/{poi_id}`

```http
PATCH /trips/{trip_id}/pois/{poi_id}
If-Match: 3
Content-Type: application/json

{
  "user_note": "...",
  "custom_marker_color": "P-04",
  "planned_arrival_at": "...",
  "budget_amount": "15000.00",
  "actual_amount": "11000.00",
  "currency": "KRW"
}
```

LWW 필드 단위 — `version + 1` + WebSocket broadcast (`poi.updated`). 예산 금액은
null 또는 0 이상, `currency`는 대문자 3글자만 허용한다.

### 2.3 `DELETE /trips/{trip_id}/pois/{poi_id}`

소프트 삭제 (`deleted_at = now()`)만 수행한다(ADR-031).

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
    { "poi_id": "uuid-2", "new_sort_order": "b2" },
  ],
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

| 정책             | 동작                                                       |
| ---------------- | ---------------------------------------------------------- |
| **lazy** (기본)  | UI 표시 시 kor-travel-map batch 조회. snapshot은 fallback  |
| **eager** (선택) | Dagster job 일 1회 + `WHERE feature_id IN (...)`           |
| **on-write**     | POI write 시점 kor-travel-map batch 조회 → snapshot upsert |

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
    { "feature_id": null, "snapshot": {...}, "user_note": "...", "sort_order": "a2" }
  ]
}
```

`POST /notice-plans/{plan_id}/copy`에서 내부적으로 사용 (직접 호출도 가능).

## 7. AI agent 구현 체크리스트

- [x] `apps/api/app/schemas/poi.py` Pydantic + `packages/schemas/src/poi.ts` Zod
- [x] `apps/api/app/services/poi.py` 비즈니스 로직 (sort_order 검증)
- [x] POI 생성 시 좌표/방문일이 있으면 KASI 출몰시각 `pending_fetch` row 생성
- [x] POI 생성/수정/정렬 응답과 Trip 상세 POI에 `rise_set` 노출
- [x] `apps/api/app/api/v1/pois.py` 라우터
- [ ] LexoRank helper `packages/hooks/src/lexorank.ts` (또는 `packages/lexorank/`)
- [x] `sort_order COLLATE "C"` Alembic + 로컬 PostGIS 통합 테스트
- [ ] WebSocket broadcast 트리거 (`poi.*`)
- [ ] feature_snapshot lazy join 패턴 통합 테스트

## 일자 이동과 재정렬 보존 (#639/#652)

PATCH /trips/{trip_id}/pois/{poi_id}에 day_index를 보내면 같은 여행의 기존 일자로 이동한다.
If-Match는 이동 전 POI 버전이다. sort_order를 생략하면 목적지 일자의 끝으로 보낸다.
메모·비용·첨부·동일 POI ID를 유지하며 원래 입력한 도착·출발 절대시각은 자동 이동하지 않는다.
새 날짜의 일출/일몰 seed와 양쪽 일자 대표 기준을 갱신한다. 없는 일자는 404, 버전·정렬 충돌은 409다.
viewer는 POI 생성·수정·삭제·정렬을 할 수 없다.
일자 삭제와 생성·이동·정렬은 같은 여행 잠금을 먼저 취득한다.
재정렬은 임시 고유 순위와 최종 순위를 한 트랜잭션으로 저장하며, 실패하면 전부 롤백하고 DB 원문을 노출하지 않는다.

## 첨부·출처 보존 (#629/#630)

사용자 파일 목록·다운로드·쿼터는 POI 및 소유 여행의 활성 상태를 공통 검사한다.
부모 삭제로 첨부 객체나 메타데이터를 자동 삭제하지 않으며 부모가 복원되면 다시 접근·집계한다.
신규 수동 POI는 source=manual이다. 기존 NULL 출처 행은 원천 확인 없는 일괄 backfill을 하지 않고 보존한다.

재정렬 요청은 day_index를 필수로 보낸다. moves 안의 모든 POI가 잠금 획득 후에도 해당 일자에 있어야 한다.
이동 전 화면에서 보낸 오래된 정렬 요청은 409로 거부한다. Web·모바일 클라이언트도 이 계약을 함께 사용한다.
이전 day_index 없는 요청은 422다. 데이터베이스 스키마 변경은 없다.
