# Feature API (`/features/*`)

`kor-travel-map` 독립 프로그램의 지도 feature를 Pinvi가 OpenAPI HTTP로 읽어서
클라이언트에 제공한다. **Pinvi는 응답 셰입을 갖고, 데이터는 kor-travel-map
`openapi.user.json` 계약으로 가져온다**(ADR-026 / ADR-003). 공통 규약
[`common.md`](./common.md).

## 1. 책임

- 본 API는 Pinvi가 제공 — URL/응답 셰입은 본 저장소 소유
- 데이터는 kor-travel-map API `12701`의 OpenAPI HTTP 호출
  (`docs/kor-travel-map-integration.md`)
- Pinvi는 provider/feature 도메인 wrapper를 두지 않음. HTTP client는 transport
  역할만 한다.
- 좌표를 query/body에 받는 endpoint는 `app.location_access_log` 자동 적재
  (`docs/architecture/user-location.md`)

### 1.1 `status` 필드 제거 (breaking, 2026-08-21)

`FeatureSummary`/`FeatureDetail`/detail-card 응답에 **`status` 키가 더 이상 없다.**
kor-travel-map의 3축 feature state cutover(`1f2bdc3a feat(api): complete feature state
cutover`)로 user 표면(`FeatureSummary`/`NearbyFeatureSummary`/`FeatureDetailResponse`)에서
`status`가 삭제됐고 **대체 필드가 없다** — lifecycle/publication/quality 3축은 admin 표면
전용이라 일반 사용자 응답으로 내려오지 않는다. 2026-08-17~2026-08-20 사이에는 web/mobile
계약을 깨지 않으려고 **항상 `null`인 키만** 남겨 뒀고, T-VN-42에서 그 키까지 제거했다.

값은 그 기간 내내 `null`이었으므로 이 필드로 분기하던 클라이언트는 이미 아무 정보도 얻지
못하고 있었다 — 표시 동작은 바뀌지 않고 키만 사라진다. feature의 상태가 필요하면 admin 표면의
3축(`lifecycle_state`/`publication_state`/`quality_state`)을 쓴다. 재도입 방지 게이트:
`apps/api/tests/unit/test_feature_schemas.py`(선언 등호 + OpenAPI 노출),
`apps/web/tests/featureContract.test.ts`(Zod 미러).

## 2. Endpoint

### 2.1 `GET /features/in-bounds`

viewport 안 feature 조회 + zoom별 클러스터링.

```http
GET /features/in-bounds?bbox=129.0,35.0,129.2,35.2&zoom=12&kinds=place&kinds=event
Cookie: pinvi_access=...
```

- `bbox`: `lng_min,lat_min,lng_max,lat_max` (EPSG:4326)
- `zoom`: 5~19 (`apps/api/app/api/v1/features.py`와
  `packages/schemas/src/feature.ts` 기준. Satellite/Hybrid는 z18까지)
- `kinds`: `place,event,notice,price,weather,route,area` 중 반복 파라미터 (`kinds=a&kinds=b`)
- `cluster_unit`(선택), `category`(선택), `limit`(기본 500, 최대 2000 → kor_travel_map `max_items`)
- zoom별 클러스터링은 **kor_travel_map 서버 책임**(`cluster_unit`/`zoom`). granularity는
  `cluster_unit`(`sido | sigungu | eupmyeondong | individual`)으로 응답에 실린다.

응답 200 — 개별 feature(`items`) + 서버 cluster(`clusters`) 분리:

```jsonc
{
  "data": {
    "items": [
      {
        "feature_id": "f_2611000000_p_abc123...",
        "kind": "place",
        "name": "광안리 해수욕장",
        "coord": { "lon": 129.118, "lat": 35.155 }, // null 가능
        "category": "해수욕장",
        "marker_color": "P-07",
        "marker_icon": "swimming",
      },
    ],
    "clusters": [
      {
        "cluster_key": "11680", // 행정구역 코드(자연키)
        "coord": { "lon": 127.04, "lat": 37.52 },
        "feature_count": 47,
      },
    ],
    "cluster_unit": "sigungu",
    "zoom": 12,
    "bbox": { "lng_min": 129.0, "lat_min": 35.0, "lng_max": 129.2, "lat_max": 35.2 },
  },
}
```

