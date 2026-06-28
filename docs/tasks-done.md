# tasks-done.md — 완료·아카이브

완료된 task와 머지 이력을 보관한다. 열린 작업은 `docs/tasks.md`, 현재 진척과
"다음 한 작업"은 `docs/resume.md`가 정본이다. 작성 규약은 `docs/tasks-rule.md`를
따른다.

## 2026-06-28

- [x] T-255 — 지도 마커 / 색상 적용 parity.
      `@pinvi/domain`에 marker resolver를 추가해 custom/resolved/upstream/snapshot/category/kind/fallback
      우선순위를 한 곳에서 계산한다. 사용자 Trip 지도, 탐색 지도, Admin Trip POI preview는 같은
      marker style metadata를 노출하고, Trip 지도는 selected/broken 상태를 DOM/e2e에서 확인한다.
      mock e2e는 Trip detail/Admin trip dialog marker parity를 검증하고, live read-only spec은
      `PINVI_ADMIN_LIVE_E2E=1` gate에서 `/map` marker metadata를 데이터 유무에 독립적으로 확인한다.
      N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 Windows fallback Playwright로 검증했다.

- [x] T-254 — Admin live e2e matrix v0.2.0 확장.
      `admin-live-matrix.live.ts` catalog를 6,195건으로 고정해 drift를 감지하고,
      read-only matrix에 `/admin/debug/request/{id}` captured request timeline,
      feature detail subpage tabs, backup restore-lock/mutation guard, ETL app-owned job rows,
      Grafana dashboard selector/WebSocket dashboard, raw secret pattern 미노출 검사를 추가했다.
      runbook은 N150 우선 실행과 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`, `2000`, full catalog gate를
      명시한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했고, catalog/typecheck 중심으로 검증했다.

- [x] T-253 — Prometheus/Grafana 운영 가시화 게이트.
      observability profile에 blackbox exporter를 추가해 Web/Dagster HTTP health를
      Prometheus target으로 확인하고, API `/metrics`에 SQLAlchemy DB pool gauge를 추가했다.
      Grafana provisioning은 기존 Overview에 API p95/error, DB pool, WebSocket, ETL/backup
      4종 dashboard를 더한다. `/admin/grafana`는 dashboard selector와
      `GET /admin/grafana/health` 기반 `ok`/`degraded` 표시를 제공하고, mock/live e2e가
      iframe, dashboard path, secret 미노출, degraded 상태를 검증한다. production httpx client는
      `kor_travel_map`, `kor_travel_map_admin`, `kor_travel_geo`, `telegram`, `google_oauth`
      provider tag를 `ApiCallTracker`에 연결하며 query secret과 Telegram bot token path를 mask한다.
      Resend SDK 경로는 T-257 deliverability/provider tracking preflight로 남겼다. N150 SSH alias는
      현재 Linux 환경에서 해석되지 않아 실제 N150 live run은 수행하지 못했다.

- [x] T-252 — Backup/restore live UI e2e.
      `/admin/backup`에 snapshot 검색/status filter와 visible count를 추가하고,
      production 기본 restore 버튼을 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0`으로
      잠갔다. `admin-live-backup.live.ts`는 read-only 목록/sort/filter/empty/masking과
      backup mutation 미발생을 검증하고, `admin-backup-live-mutating.live.ts`는
      `PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`에서 staging
      snapshot 생성, `backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을
      확인한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했다.

- [x] T-251 — Restore staging drill.
      `scripts/restore-staging-drill.sh`를 추가해 staging URL 없이는 restore를 시작하지 않도록
      가드하고, snapshot checksum, `pg_restore --list`, `restore-db.sh`, DB health row count,
      admin audit chain link, rollback rehearsal(precheck/drain)을 한 번에 수행한다.
      backup sidecar는 dump basename 기준으로 생성하고, restore 검증은 sidecar checksum 값을
      실제 dump hash와 비교하도록 정리해 staging 경로로 dump와 sidecar를 함께 옮겨도 검증이
      가능하다. N150 SSH alias는 현재 Linux 환경에서
      해석되지 않아 실제 N150 drill은 실행하지 못했고, fake DB tool 기반 스크립트 회귀로
      가드와 path masking을 검증했다.

- [x] T-250 — Backup script / snapshot endpoint hardening.
      `scripts/backup-db.sh`에 schema name guard, disk free guard, tmp dump 생성, sha256 생성/검증을
      추가했고 `scripts/restore-db.sh`는 sidecar checksum을 restore 전에 검증한다. Admin backup
      API는 snapshot/restore path를 `backup://<filename>`으로 mask하고, snapshot 생성 실패도
      `backup.snapshot_failed` audit으로 남긴다.

