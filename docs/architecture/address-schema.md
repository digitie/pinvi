# 주소 체계와 DB 스키마

이 문서는 TripMate의 현재 주소 체계, PostgreSQL/PostGIS 스키마, 외부 데이터셋과의 매핑 방식, 검증 방법을 설명한다.

목적은 두 가지다.

- 이미 검토한 주소 체계 의사결정을 나중에 처음부터 다시 반복하지 않는다.
- 대한민국 주소 체계를 잘 모르는 사람이나 AI가 읽어도 왜 이런 구조로 구현했는지 이해할 수 있게 한다.

기준 자료:

- SQLAlchemy 모델: `apps/api/app/models/address.py`
- Alembic migration: `20260424_0002`부터 `20260425_0006`까지
- 데이터 정책: `docs/data-sources.md`
- ETL 운영: `docs/runbooks/etl.md`
- OpiNet 매핑 상세: `docs/architecture/opinet-region-mapping.md`
- 유가/휴게소/날씨/관광코스 스키마:
  - `docs/architecture/fuel-schema.md`
  - `docs/architecture/rest-area-schema.md`
  - `docs/architecture/weather-air-quality-schema.md`
  - `docs/architecture/kma-tour-course-schema.md`

## 한눈에 보는 결론

TripMate의 주소 기준은 “하나의 주소 문자열”이 아니라 여러 안정 key의 조합이다.

| 기준 | 예 | TripMate 역할 |
| --- | --- | --- |
| 법정동코드 | `1111010100` | 행정구역 계층, 공간 경계, 외부 데이터 지역 매핑의 중심축 |
| 시군구 코드 | `1111000000` | 유가/날씨처럼 시군구 단위로 근사하는 데이터의 join 기준 |
| 시도 코드 | `1100000000` | 전국/광역 단위 집계와 provider 지역 매핑의 fallback |
| 도로명코드 | `111103100012` | 도로명주소 기반 주소 관리 보조 key |
| 행정동코드 | `1111051500` | Juso 주소에 포함되는 행정동 기준. 법정동코드와 같다고 보지 않는다 |
| 도로명주소관리번호 | `11110101310001200009400000` | Juso 도로명주소 row의 핵심 식별자 |
| VWorld `BJCD` | `1111010100` | SHP 경계의 행정구역 코드. 보통 법정동코드와 맞지만 code table과 별도 검증한다 |
| OpiNet 지역코드 | `0101` | 한국석유공사 provider 조회 코드. 법정동코드가 아니므로 별도 매핑한다 |
| 휴게소 `serviceAreaCode2` | `000001` | 한국도로공사 휴게소 데이터 내부 join key. 주소 코드와 직접 연결하지 않는다 |

핵심 정책:

- 앱 내부 주소 코드 기준은 `address_code_standard.legal_dong_code`다.
- 컬럼명은 `legal_dong_code`지만 시도/시군구/법정동 10자리 코드를 모두 담는다.
- 모든 주소/코드 key는 문자열로 저장한다. 선행 0이 의미를 가지므로 숫자로 변환하지 않는다.
- 원천 row는 raw 테이블에 보존하고, 앱/API 조회는 serving 테이블을 사용한다.
- 주소/행정구역/도로명주소는 사라지거나 폐지될 수 있으므로 사용자 여행 장소에는 FK와 함께 저장 당시 주소 snapshot을 둬야 한다.
- 폐지/비활성 주소는 신규 UI 검색에서 숨긴다.
- `address_code_standard`의 기존 코드는 정기 갱신 중 물리 삭제하지 않는다. FK 안전성과 과거 여행 기록 보존이 더 중요하다.
- VWorld SHP raw geometry는 EPSG:5179로 보존하고, 지도/API/공간 조회용 serving geometry는 EPSG:4326으로 둔다.
- 좌표 기반 행정구역 판정은 PostGIS `ST_Covers`를 사용한다.
- “여행지 주변” 리포트는 데이터셋에 따라 행정구역 기반 근사일 수 있으며, 정확한 원형 반경 데이터라고 표현하지 않는다.

## 대한민국 주소 key를 이렇게 나눈 이유

한국 주소 데이터에는 서로 다른 목적의 코드가 함께 등장한다.

법정동코드는 법률상 행정구역 체계에 가까운 코드다. 지도 경계, 공간 판정, 공공데이터 지역 매핑의 기준으로 쓰기 좋다. 반면 행정동코드는 행정 서비스 운영 단위라 법정동과 1:1로 대응하지 않을 수 있다. 도로명코드는 도로명을 식별하고, 도로명주소관리번호는 도로명주소 row를 식별한다.

따라서 TripMate는 “주소 문자열 하나를 파싱해서 모든 것을 해결한다”는 방식을 피한다. 대신 원천이 제공하는 안정 key를 각각 보존하고, 용도별로 맞는 key를 사용한다.

예를 들어 어떤 여행 장소의 좌표가 서울 종로구 청운동에 있으면 다음 정보가 동시에 의미를 가진다.

| 값 | 의미 |
| --- | --- |
| `1111010100` | 상세 법정동. point-in-polygon 결과 또는 Juso 주소에서 얻는 행정구역 |
| `1111000000` | 시군구. OpiNet 유가나 날씨 격자 같은 지역 단위 데이터의 기본 근사 기준 |
| `1100000000` | 시도. 시군구 매핑 실패 시 fallback 또는 광역 데이터 기준 |
| 도로명주소관리번호 | 도로명주소 row를 정확히 찾을 수 있는 경우의 가장 상세한 주소 FK |
| 주소 문자열 snapshot | 나중에 도로명주소나 건물이 사라져도 사용자가 저장한 장소를 계속 보여주기 위한 표시값 |

## 데이터 소스 역할 분담

| 소스 | 입수 방식 | 현재 구현 상태 | 역할 |
| --- | --- | --- | --- |
| data.go.kr `국토교통부_전국 법정동` | Dagster가 3개월 1회 다운로드 | 구현 | `address_code_standard`의 canonical 법정동/시도/시군구 코드 기준 |
| Juso 도로명주소 한글 전체분 | 매월 10일 이후 전체 ZIP 다운로드 | 구현 | 대한민국 전체 도로명주소와 관련 지번 snapshot |
| VWorld 법정구역정보 SHP | 운영자가 ZIP 업로드 또는 command 실행 | loader 구현 | 행정구역 polygon, 좌표→법정동, 반경→행정구역 조회 |
| VWorld reverse geocoding | 검토 이력 | 미구현 | KMA 관광코스에는 사용하지 않는다. 일반 POI에서 좌표→주소 문자열이 꼭 필요해질 경우 별도 결정 후 client/source 계약을 설계한다. |

Juso와 data.go.kr 법정동코드는 모두 주소 코드 기준에 영향을 주지만 주 역할이 다르다.

- data.go.kr 법정동 CSV는 `address_code_standard`의 장기 기준이다.
- Juso 도로명주소 ZIP은 앱 내 모든 실제 주소 row의 기준이다.
- Juso loader도 필요한 법정동 row를 보강할 수 있지만, canonical source는 data.go.kr 법정동 CSV다.
- VWorld SHP는 주소 row가 아니라 공간 경계다. `BJCD`를 코드 기준과 매칭하되, 경계 row 자체는 별도 보존한다.

## 설계 목표

- 주소와 코드 key는 모두 문자열로 저장한다. 선행 0이 의미를 가지므로 숫자로 변환하지 않는다.
- 원천 row는 재처리, 감사, 변경 비교를 위해 raw 테이블에 보존한다.
- 앱 조회에는 정규화된 serving 테이블을 사용한다.
- `address_code_standard.legal_dong_code`를 법정동 기반 주소 데이터의 안정적인 FK 기준으로 사용한다.
- `address_code_standard`는 정기 갱신 중 물리 삭제하지 않는다. 사라진 코드나 폐지 코드는 비활성 상태로 표시한다.
- 주소나 행정구역 코드가 나중에 사라져도 기존 여행 장소와 주소 snapshot이 계속 조회될 수 있어야 한다.

