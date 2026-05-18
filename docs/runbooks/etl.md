# ETL 운영 안내

## 로컬 Dagster 실행

모든 Docker 명령은 WSL2 Ubuntu에서 실행한다.

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && docker compose -f infra/docker-compose.yml up -d postgres dagster"
```

Dagster UI:

```text
http://localhost:23000
```

TripMate Compose는 `dagster dev`를 사용해 로컬/ODROID용 Dagster UI와 daemon을 같은 service에서 함께 띄운다. 운영 수준 분리가 필요해지면 webserver와 daemon을 별도 service로 나누고 이 문서를 갱신한다.

## 주요 환경변수

Dagster container 안에서 사용하는 값:

| 환경변수 | 기본값 | 의미 |
| --- | --- | --- |
| `TRIPMATE_DATABASE_URL` | `postgresql+psycopg://tripmate:tripmate_dev_password@postgres:5432/tripmate` | Dagster job이 접근하는 TripMate 앱 DB |
| `TRIPMATE_DAGSTER_DOWNLOAD_DIR` | `/opt/tripmate/.tmp/dagster-downloads` | 다운로드 파일 저장 위치 |
| `TRIPMATE_DAGSTER_LOG_DIR` | `/opt/tripmate/.tmp/dagster-logs` | ETL 보조 로그 저장 위치. 휴게소 FK 불일치 JSONL 로그가 이 하위에 저장된다. |
| `TRIPMATE_ETL_CONFIG_PATH` | `/opt/tripmate/config/etl-datasets.json` | 데이터셋별 schedule/retry/freshness 설정 파일 |
| `TRIPMATE_API_DIR` | `/app` | Dagster job이 backend module을 import할 경로 |
| `TRIPMATE_DATA_GO_SERVICE_KEY` | 로컬 `.env` | data.go.kr API/파일 다운로드 인증키. 로그와 DB payload에 원문을 남기지 않는다. |
| `TRIPMATE_KHOA_API_KEY` | 로컬 `.env` | KHOA API 인증키. 없으면 일부 KHOA 지수는 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. |
| `TRIPMATE_MOF_BEACH_SERVICE_KEY` | 로컬 `.env` | 해양수산부 해수욕장정보/수질 API 인증키. 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다. |
| `TRIPMATE_OPINET_API_KEY` | 로컬 `.env` | OpiNet 유가 API 인증키. |
| `TRIPMATE_EXPRESSWAY_API_KEY` | 로컬 `.env` | 한국도로공사 OpenAPI 인증키. |
| `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH` | 없음 | 기상청 추천 관광코스 CSV/ZIP 파일 경로. 없으면 해당 job은 skipped 로그를 남긴다. |

Windows 또는 WSL2에서 backend test를 실행할 때는 앱 DB URL이 `localhost:55432`를 사용한다. Dagster container 안에서는 compose service 이름인 `postgres:5432`를 사용한다.

로컬 비밀값은 Git에 포함하지 않는다. Docker Compose/Dagster는 저장소 루트의 `.env`를, backend 직접 실행은 `apps/api/.env`를 사용한다.

## Dagster 정의

Dagster 정의 파일:

- `apps/api/app/dagster_etl/definitions.py`: `Definitions`, job, schedule factory
- `apps/api/app/dagster_etl/registry.py`: 데이터셋별 job 이름, op 이름, loader, schedule gate
- `apps/api/app/dagster_etl/runtime.py`: 실행 로그, retry 소진 판단, Juso 수동 config, JSON payload 정규화
- `apps/api/app/dagster_etl/loaders.py`: 기존 backend ETL loader 호출

원칙:

- job import 시점에는 DB와 외부 네트워크에 접근하지 않는다.
- schedule timezone은 `Asia/Seoul`이다.
- `config/etl-datasets.json`이 schedule/retry/freshness의 단일 운영 기준이다.
- Dagster retry가 소진되기 전 실패는 `etl_run_logs`에 남기되 관리자/Telegram 알림을 만들지 않는다.
- retry 소진 실패만 `admin_notifications`, `telegram_system_notification_outbox`에 남긴다.
- KHOA 관측/지수처럼 인증키가 필요한 job은 키가 없으면 schedule을 생성하지 않는다. 수동 실행 시에는 skipped ETL log를 남긴다.
- Juso 초기 적재/복구는 op config `source_year_month: "YYYYMM"`을 사용한다.

## 주요 job

| job | dataset key | 주기 기준 |
| --- | --- | --- |
| `legal_dong_code_standard_quarterly` | `legal_dong_code_standard` | `config/etl-datasets.json` |
| `juso_monthly_address_dataset` | `juso_road_address_korean` | `config/etl-datasets.json` |
| `opinet_region_code_quarterly` | `fuel_region_code` | `config/etl-datasets.json` |
| `opinet_avg_price_daily` | `fuel_avg_price` | `config/etl-datasets.json` |
| `opinet_lowest_station_daily` | `fuel_lowest_station` | `config/etl-datasets.json` |
| `rest_area_master_monthly` | `rest_area_master` | `config/etl-datasets.json` |
| `rest_area_oil_price_daily` | `rest_area_oil_price` | `config/etl-datasets.json` |
| `rest_area_service_monthly` | `rest_area_svcs` | `config/etl-datasets.json` |
| `weather_short_term_sigungu_grid` | `weather_short_term` | `config/etl-datasets.json` |
| `weather_kma_alert` | `weather_kma_alert` | `config/etl-datasets.json` |
| `weather_mid_term_nationwide` | `weather_mid_term` | `config/etl-datasets.json` |
| `air_quality_station_daily` | `air_quality_station` | `config/etl-datasets.json` |
| `air_quality_forecast_daily` | `air_quality_forecast` | `config/etl-datasets.json` |
| `air_quality_sido_measurement_hourly` | `air_quality_sido_measurement` | `config/etl-datasets.json` |
| `kma_recommended_tour_course_annual` | `kma_recommended_tour_course` | `config/etl-datasets.json` |
| `kma_beach_*` | `kma_beach_*` | `config/etl-datasets.json` |
| `khoa_beach_*`, `khoa_*_index_*` | KHOA 해수욕장/해양지수 | 인증키가 있을 때 schedule 생성 |
| `mof_beach_*` | 해양수산부 해수욕장정보/수질 | `config/etl-datasets.json` |
| `public_*` | 공공 장소/축제 | `config/etl-datasets.json` |

개별 source, 저장 테이블, provider 주의사항은 `docs/data-sources.md`와 `docs/data-sources/*.md`를 따른다.

## 수동 실행

Dagster UI의 Launchpad에서 job을 선택해 실행한다. Juso 월간 주소를 특정 월로 적재하려면 아래 op config를 넣는다.

```yaml
ops:
  download_and_load_juso_monthly_address:
    config:
      run_type: manual
      source_year_month: "202603"
```

CLI smoke:

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && docker compose --env-file .env -f infra/docker-compose.yml exec -T dagster dagster job list -m app.dagster_etl.definitions"
```

## 6시간 ETL soak 검증

장시간 ETL 안정성을 검증할 때는 기본 운영 config를 직접 바꾸지 않는다. 대신 `config/etl-datasets.soak.json`을 Dagster container 환경변수 `TRIPMATE_ETL_CONFIG_PATH`로 주입한다. 현재 표준 soak는 6시간, 10분 점검이다.

실행:

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/etl-soak-reset-and-start.sh --yes --duration-hours 6 --check-interval-minutes 10"
```

현재 터미널을 점유하지 않고 백그라운드로 시작하려면 아래 wrapper를 사용한다. 이 wrapper는 이전 soak marker를 지우고 `reset-start.log`, `monitor.log`, pid 파일을 `.tmp/etl-soak/`에 남긴다.

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/etl-soak-background-start.sh --yes --duration-hours 6 --check-interval-minutes 10"
```

상태 확인:

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/etl-soak-status.sh"
```

