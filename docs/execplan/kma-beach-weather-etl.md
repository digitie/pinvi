# 기상청 전국 해수욕장 날씨 ETL 실행 계획

## 목적

기상청 전국 해수욕장 날씨 조회서비스의 해수욕장 위치 카탈로그를 내부 표준 장소 DB에 적재하고, 해수욕장별 예보/관측/조석/일출일몰을 raw/serving 계층으로 주기 수집한다.

## 범위

- 해수욕장 카탈로그 xlsx를 읽어 `places`와 `weather_beach_location`에 저장한다.
- 좌표는 EPSG:4326 `longitude`, `latitude`, PostGIS `POINT(4326)`으로 표준화한다.
- 법정동은 V-WORLD 법정동 경계 `ST_Covers`를 우선하고, 해안 좌표가 경계 밖이면 약 5km 이내 가장 가까운 법정동을 보조 매핑한다.
- 도로명주소코드와 도로명주소관리번호는 같은 법정동의 Juso 건물명 정확 일치가 1건일 때만 채운다.
- 날씨 응답은 `weather_raw_beach`와 `weather_serving_beach`로 분리한다.
- Airflow DAG는 자료 제공 주기와 해수욕장 운영 시즌을 반영해 6~8월 중심으로 운영한다.

## 구현 상태

- 완료: SQLAlchemy 모델과 Alembic migration `20260428_0019_kma_beach_weather_tables.py`
- 완료: `apps/api/app/etl/weather/beach.py` 카탈로그/날씨 client와 loader
- 완료: `dags/kma_beach_weather.py` 6개 DAG
- 완료: `config/etl-datasets.json`, `config/etl-datasets.soak.json` dataset 설정
- 완료: loader, Airflow contract, ETL config, model metadata, migration contract 테스트
- 완료: 공식 API 문서와 내부 구현 기준 문서화

## 운영 메모

- 개발 DB에는 2026-04-28 기준 마이그레이션을 적용하고 해수욕장 카탈로그 420건을 적재했다.
- 개발 DB의 V-WORLD 경계 적재 후 법정동 매핑은 406건이다.
- 개발 DB에 Juso 도로명주소 serving snapshot이 없어 도로명주소코드 매핑은 0건이다. Juso 도로명주소 적재 후 카탈로그 ETL을 다시 실행하면 건물명 정확 일치분만 채워진다.
- 날씨 endpoint 전체 즉시 실행은 활성 해수욕장 수만큼 반복 호출하므로 data.go.kr quota와 시즌 운영 여부를 확인한 뒤 수동 trigger한다.

## 검증

- WSL2: `.venv-wsl/bin/ruff check app/models/weather.py app/etl/weather/beach.py app/core/etl_config.py tests/test_kma_beach_weather_loader.py tests/test_airflow_dags.py tests/test_etl_config.py tests/test_etl_soak_config.py tests/test_model_metadata.py tests/test_migration_contract.py ../../dags/kma_beach_weather.py`
- WSL2: `.venv-wsl/bin/python -m pytest tests/test_kma_beach_weather_loader.py tests/test_airflow_dags.py tests/test_etl_config.py tests/test_etl_soak_config.py tests/test_model_metadata.py tests/test_migration_contract.py`
- WSL2: `.venv-wsl/bin/python -m alembic upgrade head`
- PowerShell: `git diff --check`
