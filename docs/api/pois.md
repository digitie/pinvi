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
- `rise_set`(응답 전용, 저장 없음 — 0109): 일자 effective 날짜와 장소 좌표로 응답 때 `astral` 계산한
  일출·일몰·월출·월몰(`apps/api/app/services/sun_times.py`). 날짜가 없으면 `pending_date`, 좌표가 없으면
  `pending_coord`, 있으면 `success`(그날 달이 뜨거나 지지 않으면 그 값만 null)

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
- (은퇴 0109 — 아래 두 항목은 KASI 저장 시절 기록이다. 지금은 응답마다 계산하므로 이동·날짜 변경이 바로 반영된다.)
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

## 장소 현재 날씨 (`GET /trips/{trip_id}/pois/{poi_id}/weather`)

장소 목록의 날씨 배지(아이콘 + 현재 기온 + 오늘 최고/최저)와 날씨 예보 팝업(시간별 기온·강수확률,
일별 최고/최저, 기상 특보)이 쓴다. 여행 멤버(viewer 포함)만 조회할 수 있다(비멤버 403, 없는·삭제된
장소 404).

- 응답은 `GET /features/{id}/weather`(`asof` 없음)와 같은 `FeatureWeatherCard` 셰입이다 — 관측·실황 +
  가까운 3일 예보 + 특보(`forecast_style="advisory"`).
- 좌표는 Map feature를 다시 조회하지 않고 POI snapshot 좌표(`cache_target_lon/lat`)를 쓴다. 그래서 지도
  feature가 없는 직접 추가 장소(manual/kakao/naver)도 날씨가 나온다. snapshot에 좌표가 없으면 빈 카드다.
- 위치 해석 캐시(`weather_location_links`) 키는 feature가 있으면 `feature_id`(trip view와 공유), 없으면
  `poi:{poi_id}`다. 응답의 `feature_id`가 이 키다.
- 소스 선택(Map 경로/kor-travel-weather 직접)과 `503 WEATHER_SERVICE_UNAVAILABLE` 정책은 feature
  weather와 같다. 첫 조회(캐시 미스)는 배경 해석 동안 빈 카드일 수 있다.
- 웹은 장소별 카드를 공유 캐시(`apps/web/lib/usePoiWeather.ts`, 동시 2건·성공 10분/실패 1분)로 받아
  배지·팝업·장소 정보 패널이 나눠 쓴다. 화면 표시 규칙(제공자 우선순위, 상태 판정)은
  `apps/web/lib/weatherNow.ts`가 정본이다.

## 장소 영업 정보 (`/trips/{trip_id}/pois/{poi_id}/place-details`)

지도 마커(또는 목록 행)를 고르면 뜨는 장소 정보 패널(`apps/web/components/trips/PlaceInfoPanel.tsx`)이
쓴다. 영업시간·휴무일·전화·웹사이트를 **여행에 넣은 장소 하나에만** 붙여 저장한다(`trip_poi_place_details`,
migration `20261116_0108`). 전역 장소 데이터로 보관하지 않는다.

- `GET`: 저장값이 있으면 그대로, 없으면 출처에서 한 번 받아 저장한 값을 준다. 여행 멤버(viewer 포함).
  출처에 값이 없으면 `status="empty"`로 저장해 다시 묻지 않는다. 출처 장애는 저장하지 않고
  `200 status="unavailable"`(화면은 조용히 '확인된 영업 정보가 없습니다.').
- `POST .../refresh`("다시 읽어오기"): 편집 권한(owner/co_owner/editor)만. 같은 장소 60초에 1회
  (`429 RATE_LIMITED` + `Retry-After`), 받은 값으로 덮어쓴다. 출처 장애는 `503 PLACE_DETAILS_UNAVAILABLE`이고
  기존 값을 둔다. 응답의 `refresh_available_at`이 다음 허용 시각이다.
- 삭제: 장소 삭제(`DELETE /trips/{id}/pois/{poi}` → soft delete)가 같은 트랜잭션에서 행을 지운다. 영구
  삭제(여행 purge 등)는 FK `ON DELETE CASCADE`. 같은 곳을 다시 넣으면 새 POI라 처음 열 때 다시 받는다.

### 출처별 판단 (공식 API만, 약관 준수)

| 출처                                    | 영업시간                                                                                             | 휴무일                                                       | 전화                           | 웹사이트                            | 사용                                                                                                                                                                                                                                     |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------ | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| kor-travel-map feature 상세(공공데이터) | `business_hours`(Google 호환 periods/weekday_text) 또는 출처 원문(`facility_info.operating_time` 등) | periods에서 쉬는 요일, `special_days`, 원문(`rstde_info` 등) | `phones[]`/`facility_info.tel` | `urls.homepage`/`facility_info.url` | **저장** (`sources` 값 `kor_travel_map`)                                                                                                                                                                                                 |
| Kakao Local (키워드 검색)               | 없음                                                                                                 | 없음                                                         | `phone`                        | 없음(`place_url`만)                 | 저장 안 함 — ADR-054(응답 저장·재전달 금지). 상세 카드의 라이브 표시로만                                                                                                                                                                 |
| Naver Local (지역 검색)                 | 없음                                                                                                 | 없음                                                         | `telephone`(대부분 빈 값)      | `link`(일부)                        | 저장 안 함 — ADR-054                                                                                                                                                                                                                     |
| Google Places Details (New)             | `regularOpeningHours`                                                                                | 있음                                                         | `nationalPhoneNumber`          | `websiteUri`                        | **사용 안 함** — Places 콘텐츠 캐시·저장 금지(place_id만 허용), 비 Google 지도(VWorld) 위 표시 금지(Service Specific Terms). PinVi에는 키도 없고, 키를 가진 kor-travel-concierge에도 키를 넘겨주거나 Details를 대신 조회하는 계약이 없다 |

