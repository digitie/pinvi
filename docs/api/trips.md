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

| 액션             | owner | companion (editor) | companion (viewer) | shared link       | anon |
| ---------------- | ----- | ------------------ | ------------------ | ----------------- | ---- |
| 조회             | ✓     | ✓                  | ✓                  | token + read perm | ✗    |
| 메타 편집        | ✓     | ✓                  | ✗                  | ✗                 | ✗    |
| POI CRUD         | ✓     | ✓                  | ✗                  | ✗                 | ✗    |
| 삭제 / 이관      | ✓     | ✗                  | ✗                  | ✗                 | ✗    |
| 동반자 추가/제거 | ✓     | ✗                  | ✗                  | ✗                 | ✗    |
| 공유 발급/취소   | ✓     | ✗                  | ✗                  | ✗                 | ✗    |

## 3. Trip CRUD

### 3.1 `GET /trips`

```http
GET /trips?bucket=future&q=부산&status=planned&visibility=private&date_from=2026-06-01&date_to=2026-06-30&sort=-updated_at&limit=20&cursor=...
Cookie: pinvi_access=...
```

- `bucket`: `future`(기본, 오늘 이후 종료 또는 기간 미정) | `past` | `all`
- `q`: 선택. 2자 이상. `title`, `description`, `region_hint`를 대상으로 검색한다.
- `status`: 선택. `draft` | `planned` | `in_progress` | `completed` | `archived`
- `visibility`: 선택. `private` | `unlisted` | `public`
- `date_from`, `date_to`: 선택. 여행 기간이 해당 범위와 겹치면 포함한다.
- `sort`: `-updated_at`(기본) | `start_date` | `-start_date` | `title`
- `cursor`: 선택. 이전 응답의 `meta.cursor` 값을 그대로 넘기는 불투명 cursor.
- 응답: cursor 페이지네이션된 trip 목록 (`data` 배열 + `meta.cursor` /
  `meta.has_more` / `meta.limit`).

```jsonc
{
  "data": [{ "trip_id": "uuid", "title": "부산 2박 3일", "...": "TripResponse" }],
  "meta": {
    "cursor": "eyJ2IjoxLCJvZmZzZXQiOjIwfQ", // 다음 페이지가 없으면 null
    "has_more": true,
    "limit": 20,
  },
}
```

