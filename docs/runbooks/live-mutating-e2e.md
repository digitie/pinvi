# Live mutating E2E Runbook

N150 또는 운영에 준하는 live 환경에서 실제 상태 변경을 수행하는 Playwright suite다. 기존
mock e2e와 Admin read-only live matrix와 분리하며, 각 suite의 명시적 opt-in 환경변수가 없으면
항상 skip한다. Playwright runner는 N150에서 먼저 실행하고, N150에서 실행할 수 없을 때만
Windows runner를 fallback으로 사용한다.

## 1. 범위

- `apps/web/e2e/trip-realtime-live-mutating.live.ts`
- `apps/web/e2e/trip-day-hole-live-mutating.live.ts`
- `apps/web/e2e/trip-feature-resolution-live-mutating.live.ts`
- `apps/web/e2e/admin-backup-live-mutating.live.ts`
- `apps/web/e2e/admin-feature-request-queue-live-mutating.live.ts`
- verified 사용자 계정으로 두 browser context를 로그인한다.
- test prefix가 붙은 임시 Trip을 생성하고, 실제 `WS /ws/trips/{trip_id}` 연결 상태를 확인한다.
- API `PATCH /trips/{trip_id}` mutation이 다른 context의 Trip 상세 화면에 WebSocket broadcast
  reload로 반영되는지 확인한다.
- browser에서 WebSocket을 닫아 client reconnect를 유도한 뒤, 두 번째 mutation이 최신 snapshot으로
  보이는지 확인한다.
- 종료 시 생성한 Trip은 사용자 API `DELETE /trips/{trip_id}` `soft_delete`로 활성 데이터에서
  제거한다. DB row와 POI는 retention 정책 대상이며 즉시 hard-delete하지 않는다.
- Feature resolution suite는 실 Map DB의 `found|retired|suppressed|missing` fixture를 Trip POI로
  연결하고, 만료 cache의 `row_revision` 재검증(`unchanged`), proxy 강제 503의 `unverified`, 복구를
  owner 목록·API 상태·집계에서 확인한다. 같은 suite가 실 weather 값이 있는 feature, 공개 parent지만
  weather가 없는 feature, retired parent를 40일 여행의 sparse 다중 날짜 batch로 조회한다.
  직접 Trip read 한 번당 weather batch POST가 정확히 1회인지, 40일차가 과거 31일 상한으로
  생략되지 않는지 검증한다. weather batch만 강제 503으로 바꿔 `unavailable`과 복구를 확인하고
  단건 weather 요청이 0회인지도 고정한다. 격리 API는 짧은 TTL의 feature cache를 켜고, 40일
  fixture 생성 요청이 일반 사용자 rate limit을 소진하지 않도록 rate limit을 비활성화한다.
- Trip day hole suite는 날짜가 있는 3박 4일 여행을 실제 UI에서 생성하고, 1~4일차 자동 생성,
  1일차 삭제 후 가장 빠른 빈 day 재생성, 일자 설정 팝업의 날짜 수정, 진행 중 스크린샷 저장을 확인한다.
- Backup mutating suite는 staging admin 계정으로 `/admin/backup` 수동 snapshot을 1회 생성하고,
  `backup://<filename>` masking, 최근 audit의 `backup.snapshot`, snapshot 목록 limit cap을 확인한다.
  restore hotswap endpoint는 호출하지 않으며, 호출이 발생하면 실패한다. snapshot 삭제 API는 아직
  없으므로 테스트가 만든 staging snapshot은 audit evidence로 남기고 운영 retention/스토리지 정책으로
  관리한다.
- M04 Feature 요청 큐 suite는 **격리된** Map/PinVi compatible pair에서 사전에 만든 pending
  `new_place` fixture 하나만 관리자 UI로 승인한다. PinVi 응답의 `approved`와 Map queue
  `pending` receipt(`request_id`, `review_mode=feature_request_queue`, `action=submit`)를 함께
  확인한다. production, shared staging, 재실행한 fixture에는 절대 사용하지 않는다.

