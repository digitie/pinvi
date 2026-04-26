# ETL 운영 안내

## 로컬 Airflow 실행

모든 Docker 명령은 WSL2 Ubuntu에서 실행한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d postgres airflow-postgres airflow-redis airflow-init airflow-webserver airflow-scheduler airflow-dag-processor airflow-worker"
```

Airflow UI:

```text
http://localhost:28080
```

로컬 기본 계정:

- id: `airflow`
- password: `airflow`

Airflow 3.x에서는 웹 UI/API process command가 `api-server`다. TripMate Compose에서는 운영자가 찾기 쉽도록 service 이름을 `airflow-webserver`로 둔다. 로컬 호스트의 `8080` 포트는 다른 개발 도구와 자주 충돌하므로 Airflow UI는 `28080:8080`으로 노출한다.

## 주요 환경변수

Airflow 컨테이너 안에서 사용하는 값:

| 환경변수 | 기본값 | 의미 |
| --- | --- | --- |
| `TRIPMATE_DATABASE_URL` | `postgresql+psycopg://tripmate:tripmate_dev_password@postgres:5432/tripmate` | Airflow task가 접근하는 TripMate 앱 DB |
| `TRIPMATE_AIRFLOW_DOWNLOAD_DIR` | `/opt/tripmate/.tmp/airflow-downloads` | 다운로드 파일 저장 위치 |
| `TRIPMATE_ETL_CONFIG_PATH` | `/opt/tripmate/config/etl-datasets.json` | 데이터셋별 retry/schedule 설정 파일 |
| `TRIPMATE_API_DIR` | `/opt/tripmate/apps/api` | Airflow task가 backend module을 import할 경로 |
| `TRIPMATE_DATA_GO_SERVICE_KEY` | 로컬 `.env` | data.go.kr API/파일 다운로드 인증키. 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_OPINET_API_KEY` | 로컬 `.env` | OpiNet 유가 API 인증키. 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_EXPRESSWAY_API_KEY` | 로컬 `.env` | 한국도로공사 OpenAPI 인증키. query parameter 이름은 `key`이며 실패 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_AIRFLOW_LOG_DIR` | `/opt/tripmate/.tmp/airflow-logs` | Airflow task가 ETL 보조 로그를 쓰는 위치. 휴게소 FK 불일치 JSONL 로그가 이 하위에 저장된다. |
| `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH` | 없음 | 기상청 추천 관광코스 CSV/ZIP 파일 경로. 설정하지 않으면 관광코스 DAG는 skip한다. |
| `AIRFLOW__CELERY_BROKER_TRANSPORT_OPTIONS__VISIBILITY_TIMEOUT` | `21600` | 긴 ETL task가 Redis broker에서 중복 재전달되지 않도록 하는 시간초 단위 제한 |

Windows 또는 WSL2에서 backend test를 실행할 때는 앱 DB URL이 `localhost:55432`를 사용한다. Airflow 컨테이너 안에서는 compose service 이름인 `postgres:5432`를 사용한다.
로컬 비밀값은 Git에 포함하지 않는다. Docker Compose/Airflow는 저장소 루트의 `.env`를, backend 직접 실행은 `apps/api/.env`를 사용한다.
`docker compose config` 출력에는 환경변수 값이 펼쳐질 수 있으므로, 결과를 이슈/문서/로그에 그대로 붙이지 않는다.
`.env` 파일은 UTF-8 without BOM으로 저장한다. BOM이 붙으면 일부 도구에서 첫 환경변수 이름을 잘못 읽을 수 있다.

## 시간대 기준

- 저장용 timezone-aware datetime은 KST(`Asia/Seoul`) 기준이다.
- backend SQLAlchemy engine은 PostgreSQL 연결마다 `SET TIME ZONE 'Asia/Seoul'`을 실행한다.
- ETL loader가 `collected_at`을 외부에서 받지 못하면 KST 현재 시각을 사용한다.
- Airflow DAG는 logical datetime을 KST로 변환해 loader에 넘긴다.
- 수동 command의 run key도 KST `YYYYMMDDTHHMMSS` 형식을 사용한다. UTC suffix(`Z`)를 붙이지 않는다.

`config/etl-datasets.json`은 JSON boolean과 0 이상의 정수만 허용한다. `"false"` 같은 문자열 boolean은 운영자가 의도한 값과 다르게 해석될 수 있으므로 실패시킨다.

## DAG

### `legal_dong_code_standard_quarterly`

- 목적: data.go.kr `국토교통부_전국 법정동` CSV를 내려받아 `address_code_standard`와 raw table을 갱신한다.
- schedule: `30 4 15 2,5,8,11 *`
- retry: `config/etl-datasets.json`의 `legal_dong_code_standard`를 따른다.
- DAG import 시점에는 DB와 외부 네트워크에 접근하지 않는다.

### `juso_monthly_address_dataset`

- 목적: Juso 도로명주소 한글 전체분 ZIP을 내려받아 도로명주소/관련 지번 raw와 serving snapshot을 갱신한다.
- 주소 코드와 외부 데이터셋 매핑의 상세 기준은 `docs/architecture/address-schema.md`를 따른다.
- schedule: `0 4 10-31 * *`
- 10일 이전 실행은 task 내부에서 skip한다.
- 같은 `YYYYMM` 성공 로그가 있으면 skip한다.
- 실행일이 DB 여행계획 날짜에 포함되면 skip한다.
- 10일 이후 여행계획이 없는 첫 실행일에 갱신한다.

### OpiNet 유가 데이터셋

현재 backend에는 OpiNet client, raw/serving loader, DB schema, 수동 운영 command, Airflow DAG가 구현되어 있다.

구현된 데이터셋 설정:

- `fuel_region_code`: `0 4 1 1,4,7,10 *`, 30분 간격 3회 retry
- `fuel_avg_price`: `20 5,13,21 * * *`, 5분 간격 3회 retry
- `fuel_lowest_station`: `40 5,13,21 * * *`, 5분 간격 3회 retry

Airflow DAG:

- `opinet_region_code_quarterly`: OpiNet 지역코드를 수집하고 Juso 시도/시군구 코드와 매핑한다.
- `opinet_avg_price_daily`: 전국 일별 평균가를 수집한다.
- `opinet_lowest_station_daily`: 매핑된 전국 시군구 전체의 최저가 주유소 후보를 수집한다.
- OpiNet DAG run key는 하루 여러 번 실행되는 평균가/최저가 로그가 구분되도록 Airflow logical timestamp의 KST `YYYYMMDDTHHMMSS` 형식을 사용한다.

주의:

- OpiNet 인증 파라미터 이름은 `certkey`다. 실패 로그와 Telegram outbox에 남기기 전에 반드시 마스킹한다.
- `fuel_avg_price`는 현재 OpiNet 전국 평균가를 `region_key = national`로 저장한다.
- `fuel_lowest_station`의 사용자용 평균값은 특정 OpiNet 시군구 지역의 최저가 TOP 후보 평균이다. 실제 반경 평균이나 지역 전체 평균가가 아니므로 UI/API에 "주변 평균"과 "최저가 후보 평균"을 함께 표현한다.
- OpiNet 지역코드는 Juso 법정동코드와 다르므로 `fuel_region_legal_dong_mapping`을 통해 연결한다.
- `opinet_lowest_station_daily`는 `fuel_region_code` 매핑 결과가 있어야 실행 가능하다. 매핑된 시군구가 없으면 retry 후 실패 로그와 관리자 알림으로 이어진다.
- provider API 호출 부하를 사용자 수와 분리하기 위해 `fuel_lowest_station`은 on-demand 호출이 아니라 전국 시군구 전체 주기 수집을 기본값으로 한다. 다른 공공/외부 데이터도 가능하면 같은 원칙을 적용한다.

수동 적재 command:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/python -m app.cli.opinet_fuel region-codes"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/python -m app.cli.opinet_fuel avg-prices"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/python -m app.cli.opinet_fuel lowest-stations --provider-region-code 0101 --fuel-code B027"
```

