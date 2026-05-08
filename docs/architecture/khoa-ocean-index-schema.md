# KHOA 해양 체험지수 스키마

## 목적

이 문서는 data.go.kr gateway로 제공되는 국립해양조사원(KHOA) 생활해양예보 체험지수 중 TripMate가 해수욕장 외 별도 도메인으로 저장하는 데이터를 설명한다.

현재 구현 대상:

- `khoa_mudflat_index_forecast`: 갯벌체험지수
- `khoa_sea_split_index_forecast`: 바다갈라짐 체험지수

해수욕지수(`khoa_beach_index_forecast`)는 이미 해수욕장 통합 도메인(`beach_*`)에 저장하므로 이 문서의 `ocean_activity_index_*` 테이블에 중복 저장하지 않는다.

## 출처와 endpoint

| dataset key | data.go.kr 설명 URL | endpoint | 갱신 | TripMate 수집 |
| --- | --- | --- | --- | --- |
| `khoa_mudflat_index_forecast` | `https://www.data.go.kr/data/15142489/openapi.do` | `http://apis.data.go.kr/1192136/fcstMudflatv2` | 실시간 | 매일 06:40, 18:40 |
| `khoa_sea_split_index_forecast` | `https://www.data.go.kr/data/15142485/openapi.do` | `http://apis.data.go.kr/1192136/fcstSeaSplitv2` | 실시간 | 매일 06:50, 18:50 |

관련 공지에 따라 KHOA 생활해양예보지수 v2 endpoint는 `apis.data.go.kr/1192136/*v2` gateway를 사용한다. 해수욕지수도 기존 KHOA 직접 URL 대신 `http://apis.data.go.kr/1192136/fcstBeachv2`로 맞췄다.

인증키:

- `TRIPMATE_KHOA_API_KEY`가 있으면 우선 사용한다.
- 없으면 사용자가 제공한 data.go.kr 통합 인증키인 `TRIPMATE_DATA_GO_SERVICE_KEY`를 fallback으로 사용한다.
- request params 저장 시 `serviceKey`는 항상 `***`로 마스킹한다.
- KHOA 지수계열은 data.go.kr gateway가 인코딩된 인증키를 기대할 수 있으므로, 구현에서는 `serviceKey`만 별도 query string으로 구성한다. 이미 `%3D`처럼 percent-encoding된 키는 이중 인코딩하지 않고, decoded key는 전송 직전에 URL encoding한다.

운영 검증 메모:

- 2026-04-30 기준 `fcstBeachv2`, `fcstMudflatv2`, `fcstSeaSplitv2`는 `TRIPMATE_KHOA_API_KEY`와 `TRIPMATE_DATA_GO_SERVICE_KEY` 양쪽 모두 HTTP 500을 반환했다.
- `reqDate=20260430`, `reqDate=20260429`, `reqDate` 미지정 요청도 모두 동일하게 HTTP 500이었다.
- 2026-04-30 22:36 KST에 `TRIPMATE_KHOA_API_KEY`를 명시적으로 percent-encoded query 값으로 만들어 재시도했으나 세 endpoint 모두 HTTP 500 `Unexpected errors`를 반환했다.
- 공공데이터포털 명세와 2025-12-29 변경 공지의 endpoint/`reqDate=YYYYMMDD` 형식은 현재 구현과 일치한다. 따라서 현 상태는 `SERVICE KEY IS NOT REGISTERED`가 아니라 provider gateway 오류 또는 활용 승인 상태 문제로 기록한다.

## 수집 주기 결정

포털의 업데이트 주기는 실시간이고 개발계정 트래픽은 10,000건이다. 하지만 두 지수는 사용자 화면 요청마다 직접 조회할 데이터가 아니라 지도/여행 계획에 곁들일 예보성 데이터다.

TripMate 기본값은 하루 2회다.

- 해수욕지수: 06:30, 18:30
- 갯벌체험지수: 06:40, 18:40
- 바다갈라짐 체험지수: 06:50, 18:50

이렇게 잡은 이유:

- KHOA 생활해양예보지수는 요청일자(`reqDate`) 기준 예보 row를 반환하므로, 같은 날짜에 과도하게 자주 호출해도 사용자 가치가 크지 않다.
- 하루 2회면 오전/오후 계획 작성에는 충분하고, 세 API 합산 호출량도 매우 낮아 quota 여유가 크다.
- 향후 실제 서비스에서 갯벌/바다갈라짐 상세 화면을 자주 사용하게 되면 dataset별 설정 파일에서 주기를 4회/일 등으로 조정한다.

## DB 테이블

### `ocean_activity_index_locations`

