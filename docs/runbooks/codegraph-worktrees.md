# CodeGraph + agent별 고정 worktree 운영

> ADR-017 박힘. AI 도구 (Claude Code / Codex / Antigravity)가 본 저장소를 동시
> 편집할 때 충돌 / drift를 막기 위한 1차 runbook.

## 0. 개요

```
F:/dev/tripmate              ← 사람 trunk (사용자가 직접 만지는 checkout)
  ├── (worktree)
F:/dev/tripmate-claude   ← Claude Code 전용 worktree (영속)
F:/dev/tripmate-codex    ← OpenAI Codex 전용 worktree (영속)
F:/dev/tripmate-antigravity  ← Google Antigravity 2.0 전용 worktree (영속)
```

- **worktree는 영속**, 작업마다 **branch만** 새로 따는 방식 (`git switch -c
  agent/<agent>-<task> origin/main`) — 로컬 `main` ref는 trunk가 점유하므로
  worktree에서는 `origin/main`을 직접 사용한다 (§3.3 참고).
- **CodeGraph** (`colbymchenry/codegraph`)는 worktree마다 1회 `codegraph init
  -i` 후 task 시작 시 `codegraph sync`로 유지.
- `.codegraph/` 디렉터리는 `.gitignore` — 로컬 SQLite 인덱스, 도구 / OS /
  worktree마다 별개.
- AI 도구는 **절대 trunk** (`F:/dev/tripmate`)를 직접 만지지 않는다 — 각자
  worktree만 사용.

> **환경 모델 (ADR-024)**: NTFS worktree(`F:/dev/tripmate-<agent>`)가 git source of
> truth이고 git은 Windows git(`git.exe`)으로만 다룬다. WSL ext4
> (`~/tripmate-workspaces/tripmate-<agent>`)는 의존성·테스트·docker 전용 **일회용
> 미러**(commit 금지, NTFS→ext4 단방향 rsync)다. 셋업·검증 절차는
> `docs/dev-environment.md`. 같은 worktree를 Windows git과 WSL git으로 번갈아
> 다루지 않는다(§3.6 git 포인터 함정).

## 1. 1회 setup — worktree + CodeGraph init

### 1.1 trunk 위치 확인

사람이 직접 만지는 trunk가 `F:/dev/tripmate` (Windows) 또는
`~/tripmate-workspaces/tripmate` (WSL)에 있다고 가정. 아니라면 `git rev-parse
--show-toplevel`로 확인.

### 1.2 agent별 worktree 생성

```powershell
# Windows PowerShell — trunk 위치에서 Windows git.exe 로 생성 (권장)
cd F:\dev\tripmate
git fetch origin
git worktree add ../tripmate-claude      -b agent/claude-idle      origin/main
git worktree add ../tripmate-codex       -b agent/codex-idle       origin/main
git worktree add ../tripmate-antigravity -b agent/antigravity-idle origin/main
```

- **worktree는 Windows git(`git.exe`)으로 생성**한다. WSL에서 `/mnt/f/...`에
  `git worktree add`로 만들면 `.git`/`gitdir` 포인터가 `/mnt/f/...`로 박혀, 이후
  Windows git이 `prunable`로 보고 잘못 prune할 수 있다(ADR-024, §3.6). 포인터가
  이미 환경별로 갈렸으면 `git worktree repair <경로>`로 맞춘다.
- idle 브랜치는 **`agent/<agent>-idle`** (kraddr-geo 컨벤션과 통일). 첫 dummy일 뿐,
  실제 task 시작 시 새 브랜치로 갈아탄다(§2.1).
- worktree 자체는 영속 — 사용자가 `git worktree remove`로 직접 제거하지 않는 한
  유지.

### 1.3 CodeGraph 설치 (1회, 머신 전체)

```bash
# Node 있으면
npm install -g @colbymchenry/codegraph

# Node 없으면 self-contained 빌드
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
# Windows PowerShell
irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex
```

확인:

```bash
codegraph --version
```

설치 후 본인이 쓰는 agent의 MCP 설정이 자동 wiring 되도록 한 번:

```bash
codegraph install --target=auto --location=global
```

> Claude Code는 본 명령 후 재시작 1회 필요. Codex / Antigravity도 동일.

#### 1.3.1 Claude Code 수동 wiring (`~/.claude.json`)

