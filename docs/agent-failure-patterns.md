# 반복되는 에이전트 실패 패턴과 재발 방지

본 문서는 **NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러**
정책(ADR-024) 아래에서 AI 에이전트(Claude / Codex / Antigravity)가 자주 부딪히는
**환경·도구 계층 실패**를 정리한다. 여기서 다루는 증상은 대개 프로젝트 코드 버그가
아니라 Git metadata 포인터, 명령 런처, NTFS 편집 경로, escape 다중 해석의
상호작용에서 생긴다. 같은 증상이면 프로젝트 버그로 오판하기 전에 먼저 본 문서를
확인한다.

> `kor-travel-geo`의 `docs/agent-failure-patterns.md`와 같은 목적·패턴이다
> (도구 간 일관). 절차 전체는 `docs/dev-environment.md`(ADR-024), worktree·git
> 포인터 복구는 `docs/runbooks/codegraph-worktrees.md`(ADR-017).

## 1. 한눈에 보는 분류

| 증상 | 실제 원인 | 1차 대응 |
|------|-----------|-----------|
| `fatal: not a git repository: ... F:/dev/.../.git/worktrees/...` (또는 `/mnt/f/...`) | NTFS worktree의 Git metadata 포인터를 만든 환경과 다른 환경 git으로 읽음 | NTFS worktree는 **Windows `git.exe`만**. 깨졌으면 `git worktree repair` |
| `git worktree list`에 정상 worktree가 `prunable`로 표시 | 포인터 환경 혼용(§2) | 바로 `prune` 금지 — `repair` 먼저, `prune`은 운용 환경에서만 |
| 명령이 셸 진입 전 실패 / 대량 호출이 한꺼번에 큐잉됐다 풀림 | 런처가 복잡한 quoting·heredoc·과도한 병렬 호출을 안정적으로 못 띄움 | 명령 단순화, `cd ... &&` 단일 바이너리, 병렬 호출 수 축소(§3) |
| PowerShell → WSL → SSH → Docker → Python 명령에서 quote가 반복적으로 깨짐 | 서로 다른 shell 4~5개가 같은 따옴표/escape를 다시 해석 | 중첩 quote 금지. 스크립트를 stdin/base64로 한 번만 전달(§3.1) |
| `\n` / regex backslash가 코드·문서에서 깨지거나, 멀쩡한 파일이 "손상"으로 보임 | inline shell/node/python에서 escape가 여러 계층 해석 + MSYS `grep`의 `\n` 오해석(§4) | line-oriented edit + ripgrep(Grep 도구)/`od -c` 교차검증 |
| 통합 테스트가 "table does not exist" / "another operation in progress" | async alembic 미커밋 / pytest-asyncio 루프·풀 공유(§5) | env.py commit, 함수 스코프 엔진 + NullPool |

## 2. 패턴 A — NTFS worktree에서 WSL `git` 실패 / 포인터 혼용

### 증상
- `git -C /mnt/f/dev/pinvi-codex status`가 실패한다.
- 오류에 `F:/dev/.../.git/worktrees/...` 또는 `/mnt/f/...` 경로가 섞여 나온다.
- 같은 worktree가 한 환경에선 정상인데 다른 환경에선 `prunable`로 보인다.

### 원인
worktree의 `.git` 파일과 main repo의 `worktrees/*/gitdir` 포인터에는 worktree를
**만든 환경 기준 절대경로**가 박힌다. WSL에서 만들면 `/mnt/f/...`, Windows git에서
만들면 `F:/dev/...`. 다른 환경 git으로 같은 worktree를 다루면 포인터를 해석하지
못해 repository 오류가 난다. (실측: pinvi에서 codex worktree는
`gitdir: /mnt/f/dev/pinvi/.git/worktrees/pinvi-codex`, claude worktree는
`gitdir: F:/dev/...`로 환경이 갈려 있었다.)

### 재발 방지
1. NTFS worktree에서 status·branch·commit·push·merge는 **Windows `git.exe`만**.
2. ext4 테스트 미러에서는 git commit/push를 하지 않는다(미러는 git 대상 아님).
3. 환경을 바꿔 같은 worktree를 다뤄야 하면 먼저 그 환경에서
   `git worktree repair <worktree 경로>`로 포인터를 맞춘다.
