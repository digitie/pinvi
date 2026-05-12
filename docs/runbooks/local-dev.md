# 로컬 개발 실행 안내

## 기본 원칙

- 저장소 명령은 WSL2 Ubuntu에서 실행하는 것을 최우선으로 한다.
- 로컬 Docker, Docker Compose, PostgreSQL/PostGIS, Dagster, backend test, Alembic migration 검증은 WSL2 Ubuntu에서 실행한다.
- Windows PowerShell은 WSL2 명령을 감싸서 실행하거나, 문서 확인, Git 상태 확인, 간단한 파일 탐색 같은 보조 작업에만 사용한다.
- Docker 명령을 Windows PowerShell에서 직접 실행하지 않는다.
- `rg` 검색은 PowerShell `rg.exe`를 쓰지 않는다. WSL에서도 WindowsApps 경로가 먼저 잡힐 수 있으므로 `PATH=/usr/local/bin:/usr/bin:/bin rg ...`처럼 WSL native ripgrep만 사용한다.
- Windows 쪽 현재 저장소의 WSL2 mount 경로는 `/mnt/f/dev/mapplan`이다. 검증 명령은 이 NTFS 경로에서 직접 실행하지 않고 WSL 내부 볼륨의 `~/tripmate-workspaces/mapplan` 미러에서 실행한다.
- 테스트, 빌드, lint, typecheck, formatter, backend test, Alembic, Dagster 검증 전에는 `/mnt/f/dev/mapplan`에서 WSL 미러로 동기화하고, 명령 완료 후에는 WSL 미러의 변경을 `/mnt/f/dev/mapplan`으로 다시 복사한다.
- 프로젝트 문서는 한국어로 작성한다. 코드 식별자, 명령어, 테이블명, API endpoint, provider 고유 명칭은 원문을 유지할 수 있다.

## WSL 내부 볼륨 미러

NTFS에 있는 `/mnt/f/dev/mapplan`에서 테스트를 직접 실행하면 파일 접근이 느리다. 검증 명령은 WSL ext4 내부 경로 `~/tripmate-workspaces/mapplan`에서 실행한다. 현재 프로젝트 디렉토리(`F:\dev\mapplan`)를 최종 원본으로 두고, WSL 미러는 빠른 테스트용 복제본으로 다룬다.

초기 생성은 필요할 때 한 번만 수행한다.

```bash
wsl.exe -e bash -lc "mkdir -p ~/tripmate-workspaces && git clone /mnt/f/dev/mapplan ~/tripmate-workspaces/mapplan"
```

검증 명령을 실행하기 전에는 현재 프로젝트 디렉토리의 변경을 WSL 미러로 보낸다.

```bash
wsl.exe -e bash -lc "rsync -a --delete --exclude='.git/' --exclude='node_modules/' --exclude='.next/' --exclude='.venv/' --exclude='.venv-wsl/' --exclude='.pytest_cache/' --exclude='.mypy_cache/' --exclude='.ruff_cache/' /mnt/f/dev/mapplan/ ~/tripmate-workspaces/mapplan/"
```

검증 명령은 WSL 미러에서 실행한다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm run lint"
```

명령이 완료되면 WSL 미러의 변경을 현재 프로젝트 디렉토리로 복사한다. 이 되돌림 복사는 동시 편집 파일을 지우지 않도록 기본적으로 `--delete`를 쓰지 않는다.

```bash
wsl.exe -e bash -lc "rsync -a --exclude='.git/' --exclude='node_modules/' --exclude='.next/' --exclude='.venv/' --exclude='.venv-wsl/' --exclude='.pytest_cache/' --exclude='.mypy_cache/' --exclude='.ruff_cache/' ~/tripmate-workspaces/mapplan/ /mnt/f/dev/mapplan/"
```

명령이 의도적으로 파일 삭제나 rename을 만들었다면 `git status --short`로 변경 범위를 확인한 뒤 삭제까지 현재 프로젝트 디렉토리에 반영한다. Git stage/commit/push는 별도 지시가 없으면 현재 프로젝트 디렉토리에서 수행한다.

## 검색 명령

PowerShell의 `rg.exe`는 권한 문제로 실패한 사례가 반복됐으므로 사용하지 않는다. WSL 기본 `PATH`도 WindowsApps의 Codex 번들 `rg`를 먼저 잡을 수 있으므로, 검색할 때는 Windows 경로를 제거한 WSL native ripgrep만 사용한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && PATH=/usr/local/bin:/usr/bin:/bin rg -n '검색어' docs apps/api"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && PATH=/usr/local/bin:/usr/bin:/bin rg --files docs apps/api"
```

