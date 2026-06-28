# dev-environment.md — Linux 전용 개발 환경

본 문서는 `Pinvi`를 개발할 때의 표준 환경 모델과 셋업·작업 절차다. 어느 AI
에이전트(Claude / Codex / Antigravity)든 같은 기준을 따른다.

> **모델 (ADR-051)**
>
> - **모든 개발 작업은 Linux에서 수행한다.** WSL도 Linux 환경으로 본다.
> - **git / branch / commit / push / PR은 Linux git으로 수행한다.**
> - **CodeGraph는 Linux native 실행만 허용한다.** `/mnt/c/...`, `.exe`, `.cmd`
>   Windows shim으로 잡히면 중지하고 PATH/설치를 고친다.
> - **의존성 설치, 테스트, Docker, dev server, lint/typecheck/build/Vitest도
>   Linux에서 수행한다.**
> - **Playwright는 N150에서 먼저 실행한다.** N150에서 브라우저/runtime/권한 문제로
>   불가능할 때만 Windows runner를 fallback으로 사용하고, 사유를 journal/PR에 남긴다.
>
> ADR-024의 "NTFS worktree = git source of truth + Windows git" 모델과 ADR-017의
> 2026-05-31 Windows `git.exe` amendment는 ADR-051이 supersede한다.

## 0. 왜 바꿨나

이전 모델은 NTFS worktree를 Windows `git.exe`로 다루고, WSL ext4 미러를 실행 전용
사본으로 쓰는 방식이었다. 그러나 한 저장소를 Windows git과 Linux git이 번갈아
읽으면 worktree 포인터가 서로 다른 절대경로 체계로 박힌다.

실제 Codex worktree에서 다음 문제가 재현됐다.

- `.git`이 `gitdir: F:/dev/...`를 들고 있어 Linux git이
  `fatal: not a git repository`를 냈다.
- `git worktree list`에서 정상 worktree가 `prunable`처럼 보였다.
- `codegraph`가 WSL에서 `/mnt/c/...` Windows npm shim으로 잡혔다.

한 환경으로 통일하지 않으면 같은 문제가 반복된다. 따라서 개발·git·CodeGraph를 모두
Linux로 고정한다.

## 1. 디렉터리 레이아웃

기존 경로를 즉시 버릴 필요는 없다. 중요한 것은 **그 worktree를 Linux git 기준으로
복구한 뒤 Windows git으로 다시 만지지 않는 것**이다.

```text
/mnt/f/dev/pinvi                  # 사람 trunk 또는 기존 Windows 디스크 checkout
/mnt/f/dev/pinvi-codex            # Codex 고정 worktree, Linux git으로 운용
/mnt/f/dev/pinvi-claude           # Claude 고정 worktree, Linux git으로 운용
/mnt/f/dev/pinvi-antigravity      # Antigravity 고정 worktree, Linux git으로 운용

~/pinvi-workspaces/pinvi-codex    # 선택: Linux ext4 고정 worktree로 새로 만들 때
~/pinvi-workspaces/pinvi-claude
~/pinvi-workspaces/pinvi-antigravity
```

| 종류 | 표준 위치 | 비고 |
|------|-----------|------|
| git / 편집 / commit / PR | Linux에서 접근 가능한 agent worktree | `/mnt/f/...` 기존 worktree도 Linux git 포인터로 복구 후 사용 가능 |
| 의존성·테스트·Docker·장기 실행 | Linux worktree | 별도 rsync 미러를 source of truth로 쓰지 않는다 |
| 프론트 dev/lint/typecheck/build/Vitest | Linux worktree | Linux Node/npm |
| Playwright 브라우저 e2e | N150 우선 | 불가 시 Windows fallback, 사유 기록 |
| 데이터 (`dataset/`, `refdocs/`) | 로컬 원본 또는 symlink | 변경 금지 데이터는 절대경로/symlink로 참조 |
| 빌드 산출물 (`.next`, `build`) | Linux worktree 내부 | `.gitignore` 대상, 폐기 가능 |

## 2. 기존 worktree Linux 포인터 복구

기존 worktree의 `.git` 파일이 `F:/...`를 가리키면 Linux git에서 실패한다. trunk의
공유 `.git` 디렉터리에 Linux 경로로 접근해 repair한다.

```bash
cd /mnt/f/dev/pinvi
git worktree repair /mnt/f/dev/pinvi-codex
git worktree repair /mnt/f/dev/pinvi-claude
git worktree repair /mnt/f/dev/pinvi-antigravity
git worktree list
```

정상 예:

```text
/mnt/f/dev/pinvi-codex  <sha> [agent/codex-idle]
```

금지 예:

```text
/mnt/f/dev/pinvi/.git/worktrees/.../F:/dev/pinvi-codex  <sha> [branch] prunable
```

`prunable`로 보이면 `git worktree prune`을 바로 실행하지 말고, 먼저 `git worktree
repair <worktree>`를 실행한다. 이후 같은 worktree를 Windows `git.exe`로 조작하지
않는다.

## 3. 새 task 시작

```bash
cd /mnt/f/dev/pinvi-codex
git fetch origin
git switch -c agent/codex-<task> origin/main
codegraph status
codegraph sync
```

- 로컬 `main`은 trunk가 점유할 수 있으므로 worktree에서는 `origin/main`을 기준 ref로
  쓴다.
