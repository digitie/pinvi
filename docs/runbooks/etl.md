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
| `TRIPMATE_KHOA_API_KEY` | 로컬 `.env` | KHOA 해수욕장 정보 API 인증키이자 KHOA 생활해양예보지수 우선 인증키. 생활해양예보지수는 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_MOF_BEACH_SERVICE_KEY` | 로컬 `.env` | 해양수산부 해수욕장정보/수질 API 인증키. 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. |
| `TRIPMATE_OPINET_API_KEY` | 로컬 `.env` | OpiNet 유가 API 인증키. 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_EXPRESSWAY_API_KEY` | 로컬 `.env` | 한국도로공사 OpenAPI 인증키. query parameter 이름은 `key`이며 실패 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_AIRFLOW_LOG_DIR` | `/opt/tripmate/.tmp/airflow-logs` | Airflow task가 ETL 보조 로그를 쓰는 위치. 휴게소 FK 불일치 JSONL 로그가 이 하위에 저장된다. |
| `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH` | 없음 | 기상청 추천 관광코스 CSV/ZIP 파일 경로. 설정하지 않으면 관광코스 DAG는 skip한다. |
| `AIRFLOW__CELERY_BROKER_TRANSPORT_OPTIONS__VISIBILITY_TIMEOUT` | `21600` | 긴 ETL task가 Redis broker에서 중복 재전달되지 않도록 하는 시간초 단위 제한 |

Windows 또는 WSL2에서 backend test를 실행할 때는 앱 DB URL이 `localhost:55432`를 사용한다. Airflow 컨테이너 안에서는 compose service 이름인 `postgres:5432`를 사용한다.
로컬 비밀값은 Git에 포함하지 않는다. Docker Compose/Airflow는 저장소 루트의 `.env`를, backend 직접 실행은 `apps/api/.env`를 사용한다.
`docker compose config` 출력에는 환경변수 값이 펼쳐질 수 있으므로, 결과를 이슈/문서/로그에 그대로 붙이지 않는다.
`.env` 파일은 UTF-8 without BOM으로 저장한다. BOM이 붙으면 일부 도구에서 첫 환경변수 이름을 잘못 읽을 수 있다.

Airflow 이미지는 DAG task가 mount된 backend ETL 코드를 직접 import하므로 `infra/airflow/requirements.txt`에 backend ETL과 같은 pinned provider client(`pykma`, `pykex`, `pyopinet`, `pykrtourapi`)를 포함한다. Git URL 의존성을 설치하기 위해 Airflow Dockerfile은 build 단계에서 `git`을 설치한다.

## 6시간 ETL soak 검증

장시간 ETL 안정성을 검증할 때는 기본 운영 config를 직접 바꾸지 않는다. 대신 `config/etl-datasets.soak.json`을 Airflow 컨테이너 환경변수 `TRIPMATE_ETL_CONFIG_PATH`로 주입한다. 현재 표준 soak는 6시간, 10분 점검이다.

실행:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/etl-soak-reset-and-start.sh --yes --duration-hours 6 --check-interval-minutes 10"
```

상태 확인:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/etl-soak-status.sh"
```

수동 재-trigger:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/etl-soak-trigger-all.sh"
```

검증 스크립트 동작:

- `docker compose down -v --remove-orphans`로 로컬/검증용 DB volume을 초기화한다.
- Airflow와 TripMate Postgres를 다시 올린다.
- 실행 중인 `airflow-scheduler` 컨테이너 안에서 `apps/api` Alembic migration을 `head`까지 적용한다.
- `dataset/` 하위에 법정동코드 CSV가 있으면 `python -m app.cli.legal_dong_code`로 먼저 적재한다.
- `dataset/` 하위에 VWorld SHP ZIP 3종이 있으면 `python -m app.cli.vworld_boundary`로 먼저 적재한다.
- Airflow 검증 대상 DAG를 unpause하고 같은 soak run suffix로 수동 trigger한다.
- 시작 시각은 `.tmp/etl-soak/started-at`에 UTC epoch으로 기록한다.
- Juso 초기 적재는 공개 패턴을 감안해 매월 10일 전에는 두 달 전, 10일 이후에는 직전 월을 `source_year_month` conf로 넘긴다. 필요하면 `TRIPMATE_JUSO_SOAK_SOURCE_YEAR_MONTH=YYYYMM`으로 명시 override한다.

