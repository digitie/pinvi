# 공간 데이터 규약

좌표 / SRID / lon-lat / PostGIS / fuzzy 금지. v1 `skills/geospatial-postgis.ko.md` 정리.

> **scope**: Pinvi `app` schema의 공간 사용은 적음 — feature schema에 위임.
> 본 규약은 클라이언트 ↔ Pinvi API ↔ kor-travel-map/kor-travel-geo HTTP 경계에서 좌표를 다룰 때.

## 1. SRID 항상 명시

- `geometry(Point, 4326)` — `srid=4326` 명시
- PostGIS 컬럼은 `Geometry(geometry_type="POINT", srid=4326, spatial_index=False)`
- 응용 코드에서 raw 4326 좌표는 그대로 사용 (변환 X)
- 반경 / 거리 계산은 EPSG:5179 (meter) — 라이브러리 측에서 `coord_5179`로 관리

## 2. 좌표 순서 — lon-lat

- **모든 외부 인터페이스 (API 입력/출력 + DB) = `(longitude, latitude)` 순서**
- Pydantic / Zod schema:
  ```python
  class Coord(BaseModel):
      longitude: float
      latitude: float
  ```
- PostGIS: `ST_MakePoint(lon, lat)` 항상
- GeoJSON: `coordinates: [lon, lat]`
- **Pinvi stack 전체가 `(lng, lat)` 일관** — `vworld-map-web`은 GeoJSON 순서를 따르므로 어댑터 불필요 (ADR-046)

```ts
// apps/web/lib/coordAdapter.ts
// vworld-map-web은 [lng, lat] 순서를 직접 받으므로 어댑터 불필요
// (ADR-015 — Kakao Map의 (lat, lng) 어댑터 패턴 폐기, ADR-046 — Web 패키지 전환)
export function toLngLatTuple(c: { longitude: number; latitude: number }): [number, number] {
  return [c.longitude, c.latitude];
}
```

## 3. 정밀도

- 라이브러리 / DB 원본: 소수점 6자리 (~10cm)
- 사용자 위치 (`app.location_access_log`): 6자리 저장, UI 노출은 **4자리 (~10m)**
  (PIPA 정밀도 제한 — `docs/compliance/lbs-act.md`)
- 좌표 검증: 대한민국 영역
  ```python
  CoordSchema = z.object({
      lat: z.number().min(33).max(43),
      lng: z.number().min(124).max(132),
  })
  ```

## 4. fuzzy / 근사 표기 금지

- "주변 X km" — 행정구역 근사임을 UI에 명시
- "정확한 반경 검색"이라 쓰지 않음
- 주소 매칭은 도로명 exact → 지번 exact → 법정동 point-in-polygon → not_found
- fuzzy address matching 금지 (라이브러리도 동일 — SPEC V8 SKILL)

## 5. shp / GIS 데이터

- Pinvi는 shp 직접 import X — `kor-travel-map` 또는 `kor-travel-geo`가 소유
- feature 조회는 kor-travel-map OpenAPI, geocoding/region 조회는 kor-travel-geo v2 REST
- 본 저장소에 GIS raw data 저장 X

## 6. PostGIS 사용

라이브러리 측에서:

- `ST_DWithin(coord_5179, point_5179, radius_m)` — meter
- `ST_Within(coord_4326, polygon_4326)` — 행정구역
- `ST_Covers` / `ST_Intersects` — boundary
- Index: GiST on geom + `coord_5179`

Pinvi 측에서:

- 좌표 자체는 kor-travel-map/kor-travel-geo 응답에서 받아 그대로 응답에 직렬화
- 거리 계산 (UI distance label)은 클라이언트 haversine 또는 kor-travel-map/kor-travel-geo 응답값 사용

## 7. fixture 테스트

지물 fixture:

- 경계점 (boundary)
- 근처지만 다른 구역인 점
- 잘못된 geometry (invalid)
- 인접 시군구

라이브러리 측 책임. Pinvi는 좌표 입력 검증 + 응답 변환 unit 테스트만.

## 8. AI agent 체크리스트

좌표 다루는 코드 변경 시:

- [ ] lon-lat 순서 일관 (API + Zod + Pydantic + PostGIS + GeoJSON)
- [ ] SRID 명시 (4326)
- [ ] (`vworld-map-web` 기본 — Kakao SDK lat-lng 어댑터는 제거됨, ADR-015/046)
- [ ] 사용자 위치 정밀도 4자리 (UI)
- [ ] 좌표 범위 검증 (대한민국)
- [ ] "정확한 반경" 표현 안 함 — "근사"
- [ ] fuzzy address matching 안 함
- [ ] PostGIS 직접 호출 안 함 (라이브러리 경유)
