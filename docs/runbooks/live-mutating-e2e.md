# Live mutating E2E Runbook

N150 또는 운영에 준하는 live 환경에서 실제 상태 변경을 수행하는 Playwright suite다. 기존
mock e2e와 Admin read-only live matrix와 분리하며, 각 suite의 명시적 opt-in 환경변수가 없으면
항상 skip한다. Playwright runner는 N150에서 먼저 실행하고, N150에서 실행할 수 없을 때만
Windows runner를 fallback으로 사용한다.

## 1. 범위

- `apps/web/e2e/trip-realtime-live-mutating.live.ts`
- `apps/web/e2e/admin-backup-live-mutating.live.ts`
- verified 사용자 계정으로 두 browser context를 로그인한다.
- test prefix가 붙은 임시 Trip을 생성하고, 실제 `WS /ws/trips/{trip_id}` 연결 상태를 확인한다.
- API `PATCH /trips/{trip_id}` mutation이 다른 context의 Trip 상세 화면에 WebSocket broadcast
  reload로 반영되는지 확인한다.
- browser에서 WebSocket을 닫아 client reconnect를 유도한 뒤, 두 번째 mutation이 최신 snapshot으로
  보이는지 확인한다.
- 종료 시 생성한 Trip은 사용자 API `DELETE /trips/{trip_id}` `soft_delete`로 정리한다.
- Backup mutating suite는 staging admin 계정으로 `/admin/backup` 수동 snapshot을 1회 생성하고,
  `backup://<filename>` masking, 최근 audit의 `backup.snapshot`, snapshot 목록 limit cap을 확인한다.
  restore hotswap endpoint는 호출하지 않으며, 호출이 발생하면 실패한다. snapshot 삭제 API는 아직
  없으므로 테스트가 만든 staging snapshot은 audit evidence로 남기고 운영 retention/스토리지 정책으로
  관리한다.

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

운영 공개 도메인으로 검증할 때는 `*_URL`을 실제 HTTPS 도메인으로 바꾼다.

## 4. 실패 처리

- 로그인 실패: test 계정의 이메일 인증, 비밀번호, CORS/cookie 설정을 확인한다.
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
