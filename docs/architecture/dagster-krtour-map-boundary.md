# Dagster와 python-krtour-map 경계

TripMate는 Dagster를 실행하는 애플리케이션이다. API 수집 결과를 feature/source/weather/price 계약으로 가공하는 세부 ETL 계약은 `python-krtour-map`에 둔다.

## python-krtour-map이 가진다

- `krtour_map.dagster.DagsterEtlExecution`
- `krtour_map.dagster.DagsterEtlRun`
- `krtour_map.dagster.EtlJobSpec`
- `krtour_map.dagster.EtlRunIdentity`
- logical datetime, `run_type`, 수동 backfill config 파싱
- `json_ready`, download/log directory helper, schedule env gate helper
- provider typed model을 `Feature`, `SourceRecord`, `WeatherValue`, `PriceValue`로 정규화하는 순수 함수

## TripMate가 가진다

- Dagster package import
- `@op`, `@job`, `ScheduleDefinition`, `Definitions`
- Docker Compose와 `dagster dev`
- DB session/resource 주입
- `etl_run_logs`, 관리자 알림, Telegram outbox
- retry 소진 판단과 운영 runbook

## 코드 기준

`apps/api/app/dagster_etl/runtime.py`는 `krtour_map.dagster` 계약을 import해 다시 노출한다. TripMate 내부 loader와 test는 기존 import 경로를 쓸 수 있지만, 새 공통 ETL 계약은 `python-krtour-map`에서 먼저 추가한다.

새 ETL을 만들 때 TripMate에 임시 가공 함수를 두지 않는다. TripMate의 Dagster layer는 실행 shell이고, 데이터 정규화와 feature 저장 계약은 `python-krtour-map`이 canonical이다.
