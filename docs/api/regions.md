# 행정경계 API

TripMate 행정경계 API는 VWorld SHP serving 경계를 PostGIS에서 조회한다.

좌표 입력은 EPSG:4326 경도/위도 순서다. 응답 좌표 geometry는 아직 직접 반환하지 않고, 행정구역 식별자와 표시명만 반환한다.

## 좌표 포함 행정경계 조회

```http
GET /regions/covering-point?longitude=126.9707&latitude=37.5804&boundary_level=legal_dong
```

`boundary_level`:

- `sido`
- `sigungu`
- `legal_dong`

동작:

- PostGIS `ST_Covers`로 point-in-polygon 판정을 수행한다.
- 기본값은 `legal_dong`이다.
- 경계를 찾지 못하면 `404`를 반환한다.

## 반경 교차 행정경계 조회

```http
GET /regions/within-radius?longitude=126.9707&latitude=37.5804&radius_meters=500&boundary_level=legal_dong
```

동작:

- 입력 좌표와 serving geometry를 EPSG:5179로 변환한 뒤 `ST_DWithin`을 사용한다.
- `radius_meters`는 meter 단위다.
- 이 API는 행정구역 polygon과 반경의 교차 여부를 찾는 근사 조회다. 정확한 원형 거리 내 장소 검색으로 표현하지 않는다.

## 응답 예시

```json
[
  {
    "boundary_level": "legal_dong",
    "region_code": "1111010100",
    "region_name": "청운동",
    "sido_code": "1100000000",
    "sigungu_code": "1111000000",
    "legal_dong_code": "1111010100",
    "parent_region_code": "1111000000",
    "full_region_name": "서울특별시 종로구 청운동",
    "address_code_matched": true
  }
]
```
