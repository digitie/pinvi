# Transport API — 지도 교통 정보 레이어 (ADR-076)

주유소·휴게소(유가)·고속도로 돌발·공항을 kor-travel-map `/v1/service/transport/*` 경유로 제공한다. 모두 **로그인 필요**다.
설계는 `docs/execplan/map-transport-integration.md`, 결정은 ADR-076.

`layer` 값: `fuel_station` · `rest_area` · `highway_incident` · `airport`. 상세 path는 Map과 같은 복수 kebab
(`fuel-stations` · `rest-areas` · `highway-incidents` · `airports`).

## 플래그

`PINVI_KOR_TRAVEL_MAP_TRANSPORT_ENABLED`(기본 `false`). 꺼져 있으면 Map을 부르지 않는다 — `status`는 `enabled=false`, markers는
레이어마다 `disabled`, 상세·추이는 503 `TRANSPORT_DISABLED`.

## `GET /transport/status`

```jsonc
{ "data": { "enabled": true, "layers": [
  { "layer": "fuel_station", "available": false, "reason": "NOT_LOADED", "freshness": null },
  { "layer": "airport", "available": true, "reason": null, "freshness": { /* 아래 */ } }
] } }
```

5xx를 내지 않는다. Map 장애(Valkey 다운 등)는 레이어 전부 `available=false`.

## `GET /transport/markers-in-bounds`

| query    | 필수 | 설명                                                        |
| -------- | ---- | ----------------------------------------------------------- |
| `bbox`   | ✓    | `lng_min,lat_min,lng_max,lat_max` (`/features/in-bounds`와 같음) |
| `zoom`   | ✓    | 5~19                                                        |
| `layers` |      | 쉼표 구분 또는 반복. 생략하면 전부. 모르는 값은 400          |
| `limit`  |      | 레이어당 1~500, 기본 200                                    |

```jsonc
{ "data": { "bbox": { ... }, "zoom": 12, "layers": [ {
  "layer": "rest_area", "status": "ok", "reason": null,
  "freshness": { "source_collected_at": "...", "loaded_at": "...", "age_seconds": 600, "max_age_seconds": 691200, "stale": false },
  "fuel_price_freshness": { ... },   // 휴게소만
  "truncated": false,                // true면 일부만 — 확대 안내
  "items": [ { "layer": "rest_area", "feature_id": "...", "name": "...", "coord": { "lon": 127.2, "lat": 36.9 },
               "marker_icon": "fast-food", "marker_color": "P-06", "fuel_prices": { "gasoline_price": 1650, ... }, ... } ]
} ] } }
```

- **5xx를 내지 않는다.** 레이어별 `status`: `ok` / `unavailable`(+`reason`) / `disabled`.
- `reason`: `NOT_LOADED`(Map 적재 전) · `STORE_UNAVAILABLE`(Map Valkey) · `UPSTREAM_UNAVAILABLE`(timeout·연결·3초 기한) ·
  `UPSTREAM_AUTH`(service token) · `UPSTREAM_REJECTED`(Map 4xx) · `UPSTREAM_CONTRACT`(응답 셰입).
- bbox는 국내 범위(경도 124~132, 위도 33~39)와 교차해 보낸다. 교차가 없으면 Map을 부르지 않고 빈 `ok`.
- Map 영역 검색은 상자 중심에서 가까운 순으로 자른 뒤 사각형 밖을 거른다 — `items` 개수로 완전성을 추론하지 않는다.

## `GET /transport/markers-near` — 여행 장소 반경

여행 지도가 쓴다(2026-11-16 소유자 결정). 기준 장소(여행 장소)들에서 **레이어별 고정 반경** 안의 항목만 준다 —
주유소 `fuel_station` 10 km, 교통 돌발 `highway_incident` 20 km. 반경은 서버 정책이라 query로 바꿀 수 없다.

