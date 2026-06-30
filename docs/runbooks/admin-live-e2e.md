# Admin live E2E Runbook

N150 또는 운영에 준하는 live 환경에서 Admin 기능을 검증하는 Playwright 전용 suite다.
기존 `apps/web/playwright.config.ts`는 API mock 기반 회귀 테스트를 실행하므로,
live 검증은 별도 설정 `apps/web/playwright.admin-live.config.ts`로만 실행한다.

## 1. 범위

- `apps/web/e2e/admin-live-matrix.live.ts`
- `apps/web/e2e/admin-debug-live.live.ts`
- `apps/web/e2e/admin-live-grafana.live.ts`
- `apps/web/e2e/admin-live-backup.live.ts`
- `apps/web/e2e/admin-live-map-marker-parity.live.ts`
- 전체 catalog는 `6343 tests in 5 files` 기준이다. UI 기준 live matrix 6,336건,
  로그인 검증 2개, catalog drift 1개, Debug live read-only 1개, Grafana live read-only 1개,
  Backup live read-only 1개, Map marker parity read-only 1개를 실행한다.
- route render, 좌측 navigation, 검색/필터, 테이블 정렬, placeholder 범위, dashboard card,
  MCP token 발급 form의 client validation을 실제 브라우저에서 검증한다.
- Debug live suite는 `/admin/debug/logs`의 sanitized polling fallback, filter query,
  request timeline 이동, raw secret pattern 미노출을 read-only로 검증한다.
- Grafana live suite는 `/admin/grafana` iframe, dashboard selector, health `정상`/`강등`
  상태, dashboard path와 secret pattern 미노출을 read-only로 검증한다.
- Backup live suite는 `/admin/backup` snapshot 목록, client filter/sort, empty state,
  restore 버튼 잠금, raw backup path/secret pattern 미노출을 read-only로 검증하고
  `POST /admin/backup/*` 호출이 발생하면 실패한다.
- Map marker parity live suite는 `/map` marker metadata가 있으면 upstream/category/kind/fallback/cluster
  source와 icon/hex/count를 확인하고, 운영 데이터가 없으면 legend attach까지만 read-only로 확인한다.
- Matrix catalog는 `/admin/debug/request/{id}` captured request timeline, feature detail
  subpage tabs, backup read-only variants, ETL app-owned job rows, Grafana dashboard selector
  및 WebSocket dashboard, raw secret pattern 미노출을 포함한다.
- 워커마다 `/admin/login` UI로 1회 인증한 뒤 Playwright storage state를 재사용한다.
- 기본 실행은 read-only다. 사용자 disable, PII reveal, backup 생성, restore hotswap,
  이메일 재발송, MCP token 발급/회수, feature request 승인/거절 같은 mutating action은
  이 suite에 포함하지 않는다.

## 2. 필수 환경변수

```bash
export PINVI_ADMIN_LIVE_E2E=1
export PINVI_ADMIN_LIVE_WEB_URL="https://pinvi.example.com"
export PINVI_ADMIN_LIVE_EMAIL="<admin email>"
export PINVI_ADMIN_LIVE_PASSWORD="<admin password>"
```

`apps/web/e2e/admin-debug-live.live.ts`만 단독 실행할 때는 UI credential 대신 짧은 수명의
Playwright storage state를 `PINVI_ADMIN_LIVE_STORAGE_STATE`로 전달할 수 있다. 이 경우 test는
`/admin`에서 인증 상태만 확인하고 `/admin/login` 입력은 수행하지 않는다.

선택:

```bash
export PINVI_ADMIN_LIVE_STORAGE_STATE="/path/to/admin-storage-state.json"
export PINVI_ADMIN_LIVE_THROTTLE_MS=2100
export PINVI_ADMIN_LIVE_CASE_ATTEMPTS=3
export PINVI_ADMIN_LIVE_RETRY_BACKOFF_MS=10000
export PINVI_ADMIN_LIVE_TEST_TIMEOUT_MS=120000
export PINVI_ADMIN_LIVE_AUTH_REFRESH_MS=300000
export PINVI_ADMIN_LIVE_CASE_LIMIT=200
export PINVI_ADMIN_LIVE_WORKERS=1
```

`PINVI_ADMIN_LIVE_CASE_LIMIT`는 smoke/debug용이다. 전체 검증은 설정하지 않는다.
장시간 full catalog가 중단되면 `PINVI_ADMIN_LIVE_CASE_START` / `PINVI_ADMIN_LIVE_CASE_END`로
matrix 번호를 1-based inclusive 범위로 나누어 이어서 검증한다. test title의 `[0001]` 번호는 원
catalog 번호를 유지한다. release gate는 `200` smoke → `2000` gate → full catalog 순서로 실행한다.
`PINVI_ADMIN_LIVE_THROTTLE_MS` 기본값은 2100ms다. 운영 기본 authenticated rate limit
60/min에서 Admin 화면이 `/auth/me`와 화면 API를 함께 호출하므로, live 검증에서는 이 값을
낮추지 않는다.
`PINVI_ADMIN_LIVE_CASE_ATTEMPTS`는 live rate limit 또는 순간 네트워크 실패를 흡수하기 위한
case별 재시도 횟수다. 이 suite는 read-only 및 client validation 범위만 포함하므로 같은
case 재시도가 서버 상태를 바꾸지 않는다.
재시도 backoff를 허용하기 위해 `PINVI_ADMIN_LIVE_TEST_TIMEOUT_MS` 기본값은 120000ms다.
긴 full run은 access token/cookie TTL을 넘을 수 있으므로, worker storage state는 기본 5분마다
`PINVI_ADMIN_LIVE_AUTH_REFRESH_MS` 기준으로 UI login을 다시 수행해 갱신한다. route 진입 또는
navigation 직후 로그인 화면으로 떨어진 경우에도 UI login을 다시 수행하고 원래 route로 복귀한다.

