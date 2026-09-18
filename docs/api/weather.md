# Weather Map Marker API (`/weather/*`)

지도 weather marker(위치+현재 온도) 전용 endpoint다. `kor-travel-map`을 **전혀
거치지 않는다** — feature가 아니라 `kor-travel-weather`의 location을 직접
노출한다(ADR-068, T-368). T-363 trip view가 확립한 "완전 분리" 원칙을 지도 marker
표면에 적용한 결과다. 설계 정본은
[`docs/integrations/kor-travel-weather.md`](../integrations/kor-travel-weather.md) §4.6/§7-3.
공통 규약 [`common.md`](./common.md).

## 1. 책임

- 본 API는 Pinvi가 제공 — URL/응답 셰입은 본 저장소 소유.
- 데이터는 `kor-travel-weather` 공개 read(`GET /v1/weather/nearby`, 인증 불필요)로
  가져온다. `features.py`의 `/features/in-bounds`와 달리 `kor-travel-map`을
  호출하지 않는다.
- `pinvi_kor_travel_weather_map_markers_enabled` flag(기본 `false`)가 꺼져 있으면
  항상 빈 목록을 돌려준다 — 지금 운영 중인 `/features/in-bounds`가 `weather` kind를
  기본에서 제외해 마커가 애초에 하나도 안 보이는 것과 관측상 동일하다.

## 2. Endpoint

### 2.1 `GET /weather/markers-in-bounds`

viewport 안 weather marker(위치+현재 온도) 조회. `/features/in-bounds`와 같은
`bbox`/`zoom` 계약을 쓴다(호출부가 `boundsToBbox`/`clampZoom`을 그대로 재사용할 수
있게).

```http
GET /weather/markers-in-bounds?bbox=126.9,37.4,127.1,37.6&zoom=10&limit=100
Cookie: pinvi_access=...
```

- `bbox`: `lng_min,lat_min,lng_max,lat_max` (EPSG:4326)
- `zoom`: 5~19(`/features/in-bounds`와 동일 범위). **zoom < 8이면 항상 빈
  목록**이다 — 전국 스케일에서는 bbox 대각선이 `kor-travel-weather`의 반경
  상한(500km)을 한 번의 원형 쿼리로 못 덮는다(§3 참조). 422가 아니라 빈 배열로
  응답한다.
- `limit`(선택, 기본 100, 최대 100) — `kor-travel-weather` `/nearby`의 서버 상한.

응답 200:

```jsonc
{
  "data": {
    "items": [
      {
        "location_id": "airkorea-station-abc",
        "name": "중구",
        "coord": { "lon": 127.0, "lat": 37.5 },
        "temperature_c": 21.5,
        "condition": "cloudy", // sunny | cloudy | rainy | snowy
        "provider": "python-kma-api", // null 가능
      },
    ],
    "zoom": 10,
    "bbox": { "lng_min": 126.9, "lat_min": 37.4, "lng_max": 127.1, "lat_max": 37.6 },
  },
}
```

- **현재 온도를 못 구한 location은 목록에서 제외한다** — 값이 없다고 `0`으로
  가장하지 않는다.
- `condition`은 강수 신호(안전 정규화된 `PRECIP`)가 있을 때만 `rainy`/`snowy`로
  판정하고, 신호가 없으면 항상 `cloudy`다. **`sunny`는 절대 반환하지 않는다** —
  provider마다 하늘상태 코드 체계가 달라 "맑음"을 안전하게 정규화할 방법이 없어서
  근거 없이 단정하지 않는다(`app/services/weather_map_markers.py` 모듈
  docstring).

`weather_client`가 없으면(설정 오류) 503 `WEATHER_SERVICE_UNAVAILABLE`.
`kor-travel-weather` 호출 실패도 503으로 degrade한다.

Rate limit: `/features/in-bounds`와 **같은 버킷**(분당 60회, `docs/api/common.md`
§8) — 같은 pan/zoom 이벤트로 병렬 호출되므로 다른 버킷을 쓰면 빠른 팬 중 weather
marker만 조용히 사라진다.

## 3. `bbox` → `kor-travel-weather` `/nearby` 변환

`kor-travel-weather`는 bbox가 아니라 center+radius(`lat`/`lon`/`radius_km`)만
받는다. 백엔드가 이 변환을 흡수한다 — 프런트는 항상 bbox만 안다.

- 중심 = bbox 산술 평균(`(lat_min+lat_max)/2`, `(lng_min+lng_max)/2`).
- 반경 = 중심에서 bbox 네 모서리까지 haversine 거리 중 최댓값(km).
- 반경이 `kor-travel-weather`의 상한(500km)을 넘으면 조회하지 않고 빈 목록을
  돌려준다 — `zoom >= 8` 게이트가 실무에서 이 경로를 막지만, 방어적으로 한 번 더
  잡는다.

## 4. AI agent 작업 가이드

- Pydantic: `app/schemas/weather_map.py`. Zod: `packages/schemas/src/weather-map.ts`.
  `app/schemas/feature.py`/`packages/schemas/src/feature.ts`와는 **의도적으로
  분리**돼 있다 — feature 개념을 참조하지 않는다.
- 서비스: `app/services/weather_map_markers.py`(bbox→center+radius, 온도 추출,
  condition 판정 — 전부 순수 함수, `apps/api/tests/unit/test_weather_map_markers.py`).
- client: `app/clients/kor_travel_weather.py`의 `nearby()`(T-368 신설).
- 라우터: `app/api/v1/weather_markers.py`.
- 프런트: `apps/web/components/map/FeatureMapView.tsx`의 `fetchWeatherMarkers`
  (`fetchInBounds`와 독립된 자체 debounce/abort/cache — 실패해도 장소 마커에
  영향 없음).

## 5. 관련 문서

- `docs/integrations/kor-travel-weather.md` §4.6/§6-I/§7-3 — 설계 정본.
- ADR-068 — 날씨 소스 이관 결정.
- `docs/api/features.md` §2.1 — `bbox`/`zoom` 계약이 유래한 원본 endpoint.