kor-travel-map 호출: `GET /v1/features/in-bounds` (평면 `lon`/`lat`, `cluster_key`, `max_items`).

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
    "feature_id": "f_2611000000_p_abc123...",
    "kind": "place",
    "name": "...", // 표시명 (kor_travel_map `name`)
    "coord": { "lon": 129.0, "lat": 35.0 }, // null 가능
    "category": "01070100",
    "address": {
      /* 구조화 주소 객체 (kor_travel_map 원본) */
    },
    "legal_dong_code": "1168010100",
    "sido_code": "11",
    "sigungu_code": "11680",
    "marker_color": "P-07",
    "marker_icon": "swimming",
    "urls": { "homepage": "...", "review_naver": null },
    "detail": {
      // kind+category별 payload (kor_travel_map PlaceDetail / EventDetail / ...)
      "phones": ["051-..."],
    },
    "updated_at": "...",
  },
}
```

kor-travel-map 호출: `GET /v1/features/{feature_id}` (`name`, 구조화 `address`, `*_code`).

### 2.3 `GET /features/{feature_id}/weather`

해당 좌표/지점의 날씨 (관측 + 예보 + 특보).

```http
GET /features/{feature_id}/weather?asof=2026-06-02T14:00:00+09:00
```

`asof`(선택): 보고 싶은 **관측/예보 시각**(valid time). 생략하면 최신 카드.
offset을 붙인 KST 값(`+09:00`)을 권장한다 — offset 없이 보내면 서버가 **KST(Asia/Seoul)로
해석**하고(`app/api/v1/features.py normalize_asof_query`), offset이 있으면 그대로 존중한다.
(예전에는 offset 없는 값을 UTC로 읽어 9시간 어긋난 시점이 돌아왔다.)

**`asof`를 주면 upstream 경로가 달라진다.** Pinvi는 `asof` 없이는 kor-travel-map
`GET /v1/features/{id}/weather`(query 없음)를, `asof`가 있으면 bitemporal 시점 경로
`GET /v1/features/{id}/weather/snapshot`을 호출한다. 후자는 `target_at`(=Pinvi `asof`,
valid time)과 `known_at`(knowledge time = 호출 시각, "지금 아는 최신 지식")을 **둘 다 필수**로
받는다. Pinvi는 knowledge 축을 사용자에게 노출하지 않는다 — 시점 축은 `asof` 하나뿐이다.
(`GET …/weather`에는 시각 query가 아예 없어서 예전처럼 `?asof=`를 붙이면 조용히 무시되고 늘
최신 카드가 돌아왔다 — kor-travel-map bitemporal cutover `6650aa71`.)

응답 200 — kor_travel_map는 **평탄한 metric 목록 + `forecast_style` 태그**를 준다(KMA
시간축 그룹핑은 프런트 표현 계층):

```jsonc
{
  "data": {
    "feature_id": "...",
    // 응답의 `asof`는 요청 `asof`의 에코가 아니라 **서버가 실제로 고른 시각**이다.
    // 소스는 kor-travel-map `WeatherCardData.selected_at`(구 `asof`가 `6650aa71`에서 개명).
    // Pinvi 공개 필드 이름만 `asof`로 유지하고 소스를 갈아끼웠다.
    "asof": "2026-06-10T12:00:00+09:00", // null 가능
    "latest_at": "2026-06-10T11:00:00+09:00", // null 가능
    "is_stale": false,
    "source_styles": ["nowcast", "short"],
    "metrics": [
      {
        "metric_key": "T1H",
        "metric_name": "기온",
        "forecast_style": "nowcast", // nowcast|ultra_short|short|mid|observed|index|advisory
        "timeline_bucket": null,
        "valid_at": "...",
        "issued_at": null,
        "observed_at": null,
        "value_number": 23.0,
        "value_text": null,
        "unit": "℃",
        "severity": null,
      },
    ],
  },
}
```

프런트는 `forecast_style` 별로 metric을 그룹핑해 한 카드로 표시한다. Pinvi가
별도 KMA provider 변환을 직접 구현하지 않는다(금지룰). 날씨 제공 여부/필드는
kor-travel-map 최신 `openapi.user.json` 계약을 따른다.

### 2.4 `GET /features/nearby`

좌표 주변 feature 조회.

```http
GET /features/nearby?lon=129.118&lat=35.155&radius_m=5000&kinds=place,event
Cookie: pinvi_access=...
```

- 좌표: EPSG:4326 (`lon`/`lat` 쿼리 — 구 `lng`는 거부)
- `radius_m`: meter, 최대 `50000` (50km)
- `kinds`(반복), `category`(선택), `limit`(기본 100, 최대 500 → kor_travel_map `page_size`)

응답: `FeatureSummary[]` 배열 — `features_in_bounds`의 `items` 셰입에 **`distance_m`**
(기준 좌표로부터 거리, meter)가 추가된다. cluster는 없다.

kor-travel-map 호출: `GET /v1/features/nearby`. 기준 feature(등록된 POI cache target)가
있으면 `GET /v1/features/nearby/by-target`를 우선한다(admin flow 등록 필요 — 후순위).

### 2.5 `POST /features/requests`

사용자가 "feature 추가 요청"을 Pinvi 소유 Admin 검토 큐에 등록한다. 이 엔드포인트는
`kor-travel-map`을 직접 호출하지 않고 `app.feature_suggestions`에만 적재한다. Admin
검사/승인 뒤 kor-travel-map feature change API로 반영하는 단계는 T-179에서 연결한다.

```http
POST /features/requests
Content-Type: application/json
Cookie: pinvi_access=...

