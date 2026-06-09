# Feature API (`/features/*`)

`python-krtour-map` 독립 프로그램의 지도 feature를 TripMate가 OpenAPI HTTP로 읽어서
클라이언트에 제공한다. **TripMate는 응답 셰입을 갖고, 데이터는 krtour-map
`openapi.user.json` 계약으로 가져온다**(ADR-026 / ADR-003). 공통 규약
[`common.md`](./common.md).

## 1. 책임

- 본 API는 TripMate가 제공 — URL/응답 셰입은 본 저장소 소유
- 데이터는 krtour-map API `9011`의 OpenAPI HTTP 호출
  (`docs/krtour-map-integration.md`)
- TripMate는 provider/feature 도메인 wrapper를 두지 않음. HTTP client는 transport
  역할만 한다.
- 좌표를 query/body에 받는 endpoint는 `app.location_access_log` 자동 적재
  (`docs/architecture/user-location.md`)

## 2. Endpoint

### 2.1 `GET /features/in-bounds`

viewport 안 feature 조회 + zoom별 클러스터링.

```http
GET /features/in-bounds?sw_lng=129.0&sw_lat=35.0&ne_lng=129.2&ne_lat=35.2&zoom=12&kinds=place,event
Cookie: tripmate_access=...
```

- `sw_lng, sw_lat, ne_lng, ne_lat`: bbox (EPSG:4326)
- `zoom`: 5~19 (`apps/api/app/api/v1/features.py`와
  `packages/schemas/src/feature.ts` 기준. Satellite/Hybrid는 z18까지)
- `kinds`: `place,event,notice,price,weather,route,area` 중 콤마 구분
- zoom별 클러스터 자동 (SPEC V8 I-4):
  - `zoom < 7`: 시도 단위
  - `zoom < 11`: 시군구
  - `zoom < 14`: 읍면동
  - `zoom >= 14`: 개별 마커

응답 200:

```jsonc
{
  "data": {
    "cluster_unit": "sigungu",     // sido | sigungu | eupmyeondong | individual
    "items": [
      // cluster_unit != individual:
      {
        "cluster_code": "11680",
        "display_name": "강남구",
        "count": 47,
        "center": { "longitude": 127.04, "latitude": 37.52 },
        "kind_breakdown": { "place": 30, "event": 5, "notice": 12 }
      },
      // individual:
      {
        "feature_id": "f_2611000000_p_abc123...",
        "kind": "place",
        "title": "광안리 해수욕장",
        "coord": { "longitude": 129.118, "latitude": 35.155 },
        "address_road": "...",
        "address_jibun": "...",
        "category": "해수욕장",
        "marker_color": "P-07",
        "marker_icon": "swimming",
        "parent_feature_id": null,
        "sibling_group_id": "uuid",
        "status": "active",
        "updated_at": "..."
      }
    ]
  }
}
```

krtour-map 호출: `GET /features/in-bounds`.

Rate limit: 분당 60회 per user. 클라이언트 측 디바운스 250ms + AbortController 권장.

### 2.2 `GET /features/{feature_id}`

feature 상세.

```http
GET /features/f_2611000000_p_abc123...
```

응답 200:

```jsonc
{
  "data": {
    "feature_id": "...",
    "kind": "place",
    "title": "...",
    "coord": { "longitude": ..., "latitude": ... },
    "address_road": "...",
    "address_jibun": "...",
    "category": "...",
    "marker_color": "P-07",
    "marker_icon": "swimming",
    "urls": {
      "homepage": "...",
      "sns1": null,
      "review_naver": "...",
      "review_kakao": "...",
      "review_google": null
    },
    "detail": {
      // kind+category별 Pydantic 모델 (PlaceDetail / EventDetail / ...)
      "phones": ["051-..."],
      "business_hours": { /* ... */ },
      "entry_fee": null,
      "parking_fee": null
    },
    "raw_refs": [
      { "source_type": "python-krmois-api", "source_id": "...", "fetched_at": "..." }
    ],
    "parent_feature_id": null,
    "sibling_group_id": "uuid",
    "status": "active",
    "deleted_at": null,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

krtour-map 호출: `GET /features/{feature_id}`.

### 2.3 `GET /features/{feature_id}/weather`

해당 좌표/지점의 날씨 (관측 + 예보 + 특보).

```http
GET /features/{feature_id}/weather?asof=2026-06-02T14:00:00+09:00
```

`asof`: 시각 (생략 시 now). KST aware.

응답 200:

```jsonc
{
  "data": {
    "feature_id": "...",
    "asof": "...",
    "nowcast": { /* KMA 초단기실황 */ },
    "ultra_short": [/* KMA 초단기예보 +6h */],
    "short": [/* KMA 단기예보 +3day */],
    "mid": { /* KMA 중기예보 +10day */ },
    "advisories": [/* KMA 특보 */],
    "sources": [
      // 같은 valid_at에 들어온 다른 provider 값
      { "provider": "python-krex-api", "slot": "rest_area_weather", "...": "..." },
      { "provider": "python-airkorea-api", "slot": "air_quality", "pm10": 32, "pm25": 18 },
      { "provider": "python-khoa-api", "slot": "beach_marine", "wave_m": 0.5 }
    ]
  }
}
```

KMA 시간축이 기본 (SPEC V8 R-4). 다른 provider 값은 sources 배열에 끼워 넣어
사용자에게 한 카드로 표시.

날씨 feature/detail 제공 여부는 krtour-map 최신 OpenAPI 계약을 따른다. TripMate가
별도 KMA provider 변환을 직접 구현하지 않는다.

### 2.4 `GET /features/nearby`

좌표 주변 feature 조회.

```http
GET /features/nearby?lng=129.118&lat=35.155&radius_m=5000&kinds=place,event
Cookie: tripmate_access=...
```

- 좌표: EPSG:4326
- `radius_m`: meter (라이브러리가 `coord_5179` 컬럼 사용 — SPEC V8 §SKILL DO-NOT 11)
- 최대 `radius_m = 50000` (50km)

응답: `features_in_bounds`와 같은 individual 셰입 배열 (cluster X).

krtour-map 호출: 기준 feature가 있으면 `GET /features/nearby/by-target`를 우선한다.

### 2.5 `POST /features/requests`

사용자가 "feature 추가 요청"을 TripMate 소유 Admin 검토 큐에 등록한다. 이 엔드포인트는
`python-krtour-map`을 직접 호출하지 않고 `app.feature_suggestions`에만 적재한다. Admin
검사/승인 뒤 krtour-map feature change API로 반영하는 단계는 T-179에서 연결한다.

```http
POST /features/requests
Content-Type: application/json
Cookie: tripmate_access=...

