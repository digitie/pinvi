# 로컬 개발 Runbook

Linux 전용 개발 모델(ADR-051) + 포트 + 명령 카탈로그. AI agent + 사람이 본 문서 하나로 로컬
환경을 부트스트랩할 수 있어야 한다. WSL도 Linux 환경으로 본다.

## 1. 사전 조건

### 1.1 호스트

- Linux 또는 Windows 11 + WSL2 Ubuntu 24.04 이상
- Docker Engine 또는 Docker Desktop WSL2 backend (Linux containers)
- WSL 사용 시 권장 `.wslconfig` (`%UserProfile%\.wslconfig`):

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
- IDE: VS Code / Cursor. git 조작은 Linux worktree에서 Linux `git`으로 수행.

## 2. Linux worktree 부트스트랩

예시는 Codex worktree 기준이다. Claude / Antigravity는 경로 suffix만
`pinvi-claude` / `pinvi-antigravity`로 바꾼다. 기존 `/mnt/f/...` checkout을 계속 써도 되지만,
반드시 Linux git 포인터로 복구한 뒤 Windows `git.exe`로 다시 만지지 않는다.

```bash
# 기존 고정 worktree
cd /mnt/f/dev/pinvi-codex
git status --short --branch

# F:/... 포인터가 남아 Linux git이 실패할 때만 trunk에서 repair
cd /mnt/f/dev/pinvi
git worktree repair /mnt/f/dev/pinvi-codex
```

새 task:

```bash
cd /mnt/f/dev/pinvi-codex
git fetch origin
git switch -c agent/codex-<task> origin/main
codegraph sync
```

### 2.1 dataset / refdocs

변경 금지 데이터는 worktree에 복사하지 말고 절대경로 또는 symlink로 참조한다. 새 ext4 worktree를
별도로 만들 때만 필요한 symlink를 둔다.

## 3. 실행 정책

- git / branch / commit / push / PR은 Linux git으로 수행한다.
- CodeGraph는 Linux native `codegraph`만 사용한다. `/mnt/c/...`, `.exe`, `.cmd` shim이면 중지한다.
- 의존성 설치, 테스트, Docker, dev server, lint/typecheck/build/Vitest도 Linux에서 수행한다.
- Playwright는 N150에서 먼저 실행하고, N150 Docker runner 또는 host browser 실행이 모두 불가능할 때만
  Windows fallback을 쓴다.

## 4. Windows shell wrapper

Windows shell에서 호출해야 할 때도 실제 명령은 WSL/Linux로 감싼다:

```powershell
wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && scripts/dev-up.sh"
wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && pytest apps/api/tests -q"
wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && docker compose -f infra/docker-compose.yml up -d postgres"
```

## 4.1 고정 dev 포트 (dev = `127.0.0.1`:12xxx, ADR-047)

별도 지시가 없으면 작업 대상은 **dev**다. dev 로컬 서버는 **내부 주소 `127.0.0.1`의 12xxx
고정 포트**만 쓴다(외부/LAN 미노출). dev Docker(`infra/docker-compose.yml`)는 **host
네트워크 모드 기본**이라 컨테이너가 `127.0.0.1`의 12xxx로 직접 bind한다(remap 없음).
prod는 이 경로가 아니라 `ktdctl` + 공식 도메인(`infra/.env.prod`)으로 올린다.

| 서비스                       | 포트      | dev URL (127.0.0.1)      |
| ---------------------------- | --------- | ------------------------ |
| PostgreSQL                   | 5432      | `127.0.0.1:5432`         |
| RustFS API                   | 12101     | `http://127.0.0.1:12101` |
| RustFS console               | 12105     | `http://127.0.0.1:12105` |
| kor-travel-map API/Admin API | 12701     | `http://127.0.0.1:12701` |
| FastAPI (`apps/api`)         | 12801     | `http://127.0.0.1:12801` |
| Next.js (`apps/web`)         | 12805     | `http://127.0.0.1:12805` |
| Dagster (`apps/etl`)         | 12802     | `http://127.0.0.1:12802` |
| Prometheus                   | 12401     | `http://127.0.0.1:12401` |
| cAdvisor Exporter            | 12301     | `http://127.0.0.1:12301` |
| Blackbox Exporter            | 내부 전용 | Prometheus probe target  |
| Grafana                      | 12205     | `http://127.0.0.1:12205` |

**포트 충돌 정책(ADR-047)**: `scripts/dev-up.sh`는 포트가 이미 점유돼 있으면 **새 포트로
바꾸지 않고**, prod(ktdctl)/dev 무관하게 **강제종료 여부를 사용자에게 묻는다**. 거부하면
(또는 비대화형 기본) **기동을 중지**한다 — 자동 종료하지 않는다. 비대화형에서 강제종료가
필요하면 `PINVI_DEV_FORCE_KILL=1`. 명시적 정리는 `scripts/dev-down.sh`. PostgreSQL/RustFS는
dev Docker compose(host 모드), kor-travel-map은 해당 sibling 저장소 런북으로 실행한다.

```bash
cd /mnt/f/dev/pinvi-codex
scripts/dev-up.sh
scripts/dev-down.sh
```

관측 스택은 필요할 때 별도 profile로 실행한다.

```bash
docker compose -f infra/docker-compose.yml --profile observability up -d cadvisor blackbox prometheus grafana
```

