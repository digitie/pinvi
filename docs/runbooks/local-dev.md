# Local Development Runbook

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
cd apps/api
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

WSL 기준 API 검사:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && python3 -m venv .venv-wsl"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pip install -e . pytest ruff mypy httpx"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_juso_parser.py tests/test_juso_legal_dong_loader.py tests/test_model_metadata.py tests/test_migration_contract.py"
```

## 로컬 DB

Postgres/PostGIS는 다음 명령으로 실행한다.

```bash
docker compose -f infra/docker-compose.yml up -d
```

TripMate 로컬 DB 포트는 다른 스택과 충돌을 피하기 위해 `55432`를 사용한다.

DB health check:

```bash
docker compose -f infra/docker-compose.yml ps
```

Migration:

```bash
cd apps/api
uv run alembic upgrade head
```

API 실행:

```bash
cd apps/api
uv run uvicorn app.main:app --reload
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

- 현재 웹앱 기준선은 Windows PowerShell에서 검증했다.
- 백엔드와 Docker 스택이 추가되면 로컬 개발 표준은 WSL2 + Docker로 맞춘다.
- ODROID M1S 배포 절차는 `scripts/deploy.sh`와 `docs/runbooks/deploy.md`가 생길 때 별도로 검증한다.