주의:

- 이 스크립트는 DB를 삭제하므로 운영 DB에서 사용하지 않는다.
- 6시간보다 긴 주기는 검증용 config에서 1시간 이내로 낮춘다.
- KHOA 해수욕지수, 갯벌체험지수, 바다갈라짐 체험지수는 하루 2회 quota라 검증 중에도 12시간 주기를 유지하고 retry를 0으로 둔다.
- AirKorea 일 500회 제한은 운영 config 기준으로 설계했다. soak config도 과도한 호출을 만들지 않도록 `air_quality_sido_measurement`는 시간 단위, station/tour/월간성 데이터는 12시간 단위로 제한한다.
- 기상청 관광코스 파일 경로 `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`가 없으면 관광코스 DAG skip은 정상 상태다.
- ETL 실패는 Airflow retry 소진 뒤 `etl_run_logs`, `admin_notifications`, `telegram_system_notification_outbox`에 남아야 한다.

장시간 검증 중 10분 단위로 확인할 항목:

- Docker service health
- Airflow `dag_run`과 `task_instance`의 `failed`, `up_for_retry`, 장기 `running` 상태
- `etl_run_logs`의 dataset별 success/failed/skipped 분포
- 주소, 경계, 유가, 휴게소, 날씨, 대기질 serving table row count 증가 여부
- `.tmp/airflow-logs/etl/rest_area_fk_mismatch/`의 FK 불일치 로그 누적 여부
- API quota 오류, 인증 오류, provider schema drift 오류
- 관리자 페이지와 공개 API에서 적재된 주요 데이터가 조회되는지 여부

현재 검증용 효율화:

- compose의 `TRIPMATE_ETL_CONFIG_PATH`는 환경변수로 override할 수 있다.
- `dataset/`은 Airflow 컨테이너에 read-only로 mount된다.
- 법정동코드 로컬 파일 적재는 `app.cli.legal_dong_code`로 ETL 실행 로그와 실패 알림까지 같은 방식으로 기록한다.
- 상태 점검은 앱 DB와 Airflow metadata DB를 모두 조회한다.
- `scripts/etl-soak-monitor.sh`는 각 10분 점검 로그를 `.tmp/etl-soak/status-*.log`에 남기고 최신 로그를 `.tmp/etl-soak/latest-status.log`로 복사한다.

반복 오류 방지:

- Airflow 이미지에 Alembic package가 있어도 `alembic` CLI 또는 `python -m alembic`이 항상 동작하는 것은 아니다. migration 자동화는 `python -c "from alembic.config import main; main(argv=['upgrade', 'head'])"` 형태를 사용한다.
- 이미 올라온 로컬 스택에서 migration과 수동 ETL 적재를 할 때는 `docker compose run airflow-init`보다 `docker compose exec airflow-scheduler`를 우선한다. `run`은 의도치 않은 service 재생성을 유발할 수 있다.
- 수동 import command는 성공 로그만으로 검증하지 않는다. VWorld SHP처럼 loader 결과가 성공이어도 DB commit 위치가 잘못되면 serving table이 0건일 수 있으므로 row count 검증을 함께 한다.
- Airflow 3.2 TaskFlow에서는 기존 `{{ ts }}`, `{{ ds }}` Jinja 변수가 task 인자 렌더링 시점에 없을 수 있다. DAG task는 Jinja 문자열 인자를 받지 말고 실행 시점 context에서 logical date 또는 run_after를 읽는다.
- 대용량 ETL에서 ORM object를 수백만 개 `add_all`로 누적하지 않는다. Juso처럼 GB 단위 TXT를 다룰 때는 streaming parser, hash/row_count inspect, Core batch insert, serving batch 재구성을 기본값으로 한다.
- 월간 Juso는 공개일 전에는 직전 월 파일이 없을 수 있다. 초기 DB 구축 또는 복구는 DAG conf `{"source_year_month":"YYYYMM"}`로 공개가 확인된 월을 명시한다.
- 같은 데이터셋에서 후속 success가 발생하면 이전 실패 관리자 알림과 Telegram pending outbox가 자동 resolved/cancelled 되는지 확인한다. 실패 알림이 계속 남아 있으면 운영자가 이미 조치한 장애가 반복 알림으로 보일 수 있다.

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
- 초기 적재/복구용 수동 실행은 Airflow conf `{"source_year_month":"YYYYMM"}`를 받을 수 있다. 이 경우 10일 이전 skip 규칙을 적용하지 않고, 같은 월 성공 로그가 있을 때만 skip한다.