{
  "type": "new_place",
  "kind": "place",
  "title": "새 카페",
  "coord": { "longitude": 129.0, "latitude": 35.0 },
  "categories": ["카페"],
  "note": "..."
}
```

`type`(기본 `new_place`)은 `new_place` | `correction` | `closure` 중 하나다. `correction`/`closure`
(기존 feature 정보 수정·폐업 제보)는 `target_feature_id`가 **필수**이고, `new_place`는
`target_feature_id`를 가질 수 없다(위반 시 `422 VALIDATION_ERROR`).

동일 사용자가 같은 `type` + `target_feature_id` + `kind` + 정규화된 `title` + 소수 6자리 좌표로
이미 `pending` 제안을 등록했다면 기존 row를 반환한다(`new_place`와 `correction`은 같은 이름/좌표여도
별개). 신규 등록은 사용자당 24시간 20건으로 제한하고, 초과 시 `429 RATE_LIMITED` +
`Retry-After: 86400`을 반환한다.

응답 201:

```jsonc
{
  "data": {
    "request_id": "uuid",
    "status": "pending",
    "type": "new_place",
    "kind": "place",
    "title": "새 카페",
    "coord": { "longitude": 129.0, "latitude": 35.0 },
    "categories": ["카페"],
    "note": "...",
    "target_feature_id": null,
    "created_at": "2026-06-09T11:10:00+09:00",
    "resolved_at": null
  }
}
```

### 2.5.1 `GET /features/requests/{request_id}`

로그인 사용자가 본인이 등록한 feature 제안 1건을 조회한다. 다른 사용자의 제안은
존재 여부를 숨기기 위해 `404 RESOURCE_NOT_FOUND`로 응답한다.

```http
GET /features/requests/018f4b6e-1a2b-7c3d-8e9f-001122334455
Cookie: tripmate_access=...
```

응답 셰입은 `POST /features/requests`와 같다.

### 2.6 `GET /features/search`

장소/이벤트/공지 등 지도 feature 자유 텍스트 검색. TripMate는 URL/응답 셰입만 갖고,
검색 인덱스와 ranking은 krtour-map HTTP 계약에 위임한다.

```http
GET /features/search?q=광안리&bbox=129.0,35.0,129.2,35.2&kinds=place,event&limit=20
Cookie: tripmate_access=...
```

- `q`: 2자 이상
- `bbox` (선택): bias용 bbox (`lng_min,lat_min,lng_max,lat_max`)
- `kinds` (선택): `place,event,notice,price,weather,route,area`
- `limit`: 기본 50, 최대 200

응답은 `FeatureSummary[]` 배열이다.

```jsonc
{
  "data": [
    {
      "feature_id": "f_2611000000_p_abc123...",
      "kind": "place",
      "title": "광안리 해수욕장",
      "coord": { "longitude": 129.118, "latitude": 35.155 },
      "category": "해수욕장",
      "marker_color": "P-07",
      "marker_icon": "swimming"
    }
  ]
}
```

호출 경계: feature 검색은 krtour-map `GET /features/search`로 조회한다. Naver/Kakao
검색 API는 현재 사용하지 않는다.

### 2.7 `GET /search`

통합 검색은 T-129 future endpoint다. 구현 시 한 화면에서 다음 bucket을 함께 반환한다.

```http
GET /search?q=광안리&viewport=129.0,35.0,129.2,35.2&limit=10
Cookie: tripmate_access=...
```

```jsonc
{
  "data": {
    "trips": [/* app.trips 검색 결과 */],
    "my_pois": [/* 접근 가능한 trip_day_pois 검색 결과 */],
    "features": [/* /features/search 결과 */],
    "addresses": [/* kraddr-geo v2 REST search 결과 */]
  }
}
```

- `trips`, `my_pois`는 TripMate `app` schema 검색이다.
- `features`는 본 문서 §2.6을 내부 호출 또는 서비스 함수로 재사용한다.
- `addresses`는 `kraddr-geo` v2 REST search(ADR-025)로 조회한다. krtour-map 경유
  geocoding이나 `kraddr.geo` in-process import를 쓰지 않는다.
- T-129 전까지 Web은 `/features/search` + local trip list search를 별도 호출한다.

## 3. 응답 정책

- 좌표 정밀도: 6자리 (~10cm) — 라이브러리 원본 그대로
- 단, 사용자 위치 자체를 응답에 포함할 때는 4자리 (`docs/api/common.md` §4.2)
- `feature_id`는 krtour-map `make_feature_id`가 발급한 안정적 불투명 문자열이다.
  TripMate는 UUID나 특정 prefix 구조로 파싱하지 않고 그대로 저장·전달한다(ADR-028).
- `marker_color` / `marker_icon`은 라이브러리가 카테고리 마스터로 부여한 값.
  사용자가 POI에서 override한 값은 별도 (`docs/api/pois.md`)

## 4. 캐싱

- 클라이언트: TanStack Query, `staleTime: 60_000` (1분)
- 백엔드: krtour-map HTTP 응답은 짧은 TTL 캐시를 둘 수 있다. 캐시 키에는 path,
  query/body, 사용자 권한 범위를 포함한다.
- viewport 동일 bbox+zoom 1분 캐시 (위에)

## 5. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/feature.py` Pydantic + `packages/schemas/src/feature.ts` Zod
- [ ] `apps/api/app/services/feature_view.py` — krtour-map HTTP 호출 + 응답 변환
- [ ] `apps/api/app/api/v1/features.py` 라우터
- [ ] `apps/api/app/clients/krtour_map.py` HTTP client + lifespan
- [ ] `apps/api/app/middleware/location_audit.py` — 좌표 query/body 적재
- [ ] 통합 테스트 `apps/api/tests/integration/test_features_api.py`
      (`httpx.MockTransport` 계약 테스트 + 선택적 live krtour-map)
- [ ] viewport 클러스터링 zoom 경계 unit 테스트
