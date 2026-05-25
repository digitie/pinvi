# dev-environment.md — 개발 환경

본 문서는 `TripMate`의 개발 환경 셋업이다. WSL ext4 미러가 표준 작업 위치다.

## 1. 권장 호스트

- Windows 11 + WSL2 Ubuntu 24.04
- WSL2 `.wslconfig` (`%UserProfile%\.wslconfig`):

  ```
  [wsl2]
  memory=12GB
  processors=8
  swap=8GB
  localhostForwarding=true
  ```

- Docker Desktop with WSL2 backend (Linux 컨테이너)
- Node.js 20 LTS + npm
- Python 3.11+ (uv 권장)

## 2. 파일 위치 정책

| 종류 | 위치 |
|------|------|
| 코드/git/.venv | WSL ext4 미러 — `~/tripmate-workspaces/tripmate/` |
| 작업 디렉토리(현재 프로젝트) | NTFS — `F:\dev\tripmate` (= `/mnt/f/dev/tripmate` from WSL) |
| 데이터 (`dataset/`) | NTFS — `/mnt/f/dev/tripmate/dataset/` |
| 외부 spec/문서 (`refdocs/`) | NTFS — `/mnt/f/dev/tripmate/refdocs/` |
| 빌드 산출물 (`apps/web/.next`, `apps/api/build`) | ext4 미러 (작업 후 폐기 가능) |

### 2.1 WSL 미러 초기화 (최초 1회)

```bash
# WSL ext4 작업 디렉토리 준비
mkdir -p ~/tripmate-workspaces
cd ~/tripmate-workspaces

# git clone (HTTPS)
git clone https://github.com/digitie/tripmate.git
cd tripmate

# 또는 기존 NTFS 작업 디렉토리에서 미러 부트스트랩
rsync -a --delete \
  --exclude .git --exclude node_modules --exclude .venv --exclude .next \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache \
  --exclude .ruff_cache --exclude .tmp \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/tripmate/ \
  ~/tripmate-workspaces/tripmate/
```

### 2.2 NTFS dataset/refdocs를 ext4 미러에 link

```bash
cd ~/tripmate-workspaces/tripmate
ln -s /mnt/f/dev/tripmate/dataset dataset
ln -s /mnt/f/dev/tripmate/refdocs refdocs
```

`dataset/`, `refdocs/`는 NTFS가 원본이므로 ext4에서 변경하지 않는다.

### 2.3 ext4 ↔ NTFS 동기 (rsync)

명령 실행 전후로 양방향 동기:

```bash
# NTFS → ext4 (작업 시작 전)
rsync -a --delete \
  --exclude .git --exclude node_modules --exclude .venv \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache \
  --exclude .ruff_cache --exclude .tmp --exclude .next \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/tripmate/ \
  ~/tripmate-workspaces/tripmate/

# ext4 → NTFS (명령 완료 후)
rsync -a --delete \
  --exclude .git --exclude node_modules --exclude .venv \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache \
  --exclude .ruff_cache --exclude .tmp --exclude .next \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  ~/tripmate-workspaces/tripmate/ \
  /mnt/f/dev/tripmate/
```

`.git`은 동기하지 않는다 — 양쪽 모두 같은 origin을 보지만 인덱스 상태가 다르면
혼란이 생긴다. 커밋은 ext4 미러 한 쪽에서만 한다.

## 3. 초기 셋업 (코드 작성 단계 진입 시)

```bash
# ext4 미러
cd ~/tripmate-workspaces/tripmate

# 시스템 의존성
sudo apt update
sudo apt install -y \
  build-essential \
  libpq-dev \
  libgdal-dev gdal-bin \
  libgeos-dev libproj-dev libspatialindex-dev \
  python3-dev

# Node.js 20 LTS (nvm 권장)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 20 && nvm alias default 20

# Python uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 백엔드 venv
uv venv apps/api/.venv --python 3.11
source apps/api/.venv/bin/activate
uv pip install -e "apps/api[dev,providers]"
uv pip install "gdal==$(gdal-config --version)"

# python-krtour-map (sibling checkout 권장)
cd ~/tripmate-workspaces
git clone https://github.com/digitie/python-krtour-map.git
cd tripmate
uv pip install -e ../python-krtour-map

# 프론트
npm install
npm --workspace apps/web run dev      # http://localhost:3001

# .env
cp .env.example .env
$EDITOR .env

# 인프라
docker compose -f infra/docker-compose.yml up -d postgres rustfs

# Alembic (app schema)
uv run --package apps/api alembic upgrade head

# python-krtour-map alembic은 그 저장소에서 따로 실행
cd ../python-krtour-map
alembic upgrade head
cd ../tripmate

# 단위 테스트
pytest apps/api/tests -q
```