`codegraph install`이 동작하지 않거나 (네트워크 / 권한 문제) 정확히 어떻게 박히는지
보고 싶다면 직접:

```jsonc
// ~/.claude.json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@colbymchenry/codegraph", "serve", "--mcp"]
    }
  }
}
```

- 글로벌 설치 (`npm install -g @colbymchenry/codegraph`) 이미 했다면 더 간단한
  `command: "codegraph", args: ["serve", "--mcp"]`도 동작. npx 형태는 글로벌
  설치 없이도 재현 가능하므로 새 머신 / 동료 setup용 snippet으로 권장.
- 잘못된 형태 주의: `args: [..., "mcp"]` (mcp 단독 서브커맨드)는 codegraph CLI에
  없음. **반드시 `serve --mcp`**.

권한 자동 허용 (선택, 매 호출마다 prompt 안 뜨게):

```jsonc
// ~/.claude/settings.json
{
  "permissions": {
    "allow": [
      "mcp__codegraph__codegraph_search",
      "mcp__codegraph__codegraph_context",
      "mcp__codegraph__codegraph_trace",
      "mcp__codegraph__codegraph_explore",
      "mcp__codegraph__codegraph_callers",
      "mcp__codegraph__codegraph_callees",
      "mcp__codegraph__codegraph_impact",
      "mcp__codegraph__codegraph_node",
      "mcp__codegraph__codegraph_status",
      "mcp__codegraph__codegraph_files"
    ]
  }
}
```

수정 후 **Claude Code 재시작 1회** 필요.

### 1.4 worktree마다 CodeGraph 인덱스 초기화 (1회)

worktree마다 **딱 한 번**:

```bash
cd F:/dev/tripmate-claude   # (혹은 본인 agent의 worktree)
codegraph init -i               # interactive — 진행률 출력
```

- `.codegraph/codegraph.db` 생성 (SQLite + FTS5).
- 대형 monorepo는 5~15분. 이후엔 incremental.

### 1.5 sanity 확인

```bash
codegraph status
codegraph query AdminUserSummary --limit 5
```

문제 없으면 setup 끝.

## 1.6 명령 치트시트 + 작업 룰

| 명령 | 용도 | 주기 |
|------|------|------|
| `codegraph init -i` | **인덱싱 초기화** (interactive 진행률) | worktree마다 1회 |
| `codegraph sync` | 변경 incremental 반영 | 새 task 시작 시 / 큰 git switch 후 |
| `codegraph status` | **동기화 상태 확인** (last_sync, node/edge count) | 의심될 때 |
| `codegraph query <name>` | 심볼 이름으로 빠른 lookup | 수시 |
| `codegraph index --force` | 전체 재빌드 (최후 수단) | stale 의심 + sync 실패 시 |

### 1.6.1 코드 수정 룰 — 영향도 평가 먼저

**컴포넌트 / 함수 / 서비스를 수정하기 전에 반드시 `codegraph_explore`로 영향도를
먼저 평가**한다. grep / Read fan-out 대신 한 번의 MCP 호출로 관련 심볼 소스 +
호출 관계를 가져온다.

| 의도 | 1차 도구 | 보조 도구 |
|------|---------|----------|
| 컴포넌트 / 모듈을 만지기 전 주변 파악 | **`codegraph_explore`** | `codegraph_context` |
| 이 함수 바꾸면 무엇이 깨지나 | `codegraph_impact` | `codegraph_callers` |
| X가 Y에 어떻게 도달하나 | `codegraph_trace` | — |
| 단일 심볼 정의 / 호출자 한 번에 | `codegraph_context` | — |
| 심볼 이름으로 빠른 lookup | `codegraph_search` | `codegraph_node` |

`codegraph_explore`는 budget-capped 단일 호출 — 여러 관련 심볼의 source를 파일별로
묶어서 반환한다. 답이 인덱스에서 나오면 **파일을 다시 Read 하지 않는다** (반환된
소스가 권위).

CLI에서 확인하고 싶다면:

```bash
codegraph status                            # 인덱스 신선도
codegraph callers <Symbol>                  # 호출자 트리
codegraph callees <Symbol>                  # 호출 대상
codegraph impact <Symbol> --depth 2         # 영향 반경
codegraph context "Admin 사용자 force-verify 흐름"  # 작업 컨텍스트 빌드
```