여행 목록 검색은 Pinvi `app.trips`/`app.trip_companions`만 사용한다. POI/장소/주소
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
  "primary_region_code": "26110", // optional, sido/sigungu/bjd code
  "visibility": "private",    // private | unlisted | public
  "companions": [             // optional
    { "email": "friend@example.com", "display_name": "친구" }
  ]
}
```

응답 201: `{ "data": { "...": "TripResponse" } }`. 동반자가 있으면 invite 이메일 발송.
`start_date`와 `end_date`가 모두 있으면 생성 시 기간 전체의 `trip_days`가 함께 생성된다.
예를 들어 3박 4일(`2026-06-01`~`2026-06-04`) 여행은 `day_index` 1~4와 각 날짜 row를
초기 상태로 가진다. 기간이 없는 여행은 day를 자동 생성하지 않는다.

`primary_region_code`는 `region_hint` 자유텍스트와 별개로 지역 기반 weather/oil/
Telegram brief 질의에 쓰는 구조화 코드다. 2~10자리 숫자(sido/sigungu/bjd code)를
허용하며, 사용자가 직접 입력하면 응답의 `primary_region_source`는 `manual`이다.
값을 비워 만든 trip은 POI 생성 시 `feature_snapshot.region.*` 또는 snapshot 최상위의
`sigungu_code`/`bjd_cd`/`region_code` 등에서 첫 지역 code를 찾아 `poi_snapshot`으로
자동 채울 수 있다. kor-travel-geo reverse geocoding 기반 자동 유도는 별도 후속 작업이다.

### 3.3 `GET /trips/{trip_id}`

관리 권한으로 조회할 때 일자 출몰 캐시 유지 작업은 별도 트랜잭션에서 수행한다(#684).
실패해도 호출자 Trip·POI를 만료시키지 않으며, 다음 조회에서 보정한다. 일자별 행은 원자
upsert하며 기존 성공 결과는 입력이 같으면 보존한다. 입력 조회부터 저장까지 사용자
POI·일자 변경과 Trip 선행 잠금을 공유하여 오래된 조회가 최신 이동 기준을 덮지 못하게 한다.


응답에 trip + days + pois (snapshot 포함) + companions + share links. `feature_id`가
있는 POI의 `feature` 필드는 kor-travel-map `POST /v1/features/batch`로 batch join한 최신 정보
(없거나 조회 실패 시 `feature_snapshot` 사용). feature 없는 POI는 snapshot만 사용한다.
`rise_set`은 POI 생성 시 KASI 위치별 해달
출몰시각 row가 있으면 포함하며, 아직 처리 전이면 `pending_*` 상태로 내려간다. row가
없으면 `rise_set`은 `null`이다. `feature_resolution_state`는
`not_linked|found|retired|suppressed|missing|unverified`다. Map batch의 `unchanged`는
revision이 같은 캐시를 재사용한 성공 상태이므로 소비자 응답에서는 `found`로 투영한다.
`retired`는 종료·삭제된 장소, `suppressed`는 존재하지만 공개 projection에서 비공개인 장소,
`missing`은 기준 row가 없는 장소다. `unverified`는 transport/인증/계약 실패로 최신 상태를
확인하지 못해 저장 snapshot을 썼다는 뜻이다. `broken_feature_count`는 사용자가 고쳐야 하는
`retired|missing`만 집계하며 `suppressed|unverified`는 포함하지 않는다.

일자 날씨는 `weather_by_feature_id`의 상태와 `weather_cards`의 정규화된 카드로 나뉜다.
`found` 상태는 `card_key`만 가지며, 같은 일자·`kor-travel-weather` `location_id`의
여러 feature가 같은 카드를 참조한다(`card_key := location_id`). 참조된 card가
빠지거나 참조되지 않은 card가 있으면 응답 계약 오류다.

> **소스: `kor-travel-weather`(ADR-068, T-363/T-365로 완료)**. weather 조회는
> feature batch(위 `feature_resolution_state`)와 **완전히 독립**이다 — POI 자신의
> `feature_snapshot.coord`만 보고 결정하므로 `weather_by_feature_id`의 상태는
> `found`/`no_data`/`unavailable` 셋뿐이며, feature가 `retired`/`suppressed`/`missing`이어도
> 좌표가 있으면 그 지점의 날씨를 그대로 낸다. `kor-travel-weather` client가
> 주입되지 않은 호출 경로(예: MCP 도구)는 조회를 시도하지 않고 모든 feature-linked
> POI를 균일하게 `unavailable`로 표시한다. 상세 —
> [`docs/integrations/kor-travel-weather.md`](../integrations/kor-travel-weather.md) §3.4/§3.5.
> **Map 경유(ADR-077)**: `PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED`가 켜지면 같은 셰입·상태 규칙으로 kor-travel-map
> `POST /v1/service/weather/locations/batch`(50곳씩)에서 관측·예보·지난 일자 세 구간 요약을 읽는다(특보만
> `kor-travel-weather`). 이때 kor-travel-map client가 없는 호출 경로는 균일하게 `unavailable`이다 — §9.

응답 shape:

```json
{
  "data": {
    "trip": { "...": "TripResponse" },
    "days": [
      {
        "day_index": 1,
        "date": "2026-06-01",
        "title": "1일차",
        "weather_cards": {
          "weather-card-key": {
            "asof": "2026-06-01T00:00:00+09:00",
            "latest_at": "2026-06-01T09:00:00+09:00",
            "is_stale": false,
            "source_styles": ["observed", "short"],
            "metrics": []
          }
        },
        "weather_by_feature_id": {
          "feature-id": { "state": "found", "card_key": "weather-card-key" }
        },
        "pois": [
          {
            "poi_id": "uuid",
            "feature_id": "feature-id",
            "sort_order": "a0",
            "title": "광안리",
            "feature": { "...": "snapshot 또는 최신 feature" },
            "marker_color": "P-01",
            "marker_icon": "beach",
            "feature_resolution_state": "found",
            "user_note": null,
            "planned_arrival_at": null,
            "planned_departure_at": null,
            "budget_amount": "12000.00",
            "actual_amount": null,
            "currency": "KRW",
            "user_url": null,
            "rise_set": {
              "status": "pending_fetch",
              "locdate": "2026-06-01",
              "sunrise_at": null,
              "sunset_at": null,
              "moonrise_at": null,
              "moonset_at": null,
              "fetched_at": null,
              "updated_at": "2026-06-01T00:00:00Z"
            },
            "feature_link_broken_at": null,
            "version": 1,
            "created_at": "2026-06-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z"
          }
        ]
      }
    ],
    "companions": [],
    "share_links": [
      {
        "share_id": "uuid",
        "visibility": "view_only",
        "expires_at": null,
        "revoked_at": null,
        "last_used_at": null,
        "created_at": "2026-06-01T00:00:00Z"
      }
    ],
    "broken_feature_count": 0
  }
}
```

`share_links` 목록은 공유 토큰 원문·hash를 노출하지 않는다. 토큰 원문은
`POST /trips/{trip_id}/share-tokens` 생성 응답에서만 1회 제공한다.

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
  "primary_region_code": "26110",
  "cover_attachment_id": "uuid",
  "visibility": "...",
  "status": "draft" | "planned" | "in_progress" | "completed" | "archived"
}
```