HTML 화면 스크래핑은 하지 않는다. 지도 feature가 없는 직접 추가 장소(manual/kakao/naver)는 저장 가능한
출처가 없어 `empty`다.

### Kakao 전화 라이브 표시 (`GET .../place-details/kakao-phone`, 2026-11-17 소유자 결정)

저장된 영업 정보에 전화가 없을 때만 패널(영업 정보 항목을 펼쳤을 때)이 부른다. PinVi 백엔드가 Kakao Local
키워드 검색(장소 이름 + 장소 자신의 좌표)에서 이름·300 m 가드를 통과한 장소의 전화와 카카오맵 back-link를
`ExternalEnrichment`(provider=`kakao`)로 돌려준다. **DB에 저장하지 않는다**(ADR-054 유지) — 서버 프로세스
메모리 캐시(10분, 최대 1024건)와 브라우저 세션 메모리만 쓴다. 저장된 전화가 있으면 Kakao를 부르지 않는다.
못 찾거나 장애면 200 `matched=false`이고 화면에는 아무것도 더하지 않는다. 화면은 '전화 (카카오)' 라벨과
'출처: 카카오맵' 링크로 출처를 표시한다. Google Places는 쓰지 않는다(같은 결정).

### 지도 앱 링크

네이버·카카오·구글 지도 링크는 공개 URL 규약만 써서 키가 필요 없다(`apps/web/lib/mapLinks.ts`). PC는 웹
주소를 새 탭으로, 모바일은 앱을 먼저 연다 — Android `intent://…;S.browser_fallback_url=`(앱 없으면 웹),
iOS 앱 스킴(`nmap://`, `kakaomap://`) 뒤 화면이 그대로면 1.5초 뒤 웹으로. 구글은 `google.com/maps/search/?api=1`
주소가 모바일에서 앱을 직접 연다.

## 지도 장소 상세 카드 영업시간

`GET /features/{id}/detail-card`의 `business_hours`는 Map의 구조화 영업시간(`FeatureOpeningHours`)을
요일별 줄(`월요일: 09:00~18:00`, 쉬는 요일은 `휴무`)로 펴 줄바꿈으로 이은 문자열이다(`weekday_text`가
있으면 그대로). 예전에는 문자열만 읽어 구조화 값이 카드에서 빠졌다. 장소 영업 정보 저장과 같은 규칙
(`app/services/opening_hours.py`)을 쓴다.

## 지도 장소 상세 카드 출처 소개(TourAPI)

`GET /features/{id}/detail-card`의 place 카드는 `introduction`을 함께 준다(없으면 `null`). Map이 한국관광공사
국문 관광정보 서비스(KorService2, data.go.kr 15101578)에서 적재한 관광지·문화시설·레포츠 feature의
`detail.facility_info`(`tourapi_content_id`가 있는 행만)를 투영한다(`app/services/source_introduction.py`).

| 필드                                          | 뜻                                                                                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `provider`                                    | `tourapi`                                                                                                                                   |
| `attribution`                                 | 출처 표시 문구 — `한국관광공사`                                                                                                             |
| `overview`                                    | `detailCommon2` 소개문. 서버가 태그 꼴·제어 문자를 걷어 낸 평문(줄바꿈 보존). 20,000자를 넘으면 자르지 않고 싣지 않는다(제3유형 변경금지).  |
| `images[]`                                    | 대표 이미지 원본 URL(`firstimage`, 최대 1장). `*.visitkorea.or.kr` https만, `http`는 같은 주소 https로. 공공누리 유형을 모르면 싣지 않는다. |
| `images[].no_derivatives`                     | 제3유형(변경금지)이면 `true`                                                                                                                |
| `kogl_type` / `license_label` / `license_url` | 이미지의 공공누리 유형(1·3), 표시 문구, kogl.or.kr 유형 설명 링크. 이미지가 없으면 `null`                                                   |

화면 규칙(웹 `components/map/SourceIntroduction.tsx`, 모바일 `components/SourceIntroduction.tsx`):

- 지도 상세 카드는 주소 위에, 여행 장소 정보 패널(웹 `PlaceInfoPanel`)·장소 시트(모바일 `PlaceSheet`)는 맨 앞
  `소개` 항목으로 둔다. 소개문·이미지가 둘 다 없으면 블록·항목을 만들지 않는다. 여행 장소 쪽은 저장하지 않고
  같은 detail-card를 읽는다(`trip_poi_place_details` 변경 없음).
- 이미지는 서버가 내려받거나 줄이지 않는다. 화면은 원본 URL을 크롭·필터 없이 원본 비율(`object-contain`,
  RN `resizeMode="contain"`)로 그리고, 누르면 원본을 새 창으로 연다. 불러오지 못하면 틀과 공공누리 표시를 함께 뺀다.
- 소개문은 텍스트로만 그린다(`dangerouslySetInnerHTML` 없음). 4줄·140자를 넘으면 접고 `소개 더 보기`로 펼친다.
- 출처 줄 `출처: 한국관광공사`는 소개문·이미지 중 하나라도 보이면 늘 붙는다. 이미지가 보이면 공공누리 유형 링크도 붙는다.