{
  "type": "new_place",
  "kind": "place",
  "title": "새 카페",
  "coord": { "lon": 129.0, "lat": 35.0 },
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
    "coord": { "lon": 129.0, "lat": 35.0 },
    "categories": ["카페"],
    "note": "...",
    "target_feature_id": null,
    "created_at": "2026-06-09T11:10:00+09:00",
    "resolved_at": null,
  },
}
```

### 2.5.1 `GET /features/requests/{request_id}`

로그인 사용자가 본인이 등록한 feature 제안 1건을 조회한다. 다른 사용자의 제안은
존재 여부를 숨기기 위해 `404 RESOURCE_NOT_FOUND`로 응답한다.

```http
GET /features/requests/018f4b6e-1a2b-7c3d-8e9f-001122334455
Cookie: pinvi_access=...
```

응답 셰입은 `POST /features/requests`와 같다.

### 2.6 `GET /features/search`

장소/이벤트/공지 등 지도 feature 자유 텍스트 검색. Pinvi는 URL/응답 셰입만 갖고,
검색 인덱스와 ranking은 kor-travel-map HTTP 계약에 위임한다.

```http
GET /features/search?q=광안리&bbox=129.0,35.0,129.2,35.2&kinds=place,event&limit=20
Cookie: pinvi_access=...
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
      "name": "광안리 해수욕장",
      "coord": { "lon": 129.118, "lat": 35.155 }, // null 가능
      "category": "해수욕장",
      "marker_color": "P-07",
      "marker_icon": "swimming",
    },
  ],
}
```

호출 경계: feature 검색은 kor-travel-map `GET /v1/features/search`로 조회한다(분리 4-float
bbox + `page_size`). Naver/Kakao 검색 API는 현재 사용하지 않는다.

### 2.6.1 `GET /features/categories`

마커 범례 / 필터 칩용 카테고리 카탈로그. 저빈도 데이터 → 클라이언트 긴 `staleTime` 권장.

```http
GET /features/categories?active_only=true
Cookie: pinvi_access=...
```

응답은 `FeatureCategory[]` 배열:

```jsonc
{
  "data": [
    {
      "code": "01070100", // 8자리 카테고리 코드
      "label": "해수욕장",
      "parent_code": "010701",
      "depth": 3,
      "path": ["자연", "해안", "해수욕장"],
      "maki_icon": "swimming",
      "is_active": true,
      "sort_order": 5,
    },
  ],
}
```

`active_only`(기본 `true`)는 **Pinvi가 직접 적용한다** — kor-travel-map에는 전달하지 않는다.
kor-travel-map 호출은 `GET /v1/categories`(`include_counts`만 선언)이고, 필터는 응답 항목의
`is_active`로 Pinvi가 건다. 상류로 넘기던 시절에는 FastAPI가 모르는 query를 조용히 버려
`active_only=true`가 전량을 돌려주면서 필터가 걸린 척했다(kor-travel-map T-VN-04 F-1에서
`active_only` 삭제; 삭제 전에도 그 스위치는 목록이 아니라 `db_feature_count` 집계 기준만
바꿨다). 정본 카탈로그는 kor_travel_map이며 Pinvi는 필요한 필드만 투영한다.

현재 카탈로그 145건은 전부 `is_active: true`라 `active_only=true|false`의 결과는 같다. 이
필터는 kor_travel_map이 항목을 비활성화하는 순간부터 의미를 갖는다.

### 2.7 `GET /search`

통합 검색은 T-129 future endpoint다. 구현 시 한 화면에서 다음 bucket을 함께 반환한다.

```http
GET /search?q=광안리&viewport=129.0,35.0,129.2,35.2&limit=10
Cookie: pinvi_access=...
```

```jsonc
{
  "data": {
    "trips": [
      /* app.trips 검색 결과 */
    ],
    "my_pois": [
      /* 접근 가능한 trip_day_pois 검색 결과 */
    ],
    "features": [
      /* /features/search 결과 */
    ],
    "addresses": [
      /* kor-travel-geo v2 REST search 결과 */
    ],
  },
}
```

- `trips`, `my_pois`는 Pinvi `app` schema 검색이다.
- `features`는 본 문서 §2.6을 내부 호출 또는 서비스 함수로 재사용한다.
- `addresses`는 `kor-travel-geo` v2 REST search(ADR-025)로 조회한다. kor-travel-map 경유
  geocoding이나 `kor_travel_geo` in-process import를 쓰지 않는다.
- T-129 전까지 Web은 `/features/search` + local trip list search를 별도 호출한다.

## 3. 응답 정책

- 좌표 정밀도: 6자리 (~10cm) — 라이브러리 원본 그대로
- 단, 사용자 위치 자체를 응답에 포함할 때는 4자리 (`docs/api/common.md` §4.2)
- `feature_id`는 kor-travel-map `make_feature_id`가 발급한 안정적 불투명 문자열이다.
  Pinvi는 UUID나 특정 prefix 구조로 파싱하지 않고 그대로 저장·전달한다(ADR-028).
- `marker_color` / `marker_icon`은 라이브러리가 카테고리 마스터로 부여한 값.
  사용자가 POI에서 override한 값은 별도 (`docs/api/pois.md`)

## 4. 캐싱

- 클라이언트: TanStack Query, `staleTime: 60_000` (1분)
- 백엔드: kor-travel-map HTTP 응답은 짧은 TTL 캐시를 둘 수 있다. 캐시 키에는 path,
  query/body, 사용자 권한 범위를 포함한다.
- viewport 동일 bbox+zoom 1분 캐시 (위에)

## 5. 구현 상태 (T-173/174/176/178 완료)

- [x] `apps/api/app/schemas/feature.py` Pydantic + `packages/schemas/src/feature.ts` Zod — kor_travel_map
      `openapi.user.json` 셰입 정합(`name`/평면 `lon`,`lat`/구조화 `address`/`cluster_key`/평탄 `metrics`)
- [x] `apps/api/app/api/v1/features.py` 라우터 — `clients/kor_travel_map.py` HTTP client 호출 + 응답
      투영 + 에러/저하 정책(T-178: 5xx/timeout→503, 429→Retry-After, 404)
- [x] `apps/api/app/clients/kor_travel_map.py` HTTP client + lifespan (T-170/171/181)
- [x] 클러스터링은 kor_travel_map 서버 위임 — Pinvi `services/cluster_query.py`(직접 `feature` SQL =
      경계 위반) 제거 (T-174)
- [x] `apps/api/app/middleware/location_audit.py` — `nearby` 좌표 query 적재
- [x] 통합 테스트 `tests/integration/test_features_api.py` + 매핑 단위 테스트
      `tests/unit/test_feature_mapping.py`
