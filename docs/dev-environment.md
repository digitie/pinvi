# dev-environment.md — 개발 환경 (NTFS worktree + WSL ext4 테스트 미러)

본 문서는 `TripMate`를 PC에서 개발할 때의 **표준 환경 모델**과 셋업·작업 절차다.
어느 AI 에이전트(Claude / Codex / Antigravity)든 그대로 따라 할 수 있도록 구체적인
명령과 함정을 정리한다.

> **모델 (ADR-024 — ADR-004의 source-of-truth 주장을 supersede, ADR-017 확정)**
>
> - **git source of truth = NTFS worktree** (`F:/dev/tripmate-<agent>`).
>   코드 편집 / branch / commit / push / PR은 **여기서 Windows git(`git.exe`)으로만**.
> - **WSL ext4 = 일회용 테스트 미러** (`~/tripmate-workspaces/tripmate-<agent>`).
>   의존성 설치 / 테스트 / Docker / 장기 실행은 **여기서**. **commit/push 금지.**
> - **rsync는 단방향 (NTFS → ext4)**. 미러는 언제든 폐기·재생성 가능.
>
> 과거 모델("WSL ext4가 표준 작업 위치 / Git source of truth는 ext4 / 양방향
> rsync")은 **폐기**한다. 이 문서에 그 표현이 남아 있으면 본 §0 기준으로 정정한다.

## 0. 왜 이 모델인가 (codex가 헤맨 지점)

NTFS와 WSL을 섞어 쓰면서 다음 사고가 반복됐다. 본 모델은 그걸 차단한다.

1. **worktree 포인터 환경 혼용** — 각 worktree의 `.git` 파일에는 worktree를
   **만든 환경 기준 절대경로**가 박힌다. WSL에서 만들면
   `gitdir: /mnt/f/dev/tripmate/.git/worktrees/...`, Windows git에서 만들면
   `gitdir: F:/dev/tripmate/.git/worktrees/...`. 같은 폴더라도 두 표기가 다르므로
   **다른 환경 git으로 같은 worktree를 다루면** `fatal: not a git repository`가
   나고 `git worktree list`에 `prunable`로 뜬다. 이 상태에서 `git worktree prune`을
   돌리면 **살아있는 worktree 등록까지 삭제**될 수 있다.
   → 대책: 각 worktree는 **한 환경 전용**. git은 NTFS worktree에서 `git.exe`로만.
2. **source of truth 모호** — "ext4에서 commit" vs "NTFS에서 commit"이 문서마다
   달라, 양방향 rsync 후 어느 쪽을 push 기준으로 삼을지 헤맸다. rsync 왕복 중
   파일 일부가 중복/오염되는 사고도 있었다.
   → 대책: commit은 **NTFS worktree 한 곳**. rsync는 **NTFS→ext4 단방향**.
3. **WSL에서 Windows 도구 PATH 오염** — `npm`/`git`/`rg`가 `/mnt/c/...`의 Windows
   shim으로 잡혀 `node: not found`, UNC 경로 경고, 잘못된 경로 전달.
   → 대책: WSL에서는 Linux Node/npm/git/rg를 쓴다(§6, §8).
4. **TMP가 Windows Temp를 가리킴** — WSL 셸이 `TMP=/mnt/c/...`로 열리면 pytest
   capture가 `FileNotFoundError`로 깨진다.
   → 대책: `TMPDIR=/tmp TMP=/tmp TEMP=/tmp` 명시(§7 함정).

같은 문제를 별 저장소 `python-kraddr-geo`가 ADR-041로 먼저 해결했고, 본 모델은
그와 동일 패턴이다.

## 1. 디렉터리 레이아웃

```text
F:/dev/tripmate                      # 사람 trunk (사용자 직접 사용, main 점유) — AI 편집 금지
F:/dev/tripmate-claude               # Claude Code worktree (NTFS, git source of truth)
F:/dev/tripmate-codex                # OpenAI Codex worktree
F:/dev/tripmate-antigravity          # Google Antigravity worktree
~/tripmate-workspaces/tripmate-claude     # Claude용 WSL ext4 테스트 미러 (일회용)
~/tripmate-workspaces/tripmate-codex      # Codex용 테스트 미러
~/tripmate-workspaces/tripmate-antigravity# Antigravity용 테스트 미러
```

| 종류 | 위치 | 비고 |
|------|------|------|
| git / 편집 / commit / PR | NTFS worktree `F:/dev/tripmate-<agent>` | Windows `git.exe`만 |
| 의존성·테스트·Docker·장기 실행 | WSL ext4 `~/tripmate-workspaces/tripmate-<agent>` | commit 금지 |
| 데이터 (`dataset/`, `refdocs/`) | NTFS 원본 `/mnt/f/dev/tripmate/dataset/` | ext4에선 심볼릭 링크/절대경로 참조 |
| 빌드 산출물 (`.next`, `build`) | ext4 미러 | 폐기 가능 |

에이전트별 worktree 이름·idle 브랜치는 `docs/runbooks/codegraph-worktrees.md`가
1차 reference다(ADR-017). 본 문서는 그 위에서 **WSL 테스트 미러 절차**를 다룬다.

## 2. NTFS worktree (git source of truth)

worktree 생성·branch 운영 전체 절차는 `docs/runbooks/codegraph-worktrees.md` §1~§3.
핵심만:

```powershell
# Windows PowerShell — 본인 agent worktree에서. git 은 Windows git.exe.
cd F:\dev\tripmate-claude
git fetch origin
git switch -c agent/claude-<task> origin/main   # 로컬 main은 trunk 점유 → origin/main 기준
# ... 편집 ...
git add -A
git commit -m "feat(...): ..."
git push -u origin agent/claude-<task>
gh pr create --base main --head agent/claude-<task> ...
```

- **trunk(`F:/dev/tripmate`)를 AI가 편집하지 않는다** (ADR-017).
- worktree에서 `git switch main`은 `fatal: 'main' is already checked out at
  'F:/dev/tripmate'`로 실패한다 → 항상 `origin/main`을 기준 ref로(`git fetch`
  후 `git switch -c ... origin/main`, `git rebase origin/main`).
- **이 worktree의 git은 Windows git.exe로만** 다룬다. WSL에서 같은 폴더
  (`/mnt/f/dev/tripmate-claude`)에 `git`을 실행하지 않는다(§0-1 포인터 사고).

### 2.1 로컬 secret/env 파일

`.env`, `.claude/settings.local.json` 등 로컬 키는 Git에 커밋하지 않는다
(`.gitignore` 대상). 새 worktree를 만들면 trunk/기존 worktree에서 같은 상대 경로로
복사한다.

## 3. WSL ext4 테스트 미러 (일회용)

### 3.1 미러 생성·갱신 (NTFS → ext4 단방향)

작업/검증 **직전** 매번 실행. `--delete`로 미러를 NTFS worktree와 정확히 일치시킨다.

```bash
mkdir -p ~/tripmate-workspaces/tripmate-claude
rsync -a --delete \
  --exclude .git \
  --exclude .codegraph \
  --exclude '.venv*' \
  --exclude node_modules \
  --exclude .next \
  --exclude __pycache__ \
  --exclude .mypy_cache \
  --exclude .pytest_cache \
  --exclude .ruff_cache \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/tripmate-claude/ \
  ~/tripmate-workspaces/tripmate-claude/
```

> `.git`을 **동기하지 않는다** — 미러는 git 작업용이 아니다(commit/push 금지).
> Codex/Antigravity는 경로의 `-claude`를 본인 agent로 바꾼다.

### 3.2 데이터 링크 (필요 시, 1회)

```bash
cd ~/tripmate-workspaces/tripmate-claude
test -e dataset || ln -s /mnt/f/dev/tripmate/dataset dataset
test -e refdocs || ln -s /mnt/f/dev/tripmate/refdocs refdocs
```

`dataset/`·`refdocs/`는 NTFS가 원본 — ext4에서 변경하지 않는다.

### 3.3 검증 중 발견한 수정의 반영

- 코드 수정은 **NTFS worktree에 직접** 하고 §3.1 단방향 sync를 다시 돌린다.
- 포매터/린터가 **ext4 미러의 파일을 고친 경우만** 예외적으로 그 파일에 한해
  ext4 → NTFS로 단방향 sync-back 후 `git diff`로 확인한다(역방향을 상시 절차로
  쓰지 않는다).

```bash
# 예: ext4에서 ruff format이 파일을 고쳤을 때만
rsync -a ~/tripmate-workspaces/tripmate-claude/apps/api/app/ \
        /mnt/f/dev/tripmate-claude/apps/api/app/
# NTFS worktree(PowerShell)에서 git diff 로 확인 후 commit
```

## 4. 시스템 패키지 (Ubuntu/WSL, 1회)

```bash
sudo apt update
sudo apt install -y \
  build-essential python3-dev \
  libpq-dev \
  libgdal-dev gdal-bin \
  libgeos-dev libproj-dev libspatialindex-dev
gdal-config --version    # 예: 3.8.4
```

`gdal-config`가 PATH에 없으면 GDAL 바인딩 빌드가 `gdal-config: command not found`로
실패한다.

## 5. Python / Node 셋업 (ext4 미러에서)

아래는 **NTFS가 아니라 ext4 미러**에서 실행한다.

```bash
cd ~/tripmate-workspaces/tripmate-claude

# Python — uv 권장
curl -LsSf https://astral.sh/uv/install.sh | sh    # 1회
cd apps/api
uv venv .venv-wsl --python 3.12
. .venv-wsl/bin/activate
uv pip install -e ".[dev]"
# GDAL 바인딩이 필요하면 시스템 버전에 핀
uv pip install "gdal==$(gdal-config --version)"

# python-krtour-map (함수 라이브러리, sibling checkout)
uv pip install -e ~/dev/python-krtour-map        # 또는 git URL pin (@<sha>)

# Node — Linux Node/npm (Windows shim 금지, §6)
cd ~/tripmate-workspaces/tripmate-claude
npm install
```

`.venv-wsl`처럼 ext4 전용 venv 이름을 쓰면 NTFS 쪽 `.venv`와 헷갈리지 않는다
(`.gitignore`에 `.venv*` 박힘).

## 6. WSL에서 Windows 도구 PATH 오염 방지

WSL 셸의 PATH에 `/mnt/c/...`의 Windows `npm`/`node`/`git`/`rg` shim이 먼저 잡히면
`node: not found`, UNC 경로 경고, 잘못된 경로 전달이 발생한다.

```bash
# 어느 바이너리가 잡히는지 확인
command -v npm node git rg
# /mnt/c/... 또는 *.exe / *.cmd 가 나오면 Windows shim — Linux 것으로 교정
```

- **npm/node**: nvm 등으로 설치한 Linux Node를 쓴다. `command -v npm`이
  `/mnt/c/...`면 그 셸에서 프론트 명령을 실행하지 않는다.
- **git**: WSL에서 NTFS worktree(`/mnt/f/...`)에 git을 실행하지 않는다(§0-1).
  ext4 미러는 git 작업 대상이 아니다.
- **rg(검색)**: WSL native `rg`만. PowerShell에서 호출 시
  `PATH=/usr/local/bin:/usr/bin:/bin rg <pattern>`로 WindowsApps 오염을 피한다.

## 7. 검증 게이트 (ext4 미러에서)

```bash
cd ~/tripmate-workspaces/tripmate-claude/apps/api
. .venv-wsl/bin/activate
export TRIPMATE_JWT_SECRET_KEY='tripmate-test-jwt-secret-32bytes-minimum-aaaa'
export TESTCONTAINERS_RYUK_DISABLED=true
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp     # ← Windows Temp 오염 시 pytest capture 깨짐 방지

python -m pytest tests/unit -q
python -m pytest tests/integration -q     # PostGIS testcontainer (§8) 필요
ruff check app tests
ruff format --check app tests
mypy --strict app
```

프론트(`apps/web`)는 Linux Node/npm으로 `npm run lint` / `npm run typecheck` /
`npm run build`까지. **Playwright/브라우저 e2e는 WSL에서 실행하지 않는다** — WSL
headless Chromium은 `libasound.so.2` 등 공유 라이브러리 누락으로 반복 실패한다.
브라우저 검증은 Windows Node/브라우저에서 하고, 실행 명령·스크린샷 경로를 작업
로그에 기록한다.

### 7.1 알려진 함정

- **마이그레이션이 커밋되는지 확인** — testcontainers + async alembic은 exit code만
  보면 안 된다. `alembic upgrade head` 후 실제 테이블 수까지 확인한다(과거 async
  `env.py`가 DDL 트랜잭션을 commit하지 않아 테이블이 사라진 잠재 버그가 있었음 →
  `connection.commit()` 추가로 해결).
- **pytest-asyncio function-loop** — 통합 테스트 엔진은 함수 스코프 + `NullPool`로
  만든다. 세션 스코프로 공유하면 "another operation is in progress" /
  "Future attached to a different loop"가 난다(`tests/integration/conftest.py` 참고).
- **TMP=Windows Temp** — §7의 `TMPDIR/TMP/TEMP=/tmp` 명시.

## 8. PostgreSQL + PostGIS (ext4 미러 / Docker)

통합 테스트는 `testcontainers`가 `postgis/postgis:16-3.5-alpine`를 자동 기동한다
(이미지 사전 pull 권장: `docker pull postgis/postgis:16-3.5-alpine`).

수동 기동이 필요하면:

```bash
docker run -d --name tripmate-postgis \
  -p 5432:5432 \
  -e POSTGRES_USER=tripmate -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=tripmate \
  -v tripmate-pgdata:/var/lib/postgresql/data \
  postgis/postgis:16-3.5-alpine
# DSN: postgresql+asyncpg://tripmate:changeme@localhost:5432/tripmate
```

`infra/docker-compose.yml`(개발)·`infra/docker-compose.app.yml`(운영) 상세는
`docs/runbooks/{local-dev,docker-app,odroid-docker}.md`. 컨테이너 작업은 WSL2에서
하고 NTFS 마운트에서 직접 빌드/실행하지 않는다(overlay fs 성능·권한).

### 8.1 스키마 / extension

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS x_extension;
CREATE EXTENSION IF NOT EXISTS postgis  SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm  SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension;
ALTER ROLE tripmate SET search_path TO public, x_extension;
```

`feature` / `provider_sync` schema와 그 extension은 `python-krtour-map`이 소유·적재
한다(ADR-003) — 본 저장소는 `app`/`ops`만 Alembic으로 관리한다.

## 9. 환경변수 (`.env` 예시)

```dotenv
TRIPMATE_DATABASE_URL=postgresql+asyncpg://tripmate:changeme@localhost:5432/tripmate
TRIPMATE_JWT_SECRET_KEY=change-me-32-bytes-minimum-...
TRIPMATE_RESEND_API_KEY=
TRIPMATE_GOOGLE_OAUTH_CLIENT_ID=
TRIPMATE_GOOGLE_OAUTH_CLIENT_SECRET=
TRIPMATE_WEB_BASE_URL=http://localhost:3001
```

전체 키 목록은 `apps/api/app/core/config.py`의 `Settings`가 1차 진실이다. `.env`는
권한 600, 운영은 systemd `EnvironmentFile` 또는 vault.

## 10. PowerShell ↔ WSL 호출

NTFS worktree에서 git/편집은 PowerShell(Windows git.exe). WSL 명령이 필요하면
한 줄로 감싼다.

```powershell
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate-claude && rsync -a --delete --exclude .git /mnt/f/dev/tripmate-claude/ ~/tripmate-workspaces/tripmate-claude/"
wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate-claude/apps/api && . .venv-wsl/bin/activate && python -m pytest tests/integration -q"
```

PowerShell로 한국어 문서를 읽을 때는 `Get-Content -Encoding UTF8` 명시.

## 11. 작업 흐름 요약 (체크리스트)

작업 시작 (NTFS worktree, PowerShell):

- [ ] `git fetch origin` → `git switch -c agent/<agent>-<task> origin/main`
- [ ] `codegraph sync` (`docs/runbooks/codegraph-worktrees.md`)

검증 (WSL ext4 미러):

- [ ] NTFS → ext4 단방향 rsync (§3.1)
- [ ] `pytest unit/integration` + `ruff` + `ruff format --check` + `mypy --strict`
- [ ] (프론트) Linux npm으로 lint/typecheck/build. Playwright는 Windows에서.

마무리 (NTFS worktree):

- [ ] 수정은 NTFS에 반영(필요 시 §3.3 단방향 sync-back + `git diff`)
- [ ] `git add` → `commit` → `push` → `gh pr create` (Windows git.exe)
- [ ] `docs/journal.md` + `docs/resume.md` 갱신, main 직접 push 금지

## 12. Windows 재설치 후 복구

WSL2 설치 → §4 시스템 패키지 → trunk clone + worktree 재생성
(`docs/runbooks/codegraph-worktrees.md` §1) → §5 의존성 → `.env`/secret 복원 →
§8 DB 기동. 진행 중 PR 핸드오프는 origin의 feature 브랜치가 기준이다.

## 참고

- ADR-024 — NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러.
- ADR-017 — agent별 고정 worktree + Windows git.exe.
- ADR-004 — 미러 모델(디스크/경로). source-of-truth 주장은 ADR-024가 supersede.
- ADR-003 — `feature`/`provider_sync` schema 소유권(`python-krtour-map`).
- `docs/runbooks/codegraph-worktrees.md` — worktree 생성·CodeGraph·git 포인터 함정.
- `python-kraddr-geo` `docs/dev-environment.md` — 동일 패턴 reference(ADR-041).
