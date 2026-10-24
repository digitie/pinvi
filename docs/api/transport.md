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

## 상세 — `GET /transport/{fuel-stations|rest-areas|highway-incidents|airports}/{feature_id}`

`feature_id`는 `^[A-Za-z0-9_-]{1,128}$`(아니면 422). 응답 `{item, freshness, fuel_price_freshness?}`.
404 `TRANSPORT_FEATURE_NOT_FOUND`, 503 `TRANSPORT_UNAVAILABLE`.

`feature_id`는 Map `make_feature_id` 값이다 — POI의 `feature_id`(Map PG UUID)가 아니므로 `/features/{id}`·POI 추가에 쓰지 않는다.

## 가격 추이 — `GET /transport/fuel-stations/{feature_id}/price-history`

| query         | 설명                                                   |
| ------------- | ------------------------------------------------------ |
| `days`        | 1~90, 기본 30 (`since = 지금(KST) − days`)              |
| `product_key` | `gasoline` 등. 응답 값으로 거른다 — 모르는 키는 빈 목록 |

응답 `{feature_id, status: available|unavailable, reason, truncated, items[], current_prices[], freshness}`.
`unavailable`은 오류가 아니다(`reason=disabled`: transport가 아직 추이를 내보내지 않음). 주유소 자체를 못 읽으면 404/503.
`reason`은 Map `PriceHistoryBlock.reason` enum 그대로다(Map e0131ec1 기준 `disabled`·`not_configured`·`upstream_not_found`·
`upstream_unsupported`·`request_rejected`·`upstream_no_collection`·`upstream_timeout`·`upstream_unavailable`·`upstream_rejected`·
`upstream_contract`, 모르는 값은 `upstream_contract`로 접는다). PinVi는 Map에 cursor를 보내지 않고 **첫 페이지만** 읽는다 —
Map `limit`(기본 200)이 유종 합계라 기간이 길면 `truncated=true`(= Map `has_more`)로 잘린다. 페이지를 이으려면 Map ADR-114 D6
규칙(같은 `product_code`, `since`/`until` 생략 또는 동일, 409 `TRANSPORT_PRICE_HISTORY_CURSOR_EXPIRED`면 처음부터, unavailable
페이지에서 멈춤)을 따라야 한다.