**검색은 PowerShell `rg.exe` 금지** — WindowsApps 경로 오염 회피:

```powershell
wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>"
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
cd /mnt/f/dev/pinvi-codex
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
uv run python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 12801
```

`http://127.0.0.1:12801/docs` (OpenAPI), `http://127.0.0.1:12801/health`.

### 6.2 테스트

```bash
cd /mnt/f/dev/pinvi-codex
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
cd /mnt/f/dev/kor-travel-map
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

프론트 개발 서버와 일반 검증은 **Linux worktree**에서 실행한다. Windows에서 실행하는 프론트 명령은
N150 Playwright가 불가능할 때의 fallback runner로 제한한다.

```bash
cd /mnt/f/dev/pinvi-codex
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

### 7.1 Playwright e2e

Playwright 기반 브라우저 e2e는 N150에서 먼저 실행한다. Ubuntu 26.04 host Chromium
dependency 문제를 피하려면 `scripts/n150-playwright-runner.sh` Docker runner를 사용한다.
N150 Docker runner와 host browser 실행이 모두 불가능할 때만 Windows runner를 fallback으로
사용하고, 사유와 명령을 journal/PR에 기록한다.

```bash
ssh n150
cd ~/pinvi

PINVI_ADMIN_LIVE_E2E=1 \
PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 \
scripts/n150-playwright-runner.sh -- \
  npm -w @pinvi/web run test:e2e:admin-live -- --grep malformed --workers=1
```

Windows에서 `npm run dev`, `npm run lint`, `npm run typecheck`, `npm run build`를 실행하지 않는다.
Windows Node/npm은 N150 Playwright가 불가능할 때의 fallback runner로만 쓴다.

## 8. 인프라 (Docker)

```bash
cd /mnt/f/dev/pinvi-codex
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
cd /mnt/f/dev/pinvi-codex/apps/etl
uv venv .venv --python 3.12
uv pip install -e .

# Dagster dev (UI + daemon)
uv run dagster dev --host 0.0.0.0 --port 12802   # http://localhost:12802
```

자세히는 [etl.md](./etl.md).

## 10. 자주 사용하는 명령

| 작업             | 명령                                                                                                                                                             |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 전체 dev up      | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && scripts/dev-up.sh"`                                                                                           |
| 전체 dev down    | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && scripts/dev-down.sh"`                                                                                         |
| 백엔드 dev       | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex/apps/api && uv run python -m uvicorn app.main:app --reload --port 12801"`                                        |
| 프론트 dev       | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && npm --workspace apps/web run dev"`                                                                            |
| 백엔드 테스트    | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && uv run pytest apps/api/tests -q"`                                                                             |
| 프론트 lint      | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && npm --workspace apps/web run lint"`                                                                           |
| 프론트 typecheck | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && npm --workspace apps/web run typecheck"`                                                                      |
| Playwright e2e   | `ssh n150 'cd ~/pinvi && PINVI_ADMIN_LIVE_E2E=1 scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live -- --grep malformed --workers=1'` |
| Postgres up      | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && docker compose -f infra/docker-compose.yml up -d postgres"`                                                   |
| Alembic upgrade  | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex/apps/api && uv run alembic upgrade head"`                                                                        |
| 검색 (rg)        | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>"`                                                              |
| Smoke test       | `wsl.exe -e bash -lc "cd /mnt/f/dev/pinvi-codex && scripts/docker-app-smoke-test.sh --keep-running"`                                                             |

## 11. 트러블슈팅

| 증상                                            | 원인                              | 해결                                                                                        |
| ----------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------- |
| `pip install` 매우 느림                         | NTFS 마운트 I/O 비용              | 필요하면 ext4 Linux worktree를 source-of-truth로 새로 만들고 그곳에서 실행                  |
| inotify 한도 초과                               | 너무 많은 watch                   | `sudo sysctl fs.inotify.max_user_watches=524288`                                            |
| `rg.exe` 사용 권한 오류                         | WindowsApps `rg.exe` 우선         | WSL `rg` 사용 (`PATH` 명시)                                                                 |
| Docker 컨테이너 시작 안 됨                      | Docker Desktop 종료               | Docker Desktop 시작 + WSL2 backend 확인                                                     |
| PostgreSQL 연결 실패                            | host 포트 충돌 (5432)             | `5432`로 host 포트 변경                                                                     |
| `next dev` 느림                                 | NTFS 파일 watch 비용              | 필요하면 ext4 Linux worktree를 source-of-truth로 새로 만들고 그곳에서 실행                  |
| Playwright가 N150 host에서 브라우저 의존성 오류 | host Chromium shared library 누락 | `scripts/n150-playwright-runner.sh` Docker runner 사용, 그래도 불가할 때만 Windows fallback |
| Alembic `relation does not exist`               | 다른 DB에 마이그레이션 적용됨     | `PINVI_DATABASE_URL` 확인                                                                   |
| `exec format error` (Odroid)                    | ARM64 이미지 아님                 | `docker buildx build --platform linux/arm64`                                                |

## 12. 관련 문서

- [docker-app.md](./docker-app.md) — Docker smoke test
- [etl.md](./etl.md) — Dagster 운영
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/agent-workflow.md` — agent별 작업 순서
- `docs/dev-environment.md` — 큰 그림
- `docs/decisions.md` ADR-051 (Linux 개발·git·CodeGraph + N150 우선 Playwright)
