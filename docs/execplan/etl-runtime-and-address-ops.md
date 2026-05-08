# ETL 런타임과 주소 운영 실행 계획 (이전 기록)

이 문서는 과거 ETL runtime 도입 계획의 보존 기록이다.

현재 TripMate ETL orchestration은 Dagster로 전환됐으며, 최신 실행 계획과 운영 기준은 아래 문서를 따른다.

- `docs/execplan/dagster-etl-migration.md`
- `docs/runbooks/etl.md`
- `apps/api/app/dagster_etl/`

주소/Juso/법정동코드/VWorld loader와 DB 스키마 정책은 여전히 유효하며, orchestration 계층은 Dagster 기준으로 유지한다.