## 3. N150 실행

```bash
# 운영 노드 SSH target은 docs/deploy-runbook.local.md에서만 확인한다.
cd ~/pinvi
scripts/n150-docker-doctor.sh
curl -fsS http://127.0.0.1:12801/health
curl -fsS http://127.0.0.1:12805/admin/login >/dev/null
# 공개 도메인 검증 시 Web image의 NEXT_PUBLIC_PINVI_API_URL도 실제 API 도메인과 맞아야 한다.
curl -fsS https://pinvi-api.example.com/health
```

### 3.1 Docker runner 우선 실행

N150 host에 Playwright Chromium system dependency를 직접 설치하지 않아도 되도록, 기본 실행은
공식 Playwright Docker image를 쓰는 `scripts/n150-playwright-runner.sh`를 사용한다. script는
`package-lock.json`의 `@playwright/test` 버전에 맞춰 `mcr.microsoft.com/playwright:v<version>-noble`
image를 선택하고, `--network host`로 `http://127.0.0.1:12805`에 접근한다. `PINVI_*`,
`NEXT_PUBLIC_*`, `PLAYWRIGHT_*` 값은 Docker argv에 값을 노출하지 않고 환경변수 이름만 전달한다.

N150에는 gitignore된 local-only env 파일을 두고, 실제 credential과 운영 공개 origin은 그 파일에서만
읽는다. production Web image가 공개 HTTPS API origin으로 빌드된 경우
`PINVI_ADMIN_LIVE_WEB_URL`도 public HTTPS Web origin이어야 한다. `127.0.0.1:12805`는 Web image의
빌드타임 API origin이 같은 local origin을 가리키는 dev/staging 검증에서만 사용한다.

```bash
cd ~/pinvi

set -a
source "$HOME/.pinvi-admin-live.env"
set +a

npm -w @pinvi/web run test:e2e:admin-live:list

scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live
```

gate 순서:

```bash
cd ~/pinvi
set -a
source "$HOME/.pinvi-admin-live.env"
set +a
npm -w @pinvi/web run test:e2e:admin-live:list

PINVI_ADMIN_LIVE_CASE_LIMIT=200 \
  scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live
PINVI_ADMIN_LIVE_CASE_LIMIT=2000 \
  scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live
scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live
```

운영 공개 도메인으로 검증할 때는 `*_URL`을 실제 HTTPS 도메인으로 바꾼다. 실제
도메인과 credential은 공개 repo에 기록하지 않는다.

Playwright runner는 N150에서 먼저 실행한다. N150의 OS/브라우저 지원 문제 등으로 실행할 수
없을 때만 Windows runner를 fallback으로 사용하고, fallback 사유와 대상 Web/API URL 범위를
`docs/journal.md`에 남긴다.

### 3.2 Host Chromium dependency 점검

host에서 Playwright Chromium을 직접 실행해야 할 때만 이 절차를 사용한다. 2026-06-28 T-259
기준 N150은 Ubuntu 26.04 LTS다. Playwright 1.60.0의
`npx playwright install-deps --dry-run chromium`은 `ubuntu26.04-x64`를 직접 지원하지 않아
자동 dependency 설치 목록을 만들지 못한다. 이 경우 브라우저 binary를 `ldd`로 직접 확인한다.

```bash
chromium="$(find ~/.cache/ms-playwright -path '*chrome-headless-shell' -type f | head -1)"
ldd "$chromium" | grep 'not found'
```

T-259에서 확인한 누락 라이브러리:

- `libatk-1.0.so.0`
- `libatk-bridge-2.0.so.0`
- `libXdamage.so.1`
- `libasound.so.2`
- `libatspi.so.0`

sudo 가능한 N150 셸에서 최소 후보 패키지를 설치한 뒤 `--grep malformed` smoke를 먼저 재시도한다.
Ubuntu 26.04 패키지명은 apt index 기준으로 다시 확인한다.

```bash
sudo apt-get update
sudo apt-get install -y libatk1.0-0 libatk-bridge2.0-0 libxdamage1 libasound2t64 libatspi2.0-0

cd ~/pinvi/apps/web
PINVI_ADMIN_LIVE_E2E=1 \
PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 \
npm run test:e2e:admin-live -- --grep malformed --workers=1
```

비대화형 sudo가 없으면 Codex/CI가 직접 설치하지 않는다. Docker runner 자체도 실행할 수 없을 때만
Windows fallback runner를 쓰고, N150 missing library 또는 Docker 실행 실패 사유를 release gate
문서에 남긴다.

## 4. 실패 처리

- 로그인 실패: live admin credential 또는 cookie/CORS 설정 확인.
- route render 실패: Admin guard, Next.js runtime error, 좌측 navigation document 이동 여부 확인.
- 검색/필터/정렬 실패: 화면 test id, option 값, AdminTable column key drift를 함께 확인한다.
- 403/404 alert: 계정 역할 또는 운영에서 숨긴 dev-only route 여부 확인.
- 5xx alert: N150 `docker compose ps`, API 로그, DB health를 먼저 확인한다.

실패 수정 후 전체 suite를 다시 돌리기 전에 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`으로 smoke를
먼저 재확인한다.