`If-Match` 불일치 → `409 VERSION_CONFLICT`. 성공 시 `version + 1` + WebSocket
broadcast (`trip.updated`).
`primary_region_code: null`을 보내면 `primary_region_source`도 함께 비운다.

### 3.5 `DELETE /trips/{trip_id}`

```http
DELETE /trips/{trip_id}
Content-Type: application/json

{ "mode": "soft_delete" | "transfer_leader", "new_owner_user_id": "..." }
```

- `soft_delete`: `status = 'archived'` + `deleted_at = now()`
- `transfer_leader`: `owner_user_id` 변경, 자기는 `co_owner`로 전환
- owner만 호출 가능. `transfer_leader` 대상 user가 기존 companion이면 companion row를
  제거하고 새 owner로 승격한다.

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

응답 201:

```jsonc
{
  "data": {
    "trip": { "...": "TripResponse" },
    "created_trip": true,
    "copied_day_count": 2,
    "copied_poi_count": 5,
    "copied_attachment_count": 3,
  },
}
```

새 trip을 만들면 원본 trip-level attachment와 선택된 POI attachment metadata를 복제한다.
`target_trip_id`를 지정하면 actor가 owner인 기존 trip 뒤에 선택 POI를 append한다.

## 4. Trip days

### 4.1 `POST /trips/{trip_id}/days`

```http
POST /trips/{trip_id}/days
Content-Type: application/json

{ "day_index": 4, "date": "2026-06-04", "title": "마지막 날" }
```

`day_index`는 optional이다. 생략하면 기존 day 중 비어 있는 가장 작은 `day_index`를
사용한다. 여행 기간이 있는 경우 `date`도 생략 가능하며, 서버가 `start_date + (day_index - 1)`로
기본 날짜를 채운다. 이미 모든 기간 day가 존재하면 `422 VALIDATION_ERROR`다.

기간이 있는 여행의 day는 `day_index`가 기간 길이를 넘을 수 없고, `date`는 여행 기간 안에 있어야 한다.
같은 trip 안에서 같은 `date`를 두 day가 동시에 사용할 수 없으며, 이 경우 `409 TRIP_DAY_CONFLICT`다.

### 4.2 `PATCH /trips/{trip_id}/days/{day_index}`

