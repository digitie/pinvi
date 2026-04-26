# 로컬 개발 실행 안내

## 기본 원칙

- 로컬 Docker, Docker Compose, PostgreSQL/PostGIS, Airflow, backend test, Alembic migration 검증은 WSL2 Ubuntu에서 실행한다.
- Windows PowerShell은 문서 확인, Git 상태 확인, 간단한 파일 탐색 같은 보조 작업에만 사용한다.
- Docker 명령을 Windows PowerShell에서 직접 실행하지 않는다.
- 이 저장소의 WSL2 경로는 `/mnt/f/dev/mapplan`을 기준으로 한다.
- 프로젝트 문서는 한국어로 작성한다. 코드 식별자, 명령어, 테이블명, API endpoint, provider 고유 명칭은 원문을 유지할 수 있다.

## 현재 가능한 작업

현재는 Next.js 웹앱과 FastAPI API 골격을 로컬 실행할 수 있다.

```bash
npm install
npm run dev
```

기본 주소:

```text
http://localhost:3000
```

이미 3000 포트를 사용 중이면 다른 포트를 지정한다.

```bash
npm --workspace apps/web run dev -- --port 3001
```

## 검사 명령

웹앱:

```bash
npm run lint
npm run typecheck
npm run build
```

웹앱 workspace를 직접 대상으로 실행할 수도 있다.

```bash
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
```

API:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv sync --group dev"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run pytest"
```

`uv`가 WSL2에 없고 `.venv-wsl` 가상환경을 사용할 때:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && python3 -m venv .venv-wsl"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pip install -e . pytest ruff mypy httpx"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_juso_parser.py tests/test_juso_download.py tests/test_juso_legal_dong_loader.py tests/test_juso_address_dataset_loader.py tests/test_juso_pipeline.py tests/test_legal_dong_code_loader.py tests/test_vworld_boundary_loader.py tests/test_model_metadata.py tests/test_migration_contract.py"
```

Airflow DAG contract check:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_airflow_legal_dong_dag.py"
```

## 로컬 DB

Postgres/PostGIS는 WSL2에서 다음 명령으로 실행한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d"
```

TripMate 로컬 DB 포트는 다른 스택과 충돌을 피하기 위해 `55432`를 사용한다.

DB health check:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml ps"
```

Migration:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run alembic upgrade head"
```

빈 DB 기준 migration upgrade를 검증할 때:

```bash
wsl.exe -e bash -lc "docker exec tripmate-postgres dropdb -U tripmate --if-exists tripmate_migration_check && docker exec tripmate-postgres createdb -U tripmate -O tripmate tripmate_migration_check"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && TRIPMATE_DATABASE_URL='postgresql+psycopg://tripmate:tripmate_dev_password@localhost:55432/tripmate_migration_check' uv run alembic upgrade head"
wsl.exe -e bash -lc "docker exec tripmate-postgres dropdb -U tripmate --if-exists tripmate_migration_check"
```

## PostgreSQL 마이그레이션 체크리스트

- PostgreSQL 식별자 최대 길이는 63바이트다. 긴 테이블명과 컬럼명을 쓰는 FK/index/unique/check 제약은 자동 이름 생성에 맡기지 않는다.
- 이번 Juso 스키마에서는 아래처럼 짧은 명시적 이름을 사용한다.
  - FK: `fk_addr_serv_rel_jibun_ramno`
  - Index: `ix_asjrj_ramno`
- 모델 메타데이터 검사만 통과했다고 마이그레이션이 안전한 것은 아니다. 스키마 변경 후에는 WSL2 Docker PostgreSQL/PostGIS에서 실제 `uv run alembic upgrade head`를 반드시 실행한다.
- Juso serving 적재 순서는 고정이다. `address_serving_juso_road_address`를 먼저 재구성한 뒤 `address_serving_juso_related_jibun`을 적재한다.
- `legal_dong_code`, `road_name_code`, `administrative_dong_code`, `road_address_management_no`는 선행 0 보존이 필요하므로 숫자로 캐스팅하지 않고 문자열로 유지한다.
- 자세한 배경과 결정은 `docs/decisions/20260425-postgres-migration-constraints.md`를 따른다.

API 실행:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run uvicorn app.main:app --reload"
```

API health check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

## 아직 없는 로컬 스택

다음 항목은 계획에만 있으며 아직 실행할 수 없다.

- Airflow Docker Compose
- Playwright E2E
- ODROID 배포 스크립트

## 다음 기준선 작업

1. `scripts/bootstrap-local.sh`와 `scripts/test-local.sh`를 추가한다.
2. 인증 API 구현과 `docs/api/auth.md` 계약을 실제 엔드포인트에 맞춰 확장한다.
3. `places`와 provider cache schema를 추가하기 전에 `docs/data-sources.md`를 확인한다.

## 운영 환경 메모

- 웹앱만 다루는 npm 명령은 Windows 또는 WSL2에서 실행할 수 있으나, backend와 Docker 스택이 관련되면 WSL2를 표준으로 한다.
- 백엔드와 Docker 스택의 로컬 개발 표준은 WSL2 + Docker다.
- ODROID M1S 배포 절차는 `scripts/deploy.sh`와 `docs/runbooks/deploy.md`가 생길 때 별도로 검증한다.
