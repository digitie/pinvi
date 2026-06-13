# Public API (`/public/*`)

비로그인 사용자도 접근 가능한 read-only endpoint. 로그인 화면의 축제 광고, 일반
사용자의 지도 마커 layer 등.

> **상태 (2026-06-12): 구현됨(T-130 / kor_travel_map T-222c).** kor-travel-map
> `openapi.user.json`에 `/v1/public/beaches*`와 `/v1/public/festivals*` 표면이 추가됐고,
> Pinvi는 `app.clients.kor_travel_map.KorTravelMapClient`로 해당 user OpenAPI를 호출해
> `/public/*`에 투영한다. 수질/KHOA index/weather는 kor_travel_map 응답의 nullable 필드를 그대로
> 노출한다.

## 1. 정책

- 인증 없음 (cookie / Authorization 헤더 없어도 OK)
- Rate limit: IP 기준 분당 60회 목표. 현재 앱 공통 `SlowAPI` 미들웨어는 아직 붙어 있지
  않으므로 kor_travel_map upstream 한도와 edge/CDN 제한을 우선 적용하고, 앱 내 공통 rate-limit는
  별도 후속에서 닫는다.
- 응답 데이터는 kor-travel-map OpenAPI HTTP 계약에서 가져옴
- Pinvi `app.users` / `trips`는 노출 안 됨 — 본 endpoint는 라이브러리 feature
  데이터만

## 2. Endpoint

### 2.1 `GET /public/beaches`

해수욕장 통합 listing.

```http
GET /public/beaches?sido_code=26&sigungu_code=26110&q=광안리&page_size=50&cursor=...
```

- `sido_code`(2자리) / `sigungu_code`(5자리) / `q`(최대 100자)
- `page_size` 1~200, 기본 50 / `cursor`
- `include_quality`, `include_forecast` boolean. 기본 `false`.

응답 200:

```jsonc
{
  "data": {
    "items": [
      {
        "feature_id": "f_2611000000_p_...",
        "display_name": "광안리 해수욕장",
        "lon": 129.118,
        "lat": 35.155,
        "legal_dong_code": "2611010100",
        "sigungu_code": "26110",
        "sido_code": "26",
        "road_address": "...",
        "road_name_code": "...",
        "road_address_management_no": "...",
        "address_snapshot": { /* ... */ },
        "address_mapping_method": "road_exact",
        "beach_width_m": 80,
        "beach_length_m": 1400,
        "beach_material": "모래",
        "homepage_url": "...",
        "image_url": "...",
        "emergency_contact": "...",
        "source_providers": ["data_go_kr", "khoa", "kma"],
        "latest_observation": { /* 최근 관측 */ },
        "latest_water_quality": { /* 수질 */ },
        "upcoming_index_forecasts": [/* KHOA 예보 */],
        "latest_weather": { /* KMA */ }
      }
    ]
  },
  "meta": {
    "cursor": "next-cursor-or-null",
    "has_more": true,
    "total": 50,
    "limit": 50
  }
}
```

kor-travel-map 호출: `GET /v1/public/beaches`.

### 2.2 `GET /public/beaches/map-markers`

지도 layer용 경량 응답.

```http
GET /public/beaches/map-markers?max_items=500
```

응답 200:

```jsonc
{
  "data": {
    "layer_key": "beach",
    "display_name": "해수욕장",
    "marker_color": "P-07",
    "marker_icon": "swimming",
    "items": [
      {
        "feature_id": "...",
        "name": "광안리 해수욕장",
        "lon": 129.118,
        "lat": 35.155,
        "sigungu_code": "26110"
      }
    ]
  }
}
```

### 2.3 `GET /public/beaches/{feature_id}`

[2.1과](#21-get-publicbeaches) 동일한 단일 row 셰입.

### 2.4 `GET /public/festivals/monthly`

```http
GET /public/festivals/monthly?year=2026&month=6&page_size=12
```

- `year`/`month` 생략 시 now KST 기준
- `page_size`: 1~50 (기본 12) / `cursor`
- `include_months`: 기본 `true`
- 응답 200:

```jsonc
{
  "data": {
    "months": [
      { "year": 2026, "month": 5, "count": 23 },
      { "year": 2026, "month": 6, "count": 47 },
      { "year": 2026, "month": 7, "count": 31 }
    ],
    "items": [
      {
        "feature_id": "f_..._e_...",
        "festival_name": "부산 바다축제",
        "venue_name": "광안리 해수욕장",
        "event_start_date": "2026-06-15",
        "event_end_date": "2026-06-18",
        "event_status": "scheduled",
        "road_address": "...",
        "jibun_address": "...",
        "sigungu_code": "26110",
        "sido_code": "26",
        "lon": 129.118,
        "lat": 35.155,
        "homepage_url": "..."
      }
    ]
  },
  "meta": {
    "cursor": null,
    "has_more": false,
    "total": 47,
    "limit": 12
  }
}
```

기간 overlap으로 month 매칭. `is_active=true`만.

### 2.5 `GET /public/festivals/map-markers`

```http
GET /public/festivals/map-markers?max_items=500
```

```jsonc
{
  "data": {
    "layer_key": "festival",
    "marker_color": "P-11",
    "marker_icon": "star",
    "items": [/* feature_id + name + lon + lat */]
  }
}
```

### 2.6 `GET /public/festivals/{feature_id}`

상세 (2.4 필드 + 추가):

```jsonc
{
  "data": {
    "festival_name": "...",
    "festival_content": "...",
    "mnnst_name": "주관 기관",
    "auspc_instt_name": "주최 기관",
    "suprt_instt_name": "후원 기관",
    "phone_number": "...",
    "related_info": "...",
    "provider_institution_name": "...",
    "reference_date": "2026-05-01",
    "marker_color": "P-11",
    "marker_icon": "star"
  }
}
```

## 3. 캐싱

- kor-travel-map HTTP 응답은 process LRU (5분)
- CDN 캐싱 가능 — `Cache-Control: public, max-age=300`
- viewport 의존 X — 단순 ID 기반 조회

## 4. AI agent 구현 체크리스트

- [x] `apps/api/app/schemas/public.py` Pydantic + `packages/schemas/src/public.ts` Zod
- [x] `apps/api/app/clients/kor_travel_map.py` — kor-travel-map `/v1/public/*` HTTP 호출
- [x] `apps/api/app/api/v1/public.py` 라우터
- [x] `Cache-Control: public, max-age=300` 헤더 응답
- [ ] 앱 내 공통 Rate limit 적용(IP 기준) — 공통 `SlowAPI` 미들웨어 도입 후 닫음
- [x] 통합 테스트(`httpx` ASGI + fake kor_travel_map client)