## 코드 레벨 규칙

`address_code_standard.legal_dong_code`는 항상 10자리 문자열이다.

| 레벨 | 판정 규칙 | 예 | 설명 |
| --- | --- | --- | --- |
| `sido` | 뒤 8자리가 `00000000` | `1100000000` | 서울특별시 |
| `sigungu` | 뒤 5자리가 `00000` | `1111000000` | 서울특별시 종로구 |
| `legal_dong` | 위 두 조건이 아님 | `1111010100` | 서울특별시 종로구 청운동 |

파생 규칙:

- 시도 코드: `legal_dong_code[:2] + '00000000'`
- 시군구 코드: `legal_dong_code[:5] + '00000'`
- 상세 법정동에서 시군구/시도 fallback이 필요하면 `상세 법정동 → 시군구 → 시도` 순서로 찾는다.

이 파생 규칙은 OpiNet 지역 매핑, VWorld serving boundary, 날씨 격자 mapping, 대기질 측정소 법정동 매핑에서 반복 사용한다.

## 테이블 그룹

```mermaid
erDiagram
    address_code_standard ||--o{ address_serving_juso_road_address : legal_dong_code
    address_code_standard ||--o{ address_serving_juso_related_jibun : legal_dong_code
    address_code_standard ||--o{ region_serving_boundary : address_code_standard_code
    address_serving_juso_road_address ||--o{ address_serving_juso_related_jibun : road_address_management_no
    region_boundary_import_batch ||--o{ region_raw_vworld_boundary : import_batch_id
    region_boundary_import_batch ||--o{ region_serving_boundary : import_batch_id
    region_raw_vworld_boundary ||--o{ region_serving_boundary : raw_boundary_id
```

주소 관련 테이블은 네 그룹으로 나뉜다.

| 그룹 | 테이블 | 목적 |
| --- | --- | --- |
| 법정동코드 기준 | `address_code_standard`, `address_raw_legal_dong_code` | 행정구역 코드 기준 테이블과 원천 코드 row |
| Juso 도로명주소 | `address_raw_juso_road_address`, `address_serving_juso_road_address` | 도로명주소 원천 row와 앱 조회용 정규화 row |
| Juso 관련 지번 | `address_raw_juso_related_jibun`, `address_serving_juso_related_jibun` | 관련 지번 원천 row와 앱 조회용 정규화 row |
| VWorld 경계 | `region_boundary_import_batch`, `region_raw_vworld_boundary`, `region_serving_boundary` | SHP 적재 이력, 원본 geometry, EPSG:4326 serving 경계 |

## 법정동코드 기준 테이블

### `address_code_standard`

주소 코드의 canonical 기준 테이블이다. PK 이름은 `legal_dong_code`이지만, 실제로는 원천 파일의 10자리 행정구역 코드 전 단계를 담는다.

- `sido`
- `sigungu`
- `legal_dong`

PK:

- `legal_dong_code varchar(10)`

index:

- `code_level`
- `sido_code`
- `sigungu_code`
- `previous_legal_dong_code`

주요 컬럼:

| 컬럼 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `legal_dong_code` | string(10) | 예 | 안정적인 PK 및 FK target |
| `code_level` | string(32) | 예 | `sido`, `sigungu`, `legal_dong` |
| `code_name` | string(255) | 예 | 해당 코드 row의 원천 표시명 |
| `sido_code` | string(10) | 예 | 10자리 시도 코드 |
| `sigungu_code` | string(10) | 예 | 10자리 시군구 코드 |
| `sido_name` | string(40) | 아니오 | 시도명 |
| `sigungu_name` | string(80) | 아니오 | 시군구명. 세종 시도 row처럼 없을 수 있다 |
| `legal_eupmyeondong_name` | string(80) | 아니오 | 법정 읍면동명 |
| `legal_ri_name` | string(80) | 아니오 | 법정 리명 |
| `full_legal_dong_name` | string(255) | 예 | 전체 법정동명 |
| `source_effective_date` | string(8) | 예 | 원천 기준일 또는 적용일 |
| `source_change_reason_code` | string(2) | 예 | Juso 이동사유 코드 또는 기본값 `00` |
| `source_provider` | string(32) | 예 | `data_go_legal_dong`, legacy `vworld_lawd_cd`, bootstrap `juso_road_address` |
| `source_status` | string(40) | 예 | `active`, `deleted`, `missing_from_latest_download`, legacy 상태값 |
| `source_file_name` | string(255) | 예 | 원천 파일명 |
| `source_year_month` | string(6) | 예 | 원천 연월 |
| `source_file_hash` | string(64) | 예 | 원천 파일 SHA-256 |
| `source_sort_order` | integer | 아니오 | 원천 `순위` |
| `source_created_date` | string(10) | 아니오 | 원천 `생성일자` |
| `source_deleted_date` | string(10) | 아니오 | 원천 `삭제일자` |
| `previous_legal_dong_code` | string(10) | 아니오 | 원천 `과거법정동코드` |
| `is_discontinued` | boolean | 예 | 폐지/삭제 여부 |
| `is_active` | boolean | 예 | 신규 검색과 serving 기준 활성 여부 |
| `created_at`, `updated_at` | timestamp | 예 | ORM timestamp mixin |

현재 canonical source:

- data.go.kr `국토교통부_전국 법정동`
- `apps/api/app/dagster_etl/registry.py`의 `legal_dong_code_standard_quarterly` job에서 다운로드한다.
- `app.etl.vworld.legal_dong_code_loader`가 적재한다.

갱신 정책:

- 기존 row는 upsert한다.
- 새 다운로드에서 사라진 코드는 유지하고 다음처럼 표시한다.
  - `is_active = false`
  - `is_discontinued = true`
  - `source_status = 'missing_from_latest_download'`
- 원천 `삭제일자`가 있는 코드는 유지하고 다음처럼 표시한다.
  - `is_active = false`
  - `is_discontinued = true`
  - `source_status = 'deleted'`
- 정기 갱신에서 물리 삭제하지 않는다. Juso 주소, 경계, 향후 장소, 지오코딩 snapshot이 과거 코드를 참조할 수 있기 때문이다.

### `address_raw_legal_dong_code`

법정동코드 원천 row를 저장하는 raw 테이블이다.

PK:

- `id uuid`

unique:

- `unique(source_file_hash, row_number)`

index:

- `source_file_hash`
- `legal_dong_code`

목적:

- 원천 row lineage를 보존한다.
- 파일 hash와 row number 기준으로 멱등 재적재를 지원한다.
- data.go.kr의 추가 필드를 감사와 재처리에 사용할 수 있게 보존한다.

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `source_file_name`, `source_file_hash` | 원천 파일 식별 |
| `row_number` | CSV 내부 1-based row 번호 |
| `legal_dong_code` | 원천 법정동코드 |
| `legal_dong_name` | 원천 기반 전체 법정동명 |
| `discontinued_status` | `active`/`deleted` 또는 legacy 원천 상태 |
| `sido_name`, `sigungu_name`, `legal_eupmyeondong_name`, `legal_ri_name` | 원천 명칭 필드 |
| `source_sort_order`, `source_created_date`, `source_deleted_date`, `previous_legal_dong_code` | data.go.kr 추가 필드 |
| `raw_line` | 감사용 CSV 원문 line |
| `ingested_at` | 적재 시각 |