4. `git worktree prune`은 worktree를 **실제 운용하는 환경에서만** 실행한다. 다른
   환경에서 돌리면 정상 worktree가 `prunable`로 보여 등록이 삭제될 수 있다.

### 표준 명령
```powershell
# Windows PowerShell — NTFS worktree는 Windows git.exe 로
cd F:\dev\pinvi-claude
git status -sb
git fetch origin
git switch -c agent/claude-<task> origin/main
# 포인터가 틀어졌으면 trunk에서 복구
git -C F:\dev\pinvi worktree repair F:\dev\pinvi-claude
```

## 3. 패턴 B — 명령 런처 실패 / 대량 병렬 호출 backlog

### 증상
- heredoc(`python3 - <<'PY' ... PY`), nested quote가 많은 `-c '...'`, 파이프를 여러
  개 섞은 긴 명령이 셸 실행 전 단계에서 실패하거나 결과가 비어 돌아온다.
- 한 메시지에서 너무 많은 도구를 병렬 호출하면 결과가 한꺼번에 늦게 도착하고,
  중간에 한 호출이 막히면(권한 분류기·일시 unavailable) 나머지가 cancel된다.

### 원인
명령 조립/실행 계층의 한계 + 병렬 호출 backlog. 저장소 파일 문제가 아니다.

### 재발 방지
1. 명령은 가능한 한 **단순한 한 줄**. `workdir` 대신 `cd ... && <command>`.
2. heredoc보다 `rg`/`sed`/`cat`/`git -C`/단일 `python -m pytest` 같은 단일 바이너리.
3. **상호 의존 명령을 한꺼번에 대량 병렬로 던지지 않는다.** 결과를 봐야 다음이
   정해지면 순차로. 독립적인 읽기만 소수 병렬.
4. 권한 분류기가 한 명령을 막으면(예: `git reset --hard`, `git checkout --`)
   나머지가 cancel될 수 있으니, 파괴적 명령은 분리해 보내고 의도를 먼저 확인한다.
5. 이 오류가 나오면 프로젝트 버그로 오판하지 말고 **런처/스케줄 문제**로 분류한다.

### 3.1 PowerShell → WSL → SSH → Docker → Python quote 금지

N150 같은 원격 운영 노드에서 다음 형태는 금지한다.

```powershell
# 금지: PowerShell 문자열 안에 WSL bash, ssh remote shell, docker exec, Python heredoc을
# 모두 중첩한다. 작은따옴표/큰따옴표가 각 계층에서 다시 해석돼 반복 실패한다.
wsl.exe -e bash -lc 'ssh user@host "docker exec app python - <<'PY' ... PY"'
```

표준 패턴은 **스크립트를 stdin으로 한 번만 전달**하는 것이다. 컨테이너 안에서 Python을
실행할 때는 `scripts/remote-docker-python.sh`를 1차로 사용한다.

```bash
scripts/remote-docker-python.sh <n150-ssh-target> pinvi-api-latest <<'PY'
print("hello from container")
PY
```

PowerShell에서 WSL을 거쳐야 할 때는 스크립트 본문을 here-string으로 만들고 base64로
WSL에 넘긴다.

