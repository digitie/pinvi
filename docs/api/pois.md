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

## 지도 장소 상세 카드 출처 소개·이용 안내 (Map `visitor_info`, ADR-126)

`GET /features/{id}/detail-card`의 place 카드와 event 카드(TourAPI 축제)는 `introduction`(출처 소개)과
`visit_guide`(이용 안내)를 함께 준다(보여 줄 값이 없으면 각각 `null`). 정본 입력은 Map 공개
`GET /v1/features/{id}`의 최상위 `visitor_info`(`PlaceVisitorInfo`, Map ADR-126)다
(`app/services/source_introduction.py`). Map이 `visitor_info`를 주지 않는 옛 응답이면 place만 #809의 평면 키
(`detail.facility_info`의 `tourapi_content_id`·`overview`·`image_url`·`license`)로 `introduction`을 대신 만든다
(`visit_guide`는 `null`).

원천(`provider`)과 출처 문구(`attribution`)는 PinVi가 고정한다 — Map 값으로 바꿔 달지 않고, 모르는 원천은 통째로
싣지 않는다.

| `provider`                   | `attribution`                                 | 이미지                                 |
| ---------------------------- | --------------------------------------------- | -------------------------------------- |
| `tourapi`                    | 한국관광공사                                  | `*.visitkorea.or.kr` https만           |
| `krheritage`                 | 국가유산청, www.khs.go.kr                     | 없음(라이선스 코드 미확인 — 받지 않음) |
| `datagokr_museum`            | 공공데이터포털 전국박물관미술관정보표준데이터 | 없음                                   |
| `krforest_recreation_forest` | 공공데이터포털 전국휴양림표준데이터           | 없음                                   |

### `introduction`

| 필드                                     | 뜻                                                                                                                                                                                                              |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `provider` / `attribution`               | 위 표                                                                                                                                                                                                           |
| `reference_date`                         | 원천 기준일(`YYYY-MM-DD`, 없으면 `null`) — 화면은 `출처: … · 기준일 …`로 적는다                                                                                                                                 |
| `overview`                               | 소개문(TourAPI overview·국가유산 설명문·박물관 소개). 서버가 알려진 HTML 태그·제어 문자를 걷어 낸 평문(줄바꿈 보존, `<A코스>`·`<삼국유사>` 같은 본문 꺾쇠는 그대로). 20,000자를 넘으면 자르지 않고 싣지 않는다. |
| `images[]`                               | 원본 이미지 URL(최대 10장, 첫 장이 대표). 원천 썸네일은 쓰지 않는다. `http`는 같은 주소 https로. 같은 URL은 한 번만.                                                                                            |
| `images[].kogl_type`                     | 그 이미지의 공공누리 유형(1~4 — 제0유형은 근거 확인 전까지 싣지 않는다). 이미지마다 다를 수 있다(대표 사진 제3유형, 갤러리 제1유형 등).                                                                                                                  |
| `images[].no_derivatives`                | 변경금지(제3·4유형)면 `true`                                                                                                                                                                                    |
| `images[].license_label` / `license_url` | 표시 문구(`공공누리 제3유형: 출처표시 + 변경금지` 등)와 kogl.or.kr `licenseType{N}.do` 링크                                                                                                                     |

이미지 라이선스는 fail-closed다: Map `license`의 `kogl_type`·`derivatives_allowed`·`commercial_allowed`가 서로 맞지
않거나 유형을 모르면 그 이미지를 싣지 않는다. 상업적 이용금지(제2·4유형)는 PinVi의 상업성 판단(소유자) 전까지 싣지
않는다(`_SHOW_NONCOMMERCIAL_ONLY_IMAGES`). 국가유산 이미지(Map이 싣지 않음)와 옛 `image_url`·파일 이미지는 허용
호스트가 없어 보이지 않는다.

`kogl_type`·`license_label`·`license_url`(최상위)은 **deprecated**다 — #809 클라이언트(이미 깔린 앱) 호환용으로 첫
이미지의 값을 그대로 담는다(이미지가 없으면 `null`). 새 화면은 `images[]`의 값을 이미지마다 쓴다.

