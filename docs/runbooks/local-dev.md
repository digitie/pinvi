# 로컬 개발 Runbook

NTFS worktree(git source of truth) + WSL ext4 테스트 미러(실행 전용) 워크플로
(ADR-024) + 포트 + 명령 카탈로그. AI agent + 사람이 본 문서 하나로 로컬 환경
부트스트랩 가능해야 함.

## 1. 사전 조건

### 1.1 호스트

- Windows 11 + WSL2 Ubuntu 24.04
- Docker Desktop (WSL2 backend, Linux containers)
- `.wslconfig` (`%UserProfile%\.wslconfig`):

  ```
  [wsl2]
  memory=12GB
  processors=8
  swap=8GB
  localhostForwarding=true
  ```

### 1.2 도구

- Node.js 20 LTS + npm
- Python 3.12 (`uv` 권장)
- `rg` (ripgrep), `jq`, `httpie` 등 (선택)
- IDE: VS Code / Cursor. git 조작은 NTFS worktree에서 Windows `git.exe`로 수행.

## 2. WSL 테스트 미러 부트스트랩 (최초 1회)

예시는 Codex worktree 기준이다. Claude / Antigravity는 경로 suffix만
`pinvi-claude` / `pinvi-antigravity`로 바꾼다.

```bash
# WSL Ubuntu 진입
wsl.exe -d Ubuntu-24.04

# NTFS worktree -> ext4 미러. .git은 복사하지 않는다.
mkdir -p ~/pinvi-workspaces/pinvi-codex
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude node_modules --exclude '.venv*' --exclude .next \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache \
  --exclude .ruff_cache --exclude .tmp \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/pinvi-codex/ \
  ~/pinvi-workspaces/pinvi-codex/
```

### 2.1 NTFS dataset / refdocs 심볼릭 링크

```bash
cd ~/pinvi-workspaces/pinvi-codex
ln -s /mnt/f/dev/pinvi/dataset dataset
ln -s /mnt/f/dev/pinvi/refdocs refdocs
```

## 3. 동기 정책 (NTFS → WSL 미러 단방향)

```bash
# NTFS → WSL 미러 (작업 시작 전)
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude node_modules --exclude '.venv*' \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache \
  --exclude .ruff_cache --exclude .tmp --exclude .next \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/pinvi-codex/ \
  ~/pinvi-workspaces/pinvi-codex/
```

- `.git`은 동기하지 않는다 — git source of truth는 NTFS worktree 한 곳이다.
- 커밋/푸시/PR은 NTFS worktree에서 Windows `git.exe`로만 수행한다.
- ext4 미러에서 포매터가 파일을 고친 경우만 해당 파일을 NTFS로 sync-back하고,
  NTFS worktree에서 `git diff`로 확인한다.

## 4. PowerShell wrapper

PowerShell에서 실행 전용 명령을 호출할 때는 WSL로 감싼다:

```powershell
wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && scripts/dev-up.sh"
wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && pytest apps/api/tests -q"
wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && docker compose -f infra/docker-compose.yml up -d postgres"
```

## 4.1 고정 dev 포트 (dev = `127.0.0.1`:12xxx, ADR-047)

별도 지시가 없으면 작업 대상은 **dev**다. dev 로컬 서버는 **내부 주소 `127.0.0.1`의 12xxx
고정 포트**만 쓴다(외부/LAN 미노출). dev Docker(`infra/docker-compose.yml`)는 **host
네트워크 모드 기본**이라 컨테이너가 `127.0.0.1`의 12xxx로 직접 bind한다(remap 없음).
prod는 이 경로가 아니라 `ktdctl` + 공식 도메인(`infra/.env.prod`)으로 올린다.

| 서비스 | 포트 | dev URL (127.0.0.1) |
|--------|------|-----|
| PostgreSQL | 5432 | `127.0.0.1:5432` |
| RustFS API | 12101 | `http://127.0.0.1:12101` |
| RustFS console | 12105 | `http://127.0.0.1:12105` |
| kor-travel-map API/Admin API | 12701 | `http://127.0.0.1:12701` |
| FastAPI (`apps/api`) | 12801 | `http://127.0.0.1:12801` |
| Next.js (`apps/web`) | 12805 | `http://127.0.0.1:12805` |
| Dagster (`apps/etl`) | 12802 | `http://127.0.0.1:12802` |
| Prometheus | 12401 | `http://127.0.0.1:12401` |
| cAdvisor Exporter | 12301 | `http://127.0.0.1:12301` |
| Blackbox Exporter | 내부 전용 | Prometheus probe target |
| Grafana | 12205 | `http://127.0.0.1:12205` |