## 4. PostgreSQL + PostGIS 컨테이너

### 4.1 단순 docker run

```bash
docker run -d --name tripmate-postgis \
  -p 5432:5432 \
  -e POSTGRES_USER=tripmate \
  -e POSTGRES_PASSWORD=changeme \
  -e POSTGRES_DB=tripmate \
  -v tripmate-pgdata:/var/lib/postgresql/data \
  postgis/postgis:16-3.5-alpine
```

DSN (백엔드 + `python-krtour-map` 공통):

```
postgresql+asyncpg://tripmate:changeme@localhost:5432/tripmate
```

### 4.2 docker-compose

`infra/docker-compose.yml` (코드 작성 단계에서 추가):

```yaml
services:
  postgres:
    image: postgis/postgis:16-3.5-alpine
    environment:
      POSTGRES_USER: tripmate
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: tripmate
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data

  rustfs:
    image: ghcr.io/rustfs/rustfs:latest
    ports: ["9000:9000", "9001:9001"]
    environment:
      RUSTFS_ROOT_USER: tripmate
      RUSTFS_ROOT_PASSWORD: changeme
    volumes:
      - rustfsdata:/data

  api:
    build: ./apps/api
    depends_on: [postgres, rustfs]
    environment:
      TRIPMATE_PG_DSN: postgresql+asyncpg://tripmate:changeme@postgres:5432/tripmate
    ports: ["8001:8001"]

  web:
    build: ./apps/web
    depends_on: [api]
    ports: ["3001:3001"]

  dagster:
    build: ./apps/etl
    depends_on: [postgres]
    ports: ["23000:3000"]

volumes:
  pgdata: {}
  rustfsdata: {}
```

### 4.3 운영 환경 (Odroid M1S)

- Ubuntu 24.04 + Docker Compose plugin
- `infra/docker-compose.app.yml`로 분리 (개발용과 다른 image tag/볼륨/리소스 제한)
- 운영 절차는 코드 작성 단계 진입 후 `docs/runbooks/odroid-docker.md`에 박는다.

## 5. 스키마 초기화

PostgreSQL 컨테이너 첫 기동 후:

```sql
-- 본 저장소(app 도메인)와 python-krtour-map(feature 도메인) schema
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS feature;
CREATE SCHEMA IF NOT EXISTS provider_sync;
CREATE SCHEMA IF NOT EXISTS x_extension;

-- PostGIS / pg_trgm / pgcrypto는 x_extension schema에 설치 (search_path 분리)
CREATE EXTENSION IF NOT EXISTS postgis    SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm    SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pgcrypto   SCHEMA x_extension;

-- 접속 시 search_path
ALTER ROLE tripmate SET search_path TO public, x_extension;
```

Alembic이 위 schema에 테이블을 적재한다:

- `app`, `ops`: 본 저장소 Alembic (`apps/api/alembic/versions/...`)
- `feature`, `provider_sync`: `python-krtour-map` Alembic (별 저장소)

## 6. 환경변수 (`.env` 예시)