10분 단위 strict 모니터:

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/etl-soak-monitor.sh --duration-hours 6 --check-interval-minutes 10 --strict"
```

`--strict`는 `retry_exhausted=true`인 최신 실패와 미해결 ETL 관리자 알림을 실패로 본다. Dagster retry가 남아 있는 transient 실패는 상태 로그에는 남기되 soak를 즉시 중단하지 않는다.

수동 실행:

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/etl-soak-trigger-all.sh"
```

검증 스크립트 동작:

- `docker compose down -v --remove-orphans`로 로컬/검증용 DB volume을 초기화한다.
- TripMate Postgres만 먼저 올린다.
- Dagster service image를 이용해 `apps/api` Alembic migration을 `head`까지 적용한다.
- `dataset/` 하위에 법정동코드 CSV가 있으면 `python -m app.cli.legal_dong_code`로 먼저 적재한다.
- `dataset/` 하위에 VWorld SHP ZIP 3종이 있으면 `python -m app.cli.vworld_boundary`로 먼저 적재한다.
- migration과 기준 파일 적재가 끝난 뒤 Dagster UI/daemon을 시작한다.
- 시작 시각은 `.tmp/etl-soak/started-at`에 UTC epoch으로 기록한다.
- Juso 초기 적재는 공개 패턴을 감안해 매월 10일 전에는 두 달 전, 10일 이후에는 직전 월을 `source_year_month` config로 넘긴다. 필요하면 `TRIPMATE_JUSO_SOAK_SOURCE_YEAR_MONTH=YYYYMM`으로 명시 override한다.

주의:

- 이 스크립트는 DB를 삭제하므로 운영 DB에서 사용하지 않는다.
- 6시간보다 긴 주기는 검증용 config에서 1시간 이내로 낮춘다.
- KHOA 해수욕지수, 갯벌체험지수, 바다갈라짐 체험지수도 soak config에서는 1시간 이내로 낮춘다. quota 소진 위험이 있으면 `TRIPMATE_KHOA_API_KEY`를 빼서 schedule 생성을 막고 수동 실행 결과만 확인한다.
- KHOA 지수 계열은 data.go.kr gateway가 일시적으로 HTTP 500을 돌려줄 수 있으므로 soak config에서는 10분 간격 36회 retry window를 둔다. retry가 모두 소진된 실패만 관리자/Telegram 알림으로 본다.
- OpiNet `fuel_region_code`는 provider가 일시적으로 `areaCode.do` 0건을 반환해도 freshness target 안의 기존 활성 지역코드 cache가 있으면 실패 대신 skipped 회복 상태로 기록한다. 기존 cache가 없거나 freshness가 만료되면 schema drift/인증 문제일 수 있으므로 실패로 둔다.
- AirKorea 일 500회 제한은 운영 config 기준으로 설계했다. retry가 반복되면 제한을 넘을 수 있으므로 job 일시정지 또는 주기 완화를 먼저 검토한다.
- `weather_short_term`은 시군구 대표 격자 264개와 endpoint 3개를 호출하므로 한 번에 약 800회 요청이 발생한다. soak config에서는 KMA HTTP 429를 줄이기 위해 매시 25분 1회로 제한한다.
- 기상청 관광코스 파일 경로 `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`가 없으면 관광코스 job skip은 정상 상태다.

관리자 페이지가 ETL DB를 제대로 보는지 확인하려면 같은 compose stack의 optional admin profile을 사용한다.

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate && scripts/admin-etl-data-smoke-test.sh --keep-running"
```

이 스크립트는 `infra/docker-compose.yml`의 `postgres`를 그대로 쓰며 `api`, `web` service만 admin profile로 추가 기동한다. 기본 관리자 계정으로 로그인 API를 호출하고, `/admin/datasets`, `/admin/datasets/etl_run_logs/rows`, `/admin/login` 웹 응답을 확인한다. 검증 후 브라우저에서는 `http://127.0.0.1:13082/admin/login`과 `http://127.0.0.1:23000`을 같이 확인한다.