수동 월 지정 예:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose --env-file .env -f infra/docker-compose.yml exec -T airflow-scheduler airflow dags trigger juso_monthly_address_dataset --run-id manual__juso_202603 --conf '{\"source_year_month\":\"202603\"}'"
```

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
- `kma_beach_catalog`: `0 4 15 5 *`, 30분 간격 3회 retry
- `kma_beach_ultra_short_forecast`: `45 * * 6,7,8 *`, 5분 간격 3회 retry
- `kma_beach_village_forecast`: `20 2,5,8,11,14,17,20,23 * 6,7,8 *`, 10분 간격 3회 retry
- `kma_beach_wave_height`: `35 * * 6,7,8 *`, 5분 간격 3회 retry
- `kma_beach_water_temperature`: `40 * * 6,7,8 *`, 5분 간격 3회 retry
- `kma_beach_tide_sun`: `10 5 * 6,7,8 *`, 10분 간격 3회 retry
- `khoa_beach_observation`: `20 * * * *`, 5분 간격 3회 retry
- `khoa_beach_index_forecast`: `30 6,18 * * *`, quota 보호를 위해 retry 0회
- `mof_beach_info`: `0 4 15 5 *`, 30분 간격 3회 retry
- `mof_beach_water_quality`: `20 4 15 5 *`, 30분 간격 3회 retry

Airflow DAG:

- `weather_short_term_sigungu_grid`: VWorld 시군구 경계에서 대표 격자를 만들고 기상청 초단기실황, 초단기예보, 단기예보를 수집한다.
- `weather_kma_alert`: 기상특보, 기상정보, 기상속보를 Telegram 알림 원천으로 수집한다.
- `weather_mid_term_nationwide`: `config/kma-mid-term-regions.json`의 기상청 중기예보 구역 seed와 주소 mapping을 적재하고 `getMidFcst`, `getMidLandFcst`, `getMidTa`를 전국 구역 단위로 수집한다.
- `air_quality_station_daily`: AirKorea 측정소 목록을 수집하고 좌표를 법정동 경계와 매핑한다.
- `air_quality_forecast_daily`: AirKorea 미세먼지/오존 예보통보를 수집한다.
- `air_quality_sido_measurement_hourly`: AirKorea 시도별 실시간 측정값을 수집한다.
- `kma_recommended_tour_course_annual`: 운영자가 제공한 기상청 관광코스 CSV/ZIP 파일을 DB화한다.
- `kma_beach_catalog_annual`: 기상청 해수욕장 위치 xlsx를 받아 `places`와 `weather_beach_location`에 적재한다.
- `kma_beach_ultra_short_forecast_hourly`: 활성 해수욕장 전체의 초단기예보를 6~8월 시간 단위로 수집한다.
- `kma_beach_village_forecast_3hourly`: 활성 해수욕장 전체의 단기예보를 6~8월 3시간 기준으로 수집한다.
- `kma_beach_wave_height_hourly`: 활성 해수욕장 전체의 파고를 6~8월 시간 단위로 수집한다.
- `kma_beach_water_temperature_hourly`: 활성 해수욕장 전체의 수온을 6~8월 시간 단위로 수집한다.
- `kma_beach_tide_sun_daily`: 활성 해수욕장 전체의 조석과 일출/일몰을 6~8월 일 단위로 수집한다.
- `khoa_beach_observation_hourly`: KHOA `해수욕장 정보` API와 관측소 메타데이터를 이용해 해수욕장별 최신 수온/파고/풍향풍속을 수집한다.
- `khoa_beach_index_forecast_twice_daily`: KHOA `해수욕지수` API를 공식 갱신주기와 quota에 맞춰 하루 2회 수집한다.
- `mof_beach_info_annual`: 해양수산부 해수욕장정보 서비스를 첨부문서의 연 1회 갱신주기에 맞춰 수집한다.
- `mof_beach_water_quality_annual`: 해양수산부 해수욕장 수질적합 여부 서비스를 첨부문서의 연 1회 갱신주기에 맞춰 수집한다. 시즌 전 현재 연도 데이터가 비어 있을 수 있어 현재 연도와 직전 연도를 함께 조회한다.
- `khoa_mudflat_index_forecast_twice_daily`: data.go.kr gateway의 KHOA 갯벌체험지수를 매일 06:40, 18:40에 수집한다.
- `khoa_sea_split_index_forecast_twice_daily`: data.go.kr gateway의 KHOA 바다갈라짐 체험지수를 매일 06:50, 18:50에 수집한다.

해수욕장 운영 주의:

- 해수욕장 날씨 DAG는 실행 전에 `weather_beach_location` active row가 없으면 카탈로그 적재를 먼저 시도한다.
- 카탈로그는 법정동을 좌표로 판정하고, 도로명주소코드는 Juso 건물명 정확 일치가 1건일 때만 채운다. 좌표만으로 도로명주소코드를 만들지 않는다.
- 날씨 endpoint는 전국 해수욕장 수만큼 호출하므로 비시즌에는 기본 cron이 동작하지 않는다. 수동 실행 전 data.go.kr quota와 `TRIPMATE_DATA_GO_SERVICE_KEY` 사용을 확인한다.
- `weather_serving_beach`는 endpoint/category/시각 단위 조회 테이블이라 단기예보 수집 1회에도 수십만 행이 생긴다. 행 수 점검 시 endpoint별로 분해하고, 파고/수온/조위/일출일몰의 `-`, `:`, 빈 시각 무자료 표시는 raw에만 있어야 한다.
- 통합 해수욕장 DAG는 `beach_profiles`를 기준으로 KHOA, 해양수산부, 기존 KMA 해수욕장 카탈로그를 묶는다. 일반 지도 객체(`map_features`)와 자동 병합하지 않고, 이미 연결된 KMA 카탈로그의 `map_feature_id`만 보존한다.
- KHOA 생활해양예보지수 v2 API는 data.go.kr gateway `http://apis.data.go.kr/1192136/*v2`를 사용한다. 인증은 `TRIPMATE_KHOA_API_KEY`를 우선하고 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다.
- KHOA 해수욕장 관측 메타데이터 `getOpenApiInfo.do?id=36`은 2026-04-30 검증 기준 `observatoryList`를 최상위 JSON으로 반환한다. 이전 문서형 응답처럼 `openapiinfoDetail.observatoryList`로 감싸진 형태도 함께 지원하지만, 관측 success인데 `beach_observations`가 0건이면 이 응답 shape를 먼저 확인한다.
- KHOA 지수계열 인증키는 decoded key를 전송 직전에 URL encoding하고, 이미 percent-encoding된 key는 이중 인코딩하지 않는다.
- 2026-04-30 soak 검증에서 KHOA 해수욕지수/갯벌체험지수/바다갈라짐체험지수는 양쪽 키와 전일/당일/기본 `reqDate` 모두 HTTP 500을 반환했다. 2026-04-30 22:36 KST의 encoded key 재시도도 세 endpoint 모두 HTTP 500 `Unexpected errors`였다. `SERVICE KEY IS NOT REGISTERED`와 구분해 provider gateway 오류 또는 활용 승인 상태 문제로 처리한다.
- 이 3종은 하루 quota가 2회라 retry를 켜면 정상 schedule만으로도 quota를 초과한다. 실패 원인이 provider 500이어도 자동 retry하지 말고 다음 정규 수집 또는 수동 단건 확인으로 대응한다.
- 해수욕지수/갯벌체험지수/바다갈라짐 체험지수는 포털 갱신주기가 실시간이지만 기본 수집은 하루 2회다. UI 요청마다 직접 호출하지 않고 DB 캐시를 우선한다.
- 갯벌체험지수와 바다갈라짐 체험지수는 `ocean_activity_index_locations`, `ocean_activity_index_source_records`, `ocean_activity_index_forecasts`에 저장된다. 관리자 데이터 브라우저는 이 테이블을 자동으로 노출한다.
- 해양수산부 해수욕장정보/수질 API는 포털 화면과 첨부문서의 갱신주기 표기가 다르다. 운영 기준은 첨부문서의 `년 1회`다.
- 수질 API는 현재 연도 응답이 0건이어도 정상일 수 있다. 공개 API는 적재된 수질 row 중 조사일자 기준 최신 row를 보여준다.

