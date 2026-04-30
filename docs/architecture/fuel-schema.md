# 유가 데이터 스키마

이 문서는 OpiNet 유가 데이터 적재 스키마의 기준이다. 데이터 출처, 주기, 저장 정책의 단일 기준은 `docs/data-sources.md`를 따른다.

## 범위

- provider: 한국석유공사 OpiNet
- 구현 데이터셋:
  - `fuel_region_code`: OpiNet 지역코드
  - `fuel_avg_price`: 전국 일별 평균 유가
- `fuel_lowest_station`: OpiNet 시군구 지역별 최저가 주유소 후보
- 내부 유종 enum:
  - `gasoline`
  - `premium_gasoline`
  - `diesel`
  - `lpg`
- 가격 단위: `KRW_PER_LITER`

## 테이블

### `fuel_raw_opinet_region_code`

OpiNet `areaCode.do` 응답 원문을 보존한다.

주요 컬럼:

- `provider_region_code`: OpiNet 지역코드
- `provider_region_name`: OpiNet 지역명
- `region_level`: `sido` 또는 `sigungu`
- `parent_provider_region_code`: 시군구 행의 상위 시도 OpiNet 코드
- `raw_payload`: provider 응답 row 전체
- `response_hash`
- `collected_at`

### `fuel_serving_opinet_region_code`

앱 조회와 다른 유가 테이블 join에 쓰는 OpiNet 지역코드 serving 테이블이다.

주요 컬럼:

- PK: `provider_region_code`
- `address_code_standard_code`: `address_code_standard.legal_dong_code` FK, nullable
- `mapping_status`: `matched`, `unmatched`, `ambiguous`
- `mapping_source`: 현재는 이름 기반 자동 매핑
- `raw_payload`
- `is_active`

`address_code_standard_code`는 nullable이다. OpiNet 코드가 행정구역 개편이나 provider 명칭 차이 때문에 Juso 기준 코드와 매칭되지 않아도 provider code 자체는 보존한다.

### `fuel_region_legal_dong_mapping`

OpiNet region code와 Juso 법정동코드 기준 테이블 사이의 별도 매핑 이력을 저장한다.

주요 컬럼:

- `provider_region_code`: `fuel_serving_opinet_region_code.provider_region_code` FK
- `legal_dong_code`: `address_code_standard.legal_dong_code` FK, nullable
- `mapping_status`
- `mapping_source`
- `confidence`
- `notes`

현재 자동 매핑은 시도/시군구 이름을 정규화해 수행한다. 같은 이름 후보가 중복 컬럼에서 반복되어도 같은 `legal_dong_code` 기준으로 dedupe한다.

### `fuel_raw_avg_price`

OpiNet `avgAllPrice.do` 평균가 응답 원문을 저장한다.

주요 컬럼:

- `trade_date`: provider 원천 날짜. 원천에 없으면 raw에서는 null 가능
- `timestamp`: 기준시각. `trade_date`가 있으면 KST 00:00
- `provider_fuel_code`
- `provider_fuel_name`
- `fuel_type`
- `price`
- `diff`
- `raw_payload`
- `response_hash`
- `collected_at`

### `fuel_serving_avg_price`

사용자에게 보여줄 전국 일별 평균가 serving 테이블이다.

주요 컬럼:

- unique: `region_key`, `trade_date`, `fuel_type`
- `region_key`: 현재 `national`
- `trade_date`: `YYYYMMDD`, nullable 아님
- `timestamp`
- `fuel_type`
- `provider_fuel_code`
- `provider_fuel_name`
- `price`
- `diff`
- `raw_payload`

현재 OpiNet 평균가 구현은 전국 평균가만 저장한다. 지역별 평균가가 필요하면 별도 endpoint 또는 자체 집계 정책을 결정해야 한다.

### `fuel_raw_lowest_station`

OpiNet `lowTop10.do` 최저가 주유소 후보 응답 원문을 저장한다.

주요 컬럼:

- `provider_region_code`
- `legal_dong_code`: 매핑된 시군구 법정동코드, nullable
- `timestamp`: 수집 시각
- `fuel_type`
- `station_id`
- `station_name`
- `price`
- `poll_div_code`
- `van_address`
- `road_address`
- `gis_x`
- `gis_y`
- `raw_payload`
- `response_hash`
- `collected_at`

### `fuel_serving_lowest_station`

사용자에게 보여줄 지역별 최저가 주유소 후보 serving 테이블이다.

주요 컬럼:

- unique: `provider_region_code`, `fuel_type`, `station_id`, `timestamp`
- `legal_dong_code`: `address_code_standard.legal_dong_code` FK, nullable
- `station_id`
- `station_name`
- `price`
- `gis_x`
- `gis_y`
- `raw_payload`

`station_id`는 `UNI_ID`를 우선 사용한다. 없으면 `OS_NM`, `VAN_ADR`, `NEW_ADR`, row hash 순서로 fallback한다.

## 주소 DB와의 관계

OpiNet 지역코드는 법정동코드가 아니다. 따라서 OpiNet 코드를 `address_code_standard`의 PK처럼 취급하지 않는다.

연결 규칙:

1. `fuel_region_code` 적재 시 OpiNet 시도/시군구명을 Juso 시도/시군구명과 매핑한다.
2. 매핑된 코드는 `address_code_standard.legal_dong_code`를 참조한다.
3. 여행 장소가 법정동 상세 코드만 갖고 있으면 `legal_dong_code → sigungu_code → sido_code` 순서로 OpiNet region code를 찾는다.
4. 매핑 실패 또는 모호한 OpiNet code는 provider 원문과 serving row를 보존하되 앱 join에는 사용하지 않는다.

## 사용자 제공 값

- 일별 평균 유가: `fuel_serving_avg_price`의 최신 `region_key = national` 행
- 여행지 주변 최저가: 여행 장소 법정동코드에서 찾은 OpiNet 시군구 region의 최신 `fuel_serving_lowest_station` 최저값
- 여행지 주변 평균: 같은 최신 TOP 후보들의 평균
- 최저가 후보 평균: 같은 최신 TOP 후보들의 평균

`여행지 주변 평균`과 `최저가 후보 평균`은 같은 값을 가리킨다. 실제 반경 평균이나 지역 전체 평균가가 아니라 OpiNet 시군구 최저가 TOP 후보 평균이다. UI에서는 두 라벨을 함께 표기한다.

## 남은 결정

- 사라진 OpiNet region code의 비활성화 정책과 기존 여행 장소 cache 유지 기간을 확정한다.
