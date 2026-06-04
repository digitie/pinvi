# Public API (`/public/*`)

비로그인 사용자도 접근 가능한 read-only endpoint. 로그인 화면의 축제 광고, 일반
사용자의 지도 마커 layer 등.

## 1. 정책

- 인증 없음 (cookie / Authorization 헤더 없어도 OK)
- Rate limit: IP 기준 분당 60회
- 응답 데이터는 krtour-map OpenAPI HTTP 계약에서 가져옴
- TripMate `app.users` / `trips`는 노출 안 됨 — 본 endpoint는 라이브러리 feature
  데이터만

## 2. Endpoint

### 2.1 `GET /public/beaches`

해수욕장 통합 listing.

```http
GET /public/beaches?sido_code=11&sigungu_code=11680&query=광안리&limit=100&offset=0
```

- `sido_code` / `sigungu_code` / `query` / `limit` (1~300, 기본 100) / `offset`

응답 200:

```jsonc
{
  "data": {
    "items": [
      {
        "feature_id": "f_2611000000_p_...",
        "display_name": "광안리 해수욕장",
        "longitude": 129.118,
        "latitude": 35.155,
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
    ],
    "total": 50
  }
}
```

krtour-map 호출: 최신 `openapi.user.json` 또는 public subset에 정의된 beach/listing
경로를 따른다. public beach 표면이 없으면 TripMate public API에서 노출하지 않는다.

### 2.2 `GET /public/beaches/map-markers`

지도 layer용 경량 응답.

```http
GET /public/beaches/map-markers?limit=500
```

응답 200:

```jsonc
{
  "data": {
    "layer_key": "beach",
    "display_name": "해수욕장",
    "marker_color": "P-07",
    "marker_icon": "swimming",
    "markers": [
      {
        "feature_id": "...",
        "name": "광안리 해수욕장",
        "longitude": 129.118,
        "latitude": 35.155
      }
    ]
  }
}
```

### 2.3 `GET /public/beaches/{feature_id}`

[2.1과](#21-get-publicbeaches) 동일한 단일 row 셰입.

### 2.4 `GET /public/festivals/monthly`

```http
GET /public/festivals/monthly?year=2026&month=6&limit=12
```

- `year`/`month` 생략 시 now KST 기준
- `limit`: 1~50 (기본 12)
- 응답 200:

```jsonc
{
  "data": {
    "year": 2026,
    "month": 6,
    "months": [
      { "month": 5, "count": 23 },
      { "month": 6, "count": 47 },
      { "month": 7, "count": 31 }
    ],
    "festivals": [
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
        "longitude": 129.118,
        "latitude": 35.155,
        "homepage_url": "..."
      }
    ]
  }
}
```

기간 overlap으로 month 매칭. `is_active=true`만.

### 2.5 `GET /public/festivals/map-markers`

```http
GET /public/festivals/map-markers?limit=500
```

```jsonc
{
  "data": {
    "layer_key": "festival",
    "marker_color": "P-11",
    "marker_icon": "star",
    "markers": [/* feature_id + name + lng + lat */]
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

- krtour-map HTTP 응답은 process LRU (5분)
- CDN 캐싱 가능 — `Cache-Control: public, max-age=300`
- viewport 의존 X — 단순 ID 기반 조회

## 4. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/public.py` Pydantic + `packages/schemas/src/public.ts` Zod
- [ ] `apps/api/app/services/public_view.py` — krtour-map HTTP 호출 + 셰입 변환
- [ ] `apps/api/app/api/v1/public.py` 라우터
- [ ] `Cache-Control` 헤더 응답
- [ ] Rate limit 적용 (IP 기준)
- [ ] 통합 테스트 (`httpx.MockTransport` + 선택적 live krtour-map)
