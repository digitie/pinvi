# ETL 런타임과 주소 운영 실행 계획

## 목표

주소 기준 데이터와 행정경계 데이터를 반복 가능하게 운영하기 위한 첫 런타임 단위다.

범위:

- Airflow 로컬 런타임을 Docker Compose에 연결한다.
- 기존 법정동코드 DAG를 실제 Airflow 컨테이너에서 import 가능하게 만든다.
- Juso 월간 전체 주소 업데이트 DAG를 추가한다.
- VWorld SHP는 자동 다운로드가 아니라 운영자가 ZIP을 넘기는 command로 적재한다.
- ETL 실패 로그, 관리자 알림, 권리자 Telegram 시스템 알림 outbox의 DB 기반을 만든다.

## 결정

- Docker와 Airflow 검증은 WSL2 Ubuntu에서만 실행한다.
- Airflow는 3.2.1 이미지를 기준으로 한다.
- Airflow 3.x에서는 웹 UI/API 프로세스 command가 `api-server`다. Compose service 이름은 요청과 운영 가독성을 위해 `airflow-webserver`로 둔다.
- Airflow metadata DB는 앱 DB와 분리해 `airflow-postgres`를 사용한다.
- TripMate 앱 DB는 기존 `postgres` PostGIS 서비스를 계속 사용한다.
- Airflow worker가 backend ETL 코드를 import할 수 있도록 `apps/api`를 `/opt/tripmate/apps/api`에 mount하고 `PYTHONPATH`를 지정한다.
- 데이터셋별 retry 설정은 `config/etl-datasets.json`을 기준으로 한다.
- ETL 실행 결과는 `etl_run_logs`에 저장한다.
- retry 소진 실패는 `admin_notifications`와 `telegram_system_notification_outbox`에 기록한다. 실제 Telegram 발송 worker는 후속 작업이다.

## 구현 순서

1. 공통 ETL 설정 파일과 loader를 추가한다.
2. ETL 실행 로그/알림/outbox 테이블과 사용자 권한 구분 필드를 추가한다.
3. Airflow Compose runtime과 Airflow custom image를 추가한다.
4. 법정동코드 DAG를 공통 설정과 ETL 로그에 연결한다.
5. Juso 월간 주소 DAG를 추가한다.
6. VWorld 운영 import command를 추가한다.
7. 행정경계 조회 API를 추가한다.
8. WSL2에서 test, lint, typecheck, migration, Airflow DAG import smoke를 검증한다.

## Juso 월간 업데이트 정책

- DAG schedule은 `0 4 10-31 * *`다.
- task 내부에서 `logical_date.day < 10`이면 skip한다.
- 같은 `YYYYMM` run key가 이미 성공했으면 skip한다.
- 실행일이 DB의 어떤 여행계획 날짜에 포함되면 skip한다.
- 10일 이후 여행계획이 없는 첫 실행일에 전체 주소 ZIP을 다운로드하고 serving snapshot을 갱신한다.
- source year-month는 DAG logical date의 `YYYYMM`을 사용한다.

## VWorld 운영 적재 정책

- VWorld SHP는 자동 다운로드하지 않는다.
- 운영자는 `N3A_G0010000.zip`, `N3A_G0100000.zip`, `N3A_G0110000.zip` 중 하나 이상을 command에 전달한다.
- ZIP 파일명으로 `sido`, `sigungu`, `legal_dong` layer를 판정한다.
- 같은 layer의 기존 import batch는 loader 정책에 따라 교체된다.
- 적재 결과는 `etl_run_logs`에 남긴다.

## 반복 오류 방지

- Docker 명령은 Windows PowerShell에서 직접 실행하지 않는다.
- `docker compose`와 backend test는 WSL2에서 실행한다.
- Airflow 3.x 웹 UI service는 이름이 `airflow-webserver`여도 command는 `api-server`다.
- backend 코드가 Airflow task에서 import되어야 하므로 Airflow compose의 `PYTHONPATH`와 `TRIPMATE_API_DIR`를 지우지 않는다.
- Airflow container의 앱 DB URL은 `localhost`가 아니라 compose service 이름인 `postgres`를 사용한다.
- 로컬 Windows/WSL test URL은 `localhost:55432`를 사용한다.

## 검증 계획

- `python -m pytest`
- `python -m ruff check .`
- `python -m ruff format --check .`
- `python -m mypy .`
- 임시 DB 기준 `alembic upgrade head`
- `docker compose -f infra/docker-compose.yml config`
- Airflow image build
- Airflow 컨테이너에서 DAG list 또는 DAG import smoke