- [x] T-249 — App-owned integrity source / known orphan fix.
      `app.data_integrity_violations` migration/model과 Pinvi app-owned integrity service를
      추가했다. `/admin/integrity/issues`는 `source=all|kor_travel_map|pinvi_app` filter를
      받고, persisted row와 broken POI feature link, marker color drift, curated import source
      drift, active attachment deleted target 같은 known app issue를 `source="pinvi_app"`로
      반환한다. Web `/admin/integrity`는 source filter/column을 표시하고 Pinvi app issue는
      read-only로 둔다.

- [x] T-248 — Feature detail subpages.
      `GET /admin/features/{id}/sources`, `/overrides`, `/weather-values`를 추가했다.
      sources/overrides는 `kor-travel-map` admin detail payload에서 read-only projection으로
      반환하고, weather-values는 기존 feature weather card의 metrics를 Admin tab용 list로 투영한다.
      Web은 `/admin/features/{id}/{sources,overrides,weather-values}` deep link tab과 기존 feature
      inspector의 tab link를 제공한다. override mutation은 별도 ADR 전까지 추가하지 않는다.

- [x] T-247 — Provider sync 운영 mutation 계약 정리.
      upstream `kor-travel-map` 운영 mutation을 확인해 import job cancel만 Pinvi에 relay했다.
      `POST /admin/provider-sync/import-jobs/{job_id}/cancel`은 `admin` 전용, `access_reason`
      필수, upstream reason fallback, `provider_import_job.cancel` audit을 적용한다. Web
      `/admin/provider-sync`는 queued/running job에 취소 사유 패널을 제공하고 실패 시 row를 유지한다.
      provider run-now/pause/resume/reset cursor는 upstream provider mutation 또는 별도 ADR 전까지
      추가하지 않는다.

- [x] T-246 — Debug live UI e2e 확장.
      `apps/web/e2e/admin-debug-live.live.ts`를 추가해 `/admin/debug/logs` route render,
      sanitized polling fallback status, filter query 유지, live toggle/pause, request timeline 이동,
      raw secret pattern 미노출을 read-only로 검증한다. Pinvi admin client는 현재 `X-Request-Id`를
      `kor-travel-map` admin/ops 호출에 전달하며, debug live test는 UI credential 대신
      `PINVI_ADMIN_LIVE_STORAGE_STATE`도 지원한다. N150에서는 API/Web 재빌드·health 확인 후
      Playwright Chromium이 Ubuntu 26.04 미지원으로 실패했고, Windows fallback runner에서 N150
      Web/API 대상 live test 1건이 통과했다.

- [x] T-245 — Loki/Promtail 또는 대체 log stream.
      v0.2.0에서는 Loki/Promtail LogQL WebSocket을 필수 운영 구성으로 올리지 않고,
      `kor-travel-map` sanitized system/API logs polling fallback을 선택했다.
      `GET /admin/debug/logs/stream/status`는 `mode="polling"`, 5초 polling interval,
      source 목록, `loki_enabled=false`, `sse_enabled=false`를 반환한다.
      Web `/admin/debug/logs`에는 live toggle과 pause/resume을 추가했고, live 상태에서는 기존
      sanitized system/API endpoint를 같은 filter로 재조회한다. N150 live read-only 검증은 T-246에서
      request timeline masking 검증과 함께 수행한다.