- 브랜치 이름은 `agent/<agent>-<task>`를 기본으로 한다.
- 작업 중 `git status`가 느릴 수 있다. 실패가 아니라 NTFS 마운트 비용일 수 있으므로
  기다리되, `fatal`이 나오면 §2 포인터부터 확인한다.

## 4. Linux 도구 PATH 점검

작업 셸의 첫 확인:

```bash
command -v git rg node npm codegraph
```

허용:

```text
/usr/bin/git
/usr/bin/rg
/home/<user>/.nvm/versions/node/.../bin/node
/home/<user>/.local/bin/codegraph
```

중지해야 하는 예:

```text
/mnt/c/Program Files/Git/cmd/git.exe
/mnt/c/Users/<user>/AppData/Roaming/npm/codegraph
node.exe
npm.cmd
```

Windows shim이 보이면 그 셸에서 개발 명령을 실행하지 않는다. Linux Node/npm 또는
CodeGraph standalone 설치를 PATH 앞에 둔 뒤 다시 확인한다.

## 5. 시스템 패키지

Ubuntu/WSL 기준 1회:

```bash
sudo apt update
sudo apt install -y \
  build-essential python3-dev \
  libpq-dev \
  libgdal-dev gdal-bin \
  libgeos-dev libproj-dev libspatialindex-dev
gdal-config --version
```

## 6. Python / Node 셋업

```bash
cd /mnt/f/dev/pinvi-codex

# Python
cd apps/api
uv venv .venv --python 3.12
. .venv/bin/activate
uv pip install -e ".[dev]"
uv pip install "gdal==$(gdal-config --version)"

# Node
cd /mnt/f/dev/pinvi-codex
npm install
```

Linux ext4 worktree를 별도로 쓰는 경우 경로만 `~/pinvi-workspaces/pinvi-codex`로
바꾼다. 어떤 경로든 commit/push는 그 **동일 Linux worktree**에서 수행한다.

## 7. 검증 게이트

```bash
cd /mnt/f/dev/pinvi-codex/apps/api
. .venv/bin/activate
export PINVI_JWT_SECRET_KEY='pinvi-test-jwt-secret-32bytes-minimum-aaaa'
export TESTCONTAINERS_RYUK_DISABLED=true
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp

python -m pytest tests/unit -q
python -m pytest tests/integration -q
ruff check app tests
ruff format --check app tests
mypy --strict app
```

프론트:

```bash
cd /mnt/f/dev/pinvi-codex
npm -w @pinvi/web run lint
npm -w @pinvi/web run typecheck
npm -w @pinvi/web run build
npm -w @pinvi/web run test
```

Docker, PostgreSQL/PostGIS, Dagster, dev server도 Linux에서 실행한다. 고정 dev 포트는
ADR-047을 따른다.

## 8. Playwright 실행 우선순위

1. **N150 우선**: live 또는 UI e2e는 N150 환경에서 먼저 실행한다. 운영 public
   Web/API, 컨테이너 상태, CORS/WebSocket, reverse proxy drift를 함께 잡기 위함이다.
2. **Windows fallback**: N150에서 브라우저 설치, 권한, display/runtime, 네트워크 접근
   문제가 있어 실행할 수 없을 때만 Windows runner를 사용한다.
3. **기록 필수**: 검증 로그에는 `N150`, `Windows fallback`, 또는 `Linux local` 중
   실제 실행 위치와 fallback 사유를 적는다.

예:

```bash
# N150에서 직접 실행하거나 원격 셸로 실행
npm -w @pinvi/web run test:e2e -- admin-etl-provider-sync.e2e.ts --workers=1
```

Windows fallback을 썼다면 PR 검증에는 다음처럼 남긴다.

```text
Playwright: N150 브라우저 runtime 미설치로 Windows fallback runner에서
admin-etl-provider-sync.e2e.ts 1건 통과.
```

## 9. 원격/N150 명령

N150 명령은 중첩 quote를 피한다. 가능한 한 스크립트를 stdin으로 한 번만 전달한다.

```bash
ssh -o BatchMode=yes <n150-ssh-target> 'bash -s' <<'SH'
set -euo pipefail
cd ~/pinvi
git fetch origin
git status --short --branch
SH
```

실제 SSH target, 운영 도메인, IP는 추적 문서에 쓰지 않는다. 민감 운영 값은
`docs/deploy-runbook.local.md`에만 둔다.

## 10. 작업 후 체크리스트

- [ ] Linux `git status --short --branch`로 변경 범위 확인
- [ ] Linux `codegraph status` / `codegraph sync` 확인 (`/mnt/c` shim 금지)
- [ ] 관련 Linux 테스트/lint/typecheck 실행
- [ ] UI/e2e면 N150 Playwright 우선 실행, 불가 시 Windows fallback 사유 기록
- [ ] `docs/journal.md`, `docs/resume.md`, 관련 task 문서 갱신
- [ ] push 직전 보안 감사 실행
- [ ] Linux git으로 commit/push/PR 생성

## 참고

- ADR-051 — Linux 전용 개발·git·CodeGraph + N150 우선 Playwright.
- ADR-017 — agent별 고정 worktree + CodeGraph 인덱스. Windows `git.exe` amendment는
  ADR-051이 supersede.
- ADR-024 — 과거 NTFS source / WSL 미러 모델. ADR-051이 supersede.
- `docs/runbooks/codegraph-worktrees.md` — worktree와 CodeGraph 운영.
- `docs/agent-workflow.md` — 에이전트용 붙여넣기 절차.
- `docs/agent-failure-patterns.md` — 반복 실패와 복구.
