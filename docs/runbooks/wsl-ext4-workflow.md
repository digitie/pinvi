# WSL ext4 workflow

TripMate의 로컬 개발 기준은 WSL2 Ubuntu 내부 ext4 작업본이다. NTFS 작업 디렉토리는 Windows
도구와 파일 탐색을 위한 export 대상으로만 사용한다.

## 결론

- 원본 작업본: `/home/digitie/dev/tripmate`
- Windows export: `F:\dev\tripmate`
- WSL에서 보이는 export 경로: `/mnt/f/dev/tripmate`
- Git stage/commit/push 기준: ext4 원본 작업본
- 테스트/빌드/lint/Docker/Dagster 기준: ext4 원본 작업본

예전 방식인 `F:\dev\tripmate`를 원본으로 두고 `~/tripmate-workspaces/tripmate`에 테스트 미러를
만드는 방식은 더 이상 사용하지 않는다. NTFS에서 Git과 대량 파일 테스트를 직접 실행하면 파일
메타데이터 접근이 느리고, WSL/Windows 도구가 서로 다른 줄바꿈/권한 상태를 보며 변경이 과장될 수
있다.

## 저장소 준비

새 환경에서는 WSL ext4 안에서 clone한다.

```bash
mkdir -p ~/dev
cd ~/dev
git clone https://github.com/digitie/tripmate.git tripmate
cd ~/dev/tripmate
git checkout main
```

WSL 안에서 Git 인증이 Windows Git Credential Manager와 충돌하면, clone/push만 Windows Git으로
UNC 경로를 지정해 실행할 수 있다. 이 경우에도 작업 디렉토리는 ext4에 둔다.

```powershell
git clone https://github.com/digitie/tripmate.git `
  "\\wsl.localhost\Ubuntu\home\digitie\dev\tripmate"
git -c "safe.directory=%(prefix)///wsl.localhost/Ubuntu/home/digitie/dev/tripmate" `
  -C "\\wsl.localhost\Ubuntu\home\digitie\dev\tripmate" push origin main
```

## 명령 실행

Windows에서 매번 짧은 `wsl.exe` 호출을 반복하지 않는다. 긴 작업은 WSL shell 하나에서 이어서
실행하거나, Windows에서 호출해야 할 때는 한 번의 `bash -lc` 안에 관련 명령을 묶는다.

```powershell
wsl.exe -d Ubuntu
```

```bash
cd ~/dev/tripmate
npm run lint
cd apps/api
uv run pytest
```

Windows shell에서 호출해야 할 때:

```powershell
wsl.exe -e bash -lc "cd ~/dev/tripmate && npm run lint && npm run typecheck"
wsl.exe -e bash -lc "cd ~/dev/tripmate/apps/api && uv run ruff check . && uv run pytest"
```

`wsl.exe` 프로세스 생성 비용을 더 줄여야 하면 WSL 내부 `sshd`를 켜고 Windows에서 SSH로 접속해
같은 shell을 유지한다. SSH는 선택 사항이며, 기본 기준은 ext4 작업본에서 직접 명령을 실행하는
것이다.

## NTFS export

Windows 도구가 파일을 봐야 할 때만 ext4 원본을 NTFS로 export한다. export는 Git 작업 후 또는
사용자에게 Windows 경로 확인이 필요할 때 수행한다.

```bash
cd ~/dev/tripmate
rsync -a --delete \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='.next/' \
  --exclude='.venv/' \
  --exclude='.venv-wsl/' \
  --exclude='.pytest_cache/' \
  --exclude='.mypy_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='__pycache__/' \
  ./ /mnt/f/dev/tripmate/
```

`--delete`는 export mirror를 원본과 맞추기 위한 옵션이다. 실행 전 대상 경로가
`/mnt/f/dev/tripmate`인지 확인한다. NTFS export에서 사용자가 별도로 만든 파일을 보존해야 하는
상황이면 `--delete`를 빼고, 반영 범위를 `git status --short`로 확인한다.

## Git 기준

- 일반 원칙: `cd ~/dev/tripmate` 후 WSL Git으로 `status`, `add`, `commit`을 실행한다.
- WSL Git push가 credential 문제로 실패하면 Windows Git을 UNC ext4 경로에 대해 실행한다.
- `F:\dev\tripmate`에서 Git commit/push를 하지 않는다.
- NTFS export 작업본에서 대량 변경이 보이면 줄바꿈/권한/동기화 차이일 수 있으므로, ext4 원본의
  `git status --short --branch`를 기준으로 판단한다.

## 검색과 검증

검색도 ext4 원본에서 실행한다. WSL 환경에 `rg`가 없으면 설치하거나 `git grep`으로 대체한다.
PowerShell `rg.exe`나 WindowsApps 경로의 번들 실행 파일로 우회하지 않는다.

```bash
cd ~/dev/tripmate
PATH=/usr/local/bin:/usr/bin:/bin rg -n "Dagster|Telegram" docs apps/api
git grep -n "Dagster" -- docs apps/api
```

검증 명령 예:

```bash
cd ~/dev/tripmate
npm run lint
npm run typecheck
npm run build

cd ~/dev/tripmate/apps/api
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

Docker/PostgreSQL/PostGIS/Dagster도 ext4 원본에서 실행한다.

```bash
cd ~/dev/tripmate
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
```

## 예외

- 사용자가 Windows 경로의 파일을 직접 제공한 경우에는 그 파일만 읽거나 ext4 작업본으로 복사해
  처리한다.
- Windows 전용 GUI 확인, 브라우저 확인, Google Drive 업로드 같은 작업은 Windows 도구를 쓸 수
  있다. 이때도 저장소 소스 수정과 Git 기준은 ext4 원본이다.
