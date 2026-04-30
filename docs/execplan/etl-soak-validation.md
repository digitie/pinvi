# ETL 장시간 검증 실행 계획

## 목적

TripMate 주소, 경계, 유가, 휴게소, 날씨, 대기질, 해수욕장 통합 ETL이 초기화된 DB에서 실제 Airflow 런타임으로 문제없이 동작하는지 6시간 확인한다. 6시간보다 긴 주기의 데이터셋은 운영 config를 바꾸지 않고 검증용 config에서만 1시간 이내 schedule로 낮춘다. 단, KHOA 생활해양예보지수 3종은 하루 2회 quota라 soak에서도 12시간 주기를 유지하고 retry를 0으로 둔다.

## 현재 변경

- `config/etl-datasets.soak.json` 추가
- `infra/docker-compose.yml`에서 `TRIPMATE_ETL_CONFIG_PATH` 환경변수 override 허용
- `infra/docker-compose.yml`에서 `dataset/`을 Airflow 컨테이너 read-only mount
- `scripts/etl-soak-reset-and-start.sh` 추가
- `scripts/etl-soak-trigger-all.sh` 추가
- `scripts/etl-soak-status.sh` 추가
- `scripts/odroid-docker-start.sh` 추가
- `app.cli.legal_dong_code` 추가
- Juso 도로명주소/관련 지번 loader를 대용량 파일용 streaming inspect + batch insert 방식으로 개선
- Juso DAG에 초기 적재/복구용 `source_year_month` 수동 override 추가
- KHOA 생활해양예보지수 3종 retry를 quota 보호를 위해 0으로 조정

## 실행 순서

1. WSL2 Ubuntu에서 `scripts/etl-soak-reset-and-start.sh --yes --duration-hours 6 --check-interval-minutes 10`를 실행한다.
2. 빈 DB에 Alembic migration을 적용한다.
3. `dataset/` 하위 법정동코드 CSV와 VWorld SHP ZIP 3종을 먼저 적재한다.
4. Airflow DAG 전체를 수동 trigger한다.
5. 10분 단위로 `scripts/etl-soak-status.sh`를 실행한다.
6. 실패 DAG/task가 있으면 로그를 확인하고 코드/문서/스크립트를 보완한다.
7. 6시간 이후 최종 점검에서 failed/up_for_retry task, 실패 ETL log, row count, lint/typecheck/test, 관리자 페이지 표시를 확인한다.
8. 문제가 없으면 커밋하고 GitHub에 push한다.

## 10분 점검 기준

- Docker service가 healthy 또는 running 상태인지 확인한다.
- Airflow `dag_run`과 `task_instance`에서 failed/up_for_retry 상태를 확인한다.
- `etl_run_logs`에서 dataset별 status 분포를 확인한다.
- 주요 serving table row count가 기대 방향으로 증가하는지 확인한다.
- 외부 API quota, 인증 실패, schema drift가 반복되면 즉시 원인을 분리한다.

## 현재 soak 특이사항

- Juso 202604 파일은 2026-05-01 KST 기준 아직 공개되지 않아 정상적으로 skip한다. 초기 DB 적재는 `source_year_month=202603`을 사용한다.
- Juso 도로명주소 전체분은 압축 해제 후 약 1.1GB TXT를 검사/파싱한다. ODROID에서는 raw/serving 모두 batch insert로 유지하고, worker 메모리 추이를 함께 본다.
- 해수욕장 단기예보는 420개 해수욕장과 endpoint/category/예보시각 조합으로 저장되어 1회 수집에도 `weather_serving_beach`가 수십만 행이 될 수 있다. row count만으로 중복 폭증으로 판단하지 않고 endpoint별 raw/serving 분포를 같이 확인한다.
- `SERVICE KEY IS NOT REGISTERED`가 확인된 API는 현재 없다. KHOA 해수욕지수, 갯벌체험지수, 바다갈라짐 체험지수는 2026-04-30 재시도에서 HTTP 500 `Unexpected errors`를 반환했다.
- 이후 성공 run이 생긴 데이터셋은 이전 실패 관리자 알림과 Telegram outbox pending을 자동 resolved/cancelled 처리한다.

## 효율화 후보

- Juso 전체 적재는 raw/serving batch insert가 기본이다. ODROID에서 여전히 오래 걸리면 batch 크기, FK 검증 방식, serving 재구성 SQL을 별도 측정한다.
- VWorld SHP 적재가 길면 파일별 batch commit과 geometry transform 시간을 분리해서 기록한다.
- OpiNet 전국 시군구 최저가 수집은 provider call 수가 많으므로 실패 지역 재시도 범위를 별도 큐로 분리하는 방안을 검토한다.
- 날씨 초단기 수집은 경계 기반 격자 수에 따라 API call 수가 커지므로 대표 격자 생성 결과를 고정 cache로 유지한다.

## 완료 조건

- 6시간 이상 Airflow 런타임이 유지된다.
- 운영상 정상 skip인 `kma_recommended_tour_course` 파일 미설정, Juso 미공개 월 skip, KHOA provider 500 외에 설명되지 않은 failed task가 없다.
- 관리자 페이지에서 주요 ETL/테이블 데이터가 조회된다.
- ETL 실패가 발생한 경우 retry 소진 실패 로그와 관리자/Telegram outbox 기록이 남는다.
- WSL2 기준 backend lint, format check, mypy, pytest가 통과한다.
- 관련 문서가 한국어로 갱신된다.
