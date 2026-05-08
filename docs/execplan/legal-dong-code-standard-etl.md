# Legal-Dong Code Standard ETL

## 목표

TripMate의 주소 코드 기준은 `address_code_standard.legal_dong_code`다.

이 값은 다음 데이터의 FK 기준으로 사용한다.

- Juso 도로명주소 serving
- Juso 관련 지번 serving
- VWorld 행정경계 SHP serving
- 향후 여행 장소, geocoding 결과, 주소 snapshot

## 기준 데이터 변경

초기 검토에서는 VWorld에서 별도 업로드하는 `LSCT_LAWDCD.zip`의 3컬럼 CSV를 기준으로 보았다.
하지만 공공데이터포털의 `국토교통부_전국 법정동_20250807` 파일이 자동 다운로드 가능하고,
생성일자, 삭제일자, 과거법정동코드까지 제공하므로 canonical source를 이 파일로 바꾼다.

Source:

- page: https://www.data.go.kr/data/15063424/fileData.do
- dataset name: `국토교통부_전국 법정동`
- current file name observed: `국토교통부_전국 법정동_20250807`
- format: CSV
- 직접 다운로드 URL은 상세 페이지 JSON-LD의 `contentUrl`에 노출된다.

## 두 코드 파일의 차이

### 기존 VWorld `LSCT_LAWDCD.zip`

- 운영 방식: 관리자 업로드
- 파일 형태: ZIP 안 CSV 1개
- 인코딩: `cp949`
- 필드: `법정동코드`, `법정동명`, `폐지여부`
- 상태 표현: `존재`, `폐지`
- 장점: 단순하고 VWorld SHP와 출처 계열이 같다.
- 한계: 생성일자, 삭제일자, 과거법정동코드가 없어 코드 변경 추적이 약하다.

### 공공데이터포털 `국토교통부_전국 법정동`

- 운영 방식: ETL 자동 다운로드
- 파일 형태: data.go.kr 상세 페이지에서 CSV 다운로드
- 관측 인코딩: UTF-8
- 필드: `법정동코드`, `시도명`, `시군구명`, `읍면동명`, `리명`, `순위`, `생성일자`, `삭제일자`, `과거법정동코드`
- 상태 표현: `삭제일자`가 비어 있으면 active, 값이 있으면 deleted
- 장점: 행정구역 변경 이력을 더 안전하게 저장할 수 있다.
- 확인 사항: data.go.kr CSV에는 세종특별자치시 시도 코드 `3600000000`과 시군구 코드 `3611000000`이 모두 있다. 기존 3컬럼 CSV나 일부 코드 파일에는 `3600000000`이 없을 수 있어 SHP 매칭 fallback은 유지한다.

## 수집 주기

- Dagster schedule에서 3개월에 1번 실행한다.
- 기준 권장일: 2월/5월/8월/11월 15일 새벽 04:30 KST.
- 실패 재시도 정책은 데이터셋별 ETL 설정을 따른다.
- 현재 backend 함수는 페이지 HTML을 열고 JSON-LD의 `contentUrl`을 찾아 최신 CSV를 내려받는다.

## 저장 정책

`address_code_standard.legal_dong_code`는 물리 삭제하지 않는다.

최신 다운로드에서 사라진 코드는 다음처럼 보존한다.

- `is_active = false`
- `is_discontinued = true`
- `source_status = 'missing_from_latest_download'`

삭제일자가 있는 코드는 다음처럼 저장한다.

- `is_active = false`
- `is_discontinued = true`
- `source_status = 'deleted'`
- `source_deleted_date = <CSV 삭제일자>`

이 정책은 이미 저장된 주소, 여행 장소, SHP 경계, geocoding snapshot의 FK 깨짐을 막기 위한 것이다.

## DB 구조

Canonical table:

- `address_code_standard.legal_dong_code`: PK
- `code_level`: `sido`, `sigungu`, `legal_dong`
- `sido_code`, `sigungu_code`
- `sido_name`, `sigungu_name`, `legal_eupmyeondong_name`, `legal_ri_name`
- `full_legal_dong_name`
- `source_provider`: `data_go_legal_dong` 또는 legacy `vworld_lawd_cd`
- `source_status`: `active`, `deleted`, legacy `존재`/`폐지`, 또는 `missing_from_latest_download`
- `source_sort_order`
- `source_created_date`
- `source_deleted_date`
- `previous_legal_dong_code`
- `source_file_name`, `source_year_month`, `source_file_hash`
- `is_active`, `is_discontinued`

Raw table:

- `address_raw_legal_dong_code`
- 원본 파일 hash + row number로 idempotency를 보장한다.
- data.go.kr 추가 필드도 raw에 함께 저장한다.

## 관계

Juso loader:

- `address_code_standard`를 삭제하지 않는다.
- code standard가 비어 있거나 누락된 경우에만 `source_provider = 'juso_road_address'`로 보조 생성한다.
- `data_go_legal_dong` 또는 `vworld_lawd_cd` 소유 row는 덮어쓰지 않는다.

VWorld SHP loader:

- `region_serving_boundary.address_code_standard_code`가 `address_code_standard.legal_dong_code`를 참조한다.
- exact code match를 우선한다.
- data.go.kr 기준에서는 세종특별자치시 시도 SHP `3600000000`이 exact match 된다.
- legacy code table처럼 `3600000000`이 없고 `3611000000`만 있는 경우에는 시도 레이어에서만 이름 정규화 fallback을 사용한다.

## 검증 결과

2026-04-25 기준 data.go.kr 페이지에서 직접 다운로드한 CSV를 확인했다.

- downloaded bytes: 3,799,696
- parsed rows: 49,878
- active rows: 20,556
- deleted rows: 29,322
- temp PostgreSQL load: `address_code_standard` 49,878 rows, `address_raw_legal_dong_code` 49,878 rows
- 세종특별자치시: data.go.kr CSV에서는 `3600000000` 시도 row와 `3611000000` 시군구 row가 모두 존재한다.

## 구현 파일

- `apps/api/app/etl/vworld/legal_dong_code_loader.py`
- `apps/api/app/etl/vworld/boundary_loader.py`
- `apps/api/app/models/address.py`
- `apps/api/alembic/versions/20260425_0005_legal_dong_code_csv_standard.py`
- `apps/api/alembic/versions/20260425_0006_data_go_legal_dong_fields.py`
- `apps/api/tests/test_legal_dong_code_loader.py`
- `apps/api/tests/test_vworld_boundary_loader.py`

## Dagster job

분기별 job은 `apps/api/app/dagster_etl/registry.py`에 있다.

- job name: `legal_dong_code_standard_quarterly`
- schedule: `30 4 15 2,5,8,11 *`
- 의미: 2월, 5월, 8월, 11월 15일 04:30 KST 실행
- catchup: 비활성화
- 기본 retry: 5분 간격 3회
- 필수 환경변수: `TRIPMATE_DATABASE_URL`
- 선택 환경변수: `TRIPMATE_DAGSTER_DOWNLOAD_DIR`

Dagster definition import 시점에는 DB나 data.go.kr에 접근하지 않는다. 실제 backend import, CSV 다운로드, DB write는 op body 안에서 실행한다.

## 남은 연결 작업

- 관리자 페이지 업로드 방식은 legacy/manual fallback으로만 유지한다.
- Dagster runtime은 `infra/docker-compose.yml`에 연결됐다.
- 운영 설정 파일 `config/etl-datasets.json`에 `legal_dong_code_standard` 항목이 있다.
- 실제 운영 모니터링 UI와 Telegram 발송 worker는 후속 작업이다.