## 2. 작업 흐름 — task마다 반복

### 2.1 새 task 시작

이전 작업 끝났고 worktree에 변경사항 없는 상태라고 가정.

```bash
cd F:/dev/tripmate-claude   # 본인 agent의 worktree
git fetch
git switch -c agent/claude-<task> origin/main
codegraph sync                  # incremental — 보통 < 30s
```

- 기준 ref는 **`origin/main`** — 로컬 `main` ref는 trunk(`F:/dev/tripmate`)가
  점유하므로 worktree에서 `git switch main`은 `fatal: 'main' is already checked
  out at ...`로 실패한다 (§3.3 참고).
- 브랜치 이름 컨벤션: `agent/<agent>-<task>`. 예:
  - Claude Code Sprint 3 Admin: `agent/claude-sprint-3-admin`
  - Codex 지도 prep: `agent/codex-map-prep`
  - Antigravity OAuth flow: `agent/antigravity-oauth-flow`
- task가 끝나면 PR 만들고 머지 대기 (`docs/runbooks/pr-review-sprint4.md` 참고).

### 2.2 작업 / commit / PR / merge

평소대로:

```bash
# ... 작업 ...
git add ...
git commit -m "feat(...)"
git push -u origin agent/claude-<task>
gh pr create ...
```

CodeGraph는 **file watcher가 native OS 이벤트로 자동 동기화**하지만, 큰 변경
(많은 파일 한 번에 / `git switch`)은 명시적으로 `codegraph sync` 호출이 안전.

### 2.3 task 종료 후

PR 머지되면 **별도 "main 동기화" 단계는 없다**. 바로 §2.1을 실행한다 —
`git switch -c agent/claude-<next> origin/main`이 최신 origin/main에서 새
브랜치를 따므로 이전 브랜치에서 자동으로 분기 떨어진다. worktree에서는
`git switch main`이 어차피 실패한다 (§3.3 참고).

옛 task 브랜치 정리는 누적되면 한 번에:

```bash
git fetch -p                                # 머지된 원격 브랜치 prune
git branch -d agent/claude-<old-task>       # 로컬 브랜치 제거 (머지된 것만 -d 허용)
# 머지 안 된 채 폐기하려면 -D로 강제
```

`codegraph sync`는 다음 §2.1 첫 실행 때 1회로 충분하다.

## 3. 자주 마주치는 상황

### 3.1 worktree 별도 `.gitignore` 항목

`.codegraph/`, `.next/`, `.venv/` 등은 본 저장소 `.gitignore`에 박혀 있어 모든
worktree에 일관 적용. **개인 IDE 캐시** (`.idea/`, `.vscode/`)도 마찬가지.
worktree 별로 추가 ignore가 필요하면 git의 `info/exclude`를 쓴다 (push 불필요).

### 3.2 codegraph 인덱스가 stale로 의심될 때

```bash
codegraph status      # last_sync / node_count 확인
codegraph sync        # incremental
codegraph index --force   # 전체 재빌드 (최후 수단)
```

### 3.3 worktree 간 동기화 — `origin/main`을 기준 ref로

**trunk(`F:/dev/tripmate`)가 항상 `main` 브랜치를 점유**한다. git worktree는
같은 브랜치를 한 위치에만 체크아웃할 수 있으므로, 다른 worktree에서
`git switch main`을 시도하면 다음으로 실패한다:

```
fatal: 'main' is already checked out at 'F:/dev/tripmate'
```

따라서 worktree에서는 **로컬 `main` ref 대신 항상 `origin/main`을 기준 ref로
사용**한다 — 새 브랜치 분기, diff, rebase 모두 동일:

| 의도 | trunk에서 가능 | worktree에서는 |
|------|---------------|---------------|
| 새 브랜치 분기 | `git switch -c X main` | `git switch -c X origin/main` |
| diff | `git diff main..X` | `git diff origin/main..X` |
| rebase | `git rebase main` | `git rebase origin/main` |
| main 갱신 | `git switch main && git pull` | 불가 — trunk만 갱신 (§5) |

`origin/main`은 `git fetch`만 하면 최신이므로, "main을 따라잡는다"는 개념은
worktree에서 `git fetch && git rebase origin/main` 한 줄로 끝난다 (§3.4).

