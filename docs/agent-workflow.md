# 에이전트 개발 워크플로 런북 — NTFS git + WSL 코딩/테스트

> **목적**: NTFS 고정 worktree에서 편집·git을, WSL ext4 미러에서 설치·테스트를
> 수행하는 **현재 방식**(ADR-024)을 새 에이전트(특히 WSL의 Codex)가 그대로 따라할
> 수 있게 정리한다. 배경·세부는 `docs/dev-environment.md`, 반복 실패는
> `docs/agent-failure-patterns.md`, worktree·CodeGraph는
> `docs/runbooks/codegraph-worktrees.md`.
>
> 이 문서는 "내가 손에 든 셸에서 어떤 순서로 무엇을 치면 동작하는 개발 루프가
> 되는가"에 답한다. 사양이 아니라 런북이다. `python-kraddr-geo`의
> `docs/agent-workflow.md`와 같은 구조다(도구 간 일관).

## 0. 큰 그림 — 두 위치를 절대 헷갈리지 말 것

| 위치 | 정체 | 여기서 하는 것 | 여기서 하지 않는 것 |
|------|------|----------------|---------------------|
| **NTFS 고정 worktree** (에이전트별) | git source of truth | 편집, branch, commit, push, PR | `uv pip install`, `pytest`, `npm`, `docker`, `uvicorn` 같은 무거운 실행 |
| **WSL ext4 테스트 미러** | 실행 산출물 전용 사본 | 의존성 설치, pytest, ruff/mypy, frontend 검증, docker, 장기 실행 | commit, push, PR (여기 변경은 worktree로 되가져온다) |

- 에이전트별 worktree는 **고정 이름**이다(ADR-017): Claude=`tripmate-claude`,
  Codex=`tripmate-codex`, Antigravity=`tripmate-antigravity`. idle branch는
  `agent/<agent>-idle`.
- **폐기된 옛 방식**(문서에서 보이면 무시): `geo-*` worktree 접두사, "WSL ext4가
  표준 작업 위치 / Git source of truth는 ext4 / 양방향 rsync"(ADR-024가 supersede).
- **NTFS worktree에서 직접 무거운 테스트/설치를 돌리지 않는다.** `/mnt` NTFS는
  대량 I/O·파일워치·임시파일 처리에서 반복 문제를 낸다. 그래서 미러가 따로 있다.
- **rsync는 NTFS → ext4 단방향.** 수정은 NTFS worktree에 하고 미러로 다시 내려보낸다.

## 1. 먼저 없애야 할 함정 (이게 매번 발목을 잡는다)

`docs/agent-failure-patterns.md`에 전체가 있다. 셋업 첫 단계에서 한 번에 해결한다.

### (A) NTFS worktree는 Windows git.exe로만
WSL에서 `/mnt/f/dev/tripmate-<agent>`에 `git`을 실행하면 포인터가 환경별 절대경로로
박혀 `fatal: not a git repository` / `prunable`이 난다. **NTFS worktree의 git은
Windows `git.exe`로만** 다룬다(패턴 A).

### (B) Windows npm/node/rg shim이 PATH를 가린다
WSL PATH에 `/mnt/c/...`의 Windows shim이 먼저 잡히면 `node: not found`, UNC 경로
경고가 난다. `command -v npm node git rg`로 확인하고 Linux Node를 PATH 앞에 둔다
(nvm). Playwright·브라우저 렌더링·스크린샷은 **Windows에서만**.

### (C) TMP/TEMP가 Windows Temp를 가리킨다
WSL 기본 `TMP`/`TEMP`가 `/mnt/c/...`이면 pytest capture가 시작 전 `FileNotFoundError`로
죽는다. 검증 셸에서 한 번 `export TMPDIR=/tmp TMP=/tmp TEMP=/tmp`.

## 2. 셋업 — 미러 만들기/갱신 (세션 시작마다)

NTFS worktree 기준으로 ext4 미러를 단방향 rsync한다. exclude 전체는
`docs/dev-environment.md` §3.1.

```bash
mkdir -p ~/tripmate-workspaces/tripmate-claude
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude '.venv*' \
  --exclude node_modules --exclude .next \
  --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache --exclude .ruff_cache \
  --exclude dataset --exclude refdocs --exclude testset --exclude test-results \
  /mnt/f/dev/tripmate-claude/ \
  ~/tripmate-workspaces/tripmate-claude/

cd ~/tripmate-workspaces/tripmate-claude
# 대용량 데이터는 NTFS 원본을 symlink (복사하지 않는다)
test -e dataset || ln -s /mnt/f/dev/tripmate/dataset dataset
test -e refdocs || ln -s /mnt/f/dev/tripmate/refdocs refdocs

# Python 환경 (최초 1회). GDAL 핀은 dev-environment.md §4~5.
cd apps/api && uv venv .venv-wsl --python 3.12 && . .venv-wsl/bin/activate
uv pip install -e ".[dev]"
```