`PATH=/usr/local/bin:/usr/bin:/bin command -v rg`가 비어 있으면 WSL에 `ripgrep`이 없는 상태다. 이 경우 PowerShell `rg.exe`로 우회하지 말고 WSL에 `ripgrep`을 설치하거나, 설치가 불가능한 경우에만 `git grep`/`grep`을 fallback으로 사용한다.

## 현재 가능한 작업

현재는 Next.js 웹앱과 FastAPI API 골격을 로컬 실행할 수 있다.

## TripMate 포트 기준

`3000`과 `8000`은 이 개발 환경에서 다른 서비스가 사용할 수 있으므로 TripMate의 확인 주소로 쓰지 않는다. 브라우저나 API client가 해당 포트를 보고 있다면 TripMate가 아니라 다른 서비스를 보고 있을 가능성이 높다.

| 구분 | 프론트엔드 | 백엔드 API | 설명 |
| --- | --- | --- | --- |
| 직접 개발 | `http://localhost:3001` | `http://localhost:8001` | Next.js dev server와 `uvicorn` 직접 실행 기준 |
| 앱 Docker smoke | `http://127.0.0.1:13082` | `http://127.0.0.1:18082` | `infra/docker-compose.app.yml`의 host 포트 기준 |
| 배포 | 미정 | 미정 | ODROID/reverse proxy 포트는 아직 결정하지 않는다 |

주의: 컨테이너 내부 포트는 Web `3000`, API `8000`을 계속 쓸 수 있다. 이 값은 컨테이너 안쪽 포트이며, 로컬 브라우저에서 접근할 host 포트와 구분한다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm install"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm run dev"
```

기본 주소:

```text
http://localhost:3001
```

API 서버는 별도 터미널에서 `8001`로 실행한다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
```

웹 포트나 API 포트를 임시로 바꿀 때는 두 값을 함께 맞춘다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && NEXT_PUBLIC_TRIPMATE_API_URL=http://localhost:8011 npm exec --workspace apps/web -- next dev --hostname 0.0.0.0 --port 3011"
```

웹 client의 기본 API URL은 `http://localhost:8001`이다. 명시적인 `NEXT_PUBLIC_TRIPMATE_API_URL` 설정이 있으면 그 값을 우선한다.

## 검사 명령

웹앱:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm run lint"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm run typecheck"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm run build"
```

웹앱 workspace를 직접 대상으로 실행할 수도 있다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm --workspace apps/web run lint"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm --workspace apps/web run typecheck"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && npm --workspace apps/web run build"
```

API:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv sync --group dev"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run ruff check ."
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run ruff format --check ."
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run mypy ."
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run pytest"
```

KTO TourAPI 로컬 설정은 커밋하지 않는 `apps/api/.env`에 둔다. 인증키는 공공데이터포털 decoding 인증키를 사용한다.

```bash
TRIPMATE_KTO_SERVICE_KEY=공공데이터포털_decoding_인증키
TRIPMATE_KTO_MOBILE_APP=TripMate
TRIPMATE_KTO_MOBILE_OS=WEB
TRIPMATE_KTO_TIMEOUT_SECONDS=10
TRIPMATE_KTO_MAX_RETRIES=2
```

KTO 호출 코드는 `visitkorea`의 `KrTourApiClient`와 `TourApiHubClient`를 직접 사용한다. TripMate backend에 별도 KTO adapter/gateway 래퍼를 만들지 않는다.

## 소셜 로그인 로컬 설정 계획

Google/Naver/Kakao 소셜 로그인은 아직 구현 전이다. 구현 후에는 `docs/integrations/social-login.md`와 `docs/execplan/social-login-providers.md`를 기준으로 아래 값을 `apps/api/.env`에 둔다. 실제 secret 값은 커밋하지 않는다.

```bash
TRIPMATE_WEB_BASE_URL=http://localhost:3001
TRIPMATE_OAUTH_CALLBACK_BASE_URL=http://localhost:8001
TRIPMATE_GOOGLE_OAUTH_CLIENT_ID=Google_OAuth_client_id
TRIPMATE_GOOGLE_OAUTH_CLIENT_SECRET=Google_OAuth_client_secret
TRIPMATE_NAVER_OAUTH_CLIENT_ID=Naver_client_id
TRIPMATE_NAVER_OAUTH_CLIENT_SECRET=Naver_client_secret
TRIPMATE_KAKAO_OAUTH_REST_API_KEY=Kakao_REST_API_key
TRIPMATE_KAKAO_OAUTH_CLIENT_SECRET=Kakao_client_secret_if_enabled
TRIPMATE_OAUTH_STATE_TTL_SECONDS=600
TRIPMATE_OAUTH_HTTP_TIMEOUT_SECONDS=5
```

로컬 provider console callback URI:

```text
http://localhost:8001/auth/oauth/google/callback
http://localhost:8001/auth/oauth/naver/callback
http://localhost:8001/auth/oauth/kakao/callback
```

Docker app smoke 기준 callback URI:

```text
http://127.0.0.1:18082/auth/oauth/google/callback
http://127.0.0.1:18082/auth/oauth/naver/callback
http://127.0.0.1:18082/auth/oauth/kakao/callback
```

주의:

- provider client secret은 `apps/web/.env.local`이나 `NEXT_PUBLIC_*` 변수에 넣지 않는다.
- provider access token, refresh token, id token 원문은 DB, 로그, fixture에 저장하지 않는다.
- 배포 도메인이 정해지면 provider console의 redirect URI와 ODROID runbook을 함께 갱신한다.

`uv`가 WSL2에 없고 `.venv-wsl` 가상환경을 사용할 때:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && python3 -m venv .venv-wsl"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && . .venv-wsl/bin/activate && pip install -e . pytest ruff mypy httpx"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_juso_parser.py tests/test_juso_download.py tests/test_juso_legal_dong_loader.py tests/test_juso_address_dataset_loader.py tests/test_juso_pipeline.py tests/test_legal_dong_code_loader.py tests/test_vworld_boundary_loader.py tests/test_model_metadata.py tests/test_migration_contract.py"
```

