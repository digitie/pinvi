# 휴게소 데이터 스키마

이 문서는 한국도로공사 휴게소 데이터 적재 스키마의 기준이다. 데이터 출처와 주기는 `docs/data-sources.md`를 따른다.

## 범위

구현 데이터셋:

- `rest_area_master`: 휴게소 기본정보
- `rest_area_oil_price`: 휴게소 주유소 가격/업체 현황
- `rest_area_svcs`: 휴게소 편의시설 현황

provider:

- 한국도로공사 OpenAPI
- 인증키 환경변수: `TRIPMATE_EXPRESSWAY_API_KEY`
- 인증 query parameter: `key`

## 코드 기준

TripMate 휴게소 join key는 `serviceAreaCode2`다. serving master에서는 이 값을 `svar_cd`로 저장한다.

한국도로공사 응답에는 `serviceAreaCode`와 `serviceAreaCode2`가 함께 올 수 있다.

- `serviceAreaCode`: provider의 서비스/시설 코드. 예: `A00001`, `B00001`
- `serviceAreaCode2`: 휴게소 join에 사용하는 내부 코드. 예: `000001`

`rest_area_oil_price`와 `rest_area_svcs`는 `serviceAreaCode2`를 `rest_area_serving_master.svar_cd`와 연결한다. 불일치하면 raw는 저장하고 serving row는 skip한다.

실제 master 응답에는 같은 `serviceAreaCode2`가 여러 방향 또는 provider 시설 코드로 중복 등장할 수 있다. 이 경우 raw row는 모두 보존하고, serving master는 `svar_cd` 1개 row로 병합한다. `provider_service_area_code`, `direction`처럼 값이 다른 문자열 필드는 `|`로 합쳐 저장하고, `raw_payload`에는 병합된 provider row 목록을 남긴다.

## 테이블

### `rest_area_raw_master`

휴게소 기본정보 provider row 전체를 저장한다.

주요 컬럼:

- `provider`
- `endpoint`
- `source_api_id`
- `source_key`
- `source_snapshot_date`
- `raw_payload`
- `response_hash`
- `collected_at`

### `rest_area_serving_master`

앱 조회와 다른 휴게소 데이터 FK 기준으로 쓰는 테이블이다.

주요 컬럼:

- PK: `svar_cd`
- `provider_service_area_code`
- `name`
- `direction`
- `route_code`
- `route_name`
- `address`
- `brand`
- `convenience_raw`
- `phone`
- `maintenance_yn`
- `truck_sa_yn`
- `representative_food`
- `raw_payload`
- `source_snapshot_date`
- `is_active`

좌표 컬럼 `lon`, `lat`은 provider가 좌표를 제공하는 경우에만 채운다.

### `rest_area_raw_oil_price`

휴게소 주유소 가격/업체 provider row 전체를 저장한다.

### `rest_area_serving_oil_price`

휴게소 주유소 가격을 유종별 row로 정규화한다.

주요 컬럼:

- FK: `svar_cd → rest_area_serving_master.svar_cd`
- unique: `svar_cd`, `provider_fuel_code`, `collected_at`
- `station_name`
- `oil_company`
- `lpg_yn`
- `provider_fuel_code`
- `provider_fuel_name`
- `fuel_type`
- `price_per_liter_krw`
- `price_at`
- `price_time_source`
- `price_unit`
- `raw_payload`

현재 provider 응답은 가격 기준시각을 별도로 주지 않으므로 `price_at = collected_at`, `price_time_source = collected_at`으로 저장한다. 유가 job는 하루 2회 실행되므로 serving row의 중복 기준은 날짜가 아니라 수집 시각(`collected_at`)이다. 같은 날 오전/오후 수집분은 서로 다른 스냅샷으로 보존하고, 같은 Dagster logical timestamp 재시도만 같은 스냅샷으로 갱신한다.

유종 매핑:

| provider field | provider name | fuel_type |
| --- | --- | --- |
| `gasolinePrice` | 휘발유 | `gasoline` |
| `diselPrice` | 경유 | `diesel` |
| `lpgPrice` | LPG | `lpg` |

provider field의 `diselPrice` 오탈자는 원문 field명을 그대로 보존한다.

### `rest_area_raw_service`

휴게소 편의시설 provider row 전체를 저장한다.

### `rest_area_serving_service`

`convenience` 문자열을 `|` 기준으로 나누어 편의시설별 row로 저장한다.

주요 컬럼:

- FK: `svar_cd → rest_area_serving_master.svar_cd`
- unique: `svar_cd`, `provider_service_code`, `source_snapshot_date`
- `provider_service_name`
- `display_name`
- `available`
- `quantity`
- `status`
- `raw_payload`

현재 provider는 편의시설별 별도 코드가 아니라 표시명을 제공하므로 `provider_service_code`는 편의시설명을 정규화한 값이다.

## FK 불일치 처리

`rest_area_oil_price`와 `rest_area_svcs`에서 `serviceAreaCode2`가 master에 없으면 다음처럼 처리한다.

1. raw row는 반드시 저장한다.
2. serving row는 생성하지 않는다.
3. JSONL 로그를 남긴다.
4. skip count를 ETL result에 포함한다.
5. 기본적으로 job를 즉시 실패시키지 않는다.

로그 경로:

```text
<TRIPMATE_DAGSTER_LOG_DIR>/etl/rest_area_fk_mismatch/<dataset>/<run_key>.jsonl
```

기본 로컬 경로:

```text
.tmp/dagster-logs/etl/rest_area_fk_mismatch/
```

로그 row에는 최소한 `dataset`, `source_endpoint`, `source_key`, `serviceAreaCode2`, `collected_at`, `reason`을 남긴다.

## Dagster job

- `rest_area_master_monthly`: 월 1회 휴게소 master 수집
- `rest_area_oil_price_daily`: 하루 2회 휴게소 주유소 가격 수집. Dagster logical timestamp를 `collected_at`으로 넘겨 retry 중복과 하루 2회 스냅샷 보존을 동시에 만족시킨다.
- `rest_area_service_monthly`: 월 1회 편의시설 수집

`rest_area_oil_price_daily`와 `rest_area_service_monthly`는 master 적재가 선행되어야 의미 있는 serving row를 만들 수 있다.

## 운영 주의사항

- 한국도로공사 인증키 query parameter 이름은 `key`다. 실패 로그와 Telegram outbox에 원문을 남기지 않는다.
- `serviceAreaCode2`가 실제 provider 데이터에서 비어 있거나 master와 다를 수 있다. 이 경우 임의 매칭하지 않는다.
- 2026-04-26 live smoke 기준 `business/serviceAreaRoute` master는 휴게소 코드 일부와 중복 방향 row를 반환했고, `business/curStateStation` 주유소 row의 `serviceAreaCode2`는 master와 교집합이 없었다. 현재 정책은 이름/좌표 기반 후보 매칭을 하지 않고 raw 저장 + serving skip + JSONL 로그다. 유가 serving 제공이 필요하면 한국도로공사 `apiId=0615` 코드 source에서 주유소 코드까지 포함한 master endpoint를 확인하거나, 별도 code-family mapping 정책을 새로 결정해야 한다.
- FK mismatch는 반복적으로 발생할 수 있으므로 로그를 삭제하기 전까지 보관한다.
- 신규 편의시설명은 저장을 막지 않고 `display_name = provider_service_name`으로 표시한다.