## 2. 필수 환경변수

```bash
export PINVI_LIVE_MUTATING_E2E=1
export PINVI_LIVE_WEB_URL="https://pinvi.example.com"
export PINVI_LIVE_API_URL="https://pinvi-api.example.com"
export PINVI_LIVE_EMAIL="<verified user email>"
export PINVI_LIVE_PASSWORD="<verified user password>"
```

Backup staging mutating:

```bash
export PINVI_BACKUP_LIVE_MUTATING_E2E=1
export PINVI_BACKUP_LIVE_STAGING=1
export PINVI_LIVE_WEB_URL="https://pinvi.example.com"
export PINVI_BACKUP_LIVE_EMAIL="<staging admin email>"
export PINVI_BACKUP_LIVE_PASSWORD="<staging admin password>"
```

선택:

```bash
export PINVI_LIVE_TRIP_PREFIX="[codex-live-ws]"
export PINVI_BACKUP_LIVE_REASON_PREFIX="[codex-backup-live]"
export PINVI_BACKUP_LIVE_STORAGE_STATE="/path/to/admin-storage-state.json"
export PINVI_LIVE_TEST_TIMEOUT_MS=120000
export PINVI_LIVE_WORKERS=1
```

실제 도메인과 credential은 공개 repo에 기록하지 않는다. 운영 노드 접속·도메인·계정 값은
gitignore된 `docs/deploy-runbook.local.md` 또는 로컬 env 파일에만 둔다.

## 3. 실행

```bash
cd apps/web
npm run test:e2e:live-mutating:list
PINVI_LIVE_MUTATING_E2E=1 \
PINVI_LIVE_WEB_URL=http://127.0.0.1:12805 \
PINVI_LIVE_API_URL=http://127.0.0.1:12801 \
PINVI_LIVE_EMAIL="$PINVI_LIVE_EMAIL" \
PINVI_LIVE_PASSWORD="$PINVI_LIVE_PASSWORD" \
npm run test:e2e:live-mutating
```

Trip day hole 단건:

```bash
PINVI_LIVE_MUTATING_E2E=1 \
PINVI_LIVE_WEB_URL=http://127.0.0.1:12805 \
PINVI_LIVE_API_URL=http://127.0.0.1:12801 \
PINVI_LIVE_EMAIL="$PINVI_LIVE_EMAIL" \
PINVI_LIVE_PASSWORD="$PINVI_LIVE_PASSWORD" \
PINVI_LIVE_SCREENSHOT_DIR="$PWD/../../.codex_tmp/live-e2e/trip-day-hole" \
npm run test:e2e:live-mutating -- trip-day-hole-live-mutating.live.ts --workers=1
```

### Feature resolution 단건

동시 실행이 다른 run을 정리하지 않도록 `PINVI_LIVE_TRIP_PREFIX`는 run마다 고유해야 한다. 격리 API는
feature cache를 켜고 TTL을 짧게 설정한다. Map DB에서 확인한 서로 다른
`found|retired|suppressed|missing` ID와 `found` projection의 이름·좌표를 테스트 프로세스에
전달한다. 격리 API에는 Map API와 같은 service token을 설정한다. 테스트는 batch validator와
`unchanged` 응답을 함께 검증하므로 cache가 꺼졌거나 proxy를 우회하거나 service token이 다르면
실패한다.