**포트 충돌 정책(ADR-047)**: `scripts/dev-up.sh`는 포트가 이미 점유돼 있으면 **새 포트로
바꾸지 않고**, prod(ktdctl)/dev 무관하게 **강제종료 여부를 사용자에게 묻는다**. 거부하면
(또는 비대화형 기본) **기동을 중지**한다 — 자동 종료하지 않는다. 비대화형에서 강제종료가
필요하면 `PINVI_DEV_FORCE_KILL=1`. 명시적 정리는 `scripts/dev-down.sh`. PostgreSQL/RustFS는
dev Docker compose(host 모드), kor-travel-map은 해당 sibling 저장소 런북으로 실행한다.

```bash
cd ~/pinvi-workspaces/pinvi-codex
scripts/dev-up.sh
scripts/dev-down.sh
```

관측 스택은 필요할 때 별도 profile로 실행한다.

```bash
docker compose -f infra/docker-compose.yml --profile observability up -d cadvisor blackbox prometheus grafana
```

**검색은 PowerShell `rg.exe` 금지** — WindowsApps 경로 오염 회피:

```powershell
wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>"
```

## 5. 시스템 의존성 설치

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  libpq-dev \
  libgdal-dev gdal-bin \
  libgeos-dev libproj-dev libspatialindex-dev \
  python3-dev \
  rsync ripgrep jq httpie

# Node.js 20 LTS (nvm 권장)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 20 && nvm alias default 20

# Python uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Docker buildx + QEMU (ARM64 cross-build)
docker buildx create --use --name multiarch
docker run --privileged --rm tonistiigi/binfmt --install all
docker buildx ls
```

## 6. 백엔드 (`apps/api`)

```bash
cd ~/pinvi-workspaces/pinvi-codex
uv venv apps/api/.venv --python 3.12
source apps/api/.venv/bin/activate
uv pip install -e "apps/api[dev]"
uv pip install "gdal==$(gdal-config --version)"

# kor-travel-map은 별도 sibling 저장소에서 실행 (API/Admin API 12701)
# Pinvi는 .env의 PINVI_KOR_TRAVEL_MAP_API_BASE_URL로 연결

# .env
cp .env.example apps/api/.env
$EDITOR apps/api/.env
```

### 6.1 실행

```bash
cd apps/api
# dev는 내부 주소 127.0.0.1로만 bind한다(ADR-047).
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 12801
```

`http://127.0.0.1:12801/docs` (OpenAPI), `http://127.0.0.1:12801/health`.

### 6.2 테스트

```bash
cd ~/pinvi-workspaces/pinvi-codex
uv run pytest apps/api/tests -q
uv run pytest apps/api/tests/integration -q   # PostGIS testcontainer 필요
uv run ruff check apps/api
uv run ruff format --check apps/api
uv run mypy --strict apps/api/app
```

### 6.3 Alembic

```bash
cd apps/api
uv run alembic upgrade head
uv run alembic revision -m "..." --autogenerate

# v2: Pinvi alembic만. kor-travel-map alembic은 그 저장소에서 별도
cd ~/pinvi-workspaces/kor-travel-map
alembic upgrade head
```

### 6.4 마이그레이션 검증 (별 DB)

```bash
docker exec pinvi-postgres dropdb -U pinvi pinvi_migration_check
docker exec pinvi-postgres createdb -U pinvi pinvi_migration_check
PINVI_DATABASE_URL='postgresql+psycopg://pinvi:changeme@localhost:5432/pinvi_migration_check' \
  uv run alembic upgrade head
```

## 7. 프론트 (`apps/web`)

프론트 개발 서버와 일반 검증은 **WSL ext4 미러**에서 실행한다. Windows에서 실행하는
프론트 명령은 e2e 검증용 Playwright runner / 브라우저로 제한한다.

```bash
cd ~/pinvi-workspaces/pinvi-codex
npm install
npm --workspace apps/web run dev   # http://localhost:12805
```

검사:

```bash
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
npm --workspace apps/web test       # Vitest
```

### 7.1 Playwright e2e (Windows 전용)

Playwright 기반 브라우저 e2e는 Windows Node/브라우저에서만 실행한다. 대상 dev
server는 위 WSL 미러에서 계속 띄워 둔다.

