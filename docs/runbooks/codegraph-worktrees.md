# CodeGraph + agent별 고정 worktree 운영

> ADR-017로 agent별 고정 worktree와 CodeGraph 인덱스를 도입했다. ADR-051은 이
> 운영을 **Linux 전용 git/CodeGraph** 기준으로 갱신한다.

## 0. 개요

```text
/mnt/f/dev/pinvi                  # 사람 trunk 또는 기존 checkout
/mnt/f/dev/pinvi-claude           # Claude Code 전용 worktree
/mnt/f/dev/pinvi-codex            # OpenAI Codex 전용 worktree
/mnt/f/dev/pinvi-antigravity      # Google Antigravity 전용 worktree
```

- worktree는 영속이고, 작업마다 branch만 새로 딴다.
- 새 작업은 `git fetch && git switch -c agent/<agent>-<task> origin/main`.
- CodeGraph는 worktree마다 1회 `codegraph init -i`, 이후 task 시작 시
  `codegraph sync`.
- `.codegraph/`는 `.gitignore` 대상이다.
- AI 도구는 trunk를 직접 편집하지 않고 각자 worktree만 사용한다.
- git과 CodeGraph는 모두 Linux에서 실행한다. Windows `git.exe`와 `/mnt/c/...`
  CodeGraph shim은 사용하지 않는다.

## 1. 1회 setup — worktree + CodeGraph

### 1.1 Linux 도구 확인

```bash
command -v git rg node npm codegraph
```

다음 결과가 나오면 중지한다.

```text
/mnt/c/...
*.exe
*.cmd
```

Linux native 도구가 PATH 앞에 오도록 수정한 뒤 다시 확인한다.

### 1.2 기존 worktree 포인터 복구

과거 Windows git 기반 worktree는 `.git`/`gitdir` 포인터가 `F:/...`를 들고 있을 수
있다. Linux에서 먼저 repair한다.

```bash
cd /mnt/f/dev/pinvi
git worktree repair /mnt/f/dev/pinvi-claude
git worktree repair /mnt/f/dev/pinvi-codex
git worktree repair /mnt/f/dev/pinvi-antigravity
git worktree list
```

정상 worktree가 `prunable`로 보이면 `prune`을 실행하지 말고 repair를 다시 확인한다.
복구 후에는 같은 worktree를 Windows `git.exe`로 다루지 않는다.

### 1.3 새 worktree 생성

새로 만들 때도 Linux git을 사용한다.

```bash
cd /mnt/f/dev/pinvi
git fetch origin
git worktree add ../pinvi-claude      -b agent/claude-idle      origin/main
git worktree add ../pinvi-codex       -b agent/codex-idle       origin/main
git worktree add ../pinvi-antigravity -b agent/antigravity-idle origin/main
```

idle branch는 첫 자리표시자일 뿐이다. 실제 작업은 §2.1의 새 branch에서 진행한다.

### 1.4 CodeGraph 설치

Linux native 설치만 허용한다.

```bash
# Node 기반
npm install -g @colbymchenry/codegraph
# /usr/local 권한이 없으면 사용자 prefix 사용
npm install -g --prefix "$HOME/.local" @colbymchenry/codegraph

# 또는 Linux standalone
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh

codegraph --version
codegraph install --target=auto --location=global
```

설치 후 `command -v codegraph`가 `/mnt/c/...`를 가리키지 않는지 다시 확인한다.

### 1.5 worktree마다 인덱스 초기화

```bash
cd /mnt/f/dev/pinvi-codex
codegraph init -i
codegraph status
```

## 1.6 명령 치트시트 + 작업 룰

| 명령 | 용도 | 주기 |
|------|------|------|
| `codegraph init -i` | 인덱싱 초기화 | worktree마다 1회 |
| `codegraph sync` | 변경 incremental 반영 | 새 task 시작 시 / 큰 git switch 후 |
| `codegraph status` | 동기화 상태 확인 | 의심될 때 |
| `codegraph query <name>` | 심볼 이름 lookup | 수시 |
| `codegraph index --force` | 전체 재빌드 | stale 의심 + sync 실패 시 최후 수단 |

### 코드 수정 룰 — 영향도 평가 먼저