```bash
# 격리 API container/server 환경
export PINVI_FEATURE_CACHE_ENABLED=true
export PINVI_FEATURE_CACHE_TTL_SECONDS=0.1
export PINVI_RATE_LIMIT_ENABLED=false
export PINVI_KOR_TRAVEL_MAP_API_BASE_URL=http://127.0.0.1:13701
export PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN="<same-token-as-isolated-map-api>"

# Playwright 환경
PINVI_LIVE_FEATURE_RESOLUTION_E2E=1 \
PINVI_LIVE_FEATURE_CACHE_REVALIDATION=1 \
PINVI_LIVE_FEATURE_CACHE_WAIT_MS=250 \
PINVI_LIVE_FOUND_FEATURE_ID="<fixture-found-id>" \
PINVI_LIVE_FOUND_FEATURE_NAME="<fixture-found-name>" \
PINVI_LIVE_FOUND_FEATURE_LON="<fixture-found-lon>" \
PINVI_LIVE_FOUND_FEATURE_LAT="<fixture-found-lat>" \
PINVI_LIVE_RETIRED_FEATURE_ID="<fixture-retired-id>" \
PINVI_LIVE_SUPPRESSED_FEATURE_ID="<fixture-suppressed-id>" \
PINVI_LIVE_MISSING_FEATURE_ID="<fixture-missing-id>" \
PINVI_LIVE_WEATHER_DATE="<YYYY-MM-DD>" \
PINVI_LIVE_WEATHER_FEATURE_ID="<fixture-weather-found-id>" \
PINVI_LIVE_WEATHER_FEATURE_NAME="<fixture-weather-found-name>" \
PINVI_LIVE_WEATHER_FEATURE_LON="<fixture-weather-found-lon>" \
PINVI_LIVE_WEATHER_FEATURE_LAT="<fixture-weather-found-lat>" \
PINVI_LIVE_WEATHER_NO_DATA_FEATURE_ID="<fixture-weather-no-data-id>" \
PINVI_LIVE_WEATHER_NO_DATA_FEATURE_NAME="<fixture-weather-no-data-name>" \
PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LON="<fixture-weather-no-data-lon>" \
PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LAT="<fixture-weather-no-data-lat>" \
PINVI_LIVE_TRIP_PREFIX="[codex-tvn11-<unique-run-id>]" \
PINVI_LIVE_WEB_URL=http://127.0.0.1:13805 \
PINVI_LIVE_API_URL=http://127.0.0.1:13801 \
PINVI_LIVE_MAP_PROXY_PORT=13701 \
PINVI_LIVE_MAP_UPSTREAM_PORT="<isolated-map-api-port>" \
PINVI_LIVE_EMAIL="$PINVI_LIVE_EMAIL" \
PINVI_LIVE_PASSWORD="$PINVI_LIVE_PASSWORD" \
npm run test:e2e:live-mutating -- trip-feature-resolution-live-mutating.live.ts --workers=1
```

격리 stack만 사용한다. 실제 서비스 API를 proxy base URL로 재기동하지 않는다. 실패 시 현재 run이 출력한
고유 prefix로 활성 Trip만 수동 soft-delete하며, 다른 prefix의 Trip을 일괄 삭제하지 않는다. VWorld
key가 없는 fallback 환경에서는 지도 popup이 마운트되지 않으므로 상태 문구는 owner 목록의 접근성
label로 검증하고 지도 좌표·marker 상태는 숨김 legend와 API 상태 검증으로 보완한다.
weather 날짜는 fixture의 `valid_at|observed_at|issued_at` 범위 안에서 고른다. `weather found`와
`no_data` feature는 공개 parent여야 하고, retired fixture는 현재 공개 parent가 아니어야 한다.
`PINVI_RATE_LIMIT_ENABLED=false`는 격리 API에만 적용한다. 40일 여행 생성은 39개의 추가 POI
mutation을 포함하므로 기본 분당 60회 제한을 그대로 쓰면 본 검증이 아니라 마지막 cleanup이
429로 실패할 수 있다.

Backup staging:

```bash
cd apps/web
npm run test:e2e:live-mutating:list
PINVI_BACKUP_LIVE_MUTATING_E2E=1 \
PINVI_BACKUP_LIVE_STAGING=1 \
PINVI_LIVE_WEB_URL=http://127.0.0.1:12805 \
PINVI_BACKUP_LIVE_EMAIL="$PINVI_BACKUP_LIVE_EMAIL" \
PINVI_BACKUP_LIVE_PASSWORD="$PINVI_BACKUP_LIVE_PASSWORD" \
npm run test:e2e:live-mutating -- admin-backup-live-mutating.live.ts --workers=1
```

### M04 Map Feature 요청 큐 단건

Map #1029와 PinVi #458의 검증한 exact image pair만 격리 포트/DB로 기동한다. admin UI에 보이는
새 pending `new_place` fixture UUID를 한 번만 발급하고, 값은 tracked 파일이나 로그에 기록하지
않는다. Map service writer token은 PinVi API process에만 주입한다.

```bash
cd apps/web
PINVI_M04_LIVE_E2E=1 \
PINVI_LIVE_WEB_URL=http://127.0.0.1:13805 \
PINVI_M04_LIVE_FEATURE_REQUEST_ID="$PINVI_M04_LIVE_FEATURE_REQUEST_ID" \
PINVI_M04_LIVE_EMAIL="$PINVI_M04_LIVE_EMAIL" \
PINVI_M04_LIVE_PASSWORD="$PINVI_M04_LIVE_PASSWORD" \
npm run test:e2e:live-mutating -- admin-feature-request-queue-live-mutating.live.ts --workers=1
```

성공 뒤 PinVi 응답 및 Map 격리 로그에서 같은 request UUID와 pending receipt를 대조한다. 실패한
fixture는 다시 승인하지 않고, 격리 DB만 폐기하거나 해당 제안을 운영 절차로 거절한다.

운영 공개 도메인으로 검증할 때는 `*_URL`을 실제 HTTPS 도메인으로 바꾼다.

## 4. 실패 처리

- 로그인 실패: test 계정의 이메일 인증, 비밀번호, CORS/cookie 설정을 확인한다.
- host에서 격리 API를 직접 띄우며 운영 container env를 재사용할 때
  `PROMETHEUS_MULTIPROC_DIR`가 container 내부 전용 경로면 해제하거나 실제 writable 디렉터리로
  바꾼다. 그렇지 않으면 health는 통과해도 첫 metric label 생성 요청부터 500이 날 수 있다.
- Live 계정은 `EmailStr`이 허용하는 실제 형식의 도메인을 써야 한다. 예약·special-use 도메인은
  DB에 직접 만든 계정이어도 login request validation에서 422가 된다.
- 긴 UI timeout 전에 같은 Origin의 OAuth provider GET·login POST를 직접 확인해 CORS, API 생존,
  계정 계약을 checkpoint로 고정한다. 실패 시 clone/build부터 반복하지 않고 이 checkpoint부터
  재개한다.
- Trip 생성 실패: 계정 상태, API rate limit, `POST /trips` 응답을 확인한다.
- WebSocket 연결 실패: Web build의 `NEXT_PUBLIC_PINVI_API_URL`, API `/ws/trips/{trip_id}`
  cookie 전달, reverse proxy WebSocket upgrade 설정을 확인한다.
- broadcast reload 실패: API mutation 응답, backend `realtime_broker.publish_event_nowait`,
  API worker 수를 확인한다. ADR-035 현재 구조에서는 `PINVI_API_WORKERS=1`이어야 한다.
- cleanup 실패: 생성된 Trip title prefix로 검색해 수동 정리하고, 실패 내용을 `docs/journal.md`에
  남긴다.
- Backup snapshot 생성 실패: API `POST /admin/backup/snapshot` 응답, `PINVI_BACKUP_DIR` 디스크
  여유, `pg_dump` 설치, `PINVI_BACKUP_MIN_FREE_BYTES` guard를 확인한다.
- Backup audit 확인 실패: `/admin/audit` 최근 100건에 `backup.snapshot`이 보이는지, admin 계정
  권한과 audit append commit 상태를 확인한다.
