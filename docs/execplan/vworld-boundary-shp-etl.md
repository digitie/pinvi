# VWorld 경계 SHP ETL 실행 계획

## 목표

관리자가 업로드한 VWorld 행정경계 SHP ZIP 파일을 PostGIS에 적재해 TripMate가 다음 기능을 수행할 수 있게 한다.

- 좌표로부터 법정동을 찾는다.
- 현재 좌표에서 특정 반경과 교차하는 법정동, 시군구, 시도를 찾는다.
- VWorld `BJCD` 값을 Juso 법정동코드 기준 테이블과 조인한다.

## 원천 파일

백엔드는 VWorld에서 파일을 직접 다운로드하지 않는다. 관리자가 layer별 ZIP 파일을 직접 업로드한다.

| ZIP 파일 | layer | 경계 단계 |
| --- | --- | --- |
| `N3A_G0010000.zip` | 행정경계(시도) | `sido` |
| `N3A_G0100000.zip` | 행정경계(시군구) | `sigungu` |
| `N3A_G0110000.zip` | 행정경계(읍면동/법정동코드) | `legal_dong` |

SHP DBF encoding은 `cp949`로 읽는다.

## 확인한 원천 구조

원천 PRJ는 Korea 2000 Unified Coordinate System이며 EPSG:5179다.

loader가 사용하는 DBF 필드:

- `UFID`: VWorld feature id
- `BJCD`: 법정동코드 또는 상위 행정구역 코드
- `NAME`: 행정구역명
- `DIVI`: 구분 코드
- `SCLS`: 통합 코드
- `FMTA`: 제작 정보

실제 확인한 최종 DBF 파일에는 `A0`부터 `A4`까지의 컬럼이 노출되지 않았다. 향후 업로드 파일에 추가 컬럼이 있어도 제품 로직에서 필요해지기 전까지는 serving 정규화 대상에 포함하지 않는다.

## 저장 구조

- `region_boundary_import_batch`: 업로드 ZIP 단위 적재 metadata
- `region_raw_vworld_boundary`: EPSG:5179 원본 MultiPolygon geometry와 DBF 원본 속성
- `region_serving_boundary`: API, 지도, 공간 질의용 EPSG:4326 MultiPolygon geometry
- `address_code_standard`: `sido_code`, `sigungu_code` helper column을 포함한 Juso 법정동코드 기준 테이블

`region_serving_boundary.address_code_standard_code`는 `address_code_standard.legal_dong_code`에 대한 nullable FK다. 일부 SHP polygon이 최신 코드 기준 테이블에 없는 값을 가질 수 있으므로, 코드 매칭이 없다는 이유만으로 적재가 실패하면 안 된다.

## 질의 정책

- point-in-polygon은 `region_serving_boundary.geom`에 대해 `ST_Covers`를 사용한다.
- 반경 내 행정구역 조회는 serving geometry와 query point를 EPSG:5179로 변환한 뒤 `ST_DWithin`을 사용한다. 이렇게 해야 radius 단위를 meter로 해석할 수 있다.
- API와 지도 응답 좌표는 EPSG:4326을 사용한다.

## 검증

- 생성한 cp949 SHP ZIP을 사용한 unit/integration test
- 지원하지 않는 ZIP 이름 reject 검증
- raw geometry SRID가 5179인지 검증
- serving geometry SRID가 4326인지 검증
- 법정동 SHP 코드가 `address_code_standard`와 매칭되는지 검증
- query helper가 point 기반 법정동 조회와 반경 내 행정구역 조회를 수행하는지 검증