## Juso 도로명주소 테이블

### `address_raw_juso_road_address`

Juso 도로명주소 TXT의 원천 row를 저장한다.

PK:

- `id uuid`

unique:

- `unique(source_file_hash, row_number)`

index:

- `source_year_month`
- `source_file_hash`
- `legal_dong_code`

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `source_file_name`, `source_year_month`, `source_file_hash` | 원천 snapshot 식별 |
| `row_number` | 원천 row 번호 |
| `delimiter` | 파싱 delimiter |
| `road_address_management_no` | 도로명주소관리번호 |
| `legal_dong_code` | Juso 법정동코드 |
| `road_name_code` | 도로명코드 |
| `administrative_dong_code` | 행정동코드. nullable |
| `effective_date` | 적용일자 |
| `change_reason_code` | 이동사유 코드 |
| `raw_line` | 원본 TXT line |
| `ingested_at` | 적재 시각 |

이 테이블은 raw 전용이다. 앱 조회는 `address_serving_juso_road_address`를 사용한다.

### `address_serving_juso_road_address`

앱 조회용 정규화 도로명주소 테이블이다.

PK:

- `road_address_management_no`

FK:

- `legal_dong_code -> address_code_standard.legal_dong_code`

index:

- `legal_dong_code`
- `road_name_code`
- `administrative_dong_code`

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `road_address_management_no` | 도로명주소의 주요 식별자 |
| `legal_dong_code` | canonical code table FK |
| `road_name_code` | 도로명코드 |
| `administrative_dong_code` | 행정동코드. nullable |
| `sido_name`, `sigungu_name`, `legal_eupmyeondong_name`, `legal_ri_name` | 주소 명칭 구성 요소 |
| `road_name` | 도로명 |
| `administrative_dong_name` | 행정동명 |
| `mountain_yn`, `jibun_main_no`, `jibun_sub_no` | 대표 지번 구성 요소 |
| `underground_yn`, `building_main_no`, `building_sub_no` | 건물번호 구성 요소 |
| `postal_code` | 우편번호 |
| `previous_road_address` | 이전 도로명주소 |
| `apartment_yn` | 공동주택 여부 |
| `building_registry_name`, `sigungu_building_name` | 건물명 |
| `note` | 원천 비고 |
| `full_legal_dong_name` | 전체 법정동 주소명 |
| `full_road_address` | 전체 도로명주소 |
| `source_effective_date`, `source_change_reason_code` | 원천 메타데이터 |
| `source_file_name`, `source_year_month`, `source_file_hash` | 원천 lineage |
| `is_active` | serving 표시 여부 |
| `created_at`, `updated_at` | ORM timestamp mixin |

도로명주소 기반 geocoding 결과를 TripMate의 안정적인 주소 key에 연결할 때 우선 사용한다.

## Juso 관련 지번 테이블

### `address_raw_juso_related_jibun`

Juso 관련 지번 TXT의 원천 row를 저장한다.

PK:

- `id uuid`

unique:

- `unique(source_file_hash, row_number)`

index:

- `source_year_month`
- `source_file_hash`
- `legal_dong_code`

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `source_file_name`, `source_year_month`, `source_file_hash` | 원천 snapshot 식별 |
| `row_number` | 원천 row 번호 |
| `road_address_management_no` | 도로명주소 연결 key |
| `legal_dong_code` | 법정동코드 |
| `sido_name`, `sigungu_name`, `legal_eupmyeondong_name`, `legal_ri_name` | 주소 명칭 구성 요소 |
| `mountain_yn`, `jibun_main_no`, `jibun_sub_no` | 지번 구성 요소 |
| `road_name_code` | 도로명코드 |
| `underground_yn`, `building_main_no`, `building_sub_no` | 건물번호 구성 요소 |
| `note` | 원천 비고 |
| `raw_line` | 원본 TXT line |
| `ingested_at` | 적재 시각 |

### `address_serving_juso_related_jibun`

앱 조회용 정규화 관련 지번 테이블이다.

PK:

- `id uuid`

FK:

- `road_address_management_no -> address_serving_juso_road_address.road_address_management_no`
  - `ondelete='CASCADE'`
- `legal_dong_code -> address_code_standard.legal_dong_code`

unique:

- `unique(road_address_management_no, legal_dong_code, mountain_yn, jibun_main_no, jibun_sub_no)`

index:

- `road_address_management_no`
- `legal_dong_code`
- `road_name_code`

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `road_address_management_no` | 연결된 도로명주소 row |
| `legal_dong_code` | canonical code table FK |
| `road_name_code` | 도로명코드 |
| `sido_name`, `sigungu_name`, `legal_eupmyeondong_name`, `legal_ri_name` | 주소 명칭 구성 요소 |
| `mountain_yn`, `jibun_main_no`, `jibun_sub_no` | 관련 지번 key |
| `underground_yn`, `building_main_no`, `building_sub_no` | 건물번호 구성 요소 |
| `note` | 원천 비고 |
| `full_legal_dong_name` | 전체 법정동 주소명 |
| `full_jibun_address` | 전체 지번주소 |
| `source_file_name`, `source_year_month`, `source_file_hash` | 원천 lineage |
| `is_active` | serving 표시 여부 |
| `created_at`, `updated_at` | ORM timestamp mixin |

입력 주소나 reverse geocoding 결과가 지번주소로 해석될 때 사용한다.

## VWorld 경계 테이블

### `region_boundary_import_batch`

VWorld SHP ZIP 업로드 단위의 적재 이력을 저장한다.

PK:

- `id uuid`

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `source_file_name`, `source_file_hash` | 업로드 ZIP 식별 |
| `layer_code` | VWorld layer code. 예: `N3A_G0010000` |
| `boundary_level` | `sido`, `sigungu`, `legal_dong` |
| `source_encoding` | 현재 `cp949` |
| `source_srid` | 원본 geometry SRID. 현재 `5179` |
| `serving_srid` | serving geometry SRID. 현재 `4326` |
| `row_count` | 적재 feature 수 |
| `status` | `loading`, `loaded` 등 적재 상태 |
| `created_at`, `updated_at` | ORM timestamp mixin |

layer mapping:

| ZIP/layer | boundary level |
| --- | --- |
| `N3A_G0010000` | `sido` |
| `N3A_G0100000` | `sigungu` |
| `N3A_G0110000` | `legal_dong` |

### `region_raw_vworld_boundary`

VWorld SHP 원본 geometry와 DBF 속성을 저장한다.

PK:

- `id uuid`

FK:

- `import_batch_id -> region_boundary_import_batch.id`
  - `ondelete='CASCADE'`

unique:

- `unique(import_batch_id, ufid)`

index:

- `import_batch_id`
- `bjcd`
- `geom` GiST

geometry:

- `geom geometry(MULTIPOLYGON, 5179)`
- 원본 EPSG:5179를 보존해 원천 비교와 재처리에 사용한다.

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `row_number` | SHP feature 순서 |
| `layer_code`, `boundary_level` | layer metadata |
| `ufid` | VWorld feature id |
| `bjcd` | 원천 경계/행정구역 코드 |
| `name` | 원천 경계명 |
| `divi`, `scls`, `fmta` | 원천 분류 필드 |
| `raw_attributes` | 정규화한 DBF 전체 속성 JSONB |
| `source_file_name`, `source_file_hash` | 원천 ZIP 식별 |
| `geom` | 원본 geometry |
| `ingested_at` | 적재 시각 |

### `region_serving_boundary`

지도, API, 공간 질의를 위한 정규화 경계 테이블이다.

PK:

- `id uuid`

FK:

- `raw_boundary_id -> region_raw_vworld_boundary.id`
  - `ondelete='CASCADE'`
