# Dagster ETL 전환 실행 계획

## 목적

기존 ETL orchestration을 Dagster job/schedule 기반으로 전환한다. 기존 backend ETL loader, DB schema, 실행 로그, 실패 알림 정책은 유지하고 orchestration 계층만 교체한다.

## 영향 범위

- `apps/api/app/dagster_etl/`: Dagster job, schedule, 공통 실행기, 데이터셋 registry
- `infra/docker-compose.yml`: Dagster UI/daemon 실행 service
- `scripts/etl-soak-*.sh`, `scripts/odroid-docker-*.sh`: 장시간 검증과 ODROID 실행 명령
- `apps/api/tests/test_dagster_etl.py`: job/schedule/import, retry/skip/알림, live data 획득 smoke
- `docs/runbooks/etl.md`, `docs/runbooks/local-dev.md`, `docs/architecture.md`, `docs/data-sources.md`: 운영 문서
- `AGENTS.md`, `skills/dagster-etl.ko.md`: 작업 기준

## 결정

- Dagster 정의는 API package 내부 `app.dagster_etl`에 둔다.
- Docker Compose의 `dagster` service는 `dagster dev`로 UI와 daemon을 함께 띄운다.
- 로컬 Dagster UI는 `http://localhost:23000`을 기본값으로 한다.
- schedule timezone은 `Asia/Seoul`로 고정한다.
- `config/etl-datasets.json`의 schedule/retry/freshness 값을 Dagster job/schedule의 단일 운영 기준으로 재사용한다.
- 실패 알림은 Dagster retry가 소진된 마지막 시도에서만 생성한다.
- 인증키가 필요한 KHOA 계열 저쿼터 데이터셋은 키가 없으면 schedule을 생성하지 않고, 수동 실행은 skipped ETL log로 남긴다.
- Juso 수동 backfill은 op config `source_year_month: YYYYMM`으로 받는다.

## 테스트 매트릭스

- Dagster job이 모든 ETL spec을 커버하는지 확인한다.
- schedule cron과 timezone이 `config/etl-datasets.json`과 일치하는지 확인한다.
- 인증키 유무에 따른 KHOA schedule enable/disable을 확인한다.
- KST logical datetime, run key, Juso manual config validation을 확인한다.
- 성공, skip, retry 미소진 실패, retry 소진 실패의 `etl_run_logs`와 알림 생성 여부를 확인한다.
- Dagster `execute_in_process`로 실제 job wrapper가 공통 실행기를 호출하는지 확인한다.
- `TRIPMATE_LIVE_ETL_TESTS=1`일 때 data.go.kr 법정동코드 파일 다운로드 live smoke를 실행한다.

## 완료 조건

- 이전 orchestration service와 job 파일이 실행 경로에서 제거된다.
- Dagster UI/daemon이 Compose로 함께 뜬다.
- 관련 테스트가 WSL2에서 통과한다.
- live data 획득 smoke를 실행하고 결과를 보고한다.
- 운영 문서가 Dagster 기준으로 갱신된다.
