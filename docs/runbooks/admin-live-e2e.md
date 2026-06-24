# Admin live E2E Runbook

N150 또는 운영에 준하는 live 환경에서 Admin 기능을 검증하는 Playwright 전용 suite다.
기존 `apps/web/playwright.config.ts`는 API mock 기반 회귀 테스트를 실행하므로,
live 검증은 별도 설정 `apps/web/playwright.admin-live.config.ts`로만 실행한다.

## 1. 범위

- `apps/web/e2e/admin-live-matrix.live.ts`
- UI 기준 live matrix 3230개 + 로그인 검증 2개 + catalog sanity 1개
- route render, 좌측 navigation, 검색/필터, 테이블 정렬, placeholder 범위, dashboard card,
  MCP token 발급 form의 client validation을 실제 브라우저에서 검증한다.
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

선택:

```bash
export PINVI_ADMIN_LIVE_THROTTLE_MS=2100
export PINVI_ADMIN_LIVE_CASE_ATTEMPTS=3
export PINVI_ADMIN_LIVE_RETRY_BACKOFF_MS=10000
export PINVI_ADMIN_LIVE_CASE_LIMIT=200
export PINVI_ADMIN_LIVE_WORKERS=1
```

`PINVI_ADMIN_LIVE_CASE_LIMIT`는 smoke/debug용이다. 전체 검증은 설정하지 않는다.
`PINVI_ADMIN_LIVE_THROTTLE_MS` 기본값은 2100ms다. 운영 기본 authenticated rate limit
60/min에서 Admin 화면이 `/auth/me`와 화면 API를 함께 호출하므로, live 검증에서는 이 값을
낮추지 않는다.
`PINVI_ADMIN_LIVE_CASE_ATTEMPTS`는 live rate limit 또는 순간 네트워크 실패를 흡수하기 위한
case별 재시도 횟수다. 이 suite는 read-only 및 client validation 범위만 포함하므로 같은
case 재시도가 서버 상태를 바꾸지 않는다.

## 3. N150 실행

```bash
ssh n150
cd /opt/pinvi
scripts/n150-docker-doctor.sh
curl -fsS http://127.0.0.1:12801/health
curl -fsS http://127.0.0.1:12805/admin/login >/dev/null
# 공개 도메인 검증 시 Web image의 NEXT_PUBLIC_PINVI_API_URL도 실제 API 도메인과 맞아야 한다.
curl -fsS https://pinvi-api.example.com/health

cd apps/web
npm run test:e2e:admin-live:list
PINVI_ADMIN_LIVE_E2E=1 \
PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 \
PINVI_ADMIN_LIVE_EMAIL="$PINVI_ADMIN_LIVE_EMAIL" \
PINVI_ADMIN_LIVE_PASSWORD="$PINVI_ADMIN_LIVE_PASSWORD" \
npm run test:e2e:admin-live
```

운영 공개 도메인으로 검증할 때는 `*_URL`을 실제 HTTPS 도메인으로 바꾼다. 실제
도메인과 credential은 공개 repo에 기록하지 않는다.

## 4. 실패 처리

- 로그인 실패: live admin credential 또는 cookie/CORS 설정 확인.
- route render 실패: Admin guard, Next.js runtime error, 좌측 navigation document 이동 여부 확인.
- 검색/필터/정렬 실패: 화면 test id, option 값, AdminTable column key drift를 함께 확인한다.
- 403/404 alert: 계정 역할 또는 운영에서 숨긴 dev-only route 여부 확인.
- 5xx alert: N150 `docker compose ps`, API 로그, DB health를 먼저 확인한다.

실패 수정 후 전체 suite를 다시 돌리기 전에 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`으로 smoke를
먼저 재확인한다.
