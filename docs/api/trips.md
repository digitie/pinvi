# 여행 API (`/trips/*`)

여행 plan CRUD + 동반자 초대 + 공유 토큰 + day별 item 추가 + 첨부.
[`common.md`](./common.md) 공통 규약. POI 세부는 [`pois.md`](./pois.md).

## 1. 모델

- `app.trips` — Trip 메타 (owner, title, period, status, visibility, ...)
- `app.trip_days` — day_index 합성 PK
- `app.trip_day_pois` — `sort_order TEXT COLLATE "C"` (LexoRank)
- `app.trip_companions` — 동반자 (가입 전 invited_email + 가입 후 user_id)
- `app.trip_share_links` — 256bit URL-safe base64 토큰

자세히는 `docs/data-model.md` §2.2, `docs/postgres-schema.md` §3.

## 2. 권한

| 액션 | owner | companion (editor) | companion (viewer) | shared link | anon |
|------|-------|-------------------|-------------------|-------------|------|
| 조회 | ✓ | ✓ | ✓ | token + read perm | ✗ |
| 메타 편집 | ✓ | ✓ | ✗ | ✗ | ✗ |
| POI CRUD | ✓ | ✓ | ✗ | ✗ | ✗ |
| 삭제 / 이관 | ✓ | ✗ | ✗ | ✗ | ✗ |
| 동반자 추가/제거 | ✓ | ✗ | ✗ | ✗ | ✗ |
| 공유 발급/취소 | ✓ | ✗ | ✗ | ✗ | ✗ |

## 3. Trip CRUD

### 3.1 `GET /trips`

```http
GET /trips?bucket=future&q=부산&status=planned&visibility=private&date_from=2026-06-01&date_to=2026-06-30&sort=-updated_at&limit=20&cursor=...
Cookie: tripmate_access=...
```

- `bucket`: `future` (오늘 이후 종료) | `past` | `all`
- `q`: 선택. 2자 이상. `title`, `description`, `region_hint`를 대상으로 검색한다.
- `status`: 선택. `draft` | `planned` | `in_progress` | `completed` | `archived`
- `visibility`: 선택. `private` | `unlisted` | `public`
- `date_from`, `date_to`: 선택. 여행 기간이 해당 범위와 겹치면 포함한다.
- `sort`: `-updated_at`(기본) | `start_date` | `-start_date` | `title`
- 응답: cursor 페이지네이션된 trip 목록 (`data` 배열 + `meta.cursor`).

여행 목록 검색은 TripMate `app.trips`/`app.trip_companions`만 사용한다. POI/장소/주소
검색은 본 endpoint에 섞지 않는다. 장소 검색은 `GET /features/search`, 통합 검색은
T-129의 `GET /search`가 담당한다.

### 3.2 `POST /trips`

```http
POST /trips
Content-Type: application/json

{
  "title": "부산 2박 3일",
  "description": "...",       // optional markdown
  "start_date": "2026-06-01", // optional (둘 다 비우면 period-less)
  "end_date": "2026-06-03",
  "region_hint": "부산",      // optional
  "visibility": "private",    // private | unlisted | public
  "companions": [             // optional
    { "email": "friend@example.com", "display_name": "친구" }
  ]
}
```

응답 201: `{ "data": { "trip": {...}, "days": [...] } }`. 동반자가 있으면
invite 이메일 발송.

### 3.3 `GET /trips/{trip_id}`

응답에 trip + days + pois (snapshot 포함) + companions + share links. POI의
`feature` 필드는 krtour-map `POST /tripmate/features/batch`로 batch join한 최신 정보
(없으면 `feature_snapshot` 사용). `rise_set`은 POI 생성 시 KASI 위치별 해달
출몰시각 정보조회가 완료된 경우에만 포함한다.

### 3.4 `PATCH /trips/{trip_id}`

```http
PATCH /trips/{trip_id}
If-Match: 42
Content-Type: application/json

{
  "title": "...",
  "description": "...",
  "start_date": "2026-06-01",
  "end_date": "2026-06-03",
  "region_hint": "...",
  "cover_attachment_id": "uuid",
  "visibility": "...",
  "status": "draft" | "planned" | "in_progress" | "completed" | "archived"
}
```

`If-Match` 불일치 → `409 VERSION_CONFLICT`. 성공 시 `version + 1` + WebSocket
broadcast (`trip.updated`).

### 3.5 `DELETE /trips/{trip_id}`

```http
DELETE /trips/{trip_id}
Content-Type: application/json

{ "mode": "soft_delete" | "transfer_leader", "new_owner_user_id": "..." }
```

- `soft_delete`: `status = 'archived'` + `deleted_at = now()`
- `transfer_leader`: `owner_user_id` 변경, 자기는 `co_owner`로 전환

### 3.6 `POST /trips/{trip_id}/copy`

```http
POST /trips/{trip_id}/copy
Content-Type: application/json

{
  "title": "복사된 여행",
  "scope": "all" | "day" | "range",
  "day_index": 2,                  // scope=day
  "start_day_index": 1,            // scope=range
  "end_day_index": 3,
  "date_shift_days": 7,            // 시작일 +7일
  "target_trip_id": "uuid"          // 기존 trip에 합치는 경우
}
```