`title`, `date`, `note` 갱신. `date`는 여행 기간 안에서 다른 day와 겹치지 않는 값으로 바꿀 수 있다.
날짜 중복은 `409 TRIP_DAY_CONFLICT`, 기간 밖 날짜는 `422 VALIDATION_ERROR`다.

### 4.3 `DELETE /trips/{trip_id}/days/{day_index}`

day의 모든 POI도 함께 CASCADE.

## 5. POI 추가 정본 경로

Trip day에 장소/축제/공지 기반 POI를 추가하는 정본 endpoint는
[`pois.md`](./pois.md)의 `POST /trips/{trip_id}/pois`다. `day_index`는 path가 아니라
요청 body에 담는다. v1 문서에 남아 있던 `/trips/{trip_id}/days/{day_index}/items`는
v2에서 사용하지 않는다.

### 5.1 `POST /trips/{trip_id}/pois`

```http
POST /trips/{trip_id}/pois
Content-Type: application/json

{
  "day_index": 2,
  "sort_order": "a3",                          // LexoRank
  "feature_id": "f_2611000000_p_abc123...",   // 라이브러리 feature_id (string)
  "feature_snapshot": {
    "name": "부산타워",
    "coord": { "lon": 129.0319, "lat": 35.1009 },
    "category": "관광명소"
  },
  "planned_arrival_at": "2026-06-02T14:00:00+09:00",
  "planned_departure_at": "2026-06-02T15:30:00+09:00",
  "user_note": "야경 보기",
  "budget_amount": "12000.00",
  "currency": "KRW"
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
- owner만 호출 가능. 동반자(`co_owner` 포함)는 동반자 추가/공유 토큰 발급 불가.
- `trip_invite` email_queue row를 생성한다.

### 6.2 `DELETE /trips/{trip_id}/members/{companion_id}`

owner만. 삭제 시 `app.trip_companions` row를 제거하고
`trip.member_changed` realtime event를 발행한다.

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
    "url": "https://pinvi.example.com/shared/<trip_id>/<token>",
    "visibility": "...",
    "expires_at": "...",
  },
}
```

`url`은 `PINVI_WEB_BASE_URL`을 base로 생성한다. 개발 기본값은
`http://localhost:12805`, 운영값은 `https://pinvi.example.com`다.
owner만 발급 가능하다. 공유 토큰은 비로그인 조회를 제공한다. `comment` / `edit`
visibility는 아래 공유 댓글/편집 API에서 서버가 검사하며, 로그인 없는 댓글 작성
라우트는 아직 열지 않는다.

### 7.2 `DELETE /trips/{trip_id}/share-tokens/{share_id}`

owner만. `revoked_at = now()`.

### 7.3 `GET /trips/{trip_id}/shared/{token}` (비로그인 가능)

token 검증 (`revoked_at IS NULL`, `expires_at > now()`). `last_used_at = now()` 기록.
응답은 `TripSharedView`다. companions, share_links, 토큰 원문/hash는 포함하지 않는다.

```jsonc
{
  "data": {
    "visibility": "view_only",
    "trip": { "...": "TripResponse" },
    "days": [{ "day_index": 1, "pois": [{ "...": "TripViewPoi" }] }],
    "broken_feature_count": 0,
  },
}
```

Rate limit: 분당 60회 per token.

## 8. 댓글

로그인 사용자(owner 또는 동반자)는 여행 댓글을 조회·작성할 수 있다. 댓글 작성/삭제는
`comment.created` / `comment.deleted` realtime event를 발행한다.

### 8.1 `GET /trips/{trip_id}/comments`

```http
GET /trips/{trip_id}/comments?limit=50
Cookie: pinvi_access=...
```

응답 200:

```jsonc
{
  "data": [
    {
      "comment_id": "uuid",
      "trip_id": "uuid",
      "author_user_id": "uuid",
      "body": "일정 확인했습니다.",
      "target_type": "trip", // trip | day | poi
      "target_id": null,
      "day_index": null,
      "created_at": "2026-06-06T12:00:00+09:00",
      "updated_at": "2026-06-06T12:00:00+09:00",
    },
  ],
}
```