`lowest-stations`는 `--legal-dong-code`도 받을 수 있다. 이 경우 `fuel_region_legal_dong_mapping`을 통해 OpiNet region code를 찾는다.

### 한국도로공사 휴게소 데이터셋

현재 backend에는 한국도로공사 휴게소 client, raw/serving loader, DB schema, Airflow DAG가 구현되어 있다.

구현된 데이터셋 설정:

- `rest_area_master`: `10 4 1 * *`, 30분 간격 3회 retry
- `rest_area_oil_price`: `10 6,18 * * *`, 10분 간격 3회 retry
- `rest_area_svcs`: `30 4 1 * *`, 30분 간격 3회 retry

Airflow DAG:

- `rest_area_master_monthly`: `business/serviceAreaRoute` 응답을 raw snapshot으로 저장하고, `serviceAreaCode2`를 `rest_area_serving_master.svar_cd`로 정규화한다.
- `rest_area_oil_price_daily`: `business/curStateStation` 응답을 저장한다. 하루 2회 수집분을 보존하기 위해 Airflow logical timestamp를 `collected_at`으로 넘기고, serving unique 기준은 `svar_cd + provider_fuel_code + collected_at`이다.
- `rest_area_service_monthly`: `business/conveniServiceArea` 응답의 `convenience` 문자열을 `|`로 나누어 편의시설 row로 저장한다.