컴포넌트 / 함수 / 서비스를 수정하기 전에 반드시 `codegraph_explore`로 영향도를 먼저
평가한다. grep / Read fan-out 대신 한 번의 MCP 호출로 관련 심볼 source + 호출 관계를
가져온다.

| 의도 | 1차 도구 | 보조 |
|------|---------|------|
| 컴포넌트 / 모듈 주변 파악 | `codegraph_explore` | `codegraph_context` |
| 변경 영향 반경 | `codegraph_impact` | `codegraph_callers` |
| 호출 경로 추적 | `codegraph_trace` | — |
| 심볼 이름 lookup | `codegraph_search` | `codegraph_node` |

답이 인덱스에서 나오면 같은 소스를 다시 파일 read로 펼치지 않는다.

## 2. 작업 흐름

### 2.1 새 task 시작

```bash
cd /mnt/f/dev/pinvi-codex
git fetch origin
git switch -c agent/codex-<task> origin/main
codegraph sync
```

- 기준 ref는 `origin/main`이다. 로컬 `main`은 trunk가 점유할 수 있다.
- branch convention은 `agent/<agent>-<task>`.

### 2.2 commit / push / PR

```bash
git status --short --branch
git add <intended-files>
git commit -m "docs: document linux development workflow"
git push -u origin "$(git branch --show-current)"
```

push 전에는 `AGENTS.md`의 보안 감사 절차를 실행한다.

### 2.3 PR 머지 후 다음 task

PR이 머지되면 다음 작업은 최신 `origin/main`에서 새 브랜치를 만든다.

```bash
git fetch origin
git switch -c agent/codex-<next-task> origin/main
codegraph sync
```

## 3. 자주 마주치는 상황

### 3.1 worktree 별도 ignore

`.codegraph/`, `.next/`, `.venv/` 등은 저장소 `.gitignore`에 둔다. 개인 IDE 캐시는
필요하면 `.git/info/exclude`를 쓴다.

### 3.2 CodeGraph가 stale로 의심될 때

```bash
codegraph status
codegraph sync
codegraph index --force
```

`command -v codegraph`가 Linux native인지 먼저 확인한다.

### 3.3 `main` 기준

trunk가 `main`을 점유하면 worktree에서 `git switch main`은 실패할 수 있다. 새
브랜치, diff, rebase는 모두 `origin/main` 기준으로 수행한다.

```bash
git fetch origin
git diff origin/main..HEAD
git rebase origin/main
```

### 3.4 포인터가 다시 깨졌을 때

```bash
cd /mnt/f/dev/pinvi
git worktree repair /mnt/f/dev/pinvi-codex
git worktree list
```

`F:/...`가 다시 보이면 해당 worktree를 Windows git으로 만진 흔적이다. Linux repair 후
Windows git 사용을 중지한다.

## 4. Telegram 완료 알림 MCP

각 agent worktree에는 `mcp-telegram` MCP 설정과 로컬 `.env.mcp-telegram` credential이
있다. `.env.mcp-telegram`은 gitignore 대상이며 GitHub secret/워크플로에 넣지 않는다.

단위 작업이 PR로 마무리되면 최종 응답 전 `send_message`로 완료 요약과 PR 링크를
보낸다. PR이 없는 로컬 문서/셋업 작업이면 branch/commit 또는 "PR 없음"을 명시한다.

## 5. N150 / Playwright

UI 또는 live 검증은 N150 Playwright를 우선한다. N150에서 브라우저 runtime, 권한,
display, 네트워크 문제로 실행할 수 없을 때만 Windows runner를 fallback으로 사용한다.
fallback을 쓰면 journal/PR 검증에 사유와 명령을 남긴다.

## 참고

- ADR-017 — agent별 고정 worktree + CodeGraph.
- ADR-051 — Linux 전용 개발·git·CodeGraph + N150 우선 Playwright.
- ADR-024 — 과거 NTFS source / WSL 미러 모델. ADR-051이 supersede.
- `docs/dev-environment.md` — Linux 개발 환경 정본.
- `docs/agent-workflow.md` — 붙여넣기용 작업 루프.
- `docs/agent-failure-patterns.md` — 반복 실패와 복구.
