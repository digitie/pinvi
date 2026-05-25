# Region API (`/regions/*`)

행정구역(시도/시군구/법정동) 조회 — VWorld SHP 기반. 라이브러리
(`python-kraddr-geo`)가 데이터 소유. 본 endpoint는 TripMate가 라이브러리 호출
경유로 노출.

공통 규약 [`common.md`](./common.md). 좌표는 EPSG:4326 `(longitude, latitude)`.

## 1. Endpoint

### 1.1 `GET /regions/covering-point`

좌표를 포함하는 boundary 조회.

```http
GET /regions/covering-point?longitude=129.118&latitude=35.155&boundary_level=legal_dong
```

- `boundary_level`: `sido` | `sigungu` | `legal_dong` (기본 `legal_dong`)
- 내부: `ST_Covers(geom, ST_MakePoint(lng, lat))` (라이브러리에서)

응답 200:

```jsonc
{
  "data": {
    "boundary_level": "legal_dong",
    "region_code": "2611010100",
    "region_name": "광안동",
    "sido_code": "26",
    "sigungu_code": "26110",
    "legal_dong_code": "2611010100",
    "parent_region_code": "26110",
    "full_region_name": "부산광역시 수영구 광안동",
    "address_code_matched": true
  }
}
```

매치 없으면 `404 RESOURCE_NOT_FOUND`.

### 1.2 `GET /regions/within-radius`

```http
GET /regions/within-radius?longitude=129.118&latitude=35.155&radius_meters=2000&boundary_level=sigungu
```

- 입력 좌표를 EPSG:5179로 변환 후 `ST_DWithin` (meter)
- `radius_meters`: 100 ~ 50000

응답 200:

```jsonc
{
  "data": {
    "boundary_level": "sigungu",
    "items": [
      {
        "region_code": "26110",
        "region_name": "수영구",
        "sido_code": "26",
        "sigungu_code": "26110",
        "legal_dong_code": null,
        "parent_region_code": "26",
        "full_region_name": "부산광역시 수영구",
        "address_code_matched": true
      }
    ]
  }
}
```

UI 표기: "근사 매칭" 라벨 (행정구역 경계는 정확한 반경 검색이 아님 — SPEC V8
geospatial 룰).

## 2. 라이브러리 호출

- `AsyncKrtourMapClient.regions.covering_point(lng, lat, level)`
- `AsyncKrtourMapClient.regions.within_radius(lng, lat, radius_m, level)`

라이브러리는 PostGIS 공간 인덱스를 사용 — TripMate는 인덱스 운영에 관여 X.

## 3. 위치 감사

좌표를 받는 endpoint이므로 `app.location_access_log` 자동 적재
(`docs/architecture/user-location.md`). 사용자 명시 액션 후에만 호출 (예: "내
위치 주변 지역" 검색).

## 4. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/region.py` Pydantic + `packages/schemas/src/region.ts` Zod
- [ ] `apps/api/app/services/region_view.py` — 라이브러리 호출
- [ ] `apps/api/app/api/v1/regions.py` 라우터
- [ ] 좌표 미들웨어가 자동 처리하는지 확인
- [ ] Rate limit 적용
- [ ] 통합 테스트 (라이브러리 fixture 또는 mock client)