이 호환은 부분적이다. #809 클라이언트는 응답 전체를 엄격한 zod 스키마로 검증하므로(`@pinvi/api-client`
`RESPONSE_SHAPE_INVALID`), 다음 경우 **상세 카드 전체**가 실패한다: `provider`가 `tourapi`가 아님(국가유산·박물관·
휴양림), 이미지가 3장 초과, 이미지 `kogl_type`이 1·3 밖. 실패하지 않는 TourAPI 카드에서도 #809 화면은 최상위 값(첫
이미지의 공공누리 표시) 하나만 모든 사진 아래에 단다. 확인한 배포 범위(2026-11-28): 웹은 API와 함께 배포되어 새 번들로
바뀐다. 모바일은 `apps/mobile/package.json`·`app.json` 버전 0.1.0, `eas.json`의 빌드 프로필은 `development`·`preview`가
`distribution: internal`이고 스토어 제출(`submit`) 설정이 없다 — 공개 출시본이 없고 #809(2026-11-27 머지)는 내부
빌드에만 들어갔다. 그래서 위 한계를 받아들인다(공개 출시 전에는 새 빌드로 바꾼다).

#809 대비 계약 변경: `provider`가 `tourapi` 하나에서 원천 4종으로 넓어졌고(클라이언트 스키마는 문자열로 받고 아는
값만 보인다), `reference_date`가 생겼고, 이미지 최대 1장 → 10장, 공공누리 표시가 이미지마다(`images[].license_*`)로
옮겨졌다. 클라이언트 zod는 `introduction`·`visit_guide` 블록 하나가 모양이 어긋나도 그 블록만 `null`로 두고 카드
전체를 버리지 않는다(`.catch(null)`). 서버 투영과 클라이언트 스키마의 정합은 golden
`apps/web/tests/fixtures/detail-card-golden.json`(서버 `test_visitor_info_projection.py`가 생성·대조, 웹
`detailCardGolden.test.ts`가 파싱)으로 지킨다.

소개문·이용 안내 문장 정리에서 `<script>`·`<style>`은 태그뿐 아니라 안의 내용까지 통째로 지운다.

### `visit_guide`

`usage_hours`(이용시간)·`rest_days`(휴무일)·`parking`·`parking_fee`·`fee_text`·`discount`·`reservation`·`inquiry`·
`transport`·`facilities`·`capacity`·`pet_note`는 원천 문장 그대로의 평문이다(태그·제어 문자만 걷음, 줄바꿈 보존,
2,000자 넘으면 싣지 않음). `fees[]`는 원천이 숫자로 준 요금(`audience` adult/youth/child, `amount_krw`),
`accommodation_available`은 숙박 가능 여부, `accessibility[]`는 무장애 안내(`group` physical/visual/hearing/
infant_family, `facility` 코드, `label` 시설 한글 이름, `text` 원문), `pet_policy`는 반려동물 동반 안내
(`companion_type`·`allowed_pets`·`requirements`·`notes`). 모르는 `group`·`audience` 값은 버린다.

### 화면 규칙

웹 `components/map/SourceIntroduction.tsx`·`components/map/VisitGuide.tsx`, 모바일 `components/SourceIntroduction.tsx`·
`components/VisitGuide.tsx`. 판정·문구는 `@pinvi/domain` `sourceIntroduction.ts`·`visitGuide.ts`가 한 곳에서 정한다.

- 지도 상세 카드는 소개를 주소 위에, 이용 안내를 kind별 사실 아래 `이용 안내` 구역으로 둔다. 여행 장소 정보 패널(웹
  `PlaceInfoPanel`)·장소 시트(모바일 `PlaceSheet`)는 고정 항목 뒤·지도 앱 앞에 `소개`·`이용 안내` 항목을 둔다(응답이
  늦게 와도 앞 버튼이 밀리지 않게). 보여 줄 것이 없으면(이미지가 깨진 경우 포함) 블록·항목을 만들지 않는다. 여행 장소
  쪽은 저장하지 않고 같은 detail-card를 읽는다.