### 8.2 `POST /trips/{trip_id}/comments`

```http
POST /trips/{trip_id}/comments
Content-Type: application/json

{
  "body": "일정 확인했습니다.",
  "target_type": "trip" | "day" | "poi",
  "target_id": "uuid 또는 null",
  "day_index": 1
}
```

- `body`: trim 후 1~2000자.
- `target_type='trip'`이면 `target_id`와 `day_index`는 비워둘 수 있다.
- `target_type='day'` 또는 `poi`는 현재 soft contract이며, 상세 target 존재 검증은
  day/POI 상세 API 정비 때 보강한다.

### 8.3 `DELETE /trips/{trip_id}/comments/{comment_id}`

댓글 작성자 또는 owner만. `deleted_at = now()` soft delete.

shared-token 사용자의 댓글 작성은 후속 shared comment 라우트에서 같은
`app.trip_comments` 테이블에 연결한다.

## 9. 첨부 / 파일 (`/trips/{trip_id}/attachments`, `/files`)

자세히는 [`storage.md`](./storage.md). 핵심 endpoint:

- `GET /trips/{trip_id}/attachments`
- `POST /trips/{trip_id}/attachments`
- `DELETE /trips/{trip_id}/attachments/{attachment_id}`
- `GET /trips/{trip_id}/days/{day_index}/attachments`
- `POST /trips/{trip_id}/days/{day_index}/attachments`
- `DELETE /trips/{trip_id}/days/{day_index}/attachments/{attachment_id}`
- `GET /trips/{trip_id}/days/{day_index}/attachments/{attachment_id}/download-url`
- `GET /trips/{trip_id}/pois/{poi_id}/attachments`
- `POST /trips/{trip_id}/pois/{poi_id}/attachments`
- `DELETE /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}`
- `GET /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}/download-url`
- `GET /trips/{trip_id}/files`

여행/날짜/POI 첨부 등록은 DB metadata 기준 용량 quota를 검사한다. 개별 파일, 여행계획 총량,
사용자 총량의 전역값과 사용자별 override 정책은 `storage.md` §5.7을 따른다.

## 10. 일정 자동 최적화

자세히는 SPEC V8 H-8 / `docs/spec/v8/02-backend.md` §6.

- `POST /trips/{trip_id}/days/{day_index}/optimize`
- `GET /trips/{trip_id}/days/{day_index}/distance-matrix`

T-132 MVP는 kor-travel-map live lookup 없이 저장된 `feature_snapshot.coord` 또는
`feature_snapshot.location`의 `(longitude, latitude)`를 사용한다. 거리 행렬은 haversine
meter 정수 또는 좌표 누락 시 `null`을 반환한다. optimize는 `nearest_neighbor`만 지원하며,
좌표 없는 POI는 경고와 함께 기존 순서로 뒤에 둔다. `persist=true`면 POI `sort_order`를
새 LexoRank로 저장하고 `poi.reordered` realtime event를 발행한다.

## 11. 여행 내보내기

내보내기는 **현재 저장된 Pinvi snapshot**을 기준으로 만든다. PDF/print/GPX 생성 중
kor-travel-map live lookup을 수행하지 않는다. feature 최신 정보가 없어도
`feature_snapshot`, POI 메모, 일정 순서만으로 출력 가능해야 한다.

| 형식  | 초기 구현                                                  | 권한                                    | 비고                           |
| ----- | ---------------------------------------------------------- | --------------------------------------- | ------------------------------ |
| print | Web route `/trips/{trip_id}/print`                         | owner/editor/viewer + share `view_only` | 브라우저 print/PDF 저장의 원천 |
| PDF   | print route 기반 브라우저 PDF 저장 우선, server PDF는 후속 | owner/editor/viewer                     | 서버 생성 시 저장 없이 stream  |
| GPX   | API file response                                          | owner/editor/viewer                     | share token은 v1.0 초기 제외   |

