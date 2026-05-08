# ODROID Docker 운영 안내

## 범위

ODROID M1S Ubuntu 24.04에서 TripMate PostgreSQL/PostGIS와 Dagster ETL 런타임을 Docker Compose로 실행하기 위한 기준이다. 실제 원격 배포 자동화, 무중단 배포, rollback은 아직 별도 `scripts/deploy.sh`로 분리되지 않았다.

## 전제

- OS: Ubuntu 24.04
- Docker Engine과 Docker Compose plugin 설치
- 저장소 checkout 경로 예: `/opt/tripmate`
- 운영 비밀값은 서버 로컬 `.env`에 저장하고 Git에 포함하지 않는다.
- `dataset/` 하위에는 운영자가 직접 확보한 VWorld SHP ZIP, 법정동코드 CSV, 기상청 관광코스 파일 등을 둔다.

필수 `.env` 예:

```text
TRIPMATE_DATA_GO_SERVICE_KEY=...
TRIPMATE_OPINET_API_KEY=...
TRIPMATE_EXPRESSWAY_API_KEY=...
```

실제 값을 문서, 이슈, 로그에 남기지 않는다.

## 시작

먼저 Docker/OS/.env/디스크/Compose 구성을 점검한다. 이 명령은 secret 값을 펼친 compose config 전체를 출력하지 않고 service 이름만 확인한다.

```bash
cd /opt/tripmate
scripts/odroid-docker-doctor.sh
```

ODROID에서 직접 실행:

```bash
cd /opt/tripmate
scripts/odroid-docker-start.sh
```

스크립트가 하는 일:

- Linux 환경과 Docker Compose plugin 존재 여부를 확인한다.
- `.env`가 없으면 중단한다.
- Ubuntu라면 24.04 기준과 다른 버전일 때 경고한다.
- `.tmp/dagster-downloads`, `.tmp/dagster-logs`, `.tmp/etl-soak`, `.tmp/backups`, `dataset/` 디렉터리를 만든다.
- `infra/docker-compose.yml`의 Postgres/PostGIS와 `dagster` service를 빌드/기동한다.
- Postgres와 Dagster가 healthy/running 상태가 될 때까지 기다리고, 실패하면 최근 로그를 출력한다.

Dagster UI 기본 host port:

```text
http://localhost:23000
```

## Migration

현재 migration은 WSL2 또는 ODROID에서 수동으로 실행한다. ODROID에서는 실행 중인 Dagster 이미지 안에서 실행하는 방식을 우선한다. Dagster 이미지에는 Alembic Python 패키지는 있지만 `alembic` CLI entrypoint가 없을 수 있으므로 Python API로 호출한다.

```bash
cd /opt/tripmate
scripts/odroid-docker-migrate.sh
```

## DB 백업과 복구

운영 변경 전에는 서버 로컬에 백업을 남긴다. 백업 파일은 Git에 포함하지 않는 `.tmp/backups/` 아래에 생성한다.

```bash
cd /opt/tripmate
scripts/backup-db.sh
```

특정 파일명으로 백업하려면:

```bash
cd /opt/tripmate
scripts/backup-db.sh --output .tmp/backups/tripmate-before-etl.dump
```

복구는 기존 DB object를 덮어쓰는 작업이므로 점검 창에서 실행한다.

```bash
cd /opt/tripmate
scripts/restore-db.sh --yes --input .tmp/backups/tripmate-before-etl.dump
```

## 운영 주의

- 배포 시 프론트엔드 외부 포트와 백엔드 API 외부 포트는 아직 미정이다. ODROID/reverse proxy 배포 기준이 정해지기 전까지 `3000`, `8000`, `13082`, `18082`를 운영 포트로 문서화하거나 스크립트에 고정하지 않는다.
- 컨테이너 내부 포트가 Web `3000`, API `8000`인 것과 운영자가 접속할 외부 host/reverse proxy 포트는 별개다.
- ODROID에서는 CPU와 I/O 여유가 PC보다 작다. 전국 SHP 적재, Juso 전체 파일 적재, OpiNet 전국 시군구 최저가 수집은 동시에 여러 개 돌리지 않는다.
- Juso 전체 주소 파일은 압축 해제 후 1GB 이상이 될 수 있다. loader는 streaming inspect와 5,000건 단위 batch insert를 사용하므로, 운영 중 메모리가 급증하면 이전 코드나 다른 분기에서 ORM `add_all` 방식이 되살아나지 않았는지 먼저 확인한다.
- Juso 초기 적재 또는 복구는 공개가 확인된 월을 Dagster op config `source_year_month`로 명시한다. 매월 10일 전에는 직전 월 파일이 없을 수 있다.
- Dagster local runtime은 현재 `dagster dev` 기반이다. job 동시 실행 제한이 필요해지면 Dagster instance concurrency 설정과 runbook을 함께 갱신한다.
- 운영 schedule은 `config/etl-datasets.json`을 사용한다. 장시간 검증용 `config/etl-datasets.soak.json`은 ODROID 운영 기본값으로 쓰지 않는다.
- `docker compose config` 출력에는 `.env` 값이 펼쳐질 수 있으므로 공유하지 않는다.

## 상태 확인

```bash
cd /opt/tripmate
docker compose -f infra/docker-compose.yml ps
scripts/etl-soak-status.sh
```

`scripts/etl-soak-status.sh`는 이름은 soak지만 앱 DB의 ETL 실행 로그와 Dagster service 상태를 함께 조회하므로 운영 점검에도 쓸 수 있다. 단, 6시간 soak 경과 marker가 없는 경우 해당 줄은 무시한다.

## 관리자 화면 확인

운영 포트/reverse proxy 기준이 확정되기 전까지 관리자 API/Web은 `infra/docker-compose.yml`의 `admin` profile로만 임시 기동한다. 이 profile은 같은 Postgres를 보므로 ETL 적재 데이터가 관리자 데이터 브라우저에 보이는지 확인할 수 있다.

```bash
cd /opt/tripmate
scripts/admin-etl-data-smoke-test.sh --keep-running
```

기본 확인 주소:

```text
admin web: http://127.0.0.1:13082/admin/login
api health: http://127.0.0.1:18082/health
dagster: http://127.0.0.1:23000
```

ODROID에서는 API/Web/Dagster를 장시간 동시에 띄우면 CPU와 I/O 여유가 줄어든다. 데이터 확인이 끝난 뒤 계속 서비스할 목적이 아니라면 `docker compose -f infra/docker-compose.yml stop web api && docker compose -f infra/docker-compose.yml rm -f web api`로 관리자 profile service만 정리한다.

## 후속 보완

- 원격 배포용 `scripts/deploy.sh`
- Dagster job별 리소스 제한과 worker concurrency 운영값
- 장시간 적재 작업을 위한 ODROID swap, storage health 점검 절차