| query    | 필수 | 설명                                                                 |
| -------- | ---- | -------------------------------------------------------------------- |
| `points` |      | `lon,lat;lon,lat` 국내 좌표(경도 124~132, 위도 33~43), 최대 60곳. 비우면 Map을 부르지 않고 빈 `ok` |
| `layers` |      | `fuel_station`·`highway_incident` 중 쉼표 구분. 생략하면 둘 다. 그 밖(휴게소·공항 포함)은 400 |
| `limit`  |      | 레이어당 1~500, 기본 200                                             |

```jsonc
{ "data": { "radius_m": { "fuel_station": 10000, "highway_incident": 20000 }, "layers": [ {
  "layer": "fuel_station", "status": "ok", "truncated": false, "freshness": { ... },
  "items": [ { "layer": "fuel_station", "feature_id": "...", "distance_m": 812.4, ... } ]   // 가까운 순
} ] } }
```

- 반경 거르기는 Map 묶음 근처 검색(`POST /v1/service/transport/{fuel-stations|highway-incidents}/near-batch`, Valkey
  GEOSEARCH 한 세대 — Map T-READ-04)이 한다. 레이어마다 Map을 **한 번** 부르고 기준 장소 전부(최대 60)를 보낸다(반경 +50 m
  여유). PinVi는 모든 기준 장소까지의 대원 거리로 다시 걸러 레이어 반경 밖을 버린다. `distance_m`은 가장 가까운 기준 장소까지의
  거리다.
- 묶음 route가 없는 옛 Map(405)과 짝지어지면 종전 경로로 떨어진다 — 2 km 안의 기준 장소를 한 조회로 묶어(반경 +2 km) 중심마다
  근처 검색(`lon`·`lat`·`radius_m`)을 동시 6개로 보내고 같은 방식으로 합친다. 결과 집합은 같다.
- 5xx를 내지 않는다(`markers-in-bounds`와 같은 레이어별 강등, 레이어 기한 5초). Map 조회가 실패하면(405 제외) 그 레이어는 `unavailable`.
- `truncated`: Map 조회가 상한에 닿았거나 합친 결과가 `limit`을 넘었다.

## 상세 — `GET /transport/{fuel-stations|rest-areas|highway-incidents|airports}/{feature_id}`

`feature_id`는 `^[A-Za-z0-9_-]{1,128}$`(아니면 422). 응답 `{item, freshness, fuel_price_freshness?, food?}`.

`food`(휴게소·고속도로 주유소, Map ADR-127): 한국도로공사 0502 휴게소 메뉴 요약 — `rest_area_name`·`std_rest_code`·
`menu_count`·`price_min`/`price_median`/`price_max`·`featured[]`(대표 → 프리미엄 → 추천, `{name, price, tags[], season}`)·
`seasonal[]`(여름·겨울)·`menu_updated_on`·`source_collected_at`(화면의 기준일)·`attribution`("한국도로공사"). 주유소는 Map이
400 m 안 같은 방향 휴게소와 짝지은 경우(신뢰도 0.8 이상)에만 있고 `paired_distance_m`이 채워진다. 없거나 Map 블록이 계약과
다르면 `null`이고 상세의 나머지는 그대로다. LLM 요약이 아니라 원천 데이터만 보인다.
404 `TRANSPORT_FEATURE_NOT_FOUND`, 503 `TRANSPORT_UNAVAILABLE`.

`feature_id`는 Map `make_feature_id` 값이다 — POI의 `feature_id`(Map PG UUID)가 아니므로 `/features/{id}`·POI 추가에 쓰지 않는다.

주유소 항목은 Map이 주는 `brand_code`(오피넷 상표 코드 — 로고 선택용, 이름보다 우선)와 `source_last_seen_at`(기준정보 반영
시각)을 그대로 전하고(2026-11-27 추가, 둘 다 nullable), 교통 돌발은 `route_no`(노선 번호)를 전한다.
`prices[]`는 계약대로 `price: null`(지금 판매하지 않음) 행을 포함한다 — 숨기는 것은 표시 규칙이다.

### 표시 규칙(웹·모바일 공용, `@pinvi/domain` `fuelStation.ts`)

kor-travel-transport 공개 유가 화면(`/public/fuel`)과 같은 정보·모양이다.