```powershell
$sh = @'
cd ~/pinvi-workspaces/pinvi-codex
scripts/remote-docker-python.sh <n150-ssh-target> pinvi-api-latest <<'PY'
print("hello from container")
PY
'@
$sh = $sh -replace "`r`n", "`n"
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($sh))
$b64 | wsl.exe -e bash -lc "base64 -d | bash"
```

```bash
# 이미 WSL 안이고 helper를 쓸 수 없을 때만 이 fallback을 사용한다.
ssh -o BatchMode=yes <n150-ssh-target> 'docker exec -i pinvi-api-latest python -' <<'PY'
print("fallback")
PY
```

원칙:
1. remote shell command 문자열 안에 Python heredoc을 넣지 않는다.
2. JSON payload가 필요한 `curl` smoke도 원격 bash script stdin으로 보낸다.
3. 세 번 이상 같은 quote 실패가 나면 즉시 문서화/스크립트화하고 더 이상 inline로
   재시도하지 않는다.

## 4. 패턴 C — escape 손상 + 도구별 `\n` 오해석 (이번 세션 실측)

### 증상
- inline로 만든 `"\n"`이 파일에 줄바꿈 리터럴로 들어간다. regex backslash가 준다.
- **MSYS/Git-Bash `grep`이 `\n` 패턴을 개행으로 해석**해, 정상 마크다운 문서를
  "literal `\n` 손상 N건"으로 잘못 표시한다(false positive). 실제로는 멀쩡한 파일.

### 원인
JSON → bash → Python/node → 파일 문자열로 **escape가 여러 계층 연속 해석**되며
손상된다. 또한 Windows의 MSYS `grep`은 GNU `grep`과 `\n` 처리가 달라 메타문자
카운트가 신뢰할 수 없다.

### 재발 방지
1. 대량 inline rewrite 대신 **Edit 도구의 targeted replace**(한 블록씩)를 우선한다.
2. `\n`·regex·Windows 경로처럼 backslash 많은 문자열은 수정 직후 다시 열어 확인.
3. **패턴 검사·메타문자 카운트는 MSYS `grep`이 아니라 ripgrep(Grep 도구)로** 한다.
   "손상" 의심 시 `od -c` / Read 도구로 실제 바이트를 교차검증한 뒤 판단한다.
   (이번 세션에서 MSYS `grep -c '\n'`이 정상 문서를 108건 손상으로 표시 →
   ripgrep·`od -c`로 0건 확인.)
4. escape가 많은 수정 뒤에는 `ruff`/`mypy`/`ruff format --check`를 먼저 돌려 문법
   오류를 조기 발견한다.

## 5. 패턴 D — 통합 테스트 환경 (testcontainers + async)

### 증상
- `relation "app.users" does not exist` — 마이그레이션은 "Running upgrade" 로그가
  나오는데 테이블이 없다.
- `another operation is in progress` / `Future attached to a different loop`.

### 원인·대응
- **async alembic이 DDL 트랜잭션을 커밋하지 않음** → `alembic/env.py`의 async 경로에
  `await connection.commit()` 필수. exit code만 보지 말고 **테이블 수까지 확인**.
- **pytest-asyncio function-loop** → 엔진을 함수 스코프 + `NullPool`로 생성. 세션
  스코프 공유 엔진은 루프/커넥션 충돌을 일으킨다.
- 미러에서 `TMPDIR`/`TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)면 pytest capture가
  `FileNotFoundError`로 죽는다 → `export TMPDIR=/tmp TMP=/tmp TEMP=/tmp`.
- 상세는 `apps/api/tests/integration/conftest.py` + `docs/dev-environment.md` §7.1.

## 6. WSL PATH 오염 (npm/node/git/rg shim)

WSL PATH에 `/mnt/c/...`의 Windows shim이 먼저 잡히면 `node: not found`, UNC 경로
경고, 잘못된 경로 전달이 난다. `command -v npm node git rg`로 확인하고, `/mnt/c/...`
또는 `*.exe`/`*.cmd`가 나오면 Linux 것으로 교정한다(§dev-environment §6). 검색은
WSL native `rg`만(`PATH=/usr/local/bin:/usr/bin:/bin rg ...`).

## 7. 표준 fallback 순서

1. **Git/branch/commit**: NTFS worktree + Windows `git.exe`
2. **검증**: WSL ext4 미러에서 `pytest` / `ruff` / `ruff format --check` / `mypy --strict`
3. **읽기/탐색**: Grep(ripgrep) / Read / `codegraph sync`·`status`·`impact`
4. **편집**: Edit 도구의 targeted replace 우선. 대량 inline rewrite 회피
5. **"손상" 의심**: ripgrep·`od -c`·Read로 실제 바이트 교차검증 후 판단
6. **문서화**: 새 실패 패턴이 재현되면 `docs/journal.md`와 본 문서에 추가

## 참고

- `docs/dev-environment.md` — 환경 모델·셋업·rsync·검증·함정 전체 (ADR-024).
- `docs/agent-workflow.md` — "어떤 순서로 무엇을 치는가" 런북.
- `docs/runbooks/codegraph-worktrees.md` §3.6 — Windows/WSL git 포인터 복구.
- `kor-travel-geo` `docs/agent-failure-patterns.md` — 동일 패턴 reference.
