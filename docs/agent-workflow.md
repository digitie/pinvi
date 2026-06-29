# 에이전트 개발 워크플로 런북 — Linux 전용

> **목적**: 새 에이전트가 현재 정책(ADR-051)에 맞게 개발·git·CodeGraph·검증을
> 실행하는 순서를 한 장으로 정리한다. 배경과 세부는 `docs/dev-environment.md`,
> 반복 실패는 `docs/agent-failure-patterns.md`, worktree·CodeGraph는
> `docs/runbooks/codegraph-worktrees.md`.

## 0. 큰 그림

| 위치                 | 정체            | 여기서 하는 것                                                     | 주의                                                       |
| -------------------- | --------------- | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| Linux agent worktree | source of truth | 편집, git, CodeGraph, commit, push, PR, 테스트, Docker, dev server | 기존 `/mnt/f/...` worktree도 Linux 포인터로 repair 후 사용 |
| N150                 | live 검증       | 운영/스테이징 smoke, live API/UI, Playwright 우선 실행             | 민감 host/IP/domain은 로컬 런북에만 기록                   |
| Windows              | fallback runner | N150 Playwright가 불가능할 때 브라우저 e2e fallback                | 사유를 journal/PR에 기록                                   |

- 에이전트별 worktree 이름은 고정이다(ADR-017): Claude=`pinvi-claude`,
  Codex=`pinvi-codex`, Antigravity=`pinvi-antigravity`.
- ADR-024의 “NTFS git + WSL ext4 테스트 미러”는 폐기됐다. 같은 변경을 rsync로
  왕복하지 않는다.
- 모든 git 명령과 CodeGraph 명령은 Linux에서 실행한다.

## 1. 세션 첫 확인

```bash
cd /mnt/f/dev/pinvi-codex
command -v git rg node npm codegraph
git status --short --branch
codegraph status
codegraph sync
```

중지 조건:

- `git status`가 `fatal: not a git repository ... F:/...`를 내면
  `git worktree repair /mnt/f/dev/pinvi-codex`부터 실행한다.
- `command -v codegraph`가 `/mnt/c/...`, `.exe`, `.cmd`를 가리키면 Linux native
  CodeGraph 설치/PATH를 먼저 고친다.

## 2. 새 task 시작

```bash
cd /mnt/f/dev/pinvi-codex
git fetch origin
git switch -c agent/codex-<task> origin/main
codegraph sync
```

로컬 `main`은 trunk가 점유할 수 있으므로 `origin/main`에서 새 브랜치를 딴다.

## 3. 작업 루프

```text
탐색       Linux rg/sed/git/codegraph
영향 평가  컴포넌트/함수/서비스 변경 전 codegraph_explore 우선
편집       동일 Linux worktree에서 파일 수정
검증       Linux pytest/ruff/mypy/npm/docker/dev server
브라우저   N150 Playwright 우선, 불가 시 Windows fallback
기록       journal/resume/tasks/ADR/CHANGELOG 해당 항목 갱신
publish    Linux git add/commit/push + PR
```

## 4. 붙여넣기용 검증

```bash
cd /mnt/f/dev/pinvi-codex/apps/api
. .venv/bin/activate
export PINVI_JWT_SECRET_KEY='pinvi-test-jwt-secret-32bytes-minimum-aaaa'
export TESTCONTAINERS_RYUK_DISABLED=true TMPDIR=/tmp TMP=/tmp TEMP=/tmp
python -m pytest tests/unit -q
python -m pytest tests/integration -q
ruff check app tests
ruff format --check app tests
mypy --strict app
```

```bash
cd /mnt/f/dev/pinvi-codex
npm -w @pinvi/web run lint
npm -w @pinvi/web run typecheck
npm -w @pinvi/web run build
```

## 5. Playwright

기본은 N150이다.

```bash
# N150 셸에서 실행하거나 ssh stdin script로 실행
cd ~/pinvi
scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- <spec> --workers=1
```

N150 Docker runner와 host browser 실행이 모두 runtime/권한/네트워크 문제로 불가능할 때만
Windows runner를 쓴다.
그 경우 검증 기록에 다음 정보를 남긴다.

- N150에서 실패한 이유
- Windows fallback에서 실행한 명령
- 통과/실패한 spec

## 6. PR 마무리

```bash
git status --short --branch
git diff --check
git diff --cached --name-only
git diff --cached -U0 | grep -nEi '(api[_-]?key|secret|password|passwd|token|pbkdf2_sha256|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)' && echo '의심 항목 — 푸시 중지' || echo '일반 비밀 패턴 없음'
git push -u origin "$(git branch --show-current)"
```

PR을 만들거나 머지하면 최종 응답 전 `mcp-telegram` MCP의 `send_message`로 완료 요약과
PR 링크를 보낸다. credential은 worktree 로컬 `.env.mcp-telegram`에만 둔다.

## 참고

- `docs/dev-environment.md` — Linux-only 환경 모델과 셋업.
- `docs/agent-failure-patterns.md` — 반복되는 환경/도구 실패와 재발 방지.
- `docs/runbooks/codegraph-worktrees.md` — worktree 생성·CodeGraph 운영.
- `docs/agent-guide.md` — 문서화·재개 프로토콜.