- `import_batch_id -> region_boundary_import_batch.id`
  - `ondelete='CASCADE'`
- `address_code_standard_code -> address_code_standard.legal_dong_code`
  - `ondelete='SET NULL'`

unique:

- `unique(boundary_level, region_code)`

index:

- `(boundary_level, region_code)`
- `sido_code`
- `sigungu_code`
- `legal_dong_code`
- `geom` GiST

geometry:

- `geom geometry(MULTIPOLYGON, 4326)`
- EPSG:4326 serving geometry는 지도 출력, API 응답, 웹 좌표 기반 point-in-polygon에 사용한다.

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `layer_code`, `boundary_level` | 원천 layer와 정규화 level |
| `region_code` | 원천 `BJCD` |
| `region_name` | 경계 표시명 |
| `sido_code`, `sigungu_code`, `legal_dong_code` | 정규화 코드 구성 |
| `parent_region_code` | 계층 조회용 부모 코드 |
| `full_region_name` | 전체 표시명 |
| `address_code_standard_code` | canonical address code nullable FK |
| `address_code_matched` | code table 매칭 여부 |
| `source_file_name`, `source_file_hash` | 원천 ZIP 식별 |
| `geom` | EPSG:4326 serving geometry |
| `created_at`, `updated_at` | ORM timestamp mixin |

경계와 코드 매칭 규칙:

- `BJCD == address_code_standard.legal_dong_code` exact match를 우선한다.
- code match가 없어도 경계 row는 적재한다.
- legacy code standard에서 세종 `3600000000`이 없고 `3611000000`만 있는 경우, 시도 level에 한해 정규화 이름 fallback을 사용할 수 있다.
- `address_code_standard_code`는 nullable이고 `ondelete='SET NULL'`이다. 코드 row 문제로 경계 row가 사라지지 않게 하기 위함이다.

## 주소 매칭 우선순위

향후 여행 장소나 geocoding 결과를 저장할 때 주소 FK는 다음 순서로 우선한다.

1. `road_address_management_no`
2. `legal_dong_code`
3. `road_name_code`
4. `administrative_dong_code`
5. 안전한 FK가 없으면 주소 문자열 snapshot만 저장

향후 장소/주소 테이블은 다음을 함께 저장해야 한다.

- 가능한 최선의 nullable FK
- 저장 당시 주소 문자열과 provider/geocoder 결과 snapshot

건물, 도로명주소, 행정구역 코드는 나중에 사라질 수 있으므로 snapshot은 FK와 별개로 필요하다.

## 갱신과 삭제 규칙

### code standard

- 정기 갱신 중 `address_code_standard`를 truncate/delete하지 않는다.
- 신규/현재 row는 upsert한다.
- 최신 원천에서 사라진 row는 inactive로 표시한다.
- 삭제/폐지 row도 FK 안전성을 위해 유지한다.
- 신규 UI 검색에서는 inactive/deleted row를 숨긴다.

### Juso serving

- Juso 월간 갱신은 현재 전체 파일 기준으로 serving 주소 row를 교체할 수 있다.
- raw row는 source file hash와 row number 기준으로 유지한다.
- `address_serving_juso_related_jibun`은 연결된 도로명주소 row가 삭제되면 cascade된다.
- 향후 여행 장소 snapshot은 Juso serving row에만 의존하면 안 된다. 주소가 사라질 수 있기 때문이다.

### VWorld boundary

- 경계 import는 layer별 기존 batch를 삭제하고 새 batch로 교체한다.
- raw/serving 경계 row는 import batch와 함께 cascade된다.
- `address_code_standard_code`는 nullable + `SET NULL`이므로 code table 변화가 경계 row 삭제로 이어지지 않는다.

## 공간 규칙

- SHP 원본 geometry는 EPSG:5179로 보존한다.
- serving geometry는 EPSG:4326으로 변환한다.
- 웹 지도 출력과 API 좌표 응답은 EPSG:4326을 사용한다.
- point-in-polygon은 특별한 이유가 없으면 `region_serving_boundary`의 `boundary_level = 'legal_dong'`을 사용한다.
- 반경형 행정구역 리포트는 행정구역 polygon 기반 근사이며, 정확한 원형 거리 검색과 구분해서 표현한다.

## 운영 메모

- PostgreSQL identifier는 63 bytes 제한이 있으므로 제약조건과 index 이름은 필요한 경우 짧게 유지한다.
- 모든 주소/코드 식별자는 문자열이다.
- raw 테이블은 감사와 재처리용이며 앱의 단일 진실원이 아니다.
- serving 테이블은 앱 조회용 정규화 테이블이다.
- `address_code_standard`는 코드 기반 join의 canonical FK target이다.
- 법정동코드 기준 데이터 갱신은 `apps/api/app/dagster_etl/registry.py`의 `legal_dong_code_standard_quarterly` job에서 스케줄링한다.

## 현재 검증 기준선

현재 구현은 다음으로 검증했다.

- data.go.kr 법정동 CSV 다운로드와 파싱
- 임시 PostgreSQL에 법정동코드 적재
- VWorld 시도/시군구/법정동 SHP 적재
- Juso parser와 loader 테스트
- Dagster job contract 테스트

2026-04-25 기준 data.go.kr 법정동코드 관측값:

- parsed rows: 49,878
- active rows: 20,556
- deleted rows: 29,322

VWorld 경계 매칭 관측값:

- sido: 17 / 17
- sigungu: 264 / 264
- legal_dong: 5,007 / 5,007

## 상세 ETL 흐름

### data.go.kr 법정동코드 ETL

목적:

- TripMate의 행정구역 코드 기준인 `address_code_standard`를 만든다.
- 과거/폐지 코드도 FK 안전성을 위해 유지한다.

입력:

- data.go.kr `국토교통부_전국 법정동`
- 현재 구현은 페이지 HTML에서 `contentUrl`을 찾아 CSV를 다운로드한다.
- service key가 필요한 경우 query parameter `serviceKey`를 붙인다.
- 다운로드 URL과 로그에는 service key 원문을 남기지 않고 `***`로 마스킹한다.

지원 CSV 형식:

- 현재 data.go.kr 형식:
  - `법정동코드`
  - `시도명`
  - `시군구명`
  - `읍면동명`
  - `리명`
  - `순위`
  - `생성일자`
  - `삭제일자`
  - `과거법정동코드`
- legacy VWorld 법정동코드 형식:
  - `법정동코드`
  - `법정동명`
  - `폐지여부`

인코딩:

- `utf-8-sig`
- `cp949`

적재 방식:

1. CSV 전체를 읽고 필수 필드와 10자리 코드 길이를 검증한다.
2. 같은 파일 안에서 `legal_dong_code`가 중복되면 실패시킨다.
3. raw row를 `address_raw_legal_dong_code`에 `source_file_hash + row_number` 기준으로 저장한다.
4. 같은 hash의 raw row 수가 0도 아니고 전체 row 수와도 다르면 partial raw ingest로 보고 실패시킨다.
5. `address_code_standard`를 upsert한다.
6. `삭제일자`가 있거나 legacy `폐지여부=폐지`면 `is_active=false`, `is_discontinued=true`로 둔다.
7. 새 파일에 없어진 기존 코드는 삭제하지 않고 `source_status='missing_from_latest_download'`, `is_active=false`, `is_discontinued=true`로 표시한다.

왜 삭제하지 않는가:

- 여행 장소, 과거 geocoding 결과, VWorld 경계 매핑, 외부 provider cache가 과거 코드를 참조할 수 있다.
- 행정구역 개편으로 최신 주소 검색에는 나오지 않아야 하지만, 과거 여행 기록은 깨지면 안 된다.
- 그래서 신규 UI 검색에서는 inactive/deleted row를 숨기고, DB 참조 안전성은 유지한다.