```dotenv
# DB
TRIPMATE_PG_DSN=postgresql+asyncpg://tripmate:changeme@localhost:5432/tripmate
TRIPMATE_PG_POOL_SIZE=10

# 객체 저장소
TRIPMATE_RUSTFS_ENDPOINT=http://localhost:9000
TRIPMATE_RUSTFS_ACCESS_KEY=tripmate
TRIPMATE_RUSTFS_SECRET_KEY=changeme
TRIPMATE_RUSTFS_BUCKET_APP=tripmate-app
TRIPMATE_RUSTFS_BUCKET_FEATURE=tripmate-feature-media

# 인증
TRIPMATE_JWT_SECRET=...
TRIPMATE_SESSION_COOKIE_NAME=tripmate_session
TRIPMATE_ADMIN_EMAILS=admin@example.com

# 외부 API
TRIPMATE_KMA_API_KEY=...
TRIPMATE_VISITKOREA_API_KEY=...
TRIPMATE_OPINET_API_KEY=...
TRIPMATE_KEX_GO_API_KEY=...
TRIPMATE_KASI_API_KEY=...

# 소셜 로그인
TRIPMATE_KAKAO_CLIENT_ID=...
TRIPMATE_KAKAO_CLIENT_SECRET=...
TRIPMATE_NAVER_CLIENT_ID=...
TRIPMATE_NAVER_CLIENT_SECRET=...
TRIPMATE_GOOGLE_CLIENT_ID=...
TRIPMATE_GOOGLE_CLIENT_SECRET=...

# 알림
TRIPMATE_TELEGRAM_BOT_TOKEN=...
TRIPMATE_RESEND_API_KEY=...
TRIPMATE_RESEND_FROM=noreply@tripmate.example
TRIPMATE_GEMINI_API_KEY=...

# 프론트 base
TRIPMATE_WEB_BASE_URL=http://localhost:3001
NEXT_PUBLIC_TRIPMATE_DAGSTER_URL=http://localhost:23000
```

`.env`는 권한 600. 운영은 systemd `EnvironmentFile` 또는 vault.

## 7. Windows PowerShell에서의 명령 호출

가능하면 WSL shell 안에서 작업한다. PowerShell에서 호출이 필요하면:

```powershell
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && npm run dev"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && pytest apps/api/tests -q"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && docker compose -f infra/docker-compose.yml up -d postgres"
```

검색은 PowerShell `rg.exe`를 사용하지 않는다 — WindowsApps 경로 오염을 피해
WSL native `rg`만 사용:

```powershell
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>"
```

PowerShell로 한국어 문서를 읽을 때는 `Get-Content -Encoding UTF8` 명시.

## 8. Docker / Compose

- 컨테이너 작업은 WSL2에서 실행한다. NTFS 마운트(`/mnt/f/`)에서 직접 빌드/실행하지
  않는다 — overlay fs 성능과 파일 권한 문제.
- 빌드 컨텍스트는 ext4 미러(`~/tripmate-workspaces/tripmate`)를 사용한다.
- `infra/docker-compose.yml`은 개발용. 운영은 `infra/docker-compose.app.yml`.
- Smoke test: 코드 작성 단계 진입 후 `scripts/docker-app-smoke-test.sh`로 자동화.

## 9. 디버깅 도구

- 데이터베이스 GUI: pgAdmin, DBeaver, TablePlus 등. 접속 host는 `localhost`,
  port `5432`.
- API 디버그: FastAPI 자체 OpenAPI UI (`http://localhost:8001/docs`).
- 프론트 디버그: Next.js DevTools + React DevTools.
- Dagster UI: `http://localhost:23000`.
- RustFS Web Console: `http://localhost:9001`.

## 10. Windows 재설치 후 인수인계

`docs/runbooks/windows-reinstall-recovery.md` (코드 작성 단계 진입 후 작성).
다음 항목을 포함:

- WSL2 백업/복구
- ext4 ↔ NTFS 동기 규칙
- 미러 디렉토리 부트스트랩 절차
- `.env` / secrets 인수인계
- 진행 중 PR 핸드오프

## 11. 작업 흐름 요약 (체크리스트)

작업 시작 전:

- [ ] NTFS → ext4 미러 동기
- [ ] `wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && git status"` 확인

작업 중:

- [ ] 모든 명령은 WSL ext4 미러에서 (PowerShell이면 `wsl.exe -e bash -lc`로 감쌈)
- [ ] 검색은 WSL `rg`만

작업 완료 후:

- [ ] ext4 → NTFS 동기
- [ ] git status에서 의도하지 않은 변경 없는지 확인
- [ ] (코드 작성 단계 후) `pytest -q` / `npm run lint typecheck build` 통과
- [ ] `docs/journal.md` 엔트리 추가
- [ ] PR 작성 또는 main에 push 금지 (모든 변경은 feature branch + PR)