- [x] T-244 — Request timeline API.
      `GET /admin/debug/request/{request_id}`를 추가해 Pinvi request id 중심 timeline을 반환한다.
      API call log, admin audit log, location access log/outbox, `payload.request_id`가 있는
      email queue와 upstream sanitized system/API logs를 시간순 event로 조합하되,
      `kor-travel-map` log는 보조 source로만 붙인다. upstream 보조 source 실패는
      `status="partial"`/source `degraded`로 접고, all-source not found는 404로 반환한다.
      Web `/admin/debug/logs`에는 request id 검색을, `/admin/debug/request/{request_id}`에는
      source/event table을 추가했다. N150 live read-only는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-243 — ETL live / Dagster 운영 게이트.
      `/admin/etl/summary`가 Pinvi Dagster `/server_info`와 `/graphql`을 읽어
      code location repository/job/asset/schedule, 최근 run 상태를 live snapshot으로 반환한다.
      Web `/admin/etl`은 app-owned job row에 live/registry 상태, schedule timezone, 최신 run
      status를 표시한다. GraphQL 실패 시 `pinvi.status=degraded`로 강등하고 static registry와
      app-owned outbox/retention summary는 유지한다. run tag 값은 Admin 응답에 노출하지 않는다.
      N150 API smoke / Playwright live는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-242 — Telegram system summary/outbox ETL.
      `pinvi_telegram_system_outbox` asset/job/schedule을 추가해 15분마다
      `app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped,
      failed, retry exhausted, category별 retry exhausted 비율을 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded Telegram outbox summary를
      노출하고, payload·message text·user id·chat id·token·last_error 원문은 노출하지 않는다.
      weekly/daily 사용자 브리프 생성은 후속 `pinvi_telegram_weekly` 범위로 남겼다.

- [x] T-289 — Linux-only 개발 환경 / ADR-051 문서화.
      ADR-051로 개발·git·CodeGraph는 Linux 기준, Playwright는 N150 우선 실행으로 고정했다.
      ADR-024의 NTFS source / WSL 테스트 미러 모델과 ADR-017의 Windows `git.exe` amendment를
      supersede하고, AGENTS/CLAUDE/SKILL, 개발 환경 런북, CodeGraph worktree 런북,
      실패 패턴 문서, README/Sprint 문서를 같은 기준으로 동기화했다.

- [x] T-241 — `pinvi_location_log_archive` Dagster job.
      `pinvi_location_log_archive` asset/job/schedule을 추가해 매일 KST 04:30
      `app.location_access_log`의 6개월 초과 archive 후보, active head/tail hash-chain bridge,
      미처리 `location_audit_outbox` blocker, purpose별 후보 수를 dry-run으로 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 후보 수와 bridge/pending 상태만 노출하고,
      raw 좌표·사용자 식별자는 노출하지 않는다. 실제 archive/delete/anonymize 실행은
      T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-240 — `pinvi_pii_retention` Dagster job.
      `pinvi_pii_retention` asset/job/schedule을 추가해 매일 KST 04:15 삭제 계정 PII,
      OAuth identity, 만료 verification/reset token, 오래된 session, 만료 OAuth transient row,
      location/admin audit PII 보존 기간 만료 후보를 dry-run으로 집계한다. `/admin/etl/summary`와
      Web `/admin/etl`은 후보 수, cutoff, 권한 계정 제외 수를 PII 없이 노출한다. 실제
      delete/anonymize/archive 실행은 T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-239 — `pinvi_email_outbox` Dagster job.
      `pinvi_email_outbox` asset/job/schedule을 추가해 15분마다 `app.email_queue`의 pending
      due/backoff/stuck, failed/bounced/complained, retry exhausted, template별 실패율을 PII 없이
      집계한다. `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded email outbox summary를
      노출한다. 실제 발송 source of truth는 FastAPI lifespan worker로 유지하고,
      deliverability/suppression 집행은 T-257/T-277로 남겼다.

- [x] T-238 — Pinvi app-owned ETL 표준 / ADR.
      ADR-050으로 Pinvi `apps/etl` app-owned Dagster job 표준을 고정했다. 신규 job은
      `app` schema 소유 범위, import-time side effect 금지, KST schedule, retry/backoff,
      idempotency key, bounded metadata, `run_failure_sensor` 기반 Sentry/Telegram outbox 알림,
      destructive dry-run gate를 따른다. ETL runbook, Dagster architecture 문서, Sprint 5 DoD,
      AGENTS/CLAUDE 진입 요약을 같은 기준으로 동기화했다.

