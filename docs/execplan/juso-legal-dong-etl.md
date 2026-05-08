# Juso 주소 ETL 실행 계획

## 목표

Juso 주소 데이터의 첫 구현 단위는 다음 세 가지다.

- 월간 `rnaddrkor_*.txt` 파일을 raw row와 활성 도로명주소 serving snapshot으로 적재한다.
- 월간 `jibun_rnaddrkor_*.txt` 파일을 raw row와 활성 관련 지번 serving snapshot으로 적재한다.
- 이후 주소와 공간 데이터 작업에서 사용할 법정동코드 기준 테이블을 재구성한다.

## 범위

추가한 DB 테이블:

- `address_raw_juso_road_address`
- `address_serving_juso_road_address`
- `address_raw_juso_related_jibun`
- `address_serving_juso_related_jibun`
- `address_code_standard`

추가한 parser:

- Juso 도로명주소 TXT parser
- Juso 관련 지번 TXT parser

추가한 Juso 다운로드 client:

- `business.juso.go.kr`에서 월간 `도로명주소 한글` archive metadata를 찾는다.
- `/api/jst/download`에서 ZIP 파일을 다운로드한다.
- 지역별로 분리된 `rnaddrkor_*.txt`, `jibun_rnaddrkor_*.txt` 파일을 추출한다.

추가한 도로명주소 loader:

- 추출된 TXT 파일 hash와 row number 기준으로 raw row를 보존한다.
- 모든 추출 `rnaddrkor_*.txt` 파일에서 `address_serving_juso_road_address`를 재구성한다.
- 같은 snapshot에서 `address_code_standard`를 보조 재구성한다.

추가한 관련 지번 loader:

- 추출된 TXT 파일 hash와 row number 기준으로 raw row를 보존한다.
- `address_serving_juso_related_jibun`을 재구성한다.
- 각 row가 기존 `road_address_management_no`를 참조하는지 검증한다.

테스트 범위:

- WSL2 Docker PostgreSQL/PostGIS에 연결하는 integration test를 추가한다.

## 결정 사항

- 테스트는 WSL2에서 실행하고 Docker PostgreSQL/PostGIS `localhost:55432`에 연결한다.
- Juso 월간 전체 `도로명주소 한글` 데이터는 dataset detail `rtlDtaDtlSn=1`로 조회한다.
- raw 적재 멱등성은 추출 TXT의 `source_file_hash + row_number` 조합으로 보장한다.
- `change_reason_code = 63` row는 활성 법정동코드 dictionary에서 제외한다.
- `change_reason_code = 63` row는 활성 도로명주소 serving snapshot에서 제외한다.
- serving/code snapshot metadata는 월간 ZIP metadata인 `file_name`, archive hash, year-month를 사용한다.
- `address_serving_juso_road_address`의 key는 `road_address_management_no`다.
- `address_serving_juso_related_jibun`은 `address_serving_juso_road_address`에 FK를 둔다.
- 관련 지번 unique key는 `road_address_management_no + legal_dong_code + mountain_yn + jibun_main_no + jibun_sub_no`다.
- PostgreSQL identifier 63 byte 제한을 피하기 위해 긴 FK/index 이름은 명시적으로 짧게 작성한다.
- migration 제약 관련 실무 규칙은 `docs/decisions/20260425-postgres-migration-constraints.md`에 기록했다.
- 여행/장소 FK 연결은 아직 후속 작업이다.
- 매월 10일 이후 실행, 여행계획 날짜 skip, ETL retry/alert 기반은 `juso_monthly_address_dataset` Dagster job과 공통 ETL 로그 테이블에 반영됐다.

## 검증

- 도로명주소 parser unit test
- 관련 지번 parser unit test
- 다운로드 metadata 해석 test
- ZIP 다운로드/추출 test
- 법정동 loader test
- 도로명주소 serving loader test
- 관련 지번 loader test
- `download -> extract -> road-address load -> related-jibun load` pipeline integration test
- model metadata test
- migration contract test

## Dagster job

- job 정의: `apps/api/app/dagster_etl/registry.py`
- loader 연결: `apps/api/app/dagster_etl/loaders.py`
- job name: `juso_monthly_address_dataset`
- schedule: `0 4 10-31 * *`
- retry: `config/etl-datasets.json`의 `juso_road_address_korean` 설정을 따른다.

op 내부 skip 조건:

- 실행일이 10일 이전이면 skip
- 같은 `YYYYMM` run key가 이미 성공했으면 skip
- 실행일이 DB 여행계획 날짜에 포함되면 skip

성공/skip/실패 기록:

- `etl_run_logs`
- retry 소진 실패 시 `admin_notifications`
- retry 소진 실패 시 `telegram_system_notification_outbox`