주의:

- `rest_area_oil_price`와 `rest_area_svcs`는 `serviceAreaCode2`가 master에 없으면 raw row만 저장하고 serving row는 skip한다.
- FK 불일치 row는 `<TRIPMATE_AIRFLOW_LOG_DIR>/etl/rest_area_fk_mismatch/<dataset>/<run_key>.jsonl`에 남긴다. 이 로그는 운영자가 삭제하기 전까지 보관한다.
- 한국도로공사 인증 query parameter는 `key`다. 실패 로그, Telegram outbox, 문서 예시에 실제 인증키를 남기지 않는다.
- `rest_area_oil_price` provider field의 `diselPrice` 오탈자는 provider 원문 field명이므로 코드에서 그대로 사용한다.

### 날씨와 대기질 데이터셋

현재 backend에는 data.go.kr client, raw/serving loader, DB schema, Airflow DAG가 구현되어 있다.

구현된 데이터셋 설정:

- `weather_short_term`: `*/30 * * * *`, 5분 간격 3회 retry
- `weather_kma_alert`: `*/30 * * * *`, 5분 간격 3회 retry
- `weather_mid_term`: `20 6,18 * * *`, 10분 간격 3회 retry
- `air_quality_station`: `20 4 * * *`, 30분 간격 3회 retry
- `air_quality_forecast`: `15 5,11,17,23 * * *`, 10분 간격 3회 retry
- `air_quality_sido_measurement`: `25 * * * *`, 10분 간격 3회 retry
- `kma_recommended_tour_course`: `0 5 1 3 *`, 30분 간격 3회 retry

Airflow DAG:

- `weather_short_term_sigungu_grid`: VWorld 시군구 경계에서 대표 격자를 만들고 기상청 초단기실황, 초단기예보, 단기예보를 수집한다.
- `weather_kma_alert`: 기상특보, 기상정보, 기상속보를 Telegram 알림 원천으로 수집한다.
- `weather_mid_term_nationwide`: `config/kma-mid-term-regions.json`의 기상청 중기예보 구역 seed와 주소 mapping을 적재하고 `getMidFcst`, `getMidLandFcst`, `getMidTa`를 전국 구역 단위로 수집한다.
- `air_quality_station_daily`: AirKorea 측정소 목록을 수집하고 좌표를 법정동 경계와 매핑한다.
- `air_quality_forecast_daily`: AirKorea 미세먼지/오존 예보통보를 수집한다.
- `air_quality_sido_measurement_hourly`: AirKorea 시도별 실시간 측정값을 수집한다.
- `kma_recommended_tour_course_annual`: 운영자가 제공한 기상청 관광코스 CSV/ZIP 파일을 DB화한다.

주의:

- data.go.kr 인증 query parameter는 기상청 계열에서 `ServiceKey`, AirKorea 계열에서 `serviceKey`다. 실패 로그와 Telegram outbox에 원문 인증키를 남기지 않는다.
- `weather_short_term_sigungu_grid`는 `weather_short_term_grid_mapping`이 비어 있으면 `region_serving_boundary`의 시군구 경계에서 mapping을 생성한다. VWorld 경계가 아직 없으면 수집 격자 0건으로 끝날 수 있으므로, 운영에서는 VWorld SHP를 먼저 적재한다.
- AirKorea 대기오염정보는 일 500회 제한이다. 기본값은 `air_quality_sido_measurement` 408회/일과 `air_quality_forecast` 12회/일로 약 420회/일이다. 반복 retry가 발생하면 제한을 넘을 수 있으므로 DAG 주기 완화 또는 일시정지를 먼저 검토한다.
- 기상특보/정보/속보는 좌표/주소가 없으므로 지도 마커에 표시하지 않는다. Telegram 여행 알림에만 활용한다.
- `kma_recommended_tour_course_annual`은 `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`가 없으면 skip한다. 이 skip은 장애가 아니라 운영 파일이 아직 준비되지 않은 상태다.
- 관광코스별 상세 날씨는 전체 코스를 정기 수집하지 않는다. 저장 장소/여행 장소 도메인이 연결된 뒤 해당 좌표 target 주변 관광코스만 cache 갱신 task로 호출한다.