- 취급하지 않는 유종(가격 null·0·음수·NaN)은 행을 만들지 않는다 — "판매 안 함"·"-"도 없다. 하나도 없으면 "등록된 유효 유가가
  없습니다." 한 줄. 가격 추이도 같은 규칙으로 점을 뺀다.
- 유종 이름·순서: 휘발유·고급유·등유·경유·LPG(오피넷 코드 오름차순 = transport 행 순서). 가격 `1,689원/L`.
- 관측 시각(transport `observed_at`과 같은 규칙: `provider_updated_at`이 있으면 그것, 없으면 `collected_at`)이 7일보다 오래면
  "오래됨" — 오늘 다시 수집했어도 공시가가 7일 넘게 그대로면 붙는다. 편의시설은 셀프·24시간·세차·정비·편의점 순서로 `true`인 것만.
- 상표: `brand_code`(없으면 이름 별칭)로 오피넷 원본 로고(`apps/web/public/fuel-brands/`). 자가상표·모르는 코드는 주유기 아이콘.
- 데이터 출처(접힘): 원천, 기준정보 반영, 유종별 제공기관 공시 시각.
- 지도 마커: 주유소는 상표 로고 칩 + 흰 가격 라벨("휘 1,650", 판매 유종만), 교통 돌발은 24px 원 배지. 화면 22,000px²당 1곳(6~60곳)
  예산을 넘을 때만 줌 14까지 묶고, 줌 10 이하는 늘 묶는다(transport `clusterAtScale`, 근사: 창 크기·받은 항목 수로 센다).
- transport에 있지만 Map이 싣지 않아 보이지 않는 것: 품질인증·전산보고 표시, 시군구 가격 등급·평균 대비, 30일 그래프(PinVi는
  최근 7행 목록).

## 가격 추이 — `GET /transport/fuel-stations/{feature_id}/price-history`

| query         | 설명                                                   |
| ------------- | ------------------------------------------------------ |
| `days`        | 1~90, 기본 30 (`since = 지금(KST) − days`)              |
| `product_key` | `gasoline` 등. 아는 키(`gasoline`·`diesel`·`premium_gasoline`·`kerosene`·`lpg`)는 Map `product_code`(`B027`·`D047`·`B034`·`C004`·`K015`)로 바꿔 Map이 서버에서 거르게 하고, 응답 값으로도 한 번 더 거른다 — 모르는 키는 `product_code` 없이 요청하고 빈 목록 |

응답 `{feature_id, status: available|unavailable, reason, truncated, items[], current_prices[], freshness}`.
`unavailable`은 오류가 아니다(`reason=disabled`: transport가 아직 추이를 내보내지 않음). 주유소 자체를 못 읽으면 404/503.
web은 `reason`이 `upstream_timeout`·`upstream_unavailable`이면 "잠시 후 다시 시도해 주세요", 그 밖에는 "아직 제공되지 않습니다"를 보인다.
`reason`은 Map `PriceHistoryBlock.reason` enum 그대로다(Map e0131ec1 기준 `disabled`·`not_configured`·`upstream_not_found`·
`upstream_unsupported`·`request_rejected`·`upstream_no_collection`·`upstream_timeout`·`upstream_unavailable`·`upstream_rejected`·
`upstream_contract`, 모르는 값은 `upstream_contract`로 접는다). PinVi는 Map에 cursor를 보내지 않고 **첫 페이지만** 읽는다 —
Map `limit`은 한 페이지의 유종 합계 행 수(기본 200, 최대 1000)라 PinVi는 항상 `limit=1000`을 보낸다 — 90일 × 유종 5개가 한 페이지에
들어가고, `product_key`를 주면 다른 유종 행이 상한을 먹지 않는다. 그래도 넘치면 `truncated=true`(= Map `has_more`)로 잘린다. 페이지를 이으려면 Map ADR-114 D6
규칙(같은 `product_code`, `since`/`until` 생략 또는 동일, 409 `TRANSPORT_PRICE_HISTORY_CURSOR_EXPIRED`면 처음부터, unavailable
페이지에서 멈춤)을 따라야 한다.