### 11.1 `GET /trips/{trip_id}/exports/print-data`

```http
GET /trips/{trip_id}/exports/print-data?scope=all&include=notes,rise_set
Cookie: pinvi_access=...
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
            "coord": { "lon": 129.0319, "lat": 35.1009 },
            "planned_arrival_at": "2026-06-01T14:00:00+09:00",
            "user_note": "...",
            "rise_set": { "status": "success", "sunset_at": "..." },
          },
        ],
      },
    ],
    "warnings": [],
  },
}
```

### 11.2 `GET /trips/{trip_id}/exports/gpx`

```http
GET /trips/{trip_id}/exports/gpx?scope=all&include_notes=false
Accept: application/gpx+xml
Cookie: pinvi_access=...
```

- `Content-Type`: `application/gpx+xml; charset=utf-8`
- `Content-Disposition`: `attachment; filename="pinvi-{trip_id}.gpx"`
- 각 day는 `<rte>` 하나로 만들고, POI는 `sort_order` 순서의 `<rtept>`로 출력한다.
- 좌표가 있는 POI는 `<wpt>`도 함께 출력한다. `planned_arrival_at`이 있으면 GPX `time`에
  KST offset 포함 ISO 8601로 넣는다.
- 좌표 없는 POI는 건너뛰고 `X-Pinvi-Export-Warnings`에 개수를 기록한다. 출력 가능한
  좌표가 하나도 없으면 `422 EXPORT_NO_COORDINATES`.
- `include_notes=true`는 owner/editor만 허용한다. viewer는 POI 제목·좌표·일정 시각만.

### 10.3 `GET /trips/{trip_id}/exports/pdf`