## VWorld SHP 수동 적재

VWorld SHP는 Airflow가 자동 다운로드하지 않는다. 운영자가 ZIP 파일을 확보한 뒤 backend command로 적재한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/python -m app.cli.vworld_boundary /path/to/N3A_G0010000.zip /path/to/N3A_G0100000.zip /path/to/N3A_G0110000.zip"
```

지원 파일명:

- `N3A_G0010000.zip`: 시도
- `N3A_G0100000.zip`: 시군구
- `N3A_G0110000.zip`: 법정동

파일명으로 layer를 판정하므로 파일명을 임의로 바꾸지 않는다.

## 로그와 알림

ETL 실행 기록:

- `etl_run_logs`

관리자 로그인 시 표시할 알림 기반:

- `admin_notifications`

권리자 Telegram 시스템 알림 발송 준비 outbox:

- `telegram_system_notification_outbox`

현재 단계에서는 Telegram 실제 발송 worker가 아직 없다. Airflow task가 마지막 재시도까지 실패했다고 판단한 경우에만 retry 소진 실패를 outbox에 남기는 것까지 구현되어 있다.

Airflow DAG는 실행 시작 로그를 먼저 커밋한 뒤 데이터 적재 트랜잭션과 성공/실패 로그 갱신 트랜잭션을 분리한다. 적재 도중 DB 오류가 발생해도 시작 로그와 retry 소진 실패 알림이 함께 롤백되지 않도록 하기 위한 규칙이다.
VWorld 수동 import command도 동일하게 실행 로그 생성, 데이터 적재, 성공/실패 로그 갱신을 분리한다. ZIP 파일 오류나 DB 적재 오류가 발생해도 실패 로그와 관리자/Telegram outbox가 남아야 한다.
ETL 실패 메시지와 outbox payload는 `serviceKey`, `apiKey`, `token` 계열 query parameter와 현재 설정된 data.go.kr 인증키 값을 마스킹한다.

## 반복 오류 방지

- Docker 명령은 WSL2에서 실행한다.
- Airflow task에서 backend import가 실패하면 `PYTHONPATH`, `TRIPMATE_API_DIR`, `apps/api` volume mount를 먼저 확인한다.
- Airflow 컨테이너 안에서 `localhost`는 컨테이너 자신이다. TripMate 앱 DB는 `postgres:5432`로 접근한다.
- Windows/WSL test에서는 앱 DB가 `localhost:55432`로 노출된다.
- 실패 알림은 첫 실패가 아니라 Airflow retry 소진 후에만 생성한다. DAG에서 `TaskInstance.is_eligible_to_retry()` 기준을 사용하지 않으면 첫 실패에도 관리자/Telegram 알림이 생길 수 있다.
- ETL 실행 로그와 실제 데이터 적재를 같은 DB 트랜잭션에 묶지 않는다. 적재 실패 시 로그까지 롤백되어 운영자가 원인을 놓칠 수 있다.
- 외부 API 예외 문자열에는 요청 URL이 들어갈 수 있다. 실패 로그와 Telegram outbox에 넣기 전에 `serviceKey`, `certkey`, `apiKey`, `token` 계열 query parameter와 설정된 인증키 원문을 반드시 마스킹한다.
- 새 ETL을 추가하면 `config/etl-datasets.json`, `docs/data-sources.md`, 이 runbook을 함께 갱신한다.
- 저장되는 시각 컬럼에 `datetime.now(UTC)`, `timezone.utc`, `replace(tzinfo=UTC)`를 사용하지 않는다. provider 원문이 UTC를 명시하는 경우에도 저장 전 KST로 변환하고, 원문 문자열은 raw payload에 보존한다.