### 축제/공공 장소 데이터셋

현재 backend에는 공공데이터포털 전국문화축제표준데이터와 공공 장소 표준데이터 ETL이 함께 구현되어 있다. 이 절은 축제 화면과 최근 추가한 관광안내소 수집 기준만 요약하고, 전체 공공 장소 기준은 `docs/data-sources/public-places.md`와 `docs/architecture/public-place-etl-schema.md`를 따른다.

구현된 데이터셋 설정:

- `public_cultural_festival`: `35 4 12 2,5,8,11 *`, 30분 간격 3회 retry
- `public_tourist_information_center`: `10 4 5 7 *`, 30분 간격 3회 retry

Airflow DAG:

- `public_cultural_festival_quarterly`: data.go.kr 표준 OpenAPI `tn_pubr_public_cltur_fstvl_api`를 `numOfRows=500`으로 pagination 수집한다.
- `public_tourist_information_center_annual`: data.go.kr 표준 OpenAPI `tn_pubr_public_trsmic_api`를 `numOfRows=1000`으로 pagination 수집해 `map_features`/`place_details`에 적재한다.

전국문화축제표준데이터 주기 결정:

- 공공데이터포털 확인일 2026-04-28 기준 공식 갱신주기는 `분기`, 수정일은 `2026-02-10`이다.
- 포털은 개별 기관 데이터가 매월 초 전국 단위로 병합될 수 있다고 안내한다.
- TripMate는 공식 갱신주기를 우선해 분기 수집으로 운영하되, 월초 병합과 수정일 지연을 피하기 위해 2/5/8/11월 12일 04:35 KST에 실행한다.
- freshness target은 93일이다. 분기 갱신이 며칠 지연되어도 즉시 stale 장애로 오판하지 않기 위한 값이다.