장시간 검증 중 10분 단위로 확인할 항목:

- Docker service health
- Dagster UI job 상태와 최근 로그
- `etl_run_logs`의 dataset별 success/failed/skipped 분포
- 주소, 경계, 유가, 휴게소, 날씨, 대기질 serving table row count 증가 여부
- `.tmp/dagster-logs/etl/rest_area_fk_mismatch/`의 FK 불일치 로그 누적 여부
- API quota 오류, 인증 오류, provider schema drift 오류
- 관리자 페이지와 공개 API에서 적재된 주요 데이터가 조회되는지 여부

## live 데이터 획득 테스트

실제 provider 호출은 명시 opt-in으로만 실행한다.

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate/apps/api && TRIPMATE_LIVE_ETL_TESTS=1 uv run pytest -q tests/test_dagster_etl.py -m live"
```

현재 live smoke는 data.go.kr 법정동코드 파일 다운로드를 수행한다. 인증키 원문은 테스트 출력과 저장 payload에 남기지 않는다.

## VWorld SHP 수동 적재

VWorld SHP는 Dagster가 자동 다운로드하지 않는다. 운영자가 ZIP 파일을 확보한 뒤 backend command로 적재한다.

```bash
wsl.exe -e bash -lc "cd ~/dev/tripmate/apps/api && uv run python -m app.cli.vworld_boundary /path/to/N3A_G0010000.zip /path/to/N3A_G0100000.zip /path/to/N3A_G0110000.zip"
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

현재 단계에서는 Telegram 실제 발송 worker가 아직 없다. Dagster job이 마지막 재시도까지 실패했다고 판단한 경우에만 retry 소진 실패를 outbox에 남기는 것까지 구현되어 있다.

Dagster job은 실행 시작 로그를 먼저 커밋한 뒤 데이터 적재 트랜잭션과 성공/실패 로그 갱신 트랜잭션을 분리한다. 적재 도중 DB 오류가 발생해도 시작 로그와 retry 소진 실패 알림이 함께 롤백되지 않도록 하기 위한 규칙이다.

ETL 실패 메시지와 outbox payload는 `serviceKey`, `certkey`, `apiKey`, `token` 계열 query parameter와 현재 설정된 data.go.kr 인증키 값을 마스킹한다.

## 반복 오류 방지

- Docker 명령은 WSL2에서 실행한다.
- Dagster job에서 backend import가 실패하면 `PYTHONPATH`, `TRIPMATE_API_DIR`, `/app` mount를 먼저 확인한다.
- Dagster container 안에서 `localhost`는 container 자신이다. TripMate 앱 DB는 `postgres:5432`로 접근한다.
- Windows/WSL test에서는 앱 DB가 `localhost:55432`로 노출된다.
- 실패 알림은 첫 실패가 아니라 Dagster retry 소진 후에만 생성한다. `context.retry_number >= retry_max_attempts` 기준을 유지한다.
- ETL 실행 로그와 실제 데이터 적재를 같은 DB 트랜잭션에 묶지 않는다.
- 외부 API 예외 문자열에는 요청 URL이 들어갈 수 있다. 실패 로그와 Telegram outbox에 넣기 전에 `serviceKey`, `certkey`, `apiKey`, `token` 계열 query parameter와 설정된 인증키 원문을 반드시 마스킹한다.
- 새 ETL을 추가하면 `config/etl-datasets.json`, `apps/api/app/dagster_etl/registry.py`, `docs/data-sources.md`, 이 runbook을 함께 갱신한다.
- 저장되는 시각 컬럼에 `datetime.now(UTC)`, `timezone.utc`, `replace(tzinfo=UTC)`를 사용하지 않는다. provider 원문이 UTC를 명시하는 경우에도 저장 전 KST로 변환하고, 원문 문자열은 raw payload에 보존한다.
