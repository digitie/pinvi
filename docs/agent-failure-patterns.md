# 반복되는 에이전트 실패 패턴과 재발 방지

본 문서는 ADR-051의 **Linux 전용 개발·git·CodeGraph** 정책 아래에서 AI
에이전트(Claude / Codex / Antigravity)가 자주 부딪히는 환경·도구 계층 실패를
정리한다. 같은 증상이면 프로젝트 코드 버그로 오판하기 전에 먼저 본 문서를 확인한다.

## 1. 한눈에 보는 분류

| 증상 | 실제 원인 | 1차 대응 |
|------|-----------|-----------|
| `fatal: not a git repository: ... F:/dev/.../.git/worktrees/...` | worktree 포인터가 Windows 경로로 남아 Linux git이 해석하지 못함 | Linux에서 `git worktree repair <worktree>` |
| `git worktree list`에 정상 worktree가 `prunable`로 표시 | `.git`/`gitdir` 포인터가 서로 다른 OS 경로 체계를 가리킴 | `prune` 금지, repair 먼저 |
| `command -v codegraph`가 `/mnt/c/...`를 가리킴 | Windows npm shim이 WSL PATH 앞에 있음 | Linux native CodeGraph 설치/PATH 교정 |
| `node`, `npm`, `rg`, `git`이 `.exe`/`.cmd`로 잡힘 | Windows shim 오염 | 해당 셸에서 중지하고 Linux 도구로 교정 |
| PowerShell → WSL → SSH → Docker → Python quote가 반복 실패 | 여러 shell이 따옴표/escape를 재해석 | Linux 셸에서 stdin script 방식 사용 |
| 통합 테스트가 "table does not exist" / "another operation in progress" | async alembic commit 또는 pytest-asyncio loop/pool 문제 | env.py commit, 함수 스코프 엔진 + NullPool |

## 2. 패턴 A — worktree 포인터가 Windows 경로로 남음

### 증상

- Linux에서 `git status`가 실패한다.
- 오류에 `F:/dev/...`와 `/mnt/f/...`가 섞여 나온다.
- `git worktree list`가 실제 worktree를 `prunable`로 표시한다.

### 원인

worktree의 `.git` 파일과 main repo의 `worktrees/*/gitdir`에는 worktree를 만든
환경의 절대경로가 저장된다. 과거 Windows git 기반 모델의 흔적이 남으면 Linux git은
`F:/...`를 상대경로처럼 해석하거나 존재하지 않는 경로로 판단한다.

### 재발 방지

```bash
cd /mnt/f/dev/pinvi
git worktree repair /mnt/f/dev/pinvi-codex
git worktree repair /mnt/f/dev/pinvi-claude
git worktree repair /mnt/f/dev/pinvi-antigravity
git worktree list
```

복구 후 원칙:

1. 같은 worktree를 Windows `git.exe`로 다시 조작하지 않는다.
2. `prunable`이 보여도 바로 `git worktree prune`을 실행하지 않는다.
3. 새 worktree도 Linux git으로 만든다.

## 3. 패턴 B — Windows shim PATH 오염

### 증상

```bash
command -v git rg node npm codegraph
```

결과가 다음처럼 나온다.

```text
/mnt/c/Program Files/Git/cmd/git.exe
/mnt/c/Users/<user>/AppData/Roaming/npm/codegraph
node.exe
npm.cmd
```

### 원인

WSL PATH 앞쪽에 Windows PATH가 들어와 Linux 명령 대신 Windows shim이 실행된다. 특히
CodeGraph가 Windows npm shim으로 잡히면 Linux 경로 기준 인덱스/포인터 정책을 다시 흐린다.

### 재발 방지

1. 해당 셸에서 개발 명령을 중지한다.
2. Linux Node/npm, Linux `rg`, Linux `git`, Linux native `codegraph`가 PATH 앞에 오도록
   조정한다.
3. `command -v ...`로 다시 확인한 뒤 작업을 재개한다.

## 4. 패턴 C — 중첩 quote 실패

N150 같은 원격 Linux에서 PowerShell → WSL → SSH → Docker → Python을 한 줄에 모두
넣으면 작은따옴표/큰따옴표가 계층마다 다시 해석되어 실패한다.

금지:

```powershell
wsl.exe -e bash -lc 'ssh user@host "docker exec app python - <<'PY' ... PY"'
```

표준:

```bash
ssh -o BatchMode=yes <n150-ssh-target> 'bash -s' <<'SH'
set -euo pipefail
cd ~/pinvi
docker exec -i pinvi-api-latest python - <<'PY'
print("hello")
PY
SH
```

원칙:

1. 원격 shell command 문자열 안에 Python heredoc을 직접 중첩하지 않는다.
2. JSON payload가 필요한 `curl` smoke도 stdin script로 전달한다.
3. 세 번 이상 같은 quote 실패가 나면 즉시 스크립트화하거나 문서화한다.

## 5. 패턴 D — escape 손상 + 도구별 `\n` 오해석

### 증상

- inline rewrite 뒤 `"\n"` 또는 regex backslash가 깨진다.
- MSYS/Git-Bash 계열 도구가 정상 문서를 손상으로 오판한다.

### 재발 방지

1. 대량 inline rewrite 대신 targeted patch를 우선한다.
2. `\n`, regex, Windows 경로처럼 backslash 많은 문자열은 수정 직후 다시 연다.
3. 패턴 검사는 Linux native `rg`와 `od -c`로 교차검증한다.
4. 수정 후 `git diff --check`를 실행한다.

## 6. 패턴 E — 통합 테스트 환경

### 증상

- `relation "app.users" does not exist`
- `another operation is in progress`
- `Future attached to a different loop`

### 원인·대응

- async alembic이 DDL 트랜잭션을 commit하지 않음 → async 경로에
  `await connection.commit()` 필요.
- pytest-asyncio loop/pool 공유 → 통합 테스트 엔진은 함수 스코프 + `NullPool`.
- `TMPDIR`/`TMP`/`TEMP`가 Windows Temp를 가리킴 → Linux 검증 셸에서
  `export TMPDIR=/tmp TMP=/tmp TEMP=/tmp`.

## 7. Playwright 실패 분류

1. 먼저 N150에서 실행한다.
2. 브라우저 runtime, 권한, display, 네트워크 문제로 N150 실행이 불가능하면 Windows
   fallback을 사용한다.
3. fallback을 쓴 경우 journal/PR에 N150 실패 사유와 Windows 실행 명령을 적는다.

## 8. 표준 fallback 순서

1. **Git/branch/commit**: Linux git + Linux worktree 포인터.
2. **탐색**: Linux native `rg`, `sed`, `git`, CodeGraph.
3. **검증**: Linux `pytest` / `ruff` / `mypy` / `npm` / Docker.
4. **브라우저**: N150 Playwright 우선, 불가 시 Windows fallback.
5. **문서화**: 새 실패 패턴이 재현되면 `docs/journal.md`와 본 문서에 추가.

## 참고

- `docs/dev-environment.md` — ADR-051 환경 모델·셋업·검증.
- `docs/agent-workflow.md` — 붙여넣기용 작업 루프.
- `docs/runbooks/codegraph-worktrees.md` — worktree와 CodeGraph 운영.
- ADR-051 — Linux 전용 개발·git·CodeGraph + N150 우선 Playwright.