```powershell
# 1) WSL에서 프론트 dev server 실행
wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && npm --workspace apps/web run dev"

# 2) 다른 PowerShell에서 Playwright만 Windows로 실행
cd F:\dev\pinvi-codex
npm --workspace apps/web run test:e2e
```

Windows에서 `npm run dev`, `npm run lint`, `npm run typecheck`, `npm run build`를
실행하지 않는다. Windows Node/npm은 Playwright runner와 브라우저 실행에만 쓴다.

## 8. 인프라 (Docker)

```bash
cd ~/pinvi-workspaces/pinvi-codex
docker compose -f infra/docker-compose.yml up -d postgres rustfs

# Dagster 추가 시
docker compose -f infra/docker-compose.yml up -d postgres rustfs dagster

# Prometheus/Grafana/cAdvisor 추가 시
docker compose -f infra/docker-compose.yml --profile observability up -d cadvisor blackbox prometheus grafana

# 모두
docker compose -f infra/docker-compose.yml up -d
```

`docker compose ps`로 상태 확인. `docker compose logs -f <service>`로 로그.

### 8.1 PostgreSQL 접속

```bash
docker exec -it pinvi-postgres psql -U pinvi -d pinvi

# 또는 host 포트로
psql -h localhost -p 5432 -U pinvi -d pinvi
```

## 9. ETL (`apps/etl`, Sprint 5)

```bash
cd ~/pinvi-workspaces/pinvi-codex/apps/etl
uv venv .venv --python 3.12
uv pip install -e .

# Dagster dev (UI + daemon)
uv run dagster dev --host 0.0.0.0 --port 12802   # http://localhost:12802
```

자세히는 [etl.md](./etl.md).

## 10. 자주 사용하는 명령

| 작업 | 명령 |
|------|------|
| 전체 dev up | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && scripts/dev-up.sh"` |
| 전체 dev down | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && scripts/dev-down.sh"` |
| 백엔드 dev | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex/apps/api && uv run uvicorn app.main:app --reload --port 12801"` |
| 프론트 dev | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && npm --workspace apps/web run dev"` |
| 백엔드 테스트 | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && uv run pytest apps/api/tests -q"` |
| 프론트 lint | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && npm --workspace apps/web run lint"` |
| 프론트 typecheck | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && npm --workspace apps/web run typecheck"` |
| Playwright e2e | `cd F:\dev\pinvi-codex; npm --workspace apps/web run test:e2e` (Windows PowerShell) |
| Postgres up | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && docker compose -f infra/docker-compose.yml up -d postgres"` |
| Alembic upgrade | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex/apps/api && uv run alembic upgrade head"` |
| 검색 (rg) | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>"` |
| Smoke test | `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && scripts/docker-app-smoke-test.sh --keep-running"` |

## 11. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `pip install` 매우 느림 | NTFS 마운트에서 실행 | WSL ext4 미러에서 실행 |
| inotify 한도 초과 | 너무 많은 watch | `sudo sysctl fs.inotify.max_user_watches=524288` |
| `rg.exe` 사용 권한 오류 | WindowsApps `rg.exe` 우선 | WSL `rg` 사용 (`PATH` 명시) |
| Docker 컨테이너 시작 안 됨 | Docker Desktop 종료 | Docker Desktop 시작 + WSL2 backend 확인 |
| PostgreSQL 연결 실패 | host 포트 충돌 (5432) | `5432`로 host 포트 변경 |
| `next dev` 느림 | WSL ↔ NTFS 파일 watch | WSL 미러에서만 실행 |
| Playwright가 WSL에서 브라우저 의존성 오류 | WSL headless browser 라이브러리 누락 | WSL dev server + Windows Playwright로 실행 |
| Alembic `relation does not exist` | 다른 DB에 마이그레이션 적용됨 | `PINVI_DATABASE_URL` 확인 |
| `exec format error` (Odroid) | ARM64 이미지 아님 | `docker buildx build --platform linux/arm64` |

## 12. 관련 문서

- [docker-app.md](./docker-app.md) — Docker smoke test
- [etl.md](./etl.md) — Dagster 운영
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/agent-workflow.md` — agent별 작업 순서
- `docs/dev-environment.md` — 큰 그림
- `docs/decisions.md` ADR-024 (NTFS git + WSL 테스트 미러)