체험지수의 장소 기준 테이블이다.

주요 컬럼:

- `provider`: `khoa`
- `provider_dataset_key`: `khoa_mudflat_index_forecast` 또는 `khoa_sea_split_index_forecast`
- `provider_location_id`: `placeCode`가 있으면 사용하고, 없으면 dataset/name/좌표 기반 hash를 사용한다.
- `provider_place_code`: provider가 주는 `placeCode`
- `display_name`, `normalized_name`
- `longitude`, `latitude`, `geom geometry(Point, 4326)`
- `legal_dong_code`, `sigungu_code`, `sido_code`
- `address_snapshot`, `address_mapping_method`
- `source_specific_attributes`
- `collected_at`, `is_active`

주소/좌표 매핑:

- 좌표가 있으면 V-WORLD 법정동 serving boundary에 `ST_Covers`를 수행한다.
- 바닷가/갯벌 좌표가 육지 polygon 밖에 걸릴 수 있어 5km 이내 nearest boundary를 보조로 사용한다.
- 도로명주소코드와 도로명주소관리번호는 제공되지 않으므로 생성하지 않는다.
- V-WORLD reverse geocoding으로 상세 주소를 만들었던 대안은 검토했지만 현재 구현하지 않는다.

### `ocean_activity_index_source_records`

원천 응답 row의 raw snapshot을 보존한다.

- unique: `provider + dataset_key + source_record_id + response_hash`
- `request_params`는 인증키를 마스킹한다.
- `raw_payload`는 provider 응답 row 전체다.
- raw는 재처리와 schema drift 확인을 위해 보관한다.

### `ocean_activity_index_forecasts`

체험지수 예보 row다.

주요 컬럼:

- `location_id`
- `source_record_id`
- `provider_dataset_key`
- `provider_place_code`
- `forecast_date`
- `forecast_slot`
- `activity_time_key`
- `activity_time_text`
- `activity_start_at`, `activity_end_at`
- `weather`
- `air_temperature_c`
- `wind_speed_ms`
- `index_score`
- `total_index`
- `grade`
- `raw_payload`
- `collected_at`, `is_active`

unique 기준:

`provider + provider_dataset_key + location_id + forecast_date + forecast_slot + activity_time_key`

`activity_time_key`를 unique에 포함한 이유:

- 바다갈라짐은 하루에 여러 체험 가능 시간대가 있을 수 있다.
- provider가 시간대를 구조화된 start/end로 주면 그 값을 key로 쓴다.
- 시간대가 `"10:00~13:00, 22:00~23:00"`처럼 문자열이면 문자열 hash를 key로 쓴다.
- 아무 시간 정보가 없으면 `all_day`로 저장한다.

## Dagster job

파일: `apps/api/app/dagster_etl/registry.py`

- `khoa_mudflat_index_forecast_twice_daily`
- `khoa_sea_split_index_forecast_twice_daily`

공통 동작:

- `TRIPMATE_KHOA_API_KEY` 또는 `TRIPMATE_DATA_GO_SERVICE_KEY`가 없으면 job schedule은 `None`으로 비활성화된다.
- 수동 실행 중에도 인증키가 없으면 `TripMateEtlSkip`으로 skip한다.
- 실행 로그는 `etl_run_logs`에 남긴다.
- retry 소진 시 관리자 알림과 권리자 Telegram 시스템 알림 outbox를 생성한다.

## 관리자 화면

관리자 데이터 브라우저는 SQLAlchemy `Base.metadata`에 등록된 테이블을 자동으로 나열한다. 따라서 모델 import가 유지되는 한 다음 테이블은 별도 프론트엔드 등록 없이 조회/검색/필터/정렬 대상이 된다.

- `ocean_activity_index_locations`
- `ocean_activity_index_source_records`
- `ocean_activity_index_forecasts`

## 테스트 기준

테스트 파일:

- `apps/api/tests/test_khoa_ocean_index_loader.py`
- `apps/api/tests/test_dagster_etl.py`
- `apps/api/tests/test_etl_config.py`
- `apps/api/tests/test_model_metadata.py`
- `apps/api/tests/test_migration_contract.py`

검증 내용:

- data.go.kr gateway endpoint path와 `serviceKey`, `reqDate`, pagination parameter
- raw/source record 멱등성
- 좌표 기반 법정동 매핑
- 구조화된 체험 시작/종료 시각의 KST `timestamptz` 저장
- 비구조화 체험 시간 문자열의 `activity_time_text`/`activity_time_key` 보존
- SRID 4326 geometry와 GiST index
- FK covering index
- job schedule, retry, KST start date, 인증키 없는 환경의 manual schedule
