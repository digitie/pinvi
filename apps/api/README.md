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
- pyopinet 기반 OpiNet 유가 adapter
- pykrtourapi 기반 KTO TourAPI client 설정 경계
- pykex 기반 한국도로공사 KEX OpenAPI client 설정 경계
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

OpiNet 유가 adapter는 pyopinet의 `opinet` 패키지를 사용한다. 로컬 키는 커밋하지 않는
`.env`에 아래처럼 둔다.

```bash
TRIPMATE_OPINET_API_KEY=발급받은_키
TRIPMATE_OPINET_TIMEOUT_SECONDS=10
TRIPMATE_OPINET_MAX_RETRIES=2
TRIPMATE_OPINET_RETRY_BACKOFF_SECONDS=0.5
```

KTO TourAPI는 adapter 없이 `pykrtourapi`의 `KrTourApiClient`와 `TourApiHubClient`를 직접 사용한다.
로컬 키는 `.env`에 아래처럼 둔다.

```bash
TRIPMATE_KTO_SERVICE_KEY=공공데이터포털_decoding_인증키
TRIPMATE_KTO_MOBILE_APP=TripMate
TRIPMATE_KTO_MOBILE_OS=WEB
TRIPMATE_KTO_TIMEOUT_SECONDS=10
TRIPMATE_KTO_MAX_RETRIES=2
```

한국도로공사 OpenAPI는 adapter 없이 `pykex`의 `KexClient`를 직접 사용한다. 로컬 키는
`.env`에 아래처럼 둔다.

```bash
TRIPMATE_KEX_EX_API_KEY=data.ex.co.kr_인증키
TRIPMATE_KEX_GO_API_KEY=data.go.kr_decoding_인증키
TRIPMATE_KEX_TIMEOUT_SECONDS=10
TRIPMATE_KEX_MAX_RETRIES=2
TRIPMATE_KEX_RETRY_BACKOFF_SECONDS=0.5
```

기존 로컬 `.env`의 `TRIPMATE_EXPRESSWAY_API_KEY`, `TRIPMATE_DATA_GO_SERVICE_KEY`도
fallback으로 읽는다.

Run the API:

```bash
uv run uvicorn app.main:app --reload
```

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

Run the pykrtourapi integration contract test in WSL:

```bash
cd apps/api
. .venv-wsl/bin/activate
pytest -q tests/test_kto_pykrtourapi.py
```

Run the pykex integration contract test in WSL:

```bash
cd apps/api
. .venv-wsl/bin/activate
pip install -e /mnt/f/dev/pykex
pytest -q tests/test_kex_pykex.py
```

KTO 연동 세부 계약과 운영 절차는 `docs/api/kto-tourapi.md`, `docs/runbooks/kto-tourapi.md`를 따른다.
