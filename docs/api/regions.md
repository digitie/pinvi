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

## 2. kor-travel-geo v2 REST 호출 (ADR-025)

kor-travel-map 함수 호출이 아니라 **`kor-travel-geo` v2 REST를 직접** 부른다
(`docs/integrations/kor-travel-geo.md` §5 `GeocodingClient`).

- `covering-point` → `POST /v2/reverse {lon,lat,radius_m,include_region:true}` →
  `candidates[].region`(`sig_cd`/`bjd_cd`) + `address`로 응답 구성. `match_kind="sppn"`
  후보는 제외.
- `within-radius` → v2에 1:1 대응 없음. **잠정 보류**
  (`docs/architecture/geocoding-open-decisions.md` D5). 필요 확정 시 kor-travel-geo에
  신규 endpoint 요청.

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
- [ ] `covering-point` → `/v2/reverse` 매핑, `within-radius`는 보류(D5)
- [ ] 좌표 미들웨어가 `/regions/covering-point` 자동 처리하는지 확인 (위치 감사)
- [ ] Rate limit 적용
- [ ] 통합 테스트 — `httpx.MockTransport`로 v2 응답 stub (실 kor-travel-geo 의존 금지)