### Juso 월간 도로명주소 전체분 ETL

목적:

- 앱 내 모든 실제 주소 검색/저장 기준을 구축한다.
- 도로명주소관리번호, 법정동코드, 도로명코드, 행정동코드를 문자열로 보존한다.

입력:

- 주소기반산업지원서비스 `https://business.juso.go.kr/jst/jstAddressDownload`
- 파일명 패턴: `[네자리년도][두자리월]_도로명주소 한글_전체분.zip`
- ZIP 내부 파일:
  - `rnaddrkor_*.txt`: 도로명주소 한글 전체분
  - `jibun_rnaddrkor_*.txt`: 도로명주소관리번호별 관련 지번

수집 정책:

- 매월 10일 이후 실행한다.
- 10일에 DB 여행계획 날짜가 있으면 그날은 skip한다.
- 10일 이후 여행계획이 없는 첫 날짜에 전체 ZIP을 받아 갱신한다.
- 증분 갱신은 사용하지 않고 전체 파일 기준으로 갱신한다.
- 같은 `YYYYMM` 성공 로그가 있으면 다시 갱신하지 않는다.

여행계획이 있는 날을 피하는 이유:

- 주소 serving 교체는 큰 작업이고, 여행 당일 사용자 경험에 직접 영향을 줄 수 있다.
- 여행 일정이 있는 날은 주소 DB 변동을 피하고, 다음 가능한 날짜에 업데이트한다.

파싱:

- delimiter는 `|` 또는 tab을 감지한다.
- 모든 코드 key는 문자열 그대로 유지한다.
- `rnaddrkor`는 24개 필드를 기대한다.
- `jibun_rnaddrkor`는 14개 필드를 기대한다.
- 파일명에서 `YYYYMM`을 추출한다. 없으면 실패시킨다.

도로명주소 serving 생성:

1. `AddressRawJusoRoadAddress`에 raw row를 저장한다.
2. `change_reason_code == '63'`인 폐지 주소는 serving snapshot에서 제외한다.
3. 같은 `road_address_management_no`가 여러 번 나오면 최신 `effective_date` row를 선택한다.
4. 같은 `road_address_management_no`와 같은 `effective_date`인데 내용이 다르면 충돌로 보고 실패시킨다.
5. `AddressServingJusoRoadAddress`를 전체 재구축한다.
6. Juso row에서 관측된 법정동코드 snapshot을 `address_code_standard`에 보강 upsert한다.

관련 지번 serving 생성:

1. `AddressRawJusoRelatedJibun`에 raw row를 저장한다.
2. `road_address_management_no`가 현재 `address_serving_juso_road_address`에 없으면 실패시킨다.
3. 같은 `road_address_management_no + legal_dong_code + mountain_yn + jibun_main_no + jibun_sub_no`를 unique key로 본다.
4. 같은 key의 내용이 다르면 충돌로 보고 실패시킨다.
5. `AddressServingJusoRelatedJibun`을 전체 재구축한다.

주의:

- Juso serving 테이블은 현재 snapshot 성격이다.
- 사용자 여행 장소는 Juso serving row에만 의존하면 안 된다. 주소가 삭제되거나 건물이 사라질 수 있기 때문이다.
- 따라서 장소 저장 도메인은 nullable FK와 저장 당시 주소 문자열 snapshot을 함께 가져야 한다.

### VWorld SHP 경계 ETL

목적:

- 좌표에서 법정동/시군구/시도를 찾는다.
- 현재 좌표 주변의 행정구역 목록을 찾는다.
- 지도/API 응답용 행정구역 polygon을 제공한다.

입력:

- VWorld 법정구역정보 SHP ZIP
- 자동 다운로드하지 않는다.
- 운영자가 관리자 업로드 API 또는 운영 command로 반영한다.
- ZIP 파일명으로 layer를 판정한다.

지원 파일명:

| ZIP 파일명 | layer_code | boundary_level |
| --- | --- | --- |
| `N3A_G0010000.zip` | `N3A_G0010000` | `sido` |
| `N3A_G0100000.zip` | `N3A_G0100000` | `sigungu` |
| `N3A_G0110000.zip` | `N3A_G0110000` | `legal_dong` |

SHP 필수 파일:

- `.shp`
- `.shx`
- `.dbf`
- `.prj`

DBF 필수 필드:

| 필드 | 의미 |
| --- | --- |
| `UFID` | VWorld feature id |
| `BJCD` | 행정구역 코드 |
| `NAME` | 경계명 |
| `DIVI` | 원천 분류 |
| `SCLS` | 원천 세분류 |
| `FMTA` | 원천 형상/관리 코드 |

인코딩과 좌표계:

- DBF 인코딩은 `cp949`다.
- 원본 SHP geometry는 EPSG:5179다.
- raw에는 EPSG:5179 `MULTIPOLYGON`을 그대로 저장한다.
- serving에는 EPSG:4326 `MULTIPOLYGON`으로 변환해 저장한다.

왜 raw 5179와 serving 4326을 둘 다 두는가:

- raw 5179는 원본 비교, SHP 갱신 검증, 재처리용이다.
- serving 4326은 웹 지도, API 응답, 좌표 기반 point-in-polygon에 바로 쓰기 좋다.
- 원본 좌표계를 버리고 4326만 남기면 나중에 원본 SHP와 diff 검증이 어려워진다.

적재 방식:

1. ZIP을 안전하게 해제한다. path traversal member가 있으면 실패시킨다.
2. ZIP 파일명으로 layer spec을 판정한다.
3. `.prj`에서 Korea Unified 좌표계 또는 EPSG:5179 단서를 검증한다.
4. 필수 DBF 필드를 검증한다.
5. geometry가 invalid이면 Shapely `make_valid`로 보정한다.
6. `Polygon`은 `MultiPolygon`으로 감싼다.
7. 기존 같은 layer batch를 삭제하고 새 batch를 넣는다.
8. raw boundary와 serving boundary를 함께 만든다.
9. `BJCD`와 `address_code_standard.legal_dong_code` exact match를 우선한다.
10. 세종 시도 level처럼 code table에 `3600000000`이 없고 이름으로만 맞는 legacy 상황은 시도 level에서만 이름 fallback을 허용한다.

경계 교체 정책:

- layer별 기존 batch를 삭제하고 새 batch로 교체한다.
- batch 삭제 시 raw/serving 경계는 cascade된다.
- `region_serving_boundary.address_code_standard_code`는 nullable이고 `ondelete=SET NULL`이다.
- code table 문제 때문에 경계 row 자체가 삭제되면 안 된다.

## 외부 서비스와 주소 체계 매핑

### 공통 원칙

외부 provider의 지역코드는 원칙적으로 TripMate 주소 코드와 같다고 가정하지 않는다.

매핑할 때는 다음 중 하나만 허용한다.

- provider가 Juso/법정동/시군구 코드와 명시적으로 같은 key를 제공한다.
- 좌표가 있고 VWorld 법정동 경계로 point-in-polygon 판정할 수 있다.
- provider 코드 체계가 별도이면 별도 mapping table을 둔다.

하지 않는 것:

- 주소 문자열 fuzzy matching을 기본 join 경로로 사용하지 않는다.
- 이름이 비슷하다는 이유로 휴게소/관광지/주유소를 임의 매칭하지 않는다.
- 좌표계가 확인되지 않은 provider 좌표를 실제 반경 검색에 사용하지 않는다.

### 여행 장소와 geocoding 결과

장소 저장 도메인은 아직 후속 구현이지만 주소 정책은 확정되어 있다.

저장해야 하는 것:

- 가능한 최선의 nullable FK
  - `road_address_management_no`
  - `legal_dong_code`
  - `road_name_code`
  - `administrative_dong_code`
- 저장 당시 주소 문자열 snapshot
- 저장 당시 좌표
- provider/geocoder 참조

매핑 우선순위:

1. 도로명주소관리번호가 있으면 `address_serving_juso_road_address.road_address_management_no`
2. 법정동코드가 있으면 `address_code_standard.legal_dong_code`
3. 도로명코드가 있으면 Juso 도로명주소 serving의 `road_name_code`
4. 행정동코드가 있으면 Juso 도로명주소 serving의 `administrative_dong_code`
5. 안전한 FK가 없으면 주소 문자열 snapshot만 저장하고 FK는 null

주소가 나중에 사라진 경우:

- FK가 null이거나 더 이상 active row가 아니어도 장소 자체는 조회되어야 한다.
- 신규 주소 검색에서는 비활성 주소를 숨긴다.
- 기존 장소 상세에는 저장 당시 snapshot을 표시한다.

### 좌표 → 행정구역

구현 위치:

- `apps/api/app/services/region_boundary.py`

기본 함수:

- `find_boundary_covering_point()`
  - 입력: `longitude`, `latitude`, `boundary_level`
  - 점 생성: `ST_SetSRID(ST_MakePoint(lon, lat), 4326)`
  - 판정: `ST_Covers(region_serving_boundary.geom, point)`
  - 여러 polygon이 걸리면 면적이 작은 경계를 우선한다.
- `find_boundaries_within_radius()`
  - 입력 좌표와 geometry를 EPSG:5179로 변환해 meter 단위 `ST_DWithin`을 수행한다.
  - 행정구역 polygon과 점 사이의 근접성을 보는 것이며, “주변 행정구역” 조회다.

좌표 순서:

- DB/API 내부에서는 `longitude`, `latitude` 순서로 point를 만든다.
- UI 문구는 필요하면 `lat`, `lng`를 쓰더라도 PostGIS 함수에는 `lon, lat` 순서로 넣는다.

### OpiNet 주유소/유가

OpiNet 지역코드는 Juso 법정동코드가 아니다.

예:

| 체계 | 예 |
| --- | --- |
| OpiNet 시도 | `01` |
| OpiNet 시군구 | `0101` |
| Juso 시도 | `1100000000` |
| Juso 시군구 | `1111000000` |
| Juso 법정동 | `1111010100` |

구현 테이블:

- `fuel_serving_opinet_region_code`
- `fuel_region_legal_dong_mapping`
- `fuel_serving_lowest_station`

매핑 방식:

1. OpiNet `areaCode.do`로 시도/시군구 provider code를 수집한다.
2. Juso `address_code_standard` active 시도/시군구 row를 읽는다.
3. OpiNet 지역명과 Juso 지역명을 정규화해 비교한다.
4. 후보가 하나면 `matched`, 여러 개면 `ambiguous`, 없으면 `unmatched`로 둔다.
5. matched 시군구만 전국 주기 수집 대상이 된다.

여행 장소 법정동에서 유가 region을 찾는 방식:

1. 상세 법정동코드 그대로 찾는다.
2. 없으면 시군구 코드로 축약해 찾는다.
3. 없으면 시도 코드로 축약해 찾는다.

현재 사용자 제공 값:

- 전국 일별 평균 유가: `fuel_serving_avg_price` 최신 `region_key='national'`
- 여행지 주변 최저가: 매핑된 OpiNet 시군구의 TOP 후보 중 최저가
- 여행지 주변 평균: 같은 TOP 후보의 평균
- 최저가 후보 평균: 같은 TOP 후보의 평균

중요한 표현:

- “여행지 주변”은 현재 OpiNet 시군구 기준 근사다.
- 주유소 좌표계가 확인되지 않았으므로 실제 반경 검색으로 표현하지 않는다.
- provider API 부하가 사용자 수에 비례하지 않도록 전국 시군구 전체를 주기 수집한다.

### 한국도로공사 휴게소

휴게소 데이터는 현재 주소 DB와 직접 매핑하지 않는다.

이유:

- 한국도로공사 휴게소 데이터의 안정 join key는 `serviceAreaCode2`다.
- 이 key는 Juso 법정동코드, 도로명코드, 도로명주소관리번호와 다르다.
- 현재 확정 정책은 좌표/명칭 기반 후보 매칭을 하지 않는 것이다.

구현 테이블:

- `rest_area_serving_master`
- `rest_area_serving_oil_price`
- `rest_area_serving_service`

join 기준:

- master serving PK: `svar_cd = serviceAreaCode2`
- oil/service row는 `serviceAreaCode2`가 master `svar_cd`에 있을 때만 serving row로 만든다.

FK 불일치 처리:

1. raw row는 저장한다.
2. serving row는 skip한다.
3. 별도 JSONL 로그를 남긴다.
4. job를 즉시 실패시키지 않는다.

로그 경로:

```text
<TRIPMATE_DAGSTER_LOG_DIR>/etl/rest_area_fk_mismatch/<dataset>/<run_key>.jsonl
```

휴게소 날씨:

- 휴게소 날씨 정보는 휴게소 master와 매칭하지 않는다.
- 휴게소 날씨와 master 사이에 신뢰할 join key가 없다는 전제를 유지한다.
- 좌표/명칭 기반 후보 매칭도 하지 않는다.

### 날씨와 대기질

날씨 데이터는 주소 코드와의 결합 방식이 데이터셋마다 다르다.

`weather_short_term`:

- 기상청 초단기실황/초단기예보/단기예보는 DFS 격자 `nx`, `ny` 기준이다.
- TripMate는 VWorld 시군구 경계의 `ST_PointOnSurface` 대표점을 만들고, 이를 KMA DFS 격자로 변환한다.
- mapping row는 `weather_short_term_grid_mapping`에 저장한다.
- 초기 기본은 시군구 단위다. 장소 좌표 기반 상세 격자는 후속 구현에서 추가한다.

`air_quality_station`:

- AirKorea 측정소 응답의 `dmX`, `dmY`를 smoke 기준 `dmX=위도`, `dmY=경도`로 해석한다.
- EPSG:4326 point로 보고 VWorld 법정동 경계에 `ST_Covers`를 적용한다.
- 매칭되면 `legal_dong_code`, `sigungu_code`를 저장한다.
- 매칭되지 않으면 `mapping_method='unmapped'`로 둔다.

`weather_kma_alert`:

- 기상특보/기상정보/기상속보는 지점코드와 텍스트 중심이다.
- 좌표나 주소가 없으므로 지도 마커에 표시하지 않는다.
- 법정동 FK를 붙이지 않는다.
- Telegram 알림 원천으로만 활용한다.

`weather_mid_term`:

- 중기예보 구역 seed, 주소 mapping table, raw/serving schema, loader, job를 구현했다.
- `regId`는 기상청 중기예보 API가 요구하는 예보구역코드다.
- `regId`는 단기예보 DFS 격자 `nx`, `ny`도 아니고 Juso 법정동코드도 아니다.
- 공식 중기예보 구역코드를 별도 테이블에 저장하고, TripMate 시도/시군구/법정동 코드와의 연결은 명시적 mapping table로 관리한다.
- 임의 시군구→`regId` 이름 유사도 추정은 하지 않는다.

### 기상청 추천 관광코스

CSV는 좌표를 제공하므로 주소 문자열보다 공간 판정을 우선한다.

현재 구현:

- CSV `경도(도)`를 `longitude`, `위도(도)`를 `latitude`로 저장한다.
- 좌표는 EPSG:4326으로 본다.
- VWorld 법정동 경계에 `ST_Covers`를 적용한다.
- 매칭되면 `legal_dong_code`, `sigungu_code`, `sido_code`를 저장한다.
- 매칭되지 않으면 `address_mapping_method='unmapped'`로 둔다.

주의:

- CSV의 `지역 아이디`는 10자리 코드처럼 보일 수 있지만 Juso 법정동코드와 같다고 가정하지 않는다.
- 원문 `region_id`로 보존만 한다.
- 좌표/명칭 기반 후보 매칭은 하지 않는다.

검토했지만 현재 하지 않는 것:

- VWorld reverse geocoding으로 주소 문자열 snapshot을 얻는 흐름
- reverse geocoding 결과를 Juso 도로명주소관리번호, 도로명코드, 행정동코드와 연결하는 흐름
- provider call 실패에 대한 5회 retry와 UI 알림 흐름

위 흐름은 과거에 검토했던 대안이다. 현재 KMA 관광코스는 좌표 기반 법정동 매핑만 사용하고, 상세 주소 key 매핑은 후속 작업으로 두지 않는다.

### Kakao/Naver/Google 같은 POI provider

현재 주소 DB 기준에서 후속 구현이 지켜야 할 원칙:

- provider의 장소 id와 주소 key를 혼동하지 않는다.
- 상호명, 주소, 전화번호 같은 안정 필드는 정책에 따라 지속 저장할 수 있다.
- 리뷰는 3개월 저장 후, 어떤 여행계획에도 포함되지 않은 상태로 3개월이 지나면 삭제한다.
- geocoding/reverse geocoding 결과에서 주소를 얻으면 Juso DB의 key 중 하나로 연결한다.
- 연결할 FK가 없어도 저장 당시 주소 snapshot은 반드시 보존한다.

## 검증 환경과 방식

### 공통 테스트 환경

백엔드 테스트는 WSL2 + Docker PostgreSQL/PostGIS 기준으로 실행한다.

pytest fixture 동작:

1. `TRIPMATE_TEST_ADMIN_DATABASE_URL` 또는 기본 `postgresql+psycopg://tripmate:tripmate_dev_password@localhost:55432/postgres`로 관리자 DB에 접속한다.
2. 테스트 세션마다 임시 DB `tripmate_test_<랜덤>`을 만든다.
3. Alembic `upgrade head`를 적용한다.
4. 테스트가 끝나면 임시 DB를 drop한다.
5. 각 test function 후에는 전체 테이블을 `TRUNCATE ... RESTART IDENTITY CASCADE`로 비운다.

주요 검증 명령:

```bash
wsl bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/python -m pytest"
wsl bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/python -m alembic upgrade head"
```

### 주소 parser 테스트 데이터

파일:

- `apps/api/tests/test_juso_parser.py`

테스트 목적:

- Juso TXT parser가 코드 선행 0을 잃지 않는지 확인한다.
- `|` delimiter와 tab delimiter를 모두 처리하는지 확인한다.
- 필드 수가 맞지 않으면 실패하는지 확인한다.
- 파일명에서 `YYYYMM`이 없으면 실패하는지 확인한다.

대표 도로명주소 fixture:

| 필드 | 값 |
| --- | --- |
| 도로명주소관리번호 | `1111010100100010000` |
| 법정동코드 | `0111010100` 또는 `1111010100` |
| 도로명코드 | `111100000001` |
| 행정동코드 | `0111051500` 또는 `1111051500` |
| 시도명 | `Seoul` |
| 시군구명 | `Jongno-gu` |
| 법정읍면동명 | `Cheongun-dong` |
| 도로명 | `Pirundae-ro` |
| 적용일자 | `20260410` |
| 이동사유코드 | `31` |

대표 관련 지번 fixture:

| 필드 | 값 |
| --- | --- |
| 도로명주소관리번호 | `11110101310001200009400000` |
| 법정동코드 | `1111010100` |
| 지번 | `144-3` |
| 도로명코드 | `111103100012` |
| 건물번호 | `94-0` |

### Juso snapshot loader 테스트 데이터

파일:

- `apps/api/tests/test_juso_address_dataset_loader.py`
- `apps/api/tests/test_juso_pipeline.py`

테스트 목적:

- 여러 `rnaddrkor_*.txt` 파일을 하나의 월간 snapshot으로 적재한다.
- raw row와 serving row 수가 기대와 맞는지 확인한다.
- Juso row에서 법정동코드가 `address_code_standard`에 보강되는지 확인한다.
- 관련 지번이 존재하지 않는 도로명주소관리번호를 참조하면 실패하는지 확인한다.
- ZIP 다운로드/해제/pipeline이 연결되는지 확인한다.

대표 ZIP fixture:

| ZIP 내부 파일 | row 수 | 내용 |
| --- | --- | --- |
| `rnaddrkor_seoul.txt` | 2 | 종로구 청운동, 신문로1가 |
| `rnaddrkor_busan.txt` | 1 | 부산 중구 동광동 |
| `jibun_rnaddrkor_seoul.txt` | 2 | 위 도로명주소관리번호의 관련 지번 |

기대값:

- 도로명주소 raw row: 3
- 도로명주소 serving row: 3
- 관련 지번 raw row: 2
- 관련 지번 serving row: 2
- 보강된 법정동코드 row: 3
- source file name: `202603_도로명주소 한글_전체분.zip`

### data.go.kr 법정동코드 테스트 데이터

파일:

- `apps/api/tests/test_legal_dong_code_loader.py`

대표 CSV fixture:

| 법정동코드 | 시도명 | 시군구명 | 읍면동명 | 삭제일자 | 과거법정동코드 | 기대 |
| --- | --- | --- | --- | --- | --- | --- |
| `1100000000` | 서울특별시 |  |  |  |  | `sido`, active |
| `1111000000` | 서울특별시 | 종로구 |  |  |  | `sigungu`, active |
| `1111010100` | 서울특별시 | 종로구 | 청운동 |  |  | `legal_dong`, active |
| `1111010200` | 서울특별시 | 종로구 | 신교동 | `2024-01-01` | `1111010199` | inactive/deleted |
| `3611000000` | 세종특별자치시 |  |  |  |  | 세종 특수 케이스 |
| `3611010100` | 세종특별자치시 |  | 반곡동 |  |  | 세종 법정동 |

검증 항목:

- row 6건 파싱
- active 5건, discontinued 1건
- `source_provider='data_go_legal_dong'`
- 삭제일자와 과거법정동코드 보존
- 세종처럼 시군구명이 비어 있는 row 처리
- legacy VWorld ZIP에서 사라진 기존 코드를 `missing_from_latest_download`로 유지
- ZIP path traversal 차단
- service key 다운로드 URL 마스킹

### VWorld SHP 테스트 데이터

파일:

- `apps/api/tests/test_vworld_boundary_loader.py`
- `apps/api/tests/test_vworld_boundary_cli.py`
- `apps/api/tests/test_region_api.py`

테스트 SHP 생성 방식:

- pyshp로 테스트용 polygon SHP를 만든다.
- DBF 인코딩은 `cp949`로 둔다.
- `.prj`는 EPSG:5179 Korea Unified 좌표계를 쓴다.
- 테스트 polygon은 WGS84 사각형을 EPSG:5179로 변환해서 만든다.

대표 polygon:

| 좌표계 | 값 |
| --- | --- |
| WGS84 좌상/우하 범위 | 대략 `126.9680~126.9740`, `37.5780~37.5830` |
| 테스트 점 | `longitude=126.9707`, `latitude=37.5804` |
| BJCD | `1111010100` |
| NAME | `청운동` |

검증 항목:

- raw geometry SRID가 5179인지 확인
- serving geometry SRID가 4326인지 확인
- `BJCD=1111010100`이 `address_code_standard.legal_dong_code=1111010100`과 exact match 되는지 확인
- `sido_code=1100000000`, `sigungu_code=1111000000` 파생 확인
- `find_boundary_covering_point()`가 테스트 점을 청운동으로 찾는지 확인
- `find_boundaries_within_radius()`가 반경 500m에서 해당 법정동을 찾는지 확인
- 알 수 없는 ZIP 파일명은 거부
- ZIP path traversal 차단
- 세종 시도 boundary의 이름 fallback 처리

실데이터 관측 기준:

- sido: 17 / 17 matched
- sigungu: 264 / 264 matched
- legal_dong: 5,007 / 5,007 matched

### OpiNet 주소 매핑 테스트 데이터

파일:

- `apps/api/tests/test_opinet_fuel_loader.py`

Fake OpiNet region:

| OpiNet code | 이름 | 기대 Juso code |
| --- | --- | --- |
| `01` | 서울 | `1100000000` |
| `0101` | 종로구 | `1111000000` |

Fake OpiNet 평균가:

| PRODCD | 내부 fuel_type | PRICE | TRADE_DT |
| --- | --- | --- | --- |
| `B027` | `gasoline` | `1674.12` | `20260426` |
| `B034` | `premium_gasoline` | `1890` | `20260426` |
| `C004` | 미지원 | `1200` | `20260426` |

Fake OpiNet 최저가 주유소:

| UNI_ID | 이름 | PRICE | 주소 |
| --- | --- | --- | --- |
| `A0001` | 종로셀프 | `1600` | 서울 종로구 청운동 1 |
| `A0002` | 종로주유소 | `1610` | 서울 종로구 청운동 2 |

검증 항목:

- OpiNet `01`과 `0101`이 각각 Juso 시도/시군구에 매핑된다.
- 상세 법정동 `1111010100`에서 OpiNet 시군구 `0101`을 찾는다.
- 미지원 유종은 skipped row로 처리한다.
- `trade_date=20260426`은 KST 00:00 timestamp로 저장된다.
- 주변 요약은 최저가 `1600`, 후보 평균 `1605`, 전국 평균 `1674.12`를 반환한다.
- unmatched 또는 inactive 시군구는 주기 수집 대상에서 제외한다.

### 휴게소 FK 테스트 데이터

파일:

- `apps/api/tests/test_rest_area_loader.py`

대표 master:

| serviceAreaCode | serviceAreaCode2 | 이름 |
| --- | --- | --- |
| `A00001` | `000001` | 서울만남(부산)휴게소 |
| `A99999` | 없음 또는 미사용 | 코드없는휴게소 |

대표 oil/service:

| dataset | serviceAreaCode2 | 기대 |
| --- | --- | --- |
| oil | `000001` | serving 생성 |
| oil | `999999` | raw 저장, serving skip, JSONL 로그 |
| service | `000001` | 편의시설 row 생성 |
| service | `999999` | raw 저장, serving skip, JSONL 로그 |

검증 항목:

- master duplicate join code는 serving row 1개로 병합한다.
- oil FK mismatch는 JSONL 로그에 `missing_rest_area_master_fk`로 남긴다.
- service FK mismatch도 JSONL 로그에 남긴다.
- 하루 2회 oil snapshot은 `collected_at`이 다르면 별도 row로 보존한다.

주소 체계 관점의 결론:

- 휴게소는 현재 Juso 주소 DB와 연결하지 않는다.
- `serviceAreaCode2` 내부 join만 신뢰한다.

### 날씨/대기질 매핑 테스트 데이터

파일:

- `apps/api/tests/test_weather_loader.py`
- `apps/api/tests/test_kma_grid.py`

Fake KMA 초단기실황:

| 필드 | 값 |
| --- | --- |
| nx, ny | `60`, `127` |
| baseDate/baseTime | `20260426` / `1200` |
| category | `T1H`, `REH` |
| obsrValue | `21.4`, `48` |

Fake AirKorea 측정소:

| 필드 | 값 |
| --- | --- |
| stationName | 청운효자동 |
| dmX | `37.580400` |
| dmY | `126.970700` |
| 기대 법정동 | `1111010100` |

검증 항목:

- KMA 발표시각이 KST datetime으로 저장된다.
- 시군구 경계 대표점에서 KMA DFS grid를 만든다.
- AirKorea 측정소 좌표가 법정동 경계에 매핑된다.
- 기상특보 지점코드 `108`, `109`가 저장된다.
- `NO_DATA` 응답은 오류가 아니라 empty result로 처리한다.

### 기상청 관광코스 테스트 데이터

파일:

- `apps/api/tests/test_kma_tour_course_loader.py`

CSV fixture:

```csv
테마분류,코스 아이디,관광지 아이디,지역 아이디,관광지명,경도(도),위도(도),코스순서,이동시간,실내구분,테마명
TH05,177,17703,4822051000,(통영)세병관(통제영지),128.423238,34.847749,3,2,실외,종교/역사/전통
TH05,177,17704,4822051000,(통영)충렬사,128.417847,34.846626,4,3,실외,종교/역사/전통
```

검증 항목:

- `cp949` decoding
- ZIP 안의 첫 CSV 선택
- 같은 파일 hash 재실행 시 기존 같은 hash row 삭제 후 재적재
- `TH05`를 `history_tradition`으로 매핑
- `경도(도)`를 `longitude`, `위도(도)`를 `latitude`로 저장
- 매핑 경계가 없는 테스트에서는 `address_mapping_method='unmapped'`
- `marker_source_type='kma_recommended_tour_course'`

### 모델/마이그레이션/시간대 검증

파일:

- `apps/api/tests/test_model_metadata.py`
- `apps/api/tests/test_migration_contract.py`
- `apps/api/tests/test_timezone_policy.py`

검증 항목:

- 주소/경계/유가/휴게소/날씨 관련 모델이 metadata에 등록되어 있다.
- ETL timestamp 컬럼은 timezone-aware `DateTime(timezone=True)`다.
- 저장용 기본 시각은 KST다.
- PostgreSQL 앱 세션은 `SHOW TIME ZONE = Asia/Seoul`이다.
- Alembic migration 문자열에 핵심 테이블/제약이 존재한다.

## 후속 구현 시 반드시 확인할 것

주소 도메인:

- 여행 장소 테이블에 nullable 주소 FK와 저장 당시 주소 snapshot을 모두 둔다.
- FK가 삭제/비활성/미매핑이어도 기존 장소 조회가 깨지지 않게 한다.
- 신규 UI 검색에서는 폐지/비활성 주소를 숨긴다.

관리자 업로드:

- VWorld SHP 관리자 업로드 API를 만들 때도 ZIP 파일명 기반 layer 판정을 유지한다.
- 업로드 전 `.shp/.shx/.dbf/.prj` 존재 여부와 `.prj` 좌표계를 검증한다.
- DBF 인코딩은 cp949를 기본값으로 둔다.

외부 provider:

- provider code를 Juso code로 착각하지 않는다.
- 좌표가 있으면 경계 기반 판정을 우선한다.
- 주소 문자열 fuzzy matching은 마지막 수단으로도 기본 구현하지 않는다. 필요하면 별도 ADR을 작성한다.
- 실제 반경 검색과 행정구역 기반 근사 리포트를 UI에서 구분한다.

운영:

- 주소 관련 Docker/test 명령은 WSL2에서 실행한다.
- 스키마 변경은 Alembic migration으로만 반영한다.
- raw/serving 교체 작업은 ETL run log와 함께 남긴다.
- 반복 실패 로그와 FK mismatch 로그는 운영자가 삭제하기 전까지 보관한다.