## 4. Trip days

### 4.1 `POST /trips/{trip_id}/days`

```http
POST /trips/{trip_id}/days
Content-Type: application/json

{ "day_index": 4, "date": "2026-06-04", "title": "마지막 날" }
```

### 4.2 `PATCH /trips/{trip_id}/days/{day_index}`

`title`, `date`, `note` 갱신.

### 4.3 `DELETE /trips/{trip_id}/days/{day_index}`

day의 모든 POI도 함께 CASCADE.

## 5. Day item 추가 (place / festival / route / area / notice)

v1의 `trip_plan_items`를 통합한 endpoint. 다양한 `resource_type`을 같은 timeline에.

### 5.1 `POST /trips/{trip_id}/days/{day_index}/items`

```http
POST /trips/{trip_id}/days/2/items
Content-Type: application/json

{
  "resource_type": "place" | "event" | "route" | "area" | "notice" | "festival" | "custom",
  "feature_id": "f_2611000000_p_abc123...",   // 라이브러리 feature_id (string)
  "sort_order": "a3",                          // LexoRank
  "title_snapshot": "부산타워",
  "address_snapshot": "부산 중구 용두산길 37-55",
  "longitude": 129.0319,
  "latitude": 35.1009,
  "operating_hours_snapshot": { /* ... */ },
  "starts_at": "2026-06-02T14:00:00+09:00",
  "ends_at": "2026-06-02T15:30:00+09:00",
  "note": "...",
  "resource_metadata": { /* free jsonb */ }
}
```

- `feature_id`는 **string** (라이브러리 schema). DB cross-schema FK 없음 (ADR-003).
- `feature_snapshot`은 적재 시점 캐시 — 라이브러리 변경되어도 UI 무결성 유지
- POI 본체는 `app.trip_day_pois`에 저장. `pois.md` 참조

응답 201: 생성된 POI.

## 6. 동반자

### 6.1 `POST /trips/{trip_id}/members`

```http
POST /trips/{trip_id}/members
Content-Type: application/json

{
  "email": "friend@example.com",
  "display_name": "친구",
  "role": "editor" | "viewer" | "co_owner"
}
```

- 이미 가입한 user면 `user_id` 채움 + `joined_at`
- 미가입이면 `invited_email`만 + 초대 메일 발송
- 응답 201: companion 정보

### 6.2 `DELETE /trips/{trip_id}/members/{companion_id}`

owner만. 자기 자신 제거는 `transfer_leader` 후만.

## 7. 공유 토큰

### 7.1 `POST /trips/{trip_id}/share-tokens`

```http
POST /trips/{trip_id}/share-tokens
Content-Type: application/json

{
  "visibility": "view_only" | "comment" | "edit",
  "expires_at": "2026-12-31T23:59:59+09:00"   // null 가능 (만료 없음)
}
```

응답 201:

```jsonc
{
  "data": {
    "share_id": "uuid",
    "token": "<43-char URL-safe base64>",
    "url": "https://tripmate.digitie.mywire.org/trips/<trip_id>/shared/<token>",
    "visibility": "...",
    "expires_at": "..."
  }
}
```

`url`은 `TRIPMATE_WEB_BASE_URL`을 base로 생성한다. 개발 기본값은
`http://localhost:9022`, 운영값은 `https://tripmate.digitie.mywire.org`다.

### 7.2 `DELETE /trips/{trip_id}/share-tokens/{share_id}`

`revoked_at = now()`.

### 7.3 `GET /trips/{trip_id}/shared/{token}` (비로그인 가능)

token 검증 (`revoked_at IS NULL`, `expires_at > now()`). `last_used_at = now()` 기록.
응답은 visibility별 셰입 차이 (view_only는 메타 + POI 일부만).

Rate limit: 분당 60회 per token.

## 8. 첨부 (`/trips/{trip_id}/attachments`)

자세히는 [`storage.md`](./storage.md). 핵심 endpoint:

- `GET /trips/{trip_id}/attachments`
- `POST /trips/{trip_id}/attachments`
- `DELETE /trips/{trip_id}/attachments/{attachment_id}`
- `GET /trips/{trip_id}/pois/{poi_id}/attachments`
- `POST /trips/{trip_id}/pois/{poi_id}/attachments`
- `DELETE /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}`

## 9. 일정 자동 최적화

자세히는 SPEC V8 H-8 / `docs/spec/v8/02-backend.md` §6.

- `POST /trips/{trip_id}/days/{day_index}/optimize`
- `GET /trips/{trip_id}/days/{day_index}/distance-matrix`

Sprint 6.

## 10. 여행 내보내기

내보내기는 **현재 저장된 TripMate snapshot**을 기준으로 만든다. PDF/print/GPX 생성 중
krtour-map live lookup을 수행하지 않는다. feature 최신 정보가 없어도
`feature_snapshot`, POI 메모, 일정 순서만으로 출력 가능해야 한다.

