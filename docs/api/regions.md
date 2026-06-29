# Region API (`/regions/*`)

행정구역(시도/시군구/법정동) 조회 — `kor-travel-geo`가 데이터 소유(도로명주소
전자지도 SHP 기반).

> **변경 (ADR-025)**: region/주소 조회는 **`kor-travel-geo` v2 REST API 직접 호출**
> 로 구현한다(이전: kor-travel-map 함수 경유 — 폐기). endpoint 경로/응답 셰입은 유지
> 하되 **내부 구현만 v2 REST**(`docs/architecture/geocoding-open-decisions.md` D1).
> 통합 계약은 `docs/integrations/kor-travel-geo.md`가 권위. geocoding 신규 기능
> (주소검색/역지오코딩)은 `/geo/*`(같은 v2 경로)로 노출한다.

공통 규약 [`common.md`](./common.md). 좌표는 EPSG:4326 `(longitude, latitude)`.

## 1. Endpoint

### 1.1 `GET /regions/covering-point`

좌표를 포함하는 boundary 조회.

```http
GET /regions/covering-point?lon=129.118&lat=35.155&boundary_level=emd
```

- `boundary_level`: `sido` | `sigungu` | `emd` (기본 `emd`)
- `boundary_level`은 요청 hint이며 응답에 그대로 echo된다(reverse 결과에서 파생하지 않음).
- 내부: `kor-travel-geo` `POST /v2/reverse`의 최선 후보 `region`을 사용한다.

응답 200:

```jsonc
{
  "data": {
    "boundary_level": "emd",
    "region": {
      "region_name": "광안동",
      "sig_cd": "26500",
      "bjd_cd": "2650010100",
      "full_region_name": "부산광역시 수영구 광안동"
    }
  }
}
```

매치 없으면 `404 RESOURCE_NOT_FOUND`.

### 1.2 `GET /regions/within-radius`

```http
GET /regions/within-radius?lon=129.118&lat=35.155&radius_km=2.0&levels=sigungu&levels=emd
```

- 내부: `kor-travel-geo` `POST /v2/regions/within-radius`
- `radius_km`: 최대 500 (기본 3.0)
- `levels`: `sido` | `sigungu` | `emd` (반복 query param, 기본 `sigungu`+`emd`)

응답 200: `center`/`radius_km` + level별 그룹 배열 `sido[]`/`sigungu[]`/`emd[]`. 각 항목은
`{code, name, relation}`이며 `relation`은 `contains`(중심 좌표 포함) 또는 `overlaps`(반경
원과 교차). `candidate[]`/`distance_m`은 없다.

```jsonc
{
  "data": {
    "status": "ok",
    "center": { "lon": 129.118, "lat": 35.155 },
    "radius_km": 2.0,
    "sido": [],
    "sigungu": [
      { "code": "26500", "name": "수영구", "relation": "contains" }
    ],
    "emd": [
      { "code": "2650010100", "name": "광안동", "relation": "contains" },
      { "code": "2650010200", "name": "민락동", "relation": "overlaps" }
    ]
  }
}
```

UI 표기: "근사 매칭" 라벨 (행정구역 경계는 정확한 반경 검색이 아님 — SPEC V8
geospatial 룰).

## 2. kor-travel-geo v2 REST 호출 (ADR-025)

kor-travel-map 함수 호출이 아니라 **`kor-travel-geo` v2 REST를 직접** 부른다
(`docs/integrations/kor-travel-geo.md` §5 `GeocodingClient`).

- `covering-point` → `POST /v2/reverse {lon,lat,radius_m,include_region:true}` →
  `candidates[].region`(`sig_cd`/`bjd_cd`) + `address`로 응답 구성. `match_kind="sppn"`
  후보는 제외.
- `within-radius` → `POST /v2/regions/within-radius {lon,lat,radius_km,levels[]}` →
  level별 그룹 배열(`sido[]`/`sigungu[]`/`emd[]`, 항목 `{code,name,relation}`)을
  pass-through한다(`docs/architecture/geocoding-open-decisions.md` D5 결정됨).
- 두 내부 호출 모두 `key=<PINVI_VWORLD_API_KEY>` query를 붙인다(ADR-048). 공개 API key
  hash 저장/검증은 `kor-travel-geo`가 소유하며, Pinvi에는 별도 geo key env를 두지 않는다.

PostGIS 공간 인덱스는 kor-travel-geo 서비스 책임 — Pinvi는 v2 응답만 신뢰
(VWorld/juso 직접 호출 금지).

## 3. 위치 감사

좌표를 받는 endpoint이므로 `app.location_access_log` 자동 적재
(`docs/architecture/user-location.md`). 사용자 명시 액션 후에만 호출 (예: "내
위치 주변 지역" 검색).

## 4. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/region.py` Pydantic + `packages/schemas/src/region.ts` Zod
- [ ] `apps/api/app/services/region_view.py` — `GeocodingClient`(kor-travel-geo v2) 호출
      (`docs/integrations/kor-travel-geo.md` §5)
- [ ] `apps/api/app/api/v1/regions.py` 라우터
- [ ] `covering-point` → `/v2/reverse` 매핑, `within-radius` → `/v2/regions/within-radius` 매핑
- [ ] 좌표 미들웨어가 `/regions/covering-point` 자동 처리하는지 확인 (위치 감사)
- [ ] Rate limit 적용
- [ ] 통합 테스트 — `httpx.MockTransport`로 v2 응답 stub (실 kor-travel-geo 의존 금지)
