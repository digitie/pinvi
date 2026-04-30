# TripMate API

FastAPI backend for TripMate.

## Current Scope

This package currently provides the Phase 1 backend baseline:

- FastAPI application factory
- `/health`
- `/health/db`
- SQLAlchemy 2 base/session setup
- Alembic migration setup
- KMA DFS weather grid conversion helper
- Juso road-address parser and legal-dong code loader
- Initial core tables:
  - `users`
  - `sessions`
  - `trips`
  - `trip_days`
  - `address_raw_juso_road_address`
  - `address_code_standard`

Full authentication endpoints are planned for Phase 2.

## Local Commands

The backend test baseline is now `WSL2 + Docker Postgres/PostGIS`.

Start Postgres/PostGIS from the repo root:

```bash
docker compose -f infra/docker-compose.yml up -d
```

The container is published on `localhost:55432` to avoid conflicts with other local stacks.

Install dependencies after `uv` is available:

```bash
uv sync --group dev
```

For WSL-based checks, create a Linux virtualenv once:

```bash
cd apps/api
python3 -m venv .venv-wsl
. .venv-wsl/bin/activate
pip install -e . pytest ruff mypy httpx
```

Run the API:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

TripMate 직접 로컬 개발은 API 포트 `8001`, 웹 포트 `3001`을 사용한다. 이 workspace에서는 다른 로컬 서비스가 `8000`을 사용할 수 있으므로 host-facing API 확인 포트로 쓰지 않는다.

Run checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

Run migrations:

```bash
uv run alembic upgrade head
```

Run the Juso ETL target tests in WSL:

```bash
cd apps/api
. .venv-wsl/bin/activate
pytest -q tests/test_juso_parser.py tests/test_juso_legal_dong_loader.py
```