| 형식 | 초기 구현 | 권한 | 비고 |
|------|-----------|------|------|
| print | Web route `/trips/{trip_id}/print` | owner/editor/viewer + share `view_only` | 브라우저 print/PDF 저장의 원천 |
| PDF | print route 기반 브라우저 PDF 저장 우선, server PDF는 후속 | owner/editor/viewer | 서버 생성 시 저장 없이 stream |
| GPX | API file response | owner/editor/viewer | share token은 v1.0 초기 제외 |

### 10.1 `GET /trips/{trip_id}/exports/print-data`

```http
GET /trips/{trip_id}/exports/print-data?scope=all&include=notes,rise_set
Cookie: tripmate_access=...
```

- `scope`: `all` | `day` | `range`
- `day_index`: `scope=day`일 때 필수
- `start_day_index`, `end_day_index`: `scope=range`일 때 필수
- `include`: 콤마 구분. `notes`, `attachments`, `rise_set`, `map_overview`

응답은 print/PDF 렌더러용 JSON이다. companion email, refresh/session, 감사 로그, 내부
provider 원문은 포함하지 않는다. `attachments`는 사용자가 접근 가능한 파일의
presigned read URL 또는 thumbnail URL만 포함한다.

```jsonc
{
  "data": {
    "trip": { "trip_id": "...", "title": "부산 2박 3일", "date_range": "..." },
    "days": [
      {
        "day_index": 1,
        "date": "2026-06-01",
        "pois": [
          {
            "poi_id": "...",
            "title": "부산타워",
            "coord": { "longitude": 129.0319, "latitude": 35.1009 },
            "planned_arrival_at": "2026-06-01T14:00:00+09:00",
            "user_note": "...",
            "rise_set": { "status": "success", "sunset_at": "..." }
          }
        ]
      }
    ],
    "warnings": []
  }
}
```

### 10.2 `GET /trips/{trip_id}/exports/gpx`

```http
GET /trips/{trip_id}/exports/gpx?scope=all&include_notes=false
Accept: application/gpx+xml
Cookie: tripmate_access=...
```

- `Content-Type`: `application/gpx+xml; charset=utf-8`
- `Content-Disposition`: `attachment; filename="tripmate-{trip_id}.gpx"`
- 각 day는 `<rte>` 하나로 만들고, POI는 `sort_order` 순서의 `<rtept>`로 출력한다.
- 좌표가 있는 POI는 `<wpt>`도 함께 출력한다. `planned_arrival_at`이 있으면 GPX `time`에
  KST offset 포함 ISO 8601로 넣는다.
- 좌표 없는 POI는 건너뛰고 `X-TripMate-Export-Warnings`에 개수를 기록한다. 출력 가능한
  좌표가 하나도 없으면 `422 EXPORT_NO_COORDINATES`.
- `include_notes=true`는 owner/editor만 허용한다. viewer는 POI 제목·좌표·일정 시각만.

### 10.3 `GET /trips/{trip_id}/exports/pdf`

```http
GET /trips/{trip_id}/exports/pdf?scope=all&include=notes,rise_set,map_overview
Cookie: tripmate_access=...
```

서버 PDF는 `/trips/{trip_id}/print`와 같은 HTML/CSS를 headless renderer로 출력한다.
초기 Sprint 4 UI는 브라우저 print route에서 "PDF로 저장"을 제공하고, 서버 PDF endpoint는
Sprint 6에서 운영 dependency(Chromium/Playwright 또는 대체 renderer)와 함께 켠다.
생성 파일은 기본적으로 RustFS에 저장하지 않고 stream한다. 저장형 export가 필요하면
별도 `app.trip_exports` 모델을 후속 ADR로 추가한다.

## 11. WebSocket 이벤트

POI / day / trip 변경 시 `WS /ws/trips/{trip_id}` 채널로 broadcast:

- `poi.created`, `poi.updated`, `poi.deleted`, `poi.reordered`
- `day.created`, `day.updated`, `day.deleted`
- `trip.updated`, `trip.member_changed`
- `presence.update`

자세히는 [`websocket.md`](./websocket.md).

## 12. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/{trip,companion,share_link}.py` Pydantic + `packages/schemas/src/trip.ts` Zod
- [ ] `apps/api/app/services/trip.py` 비즈니스 로직 (권한 검사 + krtour-map batch join)
- [ ] `apps/api/app/api/v1/trips.py` 라우터
- [ ] `GET /trips` 검색 파라미터(`q`, `status`, `visibility`, `date_from/to`, `sort`) 구현
- [ ] `exports/print-data`, `exports/gpx`, `exports/pdf` 계약에 맞는 schema / permission 테스트
- [ ] krtour-map HTTP client에서 `POST /tripmate/features/batch` 호출 패턴
- [ ] 통합 테스트 `apps/api/tests/integration/test_trips_api.py`
- [ ] WebSocket broadcast 트리거 추가
- [ ] 본 문서 + `common.md` 표준 에러 코드 갱신
