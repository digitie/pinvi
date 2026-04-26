# OpiNet 지역코드와 시군구 코드 매핑

이 문서는 OpiNet 유가 API의 provider 지역코드와 TripMate 주소 기준 코드 사이의 관계를 설명한다. 구현 기준은 `apps/api/app/etl/opinet/loader.py`와 `docs/architecture/fuel-schema.md`다.

## 핵심 결론

OpiNet 지역코드는 Juso 법정동코드가 아니다. 따라서 OpiNet 지역코드를 `address_code_standard.legal_dong_code`처럼 PK/FK 기준으로 직접 쓰면 안 된다.

TripMate는 다음 구조로 분리한다.

| 구분 | 예 | 의미 | 저장 위치 |
| --- | --- | --- | --- |
| OpiNet 시도 코드 | `01` | OpiNet provider의 시도 조회 코드 | `fuel_serving_opinet_region_code.provider_region_code` |
| OpiNet 시군구 코드 | `0101` | OpiNet provider의 시군구 조회 코드 | `fuel_serving_opinet_region_code.provider_region_code` |
| Juso 시도 코드 | `1100000000` | TripMate 주소 기준 시도 코드 | `address_code_standard.legal_dong_code` |
| Juso 시군구 코드 | `1111000000` | TripMate 주소 기준 시군구 코드 | `address_code_standard.legal_dong_code` |
| Juso 법정동 코드 | `1111010100` | TripMate 장소/주소의 상세 법정동 코드 | `address_code_standard.legal_dong_code` |

## 왜 별도 매핑이 필요한가

OpiNet API 조회에는 OpiNet provider code가 필요하다.

- `areaCode.do`: OpiNet 지역코드 목록
- `lowTop10.do`: `area=<OpiNet region code>`로 지역별 최저가 후보 조회

반면 TripMate의 주소와 장소는 Juso 기준 법정동코드 체계를 사용한다.

- 주소 DB의 기준 PK는 `address_code_standard.legal_dong_code`
- 여행 장소는 좌표 또는 주소에서 Juso 법정동코드로 귀속된다.
- 다른 데이터셋과의 join도 Juso 법정동/시군구/시도 코드를 기준으로 한다.

두 코드 체계는 숫자 길이와 값 체계가 모두 다르므로 직접 비교하지 않는다.

## 테이블 역할

### `fuel_serving_opinet_region_code`

OpiNet provider region code의 serving 기준 테이블이다.

중요 컬럼:

- `provider_region_code`: OpiNet 코드. 앱이 OpiNet API를 다시 호출할 때 사용한다.
- `provider_region_name`: OpiNet 지역명.
- `region_level`: `sido` 또는 `sigungu`.
- `parent_provider_region_code`: 시군구 코드의 상위 OpiNet 시도 코드.
- `address_code_standard_code`: 매핑된 Juso 시도/시군구 코드. nullable.
- `mapping_status`: `matched`, `unmatched`, `ambiguous`.
- `mapping_source`: 현재는 이름 기반 자동 매핑.
- `is_active`: 주기 수집 대상 여부.

### `fuel_region_legal_dong_mapping`

OpiNet region code와 Juso 기준 코드의 매핑 상태를 추적하는 보조 테이블이다.

중요 컬럼:

- `provider_region_code`
- `provider_region_name`
- `region_level`
- `legal_dong_code`: Juso 코드. 이름은 legacy지만 시도/시군구 코드도 저장한다.
- `mapping_source`
- `mapping_status`
- `confidence`
- `notes`

## 매핑 생성 방식

`fuel_region_code` ETL은 다음 순서로 동작한다.

1. OpiNet `areaCode.do`를 `area` 없이 호출해 시도 코드를 얻는다.
2. 각 OpiNet 시도 코드를 `area` 파라미터로 다시 호출해 시군구 코드를 얻는다.
3. Juso `address_code_standard`의 active 시도/시군구 행을 읽는다.
4. OpiNet 지역명과 Juso 지역명을 공백 제거 및 약칭 보정 후 비교한다.
5. 시도는 이름만으로 매핑한다.
6. 시군구는 상위 시도 매핑이 성공한 경우에만, 같은 Juso 시도 안에서 시군구명을 비교한다.
7. 후보가 1개면 `matched`, 2개 이상이면 `ambiguous`, 없으면 `unmatched`로 저장한다.

이름 인덱스는 같은 Juso 코드가 `code_name`, `sido_name`, `full_legal_dong_name`에 반복되어도 같은 `legal_dong_code` 기준으로 dedupe한다. 이 처리가 없으면 하나의 시도 행이 후보 여러 개로 보이는 문제가 생긴다.

## 장소 법정동에서 OpiNet region 찾기

여행 장소가 상세 법정동코드만 갖고 있을 수 있다. 예를 들어 `1111010100`은 서울특별시 종로구의 법정동 코드다.

이때 OpiNet 조회 코드는 다음 우선순위로 찾는다.

1. 상세 법정동코드 그대로: `1111010100`
2. 시군구 코드로 축약: `1111000000`
3. 시도 코드로 축약: `1100000000`

현재 OpiNet 매핑은 시도/시군구 수준이므로 보통 2번에서 매칭된다.

예:

| 입력 | 후보 | 결과 |
| --- | --- | --- |
| `1111010100` | `1111010100 → 1111000000 → 1100000000` | OpiNet `0101` |

## 주기 수집 대상

`fuel_lowest_station`은 사용자 요청 시 on-demand 호출하지 않는다. 사용자 수가 늘수록 provider API call이 함께 늘어나는 구조를 피하기 위해, 매핑된 전국 시군구 전체를 Airflow가 주기 수집한다.

수집 대상 조건:

- `region_level = sigungu`
- `mapping_status = matched`
- `address_code_standard_code IS NOT NULL`
- `is_active = true`

이 조건은 `list_opinet_sigungu_region_codes_for_periodic_collection()`에서 관리한다.

## 사용자 표시 정책

TripMate의 “여행지 주변 유가”는 실제 반경 평균이 아니다. OpiNet 시군구 기준 근사다.

- 여행지 주변 최저가: 해당 시군구 OpiNet region의 TOP 후보 중 최저가
- 여행지 주변 평균: 같은 TOP 후보의 평균
- 최저가 후보 평균: 같은 TOP 후보의 평균

`주변 평균`과 `최저가 후보 평균`은 같은 값이다. UI에서는 둘 다 표기해 사용자가 이 값이 최저가 후보군의 평균임을 이해할 수 있게 한다.

## 실패와 예외 처리

- OpiNet region code가 Juso 코드와 매핑되지 않아도 raw/serving provider row는 보존한다.
- `unmatched` 또는 `ambiguous` row는 앱 join과 주기 최저가 수집 대상에서 제외한다.
- 행정구역 개편으로 OpiNet 코드가 사라지거나 이름이 바뀌는 경우 `is_active`와 mapping status 정책을 별도로 확정해야 한다.
- OpiNet 인증키는 `TRIPMATE_OPINET_API_KEY`로 주입하고 로그에는 원문을 남기지 않는다.

## 테스트 기준

현재 자동 테스트는 다음을 검증한다.

- OpiNet `01 서울`이 Juso `1100000000`에 매핑된다.
- OpiNet `0101 종로구`가 Juso `1111000000`에 매핑된다.
- 상세 법정동 `1111010100`은 시군구 후보를 통해 OpiNet `0101`로 해석된다.
- 주기 수집 대상은 matched/active 시군구만 포함한다.
- unmatched/inactive/provider 시도 row는 최저가 주기 수집 대상에서 제외된다.
