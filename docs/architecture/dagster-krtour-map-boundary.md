# Dagster와 python-krtour-map 경계

TripMate는 Dagster를 실행하는 애플리케이션이다. API 수집 결과를 feature/source/weather/price 계약으로 가공하는 세부 ETL 계약은 `python-krtour-map`에 둔다.

Canonical 문서:

- [Dagster boundary](https://github.com/digitie/python-krtour-map/blob/main/docs/dagster-boundary.md)

TripMate가 가진다:

- Dagster package import
- `@op`, `@job`, `ScheduleDefinition`, `Definitions`
- Docker Compose와 `dagster dev`
- DB session/resource 주입
- `etl_run_logs`, 관리자 알림, Telegram outbox
- retry 소진 판단과 운영 runbook
- Odroid 단일 worker 환경의 concurrency=1 실행 설정
- TripMate 제품 DB와 API serving 조립

새 ETL을 만들 때 TripMate에 임시 가공 함수를 두지 않는다. TripMate의 Dagster layer는 실행 shell이고, 데이터 정규화, 중복 후보 산출, feature 저장 계약은 `python-krtour-map`이 canonical이다.