- 이미지는 서버가 내려받거나 줄이지 않는다. 화면은 원본 URL을 크롭·필터 없이 원본 비율(`object-contain`, RN
  `resizeMode="contain"`)로 그리고, 누르면 원본을 새 창으로 연다. 여러 장이면 가로 갤러리(웹 `overflow-x-auto`, RN
  가로 `FlatList` — 화면 근처 2~3장만 그린다, `removeClippedSubviews`는 쓰지 않는다), 웹은 lazy loading. 갤러리 레이아웃은 처음 받은 장수로 정해 한 장이
  깨져도 틀이 바뀌지 않는다. 공공누리 표시는 이미지마다 그 아래에 붙고, 불러오지 못한 이미지는 틀과 표시를 함께 뺀다.
- 소개문·이용 안내 문장은 텍스트로만 그린다(`dangerouslySetInnerHTML` 없음, 웹 `whitespace-pre-line`). 소개문은 4줄·140자를
  넘으면 접고 `소개 더 보기`로 펼친다.
- 요금은 `성인 2,000원 · 청소년 1,000원 · 어린이 무료`로 적고 `fee_text` 원문을 그 아래 둔다. `fee_text`가 있으면 0원이
  조건부일 수 있어 `무료`로 해석하지 않고 `0원`으로 적는다.
- 여행 장소 정보 패널·장소 시트는 영업 정보 항목이 이미 보이는 이용시간·휴무를 이용 안내에서 뺀다(같은 원문이 두 번
  보이지 않게, `omitShownHours`). 저장된 영업 정보의 그 필드 출처(`sources`)가 이 이용 안내의 원천과 같을 때만 뺀다 —
  구조화 영업시간(Map)이나 다른 원천·옛 캐시 값이면 내용이 다를 수 있어 둘 다 보인다. 지도 상세 카드는 영업 정보 항목이
  없으므로 다 보인다.
- 배지 `무장애 안내`(`accessibility`가 비지 않을 때)와 `반려동물 동반`(`pet_policy`가 있을 때)은 아이콘·글자·펼침 표시가
  있는 버튼(`aria-expanded`, 펼쳤을 때만 `aria-controls`, 44px; 모바일은 펼침 기호 없이 글자만 읽힌다)이다 — 색만으로 뜻을 전하지 않는다. 무장애는 분류별로 `label: text`.
  `pet_note` 한 줄은 배지가 아니라 표 줄 `반려동물`이다(원문을 해석하지 않는다).
- 출처 줄 `출처: {attribution}`(+ `· 기준일 {reference_date}`)은 소개·이용 안내 블록마다 늘 붙는다.
- 이미지 URL(원천별 허용 호스트 https)과 공공누리 링크(`https://www.kogl.or.kr/`)는 화면도 `@pinvi/domain`으로 한 번 더
  거른다(서버 검증과 이중). 이미지 틀은 고정 높이(웹 `h-56`, 모바일 180)이고 모서리를 깎지 않는다.

### 여행 장소 영업 정보(`trip_poi_place_details`)

`app/services/poi_place_details.py`는 구조화 영업시간(`business_hours`)이 없을 때 `visitor_info.usage_hours`·
`rest_days` 원문을 옛 평면 키(`usetime`·`restdate` 등)보다 먼저 읽는다(원문 한 줄 그대로 — 여러 줄이면 줄바꿈 포함).
아는 원천(`source`)일 때만 읽고, 그 값을 쓴 필드는 `sources`에 실제 원천(`tourapi` 등)을 남겨 화면이
`출처: 한국관광공사`처럼 정확히 보인다(`@pinvi/domain` `placeDetails.ts` `SOURCE_LABELS`). 구조화 영업시간을 썼으면 휴무도
구조화 값(쉬는 요일·특별 휴무)을 `visitor_info.rest_days` 원문보다 앞세운다. `visitor_info`가 없어 옛 평면 키
(`facility_info.usetime`·`restdate` 등)로 떨어져도 TourAPI 행(`tourapi_content_id`가 있음)이면 출처를 `tourapi`로 남긴다.
출처 표시 문구는 소개 블록과 같다(`krheritage` → `국가유산청, www.khs.go.kr`).
저장된 행은 캐시라 Map이 `visitor_info`를 새로 줘도 그 장소에서 **"다시 읽어오기"를 누르기 전까지 예전 값**을 보인다
(일괄 재수집 없음).