각 worktree는 **독립된 작업 영역**이지만 같은 `.git` 디렉터리를 공유. 다른
worktree의 브랜치를 보고 싶다면:

```bash
git log agent/codex-<task>            # 다른 worktree에서 만든 브랜치도 visible
git diff origin/main..agent/codex-<task>
```

다른 worktree의 PR이 머지된 뒤 본인 worktree를 origin/main에 따라잡으려면 두
가지 흐름 중 하나:

```bash
# (a) 진행 중인 task 브랜치를 최신 origin/main 위로 rebase — §3.4 참고
git fetch
git rebase origin/main
codegraph sync

# (b) task가 이미 끝났으면 §2.3 → §2.1 흐름. 다음 task의
#     `git switch -c agent/claude-<next> origin/main`이 자동으로 최신 tip에서 떨어진다.
```

### 3.4 main 기준이 바뀌어 rebase 필요할 때

```bash
git fetch
git rebase origin/main
codegraph sync
```

충돌 해결 후 `git rebase --continue`. CodeGraph는 충돌 자체에는 도움 안 됨 (그
건 사람이 한다). 단 "이 함수 호출자 어디?" 같은 질문은 conflict 영역의 영향 평가
때 유용.

### 3.5 worktree 제거

장기 미사용 / 디스크 회수 시:

```bash
cd F:/dev/tripmate
git worktree remove ../tripmate-codex --force
# .codegraph/는 worktree 디렉터리와 함께 사라짐
```

다시 살릴 때는 `§1.2 ~ §1.4` 재실행.

### 3.6 Windows/WSL git 포인터 혼용 함정 (codex가 겪은 사고)

각 worktree의 `.git` 파일과 `.git/worktrees/<name>/gitdir`에는 worktree를 **만든
환경 기준의 절대경로**가 기록된다. WSL에서 만들면 `gitdir:
/mnt/f/dev/tripmate/.git/worktrees/tripmate-codex`처럼 마운트 경로가, Windows
git에서 만들면 `gitdir: F:/dev/tripmate/.git/worktrees/...`처럼 드라이브 경로가
들어간다. 같은 폴더라도 두 표기가 다르므로 **다른 환경 git으로 같은 worktree를
다루면**:

```
fatal: not a git repository
# git worktree list 에는 해당 worktree가 prunable 로 표시됨
```

**이 상태에서 `git worktree prune`을 그대로 돌리면 살아있는 worktree 등록까지
지워질 수 있다.** 바로 prune하지 않는다.

원칙(ADR-024): 각 worktree는 **한 환경 전용**으로 운용한다. TripMate에서는 NTFS
worktree의 git을 **Windows git(`git.exe`)으로만** 다룬다. WSL에서 `/mnt/f/dev/
tripmate-<agent>`에 `git`을 실행하지 않는다(ext4 미러는 git 대상이 아니다).

복구가 필요하면 실제로 사용할 환경에서 포인터를 그 환경 기준으로 맞춘다(`.git`과
admin `gitdir` 양방향):

```powershell
# Windows PowerShell — trunk에서
git worktree repair F:\dev\tripmate-claude
git worktree list          # prunable 사라졌는지 확인
```

repair로 살아있는 worktree를 먼저 valid 상태로 만든 뒤에만, 폴더가 실제로 사라진
등록을 표적 prune한다. `prune`은 **그 worktree를 운용하는 환경에서만** 실행한다.

### 3.7 Telegram 완료 알림 MCP (모든 agent 공통)

단위 작업 완료 시 사용자가 Telegram으로 짧은 요약과 PR 링크를 받도록 **모든 agent
worktree**(claude / codex / antigravity)에 `mcp-telegram` MCP 서버를 등록한다. 등록은
이미 tracked 설정에 들어 있다 — Claude `claude.json`, Codex `.codex/config.toml`,
Antigravity `antigravity.json`, Gemini `.gemini/mcp.json` 각각의 `mcp-telegram` 항목
(`cwd`는 각 worktree). GitHub Actions secret/워크플로는 쓰지 않는다(T-062 유지).

설치(1회, 머신 전체 — 각 agent 런타임 Python에):

```bash
# WSL/uv
uv tool install mcp-telegram
# Windows MCP 클라이언트가 직접 실행하는 사용자 Python에도 설치
/mnt/c/Python314/python.exe -m pip install --user mcp-telegram
```

