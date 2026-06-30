# v1.0.0 E2E / Live Gate Runbook

T-273의 실행 runbook이다. `scripts/verify-v100-live-gate.sh`는 v1.0 release gate에서 반복 실행할
phase를 한 곳에 묶는 얇은 wrapper다. 각 phase의 위험도와 opt-in guard는 숨기지 않는다.

## 1. 범위

- mock Playwright E2E
- Admin read-only live catalog 목록, smoke, full catalog
- live mutating suite 목록
- trip realtime mutating suite
- backup staging mutating suite
- restore staging drill
- geofence 검증
- MCP 외부 인터페이스 검증
- API p95/error-rate 성능 smoke
- CSP/CORS/security header smoke

T-271 제거 기준에 따라 Odroid 병행 운영 smoke는 v1.0 blocker가 아니다. v1.0 live gate의 운영
기준은 N150이며, Playwright는 N150 Docker runner를 먼저 사용한다. N150 Docker runner와 host browser가
모두 불가능할 때만 Windows fallback을 사용하고 사유와 명령을 `docs/journal.md`와 PR에 남긴다.

## 2. Guard

`run` action은 항상 다음 명시 opt-in이 필요하다.

```bash
PINVI_V100_LIVE_GATE=1 scripts/verify-v100-live-gate.sh run
```

mutating phase는 하위 suite의 guard도 별도로 필요하다. 이 wrapper는 `PINVI_V100_LIVE_GATE=1`만으로
backup restore, live state 변경, rate-limit probe를 자동 허용하지 않는다. 실제 credential, 운영 origin,
token, DB URL은 gitignore된 local-only env 파일에서만 읽는다.

## 3. Phase 확인

기본 phase는 read-only/list 계열만 실행한다.

```bash
scripts/verify-v100-live-gate.sh plan
```

특정 phase 목록을 확인할 수 있다.

```bash
scripts/verify-v100-live-gate.sh plan admin-live-list live-mutating-list geofence mcp
```

환경변수로 phase를 줄 수도 있다.

```bash
PINVI_V100_GATE_PHASES="admin-live-list,live-mutating-list" \
  scripts/verify-v100-live-gate.sh plan
```

## 4. N150 Playwright 실행

N150에서 local-only env를 먼저 로드한다.

```bash
cd ~/pinvi
set -a
source "$HOME/.pinvi-admin-live.env"
set +a
```

Playwright phase를 N150 Docker runner로 감싼다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_GATE_N150_RUNNER=1 \
  scripts/verify-v100-live-gate.sh run admin-live-list live-mutating-list
```

Admin smoke는 기본 200 case다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_GATE_N150_RUNNER=1 \
PINVI_V100_ADMIN_LIVE_CASE_LIMIT=200 \
  scripts/verify-v100-live-gate.sh run admin-live-smoke
```

full catalog는 장시간 실행이다. 실행 전 N150 smoke, credential, rate-limit 상태를 먼저 확인한다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_GATE_N150_RUNNER=1 \
  scripts/verify-v100-live-gate.sh run admin-live-full
```

장시간 실행이 중간에 끊긴 경우 `PINVI_ADMIN_LIVE_CASE_START` / `PINVI_ADMIN_LIVE_CASE_END`로
matrix 번호를 1-based inclusive 범위로 나누어 재개한다. test title의 `[0001]` 번호는 원 catalog
번호를 유지하므로, 통과 구간은 PR/journal에 `[0001]..[0200]`처럼 기록한다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_ADMIN_LIVE_CASE_START=201 \
PINVI_V100_GATE_N150_RUNNER=1 \
  scripts/verify-v100-live-gate.sh run admin-live-full
```

## 5. Mutating / Staging 실행

mutating phase는 dev/staging 대상에서만 실행한다. 운영 public DB에 직접 restore drill을 실행하지 않는다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_GATE_N150_RUNNER=1 \
  scripts/verify-v100-live-gate.sh run trip-realtime-mutating
```

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_GATE_N150_RUNNER=1 \
  scripts/verify-v100-live-gate.sh run backup-mutating
```

restore staging drill은 snapshot 경로를 명시한다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_RESTORE_SNAPSHOT="/path/to/snapshot.dump" \
  scripts/verify-v100-live-gate.sh run restore-staging
```

대상 host에 `pg_restore` / `psql`이 없으면 PostgreSQL Docker image를 일회성 runner로 사용한다. 이
방식은 repo와 snapshot directory를 read-only mount하고, staging DB URL은 host env에서 container env로만
전달한다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_V100_RESTORE_DOCKER_RUNNER=1 \
PINVI_V100_RESTORE_DOCKER_NETWORK="container:<staging-postgres-container>" \
PINVI_V100_RESTORE_SNAPSHOT="/path/to/snapshot.dump" \
PINVI_RESTORE_STAGING_DATABASE_URL="$STAGING_DATABASE_URL" \
  scripts/verify-v100-live-gate.sh run restore-staging
```

## 6. Read-only 운영 검증

geofence와 MCP 검증은 각 스크립트의 하위 환경변수와 guard를 따른다.

```bash
PINVI_V100_LIVE_GATE=1 scripts/verify-v100-live-gate.sh run geofence mcp
```

성능과 보안 smoke는 `docs/runbooks/performance-security-gate.md` 기준으로 운영 HTTPS 대상에서 실행한다.

```bash
PINVI_V100_LIVE_GATE=1 \
PINVI_API_BASE_URL="https://pinvi-api.example.com" \
PINVI_WEB_ORIGIN="https://pinvi.example.com" \
PINVI_V100_REQUIRE_HSTS=1 \
  scripts/verify-v100-live-gate.sh run perf security
```

## 7. 기록 기준

- 실행 위치를 `Linux`, `N150`, `Windows fallback` 중 하나로 적는다.
- N150 fallback을 쓴 경우 Docker runner 실패 사유와 host browser 실패 사유를 모두 적는다.
- 실제 credential, token, 운영 origin, SSH target, IP는 공개 문서에 기록하지 않는다.
- Admin live catalog는 `npm -w @pinvi/web run test:e2e:admin-live:list`의 최종 total을 함께 기록한다.
- JSON 출력 전체를 붙이지 않고, 통과 여부와 핵심 수치만 기록한다.