저장/조회:

- 전국문화축제 raw는 `tour_raw_public_cultural_festival`, serving은 `tour_serving_public_cultural_festival`다.
- 지도와 로그인 화면은 serving table을 조회한다.
- 전국문화축제 지도 marker API는 `GET /public/festivals/map-markers`다.
- 축제를 여행계획에 추가하면 `trip_plan_items.resource_type = festival`, `trip_plan_items.festival_id = tour_serving_public_cultural_festival.id`로 연결한다.

수동 검증 명령:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/pytest tests/test_public_cultural_festival_loader.py tests/test_airflow_dags.py tests/test_etl_config.py"
```

실제 provider 호출은 `TRIPMATE_DATA_GO_SERVICE_KEY`가 설정된 Airflow 환경에서만 수행한다. 인증키 원문은 Airflow log, ETL run log, 문서에 남기지 않는다.

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

## 공공 장소 정보 ETL

수목원, 휴양림, 박물관, 미술관, 캠핑장 데이터는 `dags/public_places.py`의 DAG가 수집하고 표준 장소 DB에 적재한다.

| DAG | dataset key | 주기 | 주요 저장 테이블 |
| --- | --- | --- | --- |
| `public_arboretum_basic_annual` | `public_arboretum_basic` | 매년 7월 5일 04:05 | `source_records`, `map_features`, `place_details`, `map_feature_provider_refs` |
| `public_recreation_forest_semiannual` | `public_recreation_forest` | 1월/7월 15일 04:15 | `source_records`, `map_features`, `place_details`, `map_feature_provider_refs` |
| `public_museum_art_gallery_annual` | `public_museum_art_gallery` | 매년 7월 15일 04:25 | `source_records`, `map_features`, `place_details`, `map_feature_provider_refs` |
| `public_campground_daily` | `public_campground` | 매일 04:45 | `source_records`, `map_features`, `place_details`, `map_feature_provider_refs` |

운영 원칙:

- 상류 원천 row는 `source_records.raw_data`에 보관하고, 앱 검색과 지도 노출은 `map_features(feature_type='place')`를 기준으로 한다.
- 모든 장소에 공통인 이름, 주소, 좌표, 법정동코드, 카테고리, 전화번호, 운영상태는 typed column으로 저장한다.
- 장소 유형별 긴 필드는 `place_details.extra` JSONB에 저장한다. JSONB 내부 값을 검색/정렬 조건으로 자주 쓰게 되면 typed column 또는 별도 detail table로 승격한다.
- 법정동 매핑은 주소 문자열 fuzzy matching이 아니라 EPSG:4326 좌표와 V-WORLD 법정동 경계의 PostGIS `ST_Covers`로 수행한다.
- 공공데이터에 전역 고유 ID가 없는 경우가 많아 dataset key, 장소명, 주소, 좌표, 제공기관 정보를 조합한 hash를 provider source id로 사용한다. 상류 정정으로 hash가 바뀌면 자동 병합하지 않고 새 provider ref로 적재한다.
- 캠핑장은 2026-04-29부터 한국관광공사 고캠핑 API(`http://apis.data.go.kr/B551011/GoCamping/basedList`)를 사용한다. `serviceKey`, `MobileOS=ETC`, `MobileApp=TripMate`, `_type=json`, `pageNo`, `numOfRows`를 보낸다.
- Go Camping, 전국문화축제표준데이터, 전국휴양림표준데이터, 전국박물관미술관정보표준데이터는 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. 인증키 원문은 DB payload, ETL log, 알림 payload에 저장하지 않는다.
- 과거 localdata 캠핑장 CSV URL은 WSL2 검증에서 403이 발생해 기본 수집 경로에서 제외했다. 다시 도입할 때는 상류 방화벽, User-Agent, 네트워크 정책을 먼저 확인한다.
- data.go.kr 표준 OpenAPI는 정상 키에서도 간헐적으로 `[Errno 104] Connection reset by peer`가 발생할 수 있다. 클라이언트는 요청 단위로 짧게 재시도하고, Airflow retry는 여전히 최종 보호막으로 둔다.