> 미러에서 발견한 수정은 **NTFS worktree에 반영**하고 다시 단방향 sync. commit/push는
> NTFS worktree에서만. 미러는 버려도 되는 실행 사본이다.

## 3. 작업 루프 (편집은 NTFS, 실행은 미러)

```
편집/branch/commit/push/PR  ── NTFS worktree (F:/dev/tripmate-<agent>, Windows git.exe)
        │   (변경을 미러로 NTFS→ext4 단방향 rsync — 미러에서 같은 파일을 직접 편집하지 말 것)
        ▼
검증                         ── WSL ext4 미러 (~/tripmate-workspaces/tripmate-<agent>)
  backend:  cd apps/api && . .venv-wsl/bin/activate
            export TRIPMATE_JWT_SECRET_KEY=... TESTCONTAINERS_RYUK_DISABLED=true TMPDIR=/tmp TMP=/tmp TEMP=/tmp
            pytest tests/unit -q · pytest tests/integration -q · ruff check . · ruff format --check . · mypy --strict app
  frontend: Linux Node 로 npm run lint · npm run typecheck · npm run build
  browser:  Playwright/스크린샷은 Windows에서만, 명령·경로를 journal에 기록
        │
        ▼
기록                         ── journal.md(append) + resume.md 갱신 (NTFS worktree)
```

## 4. git worktree 환경 정책 (Windows Git metadata 기준)

worktree의 `.git` 포인터에는 만든 환경의 절대경로가 박힌다(§1-A). 둘이 섞이면
`fatal: not a git repository` / `prunable`. 그래서 **NTFS worktree의 git은 Windows
git.exe로 통일**한다.

- WSL에서 worktree git 작업이 꼭 필요하면 Windows git을 호출:
  `"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/tripmate-<agent> status -sb`.
- 포인터가 깨지면 Windows에서 `git -C F:/dev/tripmate worktree repair
  F:/dev/tripmate-<agent>` 한 번으로 복구. `prune`은 **Windows에서만**.
- 커밋되는 문서/코드에는 사용자명·머신 구조가 드러나는 절대경로를 넣지 않는다
  (상대경로/`<placeholder>`).
- 반복 환경/도구 실패는 `docs/agent-failure-patterns.md` 먼저 확인.

## 5. 붙여넣기용 체크리스트

```bash
# --- WSL ext4 미러에서 (검증) ---
cd ~/tripmate-workspaces/tripmate-claude
rsync -a --delete --exclude .git --exclude '.venv*' --exclude node_modules \
  --exclude .next --exclude __pycache__ --exclude .mypy_cache --exclude .pytest_cache --exclude .ruff_cache \
  /mnt/f/dev/tripmate-claude/ ./
cd apps/api && . .venv-wsl/bin/activate
export TRIPMATE_JWT_SECRET_KEY='tripmate-test-jwt-secret-32bytes-minimum-aaaa'
export TESTCONTAINERS_RYUK_DISABLED=true TMPDIR=/tmp TMP=/tmp TEMP=/tmp
pytest tests/unit -q && pytest tests/integration -q
ruff check . && ruff format --check . && mypy --strict app
codegraph sync && codegraph status      # NTFS는 watcher 비활성 → 수동
```

```powershell
# --- NTFS worktree에서 (편집/git, Windows PowerShell) ---
cd F:\dev\tripmate-claude
git fetch origin
git switch -c agent/claude-<task> origin/main
# ...편집...
git add -A; git commit -m "..."; git push -u origin agent/claude-<task>
gh pr create --base main --head agent/claude-<task> ...
# PR 생성 후, 최종 응답 전: mcp-telegram MCP send_message로 완료 요약 + PR 링크 전송
#   (AGENTS.md "Telegram 작업 완료 알림 MCP", 셋업: codegraph-worktrees.md §3.6)
```

> **PR 후 Telegram 알림**: 단위 작업이 PR로 마무리되면 최종 응답 전에 `mcp-telegram`
> MCP의 `send_message`(`entity`=알림 대상, 기본 `me`)로 짧은 완료 요약 + PR 링크를
> 보낸다. credential은 worktree 로컬 `.env.mcp-telegram`에만 둔다.

## 참고

- `docs/dev-environment.md` — 시스템 패키지·미러 rsync exclude·검증 게이트·함정 전체 (ADR-024).
- `docs/agent-failure-patterns.md` — 반복되는 환경/도구 실패와 재발 방지.
- `docs/runbooks/codegraph-worktrees.md` — worktree 생성·CodeGraph·git 포인터 복구 (ADR-017).
- `docs/agent-guide.md` — 문서화·재개 프로토콜(본 런북은 그 환경 부분을 구체화).
- `python-kraddr-geo` `docs/agent-workflow.md` — 동일 구조 reference.