각 agent worktree 루트에 로컬 credential 파일 `.env.mcp-telegram`을 둔다(형식은
`.env.mcp-telegram.example`). `.gitignore`로 커밋되지 않는다:

```dotenv
API_ID=<telegram-api-id>
API_HASH=<telegram-api-hash>
# 선택: 기본 알림 대상. 생략 시 send_message entity로 지정(예: "me")
# TELEGRAM_NOTIFY_CHAT=<chat-id-or-username>
```

- 같은 `API_ID`/`API_HASH`를 모든 worktree가 공유해도 된다. Telethon 세션은
  사용자 전역(`%LOCALAPPDATA%`/`~/.local/state/mcp-telegram/session.session`)에
  저장되므로 한 worktree에서 로그인하면 다른 agent도 재사용한다.
- 최초 1회 로그인(인증번호/2FA)은 사람이 실행한다 — agent 무관, 1회면 충분:

```powershell
# Windows
cd F:\dev\tripmate-<agent>
C:\Python314\python.exe scripts\mcp_telegram_start.py login
```

- 동작 확인: `... scripts\mcp_telegram_start.py version` (wrapper가 creds 로드 +
  `mcp-telegram` 실행 파일 resolve). 실제 발송은 MCP `send_message`(`entity`,
  `message`)로 한다. 발송 시점/규칙은 `AGENTS.md` "Telegram 작업 완료 알림 MCP".

## 4. AI 도구별 메모

### 4.1 Claude Code (`tripmate-claude`)

- `CLAUDE.md` (trunk와 worktree 모두 같음) 1쪽 요약을 읽고 진입.
- CodeGraph가 `.codegraph/`를 찾으면 자동으로 `mcp__codegraph__*` 도구가
  활성화 — Explore sub-agent 대신 `codegraph_context` / `codegraph_trace`로
  직접 답한다 (ADR-017 §결정 참고).
- 새 task 첫 호출 때 `codegraph status`로 인덱스 신선도 확인 권장.
- `claude.json`에 `mcp-telegram` 등록됨 — PR 후 `send_message`로 완료 알림(§3.7).

### 4.2 OpenAI Codex (`tripmate-codex`)

- `AGENTS.md` 진입. ADR-016에 따라 `CLAUDE.md`와 동기.
- Codex CLI는 `~/.codex/AGENTS.md`도 본다 — codegraph installer가
  자동 wiring.
- `.codex/config.toml`에 `mcp-telegram` 등록됨 — PR 후 완료 알림(§3.7).

### 4.3 Google Antigravity 2.0 (`tripmate-antigravity`)

- `AGENTS.md` 진입. Gemini 3.1 Pro로 작성된
  `maplibre-vworld-js` 등 라이브러리 작업도 본 worktree에서.
- Antigravity는 (현 시점) codegraph MCP를 표준 지원하지 않을 수 있음 —
  설치 후 동작 안 하면 `codegraph install --print-config codex`로 수동 wiring.
- `antigravity.json` / `.gemini/mcp.json`에 `mcp-telegram` 등록됨 — PR 후 완료 알림(§3.7).

## 5. trunk와의 관계

`F:/dev/tripmate` (사람 trunk)는 worktree 정책 밖이다. 사용자가 직접
git operation, branch 정리, hotfix 등을 할 때 사용. AI 도구는 trunk에 절대
checkout하지 않는다. trunk와 worktree는 같은 `.git`을 공유하므로 trunk에서 한
`git fetch`는 모든 worktree에 즉시 반영.

## 6. 참고

- ADR-017 — `docs/decisions.md` (agent별 고정 worktree + Windows git.exe)
- ADR-024 — NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러
- ADR-016 — AI 에이전트 도구 다중 지원 (AGENTS.md ↔ CLAUDE.md)
- ADR-004 — WSL 미러 모델 (디스크 / 경로). source-of-truth 주장은 ADR-024가 supersede
- `docs/dev-environment.md` — 셋업·검증·rsync·PATH 함정 전체 절차 (ADR-024)
- `docs/agent-workflow.md` — "어떤 순서로 무엇을 치는가" 런북
- `docs/agent-failure-patterns.md` — WSL git·런처·escape·통합테스트 반복 실패
- `colbymchenry/codegraph` — https://github.com/colbymchenry/codegraph
  (Docs: https://colbymchenry.github.io/codegraph/)