Dagster ETL contract check:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_dagster_etl.py"
```

## 로컬 DB

Postgres/PostGIS는 WSL2에서 다음 명령으로 실행한다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && docker compose -f infra/docker-compose.yml up -d"
```

TripMate 로컬 DB 포트는 다른 스택과 충돌을 피하기 위해 `55432`를 사용한다.

DB health check:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && docker compose -f infra/docker-compose.yml ps"
```

Migration:

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run alembic upgrade head"
```

빈 DB 기준 migration upgrade를 검증할 때:

```bash
wsl.exe -e bash -lc "docker exec tripmate-postgres dropdb -U tripmate --if-exists tripmate_migration_check && docker exec tripmate-postgres createdb -U tripmate -O tripmate tripmate_migration_check"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && TRIPMATE_DATABASE_URL='postgresql+psycopg://tripmate:tripmate_dev_password@localhost:55432/tripmate_migration_check' uv run alembic upgrade head"
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
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan/apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
```

API health check:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/health/db
```

## Dagster 로컬 스택

Dagster는 Docker Compose로 실행한다. TripMate 로컬 Compose는 Dagster UI와 daemon을 같은 `dagster` service에서 함께 띄운다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && docker compose -f infra/docker-compose.yml up -d postgres dagster"
```

Dagster UI:

```text
http://localhost:23000
```

상세 운영 방법은 `docs/runbooks/etl.md`를 따른다.

## 로컬 ETL 장시간 검증

DB를 초기화하고 로컬 기준 파일을 적재한 뒤 Dagster job을 장시간 검증할 때는 아래 스크립트를 사용한다.

```bash
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && scripts/etl-soak-reset-and-start.sh --yes"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/mapplan && scripts/etl-soak-status.sh"
```

주의:

- 이 스크립트는 `docker compose down -v`로 TripMate 앱 DB와 Dagster local state volume을 삭제한다.
- `--yes`가 없으면 실행하지 않는다.
- 기본 운영 schedule은 바꾸지 않고, 검증용으로만 `TRIPMATE_ETL_CONFIG_PATH=/opt/tripmate/config/etl-datasets.soak.json`을 사용한다.
- `dataset/` 하위의 `국토교통부_법정동코드_*.csv`, `N3A_G0010000.zip`, `N3A_G0100000.zip`, `N3A_G0110000.zip`이 있으면 migration 직후 먼저 적재한다.
- `dataset/`은 Git에 포함하지 않는 로컬 운영 파일 보관소다.

## 아직 없는 로컬 스택

다음 항목은 계획에만 있으며 아직 실행할 수 없다.

- Playwright E2E

## 다음 기준선 작업

1. `scripts/bootstrap-local.sh`와 `scripts/test-local.sh`를 추가한다.
2. 인증 API 구현과 `docs/api/auth.md` 계약을 실제 엔드포인트에 맞춰 확장한다.
3. `places`와 provider cache schema를 추가하기 전에 `docs/data-sources.md`를 확인한다.

## 운영 환경 메모

- 웹앱만 다루는 npm 명령도 WSL2를 우선한다. Windows 실행은 WSL2에서 Node/npm 사용이 불가능한 예외 상황에서만 선택한다.
- 백엔드와 Docker 스택의 로컬 개발 표준은 WSL2 + Docker다.
- ODROID M1S Docker 실행 절차는 `scripts/odroid-docker-start.sh`와 `docs/runbooks/odroid-docker.md`를 따른다. 실제 원격 배포/rollback 스크립트는 `scripts/deploy.sh`가 생길 때 별도로 검증한다.