- [x] T-237 — WebSocket backend hardening / metrics.
      Trip WebSocket backend에 bounded-label Prometheus gauge/counter와 `pinvi.websocket.close`
      구조화 로그를 추가했다. connection accept/reject, close code/reason, client message,
      broadcast result, send timeout/error를 계측하고, permission/rate-limit/connection-cap/
      heartbeat-timeout 회귀 테스트와 broker stale-removal metric 테스트를 보강했다. 기존 문서의
      rate-limit grace slot 반환 설명도 실제 구현처럼 "close까지 유지"로 정정했다.

- [x] T-236a — WebSocket multi-client N150 live e2e drill.
      N150 live mutating Playwright에서 실제 WebSocket broadcast/reconnect 뒤 Trip snapshot reload를
      검증했다. 첫 실패로 `pinvi-api` worker 2개와 process-local realtime broker 충돌을 확인해
      Pinvi compose 기본 worker를 1로 낮추고, `kor-travel-docker-manager` PR #44에서 운영 compose도
      `PINVI_API_WORKERS=1` 기본값으로 맞췄다. 두 번째 실패로 public Web/API CORS 주입 drift를 확인해
      docker-manager PR #45에서 `PINVI_PUBLIC_API_URL`/`PINVI_CORS_ALLOWED_ORIGINS`를 gitignore `.env`
      주입값으로 분리했다. 최종 Windows Playwright live mutating e2e 1건이 통과했다.

- [x] T-236 — WebSocket multi-client collaboration e2e.
      Trip 상세 mock Playwright e2e에 2개 브라우저 컨텍스트 presence/broadcast reload,
      재연결 후 최신 snapshot 반영, 5개 컨텍스트 presence fan-out와 offline cleanup 검증을
      추가했다. Fake WebSocket은 React Strict Mode 재마운트와 재연결에서 마지막 active socket을
      기준으로 서버 이벤트를 주입하도록 정리했다. N150 staging live 검증은 작업 크기를 분리해
      T-236a로 남겼다.

- [x] T-288 — Task 문서 분리 정책 반영.
      `kor-travel-map`의 `tasks.md`/`tasks-done.md`/`resume.md` 분리 정책을 확인하고,
      Pinvi에 `docs/tasks-rule.md`와 본 파일을 추가했다. 신규 task 진입 전 최근 2일 PR
      리뷰 코멘트 확인, task 분리 기준, 완료 후 `tasks-done.md` 아카이브 규칙을 고정했다.
      기존 `tasks.md`의 legacy 완료 이력 전체 이관은 `T-288-legacy-task-archive`로 분리했다.

- [x] T-235 — Optimistic lock / conflict dialog.
      Trip/POI 409 conflict UX, LWW/수동 병합, server/my value 선택과 API/Vitest/Windows
      Playwright 회귀 테스트를 구현했다. Day API는 현재 `If-Match` 계약이 없어 T-287로
      분리했다.

- [x] T-234 — WebSocket client invalidation / auth close handling.
      WebSocket close code/reason 분류, 4401 refresh 재연결, 4403 권한 상실 안내,
      4408/4429 backoff 안내, realtime invalidation key와 duplicate reload 방지를 구현했다.

- [x] T-233 — Sprint 5/6 상세 Task 계획.
      `docs/execplan/sprint5-v020-release-plan.md`에 Sprint 5 `v0.2.0` 잔여 구현
      Task와 Sprint 6 `v1.0.0` 후속 Task 초안을 정리하고, PR 리뷰에서 지적된 법무/운영
      gap을 T-256~T-286으로 보강했다.

- [x] T-232 — Trip WebSocket frontend client / presence 첫 연결.
      `@pinvi/api-client`에 `TripRealtimeClient`와 `tripWebSocketUrl`을 추가하고,
      사용자 Trip 상세 화면을 `WS /ws/trips/{trip_id}` presence/reload 흐름에 연결했다.

## Legacy

- 기존 `docs/tasks.md`의 `Admin 콘솔 기능 보강 프로그램`, `완료`, `머지 히스토리`,
  그리고 완료/보류가 섞인 하위 legacy 섹션은 `T-288-legacy-task-archive`에서
  단계적으로 이관한다.