## 전국문화축제표준데이터 ETL

공공데이터포털 전국문화축제표준데이터는 `public_cultural_festival_quarterly` DAG가 수집한다.

- dataset key: `public_cultural_festival`
- schedule: `35 4 12 2,5,8,11 *`
- retry: 30분 간격 3회
- freshness target: 93일
- source: `https://api.data.go.kr/openapi/tn_pubr_public_cltur_fstvl_api`
- page size: 500
- 저장 테이블: `tour_raw_public_cultural_festival`, `tour_serving_public_cultural_festival`

운영 원칙:

- `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. 인증키 원문은 DB payload, ETL log, 알림 payload에 저장하지 않는다.
- provider 안정 ID가 없으므로 축제명, 기간, 장소, 주소, 제공기관코드를 조합한 해시를 `source_record_id`로 사용한다.
- raw snapshot은 같은 `provider + source_record_id + response_hash`를 중복 저장하지 않는다.
- 같은 API fetch 안에서 동일 `source_record_id`가 반복되면 마지막 row만 serving 후보로 사용하고 `duplicate_row_count`에 기록한다. Airflow 세션은 `autoflush=False`이므로 이 방어가 없으면 마지막 flush 시 raw/serving unique constraint 충돌이 날 수 있다.
- serving row는 `provider + source_record_id`로 upsert하고, 이번 수집에서 확인되지 않은 기존 row는 `is_active=false`로 둔다.
- 주소 매핑은 Juso 도로명주소 exact match, Juso 지번주소 exact match, V-WORLD 법정동 경계 point-in-polygon 순서로 시도한다.
- fuzzy 주소 매칭은 하지 않는다. 운영 검증 UI가 생기기 전까지 잘못된 자동 연결보다 `unmapped` 보존을 우선한다.
- 로그인 화면의 `/public/festivals/monthly` API는 이 serving 테이블만 조회한다.
- 지도 marker 색상과 icon은 `docs/architecture/map-marker-design.md`의 축제 source type 기준을 따른다.

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