```http
GET /trips/{trip_id}/exports/pdf?scope=all&include=notes,rise_set,map_overview
Cookie: pinvi_access=...
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
- [ ] `apps/api/app/services/trip.py` 비즈니스 로직 (권한 검사 + kor-travel-map batch join)
- [ ] `apps/api/app/api/v1/trips.py` 라우터
- [ ] `GET /trips` 검색 파라미터(`q`, `status`, `visibility`, `date_from/to`, `sort`) 구현
- [ ] `exports/print-data`, `exports/gpx`, `exports/pdf` 계약에 맞는 schema / permission 테스트
- [x] kor-travel-map HTTP client에서 `POST /v1/features/batch` 호출 패턴
- [ ] 통합 테스트 `apps/api/tests/integration/test_trips_api.py`
- [ ] WebSocket broadcast 트리거 추가
- [ ] 본 문서 + `common.md` 표준 에러 코드 갱신

### 여행 기간 부분 수정 검증 (#624)

PATCH는 날짜 입력을 기존 값과 합쳐 시작·종료 날짜가 함께 있고 종료일이 시작일 이상인지 검사한다. 날짜의 생략·null은 기존 값을 유지한다. 무효한 기간은 다른 필드·버전을 변경하지 않고 422 VALIDATION_ERROR와 날짜 안내를 반환한다(문구는 화면에 그대로 보이는 한국어 — '종료일은 시작일 이후여야 합니다.', '시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.'). 버전 충돌은 우선하여 409를 반환한다.

시작일이 바뀌면 지정 날짜가 없는 일자의 날짜도 함께 움직인다. 그 결과 두 일자의 유효 날짜가 같아지면 422('N일차와 M일차의 날짜가 겹칩니다. …')로 거부한다(#649와 같은 불변식). PATCH와 휴지통 이동(soft delete)은 같은 여행 행을 잠근 뒤 휴지통 여부와 version을 다시 확인하므로, 같은 If-Match의 동시 PATCH는 하나만 성공하고 삭제된 여행은 404다. 공유 편집 링크 PATCH도 같은 경로를 쓴다.

### 공유 댓글·여행 정보 편집 (#625)

유효한 토큰으로 GET /trips/{trip_id}/shared/{token}/comments를 읽는다(comment/edit 링크만).
로그인 사용자는 같은 경로에 POST로 여행 댓글을 작성하고 /comments/{comment_id} DELETE로 본인 댓글을 지울 수 있다.
여행 소유자도 댓글을 삭제할 수 있다. view_only 링크는 이 경로에서 403이다.
edit 링크는 PATCH /trips/{trip_id}/shared/{token}로 제목·설명·지역·기간을 변경할 수 있다.
If-Match 버전을 요구하고 공유 관리·소유권·visibility·status 필드는 허용하지 않는다.
모든 요청에서 trip_id, 토큰 만료·철회를 검사하며 공유 권한을 영구 동반자 권한으로 전환하지 않는다.
미래의 timezone-aware expires_at만 발급 가능하다(#626). 날짜 UI는 한국 날짜 기준으로 과거 일자를 막는다.

## 휴지통과 복원 (#633)

GET /trips?trashed=true는 호출자가 소유한 삭제 여행만 기존 cursor 방식으로 나열한다. 휴지통에는 bucket(예정/지난)을 적용하지 않는다 — bucket을 생략해도 지난 여행이 포함된다.
POST /trips/{trip_id}/restore는 소유자의 삭제 여행을 초안으로 복원하고 version을 올려 200을 반환한다.
이미 활성화됐거나 다른 소유자의 여행은 404다. 기존 삭제가 원래 상태를 보관으로 덮어썼으므로 복원 상태는 초안으로 통일한다.
공개 범위와 공유 링크를 보존한다. 복원 후 만료·철회되지 않은 기존 공유 링크는 다시 접근 가능하다.
일자·POI·첨부 메타데이터와 객체를 보존한다. 복원·업로드는 여행과 업로더를 같은 순서로 잠가 총량을 검사한다.
삭제 후 30일 미만이며 정리가 시작되지 않은 여행만 복원한다. 기한 경과 또는 정리 시작 뒤에는 410 TRIP_TRASH_EXPIRED다. 보존 파일은 계속 과금하므로 복원은 추가 용량으로 계산하지 않는다.

## 일자 메모와 유효 날짜 (#640/#649)

TripViewDay.note는 nullable이며 소유자·공유 뷰 모두 제공한다. 생성·수정 시 note는 최대 2,000자(댓글과 같은 상한)이고 넘으면 422다.
PATCH 일자의 date는 override 전용이다. null이면 시작일에서 파생한 날짜를 쓰고, 다른 일자의 override 또는 파생 날짜와 중복되면 422 VALIDATION_ERROR다.
버전 충돌은 날짜 검증에 앞서 409를 반환한다. 날짜 검사와 수정은 동일한 여행 잠금 안에서 실행한다.
POI 생성으로 없는 일자를 자동 생성할 때도 같은 날짜·여행 기간 규칙을 적용한다.

### 날씨 카드의 오래된 정보 표시

Map 경로는 선택된 부분의 freshness.stale가 true이거나 source_status가 stale이면 내부 사실에 경고 근거를 보존한다. provider 중복 제거와 여행 날짜 선택 이후 남은 사실 중 하나라도 해당하면 카드의 is_stale가 true다. 위치 roster의 신선도와 위치 해석 캐시의 stale는 카드에 섞지 않으며, 대상 날짜가 과거라는 이유만으로 경고하지 않는다.

이 bool은 카드 전체에 업데이트가 지연된 자료가 포함됨을 뜻한다. 특정 현재기온 한 값이 오래됐다는 뜻은 아니다. 직접 weather 경로와 freshness 메타 부재에서 false는 최신 검증을 뜻하지 않으며, 근거 없는 수집 SLA를 새로 정하지 않는다.

### 휴지통 보존 기한 (#667)

TripResponse의 trash_expires_at은 삭제 시각+30일이며 can_restore는 서버에서 계산한다. 미삭제 여행은 기한이 없고 복원 대상이 아니다. UI는 휴지통 보존 안내와 복원 불가 이유를 표시한다. 기한 경과는 관리자 영구 정리의 실제 실행 여부와 무관하게 복원을 차단한다.
