# Sprint 5 / v0.2.0 상세 실행 계획

본 문서는 `v0.2.0` 후보를 닫기 위한 남은 Sprint 5 작업을 Task 단위로 쪼갠다.
단위 기능은 로컬 WSL ext4 미러에서 검증하고, 기능 묶음은 N150 live API/UI/e2e로
검증한다. Playwright runner는 Windows에서 실행한다.

## 1. 범위와 원칙

- Pinvi 책임만 구현한다. feature/provider 정규화, provider raw 적재, dedup 원천 처리는
  `kor-travel-map` 소유다.
- 운영 도메인, SSH target, credential, token, 내부 IP는 추적 파일에 기록하지 않는다.
- live e2e는 read-only matrix와 mutating staging suite를 분리한다. production mutating
  live e2e는 별도 사용자 승인 없이는 실행하지 않는다.
- 사용자 화면과 Admin 화면의 지도뷰는 같은 marker palette / icon fallback / custom override
  규칙을 따른다. 지도 마커 색은 데이터 표현에만 쓰고 CTA나 일반 UI 강조색으로 재사용하지 않는다.
- 모든 mutating Admin/운영 API는 `access_reason`, audit, idempotency 또는 중복 실행 방지,
  실패 rollback 기준을 포함한다.
- WebSocket 협업은 HTTP mutation을 source of truth로 두고, WebSocket은 presence와 성공한
  mutation broadcast/invalidation만 담당한다.

## 2. 현재 완료 상태

- T-232: `packages/api-client/src/websocket.ts`와 사용자 Trip 상세 1차 연결 완료.
- 기존 완료: WebSocket backend broker, POI/Trip HTTP route broadcast, Admin ETL/provider
  read view, Admin debug logs read view, Grafana prod URL 주입, backup snapshot/restore
  service foundation, 사용자 Trip/Feature map 1차 marker palette 적용, Admin live read-only matrix.

## 3. Task Backlog

### T-233 — Sprint 5 상세 실행 계획

- 산출물: 본 문서, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`.
- 검증: 문서 diff check, 민감정보 패턴 스캔.
- 완료 기준: T-234 이후 task가 구현 순서와 검증 게이트를 가진다.

### T-234 — WebSocket client invalidation / auth close handling

- `TripRealtimeClient` close event에 close code/reason을 노출한다.
- `4401` 계열 close 시 `/auth/refresh` 또는 기존 auth recovery 경로를 호출하고 재연결한다.
- `4403`은 권한 상실 안내와 Trip 목록 복귀 CTA를 제공한다.
- `4408`/`4429`는 rate/cap 안내와 backoff 상태를 표시한다.
- domain event별 TanStack Query invalidation key를 정의한다.
- duplicate reload 방지: HTTP mutation 성공 reload와 WebSocket event reload가 같은 tick에
  겹치면 1회로 합친다.

검증 케이스:

- Vitest: URL query 보존, close code mapping, reconnect backoff cap, manual disconnect는
  reconnect하지 않음, `4401` refresh 성공/실패.
- Web typecheck/lint.
- Playwright mock: 연결됨/재연결 대기/권한 상실/rate limited 상태 표시.

### T-235 — Optimistic lock / conflict dialog

- POI/Trip/Day update의 `409` 응답 shape를 UI에서 식별한다.
- `apps/web/components/poi/ConflictDialog.tsx`를 추가한다.
- LWW 가능 필드와 수동 병합 필드를 구분한다.
- server 값 보기, 내 값 다시 적용, 서버 값 수락, reload 후 닫기 흐름을 제공한다.
- 충돌 해결 action에도 사용자에게 보이는 실패/성공 상태를 둔다.

검증 케이스:

- API integration: If-Match 누락/오래된 version/최신 version 성공.
- Vitest: conflict payload parser, merge field label.
- Playwright mock: POI memo 충돌, marker_color 충돌, 삭제된 POI 충돌, day 삭제 후 POI update 충돌.

### T-236 — WebSocket multi-client collaboration e2e

- Windows Playwright에서 두 browser context가 같은 Trip에 접속하는 e2e를 추가한다.
- context A가 day/POI/trip을 변경하면 context B가 WebSocket event로 reload되는지 확인한다.
- presence online/offline/viewing_day 표시를 검증한다.
- reconnect 중 mutation이 발생해도 재연결 후 최신 HTTP snapshot이 보이는지 확인한다.

검증 케이스:

- Mock e2e: fake WebSocket server 또는 route-level WebSocket shim으로 event 주입.
- Local live e2e: WSL dev stack + Windows Playwright, ephemeral trip 생성/정리.
- N150 staging live e2e: `PINVI_LIVE_MUTATING_E2E=1`, test prefix 기반 Trip 생성/정리.
- 5명 시뮬레이션: browser context 5개, presence count, cap 미초과, event fan-out.

### T-237 — WebSocket backend hardening / metrics

- close code별 구조화 로그와 Prometheus counter/gauge를 추가한다.
- active connection, per-trip connection, message rate limited, broadcast failure/timeout metric을
  노출한다.
- member role 변경 시 대상 사용자의 기존 WebSocket을 close하는 경로를 확인/보강한다.
- heartbeat timeout을 테스트 가능한 clock/setting으로 낮춰 회귀 테스트를 추가한다.
- 운영 문서에 single-worker/sticky session 제약과 scale-out 전환 조건을 다시 고정한다.

검증 케이스:

- Unit: broker disconnect idempotency, slow peer timeout, cap slot 반환.
- API integration: missing token, invalid token, permission denied, trip cap, process cap,
  rate limit, unknown event, bad cursor, heartbeat timeout, companion removed close.
- Metrics test: `/metrics`에 WebSocket gauge/counter가 노출된다.

### T-238 — Pinvi app-owned ETL 표준 / ADR

- Pinvi `app` schema 소유 Dagster job 표준을 ADR로 고정한다.
- 대상 job: email outbox drain/monitor, PII retention, location log archive,
  Telegram summary/outbox.
- import-time DB/network 금지, KST schedule, retry/backoff, idempotency key,
  run metadata, Sentry/Telegram failure notification 기준을 문서화한다.
- `kor-travel-map` feature/provider ETL 침범 금지를 체크리스트에 넣는다.

검증 케이스:

- `apps/etl/tests/test_definitions.py`가 모든 asset/job/schedule import를 검증한다.
- 문서: `docs/runbooks/etl.md`, `docs/sprints/SPRINT-5.md`, `docs/decisions.md`.

### T-239 — `pinvi_email_outbox` Dagster job

- `app.email_queue` pending/backoff 상태를 집계하고 drain worker 상태를 검증하는 asset/job을
  추가한다.
- 실제 메일 발송 source of truth는 API lifespan worker로 유지하되, Dagster는 운영 점검과
  stuck item 재시도 요청을 담당한다.
- stuck threshold, max retry, template별 실패율 metadata를 Admin ETL summary에 노출한다.

검증 케이스:

- ETL unit: pending 없음, due pending 있음, retry 초과, stuck item, template별 집계.
- API integration: `/admin/etl/summary`에 email outbox job/metadata 노출.
- Admin e2e mock: ETL 화면에서 email outbox 상태/필터 표시.

### T-240 — `pinvi_pii_retention` Dagster job

- disabled/deleted 사용자, 만료 verification token, 만료 reset token, 오래된 sessions,
  보존 기간 지난 PII 후보를 식별한다.
- destructive action은 첫 PR에서 dry-run metadata만 제공하고, 실제 삭제/anonymize는 별도 kill-switch
  후속으로 둔다.
- PIPA/LBS 문서와 보존 기간을 대조한다.

검증 케이스:

- ETL unit: cutoff KST/UTC 경계, dry-run count, 제외 대상(active/admin/self) 필터.
- API integration: Admin ETL summary에 retention dry-run 결과 노출.
- 문서: compliance 문서와 retention policy cross-reference.

### T-241 — `pinvi_location_log_archive` Dagster job

- `app.location_access_log` 보존/아카이브 후보를 dry-run으로 집계한다.
- CPO 접근 로그 chain 검증과 충돌하지 않는 archive 정책을 문서화한다.
- archive 대상은 Sprint 5에서 metadata/dry-run까지, 실제 이동은 별도 승인 후 진행한다.

검증 케이스:

- ETL unit: 기간 경계, CPO-only log 제외/포함 정책, dry-run metadata.
- API integration: `/admin/audit/location`과 archive dry-run 결과가 동시에 조회 가능.

### T-242 — Telegram system summary/outbox ETL

- Telegram system notification outbox와 weekly/daily summary 후보 job을 추가한다.
- 실제 credential은 `.env.mcp-telegram` 또는 운영 secret에만 둔다.
- 실패 시 retry/backoff와 Sentry tag를 남긴다.

검증 케이스:

- ETL unit: no credential skip, pending notification, retryable failure, permanent failure.
- API integration: Admin ETL summary에 telegram job 상태 노출.
- Telegram live는 PR 완료 알림 MCP와 분리하고, 운영 credential 원문을 로그에 남기지 않는다.

### T-243 — ETL live / Dagster 운영 게이트

- N150 Dagster `/server_info`와 code location repository/job/asset/schedule 목록을 live로 검증한다.
- app-owned job materialize dry-run을 staging에서 실행한다.
- Admin `/admin/etl` live UI matrix에 app-owned job rows, upstream degraded 상태, import jobs
  pagination/filter를 추가한다.

검증 케이스:

- Windows Playwright live: `/admin/etl`, `/admin/provider-sync` read-only 확장.
- N150 API smoke: `/admin/etl/summary` authenticated read.
- Dagster live: job list, schedule timezone, latest run status.

### T-244 — Request timeline API

- `GET /admin/debug/request/{request_id}`를 추가한다.
- source 후보: API call log, admin audit log, location access log, email queue, backup run,
  upstream sanitized API logs.
- 응답은 시간순 event list, duration, status, error code, sanitized detail만 포함한다.
- invalid UUID, not found, mixed-source partial failure를 명확히 반환한다.

검증 케이스:

- API unit/integration: valid timeline, not found, invalid id, partial upstream failure,
  secret/header/path masking.
- Web e2e mock: request id 검색 → timeline 단계 표시.
- N150 live read-only: 기존 request id 하나를 찾아 timeline render.

### T-245 — Loki/Promtail 또는 대체 log stream

- 운영 선택지 A: Loki/Promtail compose + LogQL proxy/stream.
- 운영 선택지 B: 현재 sanitized API/system logs polling + server-sent stream.
- Sprint 5에서 실제 인프라 부담과 N150 디스크 여유를 보고 하나를 선택한다.
- `/admin/debug/logs`에 live stream toggle, pause/resume, level/source filter를 추가한다.
- raw log, Authorization, cookie, 운영 도메인/IP, secret value는 API와 UI 양쪽에서 마스킹한다.

검증 케이스:

- API integration: LogQL success, Loki down graceful degrade, sanitization.
- Web e2e mock: stream open, new row append, pause, resume, filter 유지.
- N150 live read-only: stream 또는 polling fallback으로 최근 log render.

### T-246 — Debug live UI e2e 확장

- `apps/web/e2e/admin-debug-live.live.ts`를 분리한다.
- live read-only: `/admin/debug/logs`, `/admin/debug/request/{id}`, masking, filter/pagination,
  stream fallback.
- mutating 없음. 운영 rate limit을 고려해 worker 1, throttle 기본 2100ms를 유지한다.

검증 케이스:

- Windows Playwright on N150: route render, filter, request id search, no raw secret pattern.
- failure artifact: screenshot/video/trace는 로컬에만 두고 커밋하지 않는다.

### T-247 — Provider sync 운영 mutation 계약 정리

- Sprint 5 DoD의 retry/pause/resume을 구현하려면 upstream `kor-travel-map` mutation 계약이
  필요하다.
- 현재 Pinvi는 read-only proxy이므로, upstream OpenAPI에 run-now/retry/cancel/pause/resume이
  없으면 먼저 `kor-travel-map` PR을 만든다.
- Pinvi relay는 access_reason, audit, idempotency key, upstream kill-switch, role gate를
  포함한다.

검증 케이스:

- Contract test: upstream OpenAPI path/schema drift.
- API integration: success, upstream 404/409/503, idempotency duplicate, audit.
- Web e2e mock: retry/pause/resume dialog, disabled state, failure rollback.

### T-248 — Feature detail subpages

- `/admin/features/{id}/sources`, `/overrides`, `/weather-values` route를 추가하거나 기존 detail
  inspector에서 deep-link 가능한 tab으로 제공한다.
- source links, override history, weather timeline은 upstream read-only 계약을 사용한다.
- Pinvi-owned override mutation은 별도 ADR 전까지 추가하지 않는다.

검증 케이스:

- API integration: sources/overrides/weather-values proxy success/degraded.
- Web e2e mock: direct deep link, tab navigation, empty state, upstream error state.
- Admin live matrix: route render/read-only filters.

### T-249 — App-owned integrity source

- `app.data_integrity_violations` 또는 동등한 Pinvi-owned integrity source가 필요한지 결정한다.
- 필요한 경우 migration, service, Admin `/admin/integrity` source filter를 추가한다.
- kor-travel-map consistency issue와 Pinvi app integrity issue를 같은 table UI에서 구분한다.

검증 케이스:

- DB migration contract: indexes/status enum/cascade.
- API integration: Pinvi issue list, upstream issue list, combined source filter.
- Web e2e mock/live: source filter, severity/status filter, action availability.

### T-250 — Backup script / snapshot endpoint hardening

- `scripts/backup-db.sh`, `scripts/restore-db.sh`, `scripts/restore-hotswap.sh`를 실제 N150 경로와
  현재 docker-manager 운영 모델에 맞춘다.
- disk guard, sha256, `pg_restore --list`, timeout, lock, audit 실패 기록을 보강한다.
- backup snapshot API가 path 원문을 과다 노출하지 않도록 response와 UI를 점검한다.

검증 케이스:

- Unit: script output parse, failed script, timeout, checksum missing, sorted snapshots.
- API integration: list/create 권한, audit, failure, path masking.
- CLI staging: backup 생성, sha256 검증, `pg_restore --list`.

### T-251 — Restore staging drill

- N150 또는 staging DB에서 `scripts/restore-db.sh` 단순 restore 훈련을 수행한다.
- production data를 쓰는 경우 PII export/로그를 남기지 않고, 결과는 status와 checksum만 문서화한다.
- schema-swap은 Sprint 6 정식 범위지만, Sprint 5에서는 dry-run/precheck까지 수행한다.

검증 케이스:

- staging restore: app schema restore, DB health, audit chain verify.
- rollback rehearsal: restore 실패 시 기존 schema 유지 확인.
- 문서: `docs/runbooks/backup-restore.md` 실제 명령/경로 정합화.

### T-252 — Backup/restore live UI e2e

- read-only live: `/admin/backup` snapshot list, sort/filter, empty/error state.
- staging mutating live: manual snapshot 생성, audit 확인, cleanup/retention 확인.
- restore-hotswap 버튼은 production live에서 disabled 또는 explicit staging flag 없이는 실행하지
  않는다.

검증 케이스:

- Windows Playwright live read-only on N150.
- Windows Playwright staging mutating with `PINVI_BACKUP_LIVE_MUTATING_E2E=1`.
- UI에서 raw absolute path/secret/domain이 노출되지 않는지 regex assertion.

### T-253 — Prometheus/Grafana 운영 가시화 게이트

- Prometheus scrape target, cAdvisor, Pinvi API metrics, Web health, Dagster health를 확인한다.
- Grafana dashboard 4개(API p95/error, DB pool, WebSocket, ETL/backup)를 provisioning한다.
- `/admin/grafana` iframe에서 dashboard path와 frame policy가 실제로 동작하는지 검증한다.

검증 케이스:

- API unit: Grafana embed config placeholder/secret 비노출.
- N150 smoke: Prometheus target UP, Grafana login/embed route 200.
- Windows Playwright live: `/admin/grafana` iframe visible, blocked/degraded state.

### T-254 — Admin live e2e matrix v0.2.0 확장

- read-only matrix에 신규 route/case를 추가한다.
- route: `/admin/debug/request/{id}`, feature detail subpages/tabs, backup read-only variants,
  ETL app-owned rows, Grafana dashboards, system WebSocket metrics.
- mutating live suite는 별도 파일과 env gate로 분리한다.
- full run 전 200 case smoke, 이후 2000 case gate, release 직전 full catalog를 수행한다.

검증 케이스:

- Windows list: catalog count drift 기록.
- Windows N150: `PINVI_ADMIN_LIVE_CASE_LIMIT=200`, `2000`, full.
- auth refresh, throttle, relogin 복귀, no raw secret regex.

### T-255 — 지도 마커 / 색상 적용 parity

- 사용자 화면 지도뷰(`FeatureMapView`, `TripMapView`, 공유 Trip 지도)와 Admin 화면 지도뷰
  또는 지도 preview(Admin Trip POI dialog, Admin POI detail, category mapping preview)가 같은
  색상 해석 규칙을 쓰도록 정리한다.
- 우선순위: POI custom marker color/icon → feature snapshot marker color/icon →
  upstream category `maki_icon`/marker color → Pinvi fallback palette → invalid 값은 `P-13`.
- marker color는 `P-01`~`P-16` token만 정상값으로 취급한다. raw hex 저장/응답이 들어와도
  UI에서는 안전 fallback 또는 운영 오류 상태로 표시한다.
- selected/hover/focus marker state는 색을 임의 변경하지 않고 stroke/ring/scale로만 구분한다.
- broken feature, orphan POI, 좌표 없음, cluster, route line, user location marker의 색상 규칙을
  문서화한다.
- Admin category mapping은 upstream category 색/아이콘과 Pinvi fallback drift를 지도 preview로
  확인할 수 있게 한다.

검증 케이스:

- Domain/Vitest: `paletteHex`, invalid marker color fallback, custom override 우선순위,
  label color contrast.
- Playwright mock: 사용자 map shell feature P-01/P-07/P-13, Trip POI custom P-08,
  shared trip marker, broken feature fallback, selected marker ring.
- Playwright mock: Admin Trip POI dialog map preview, Admin POI detail marker swatch/map preview,
  category mapping palette preview.
- Windows Playwright visual/pixel smoke: marker canvas 또는 DOM marker가 비어 있지 않고,
  대표 P-01/P-07/P-13 색상 swatch가 렌더된다.
- N150 live read-only: `/trips/{id}` 샘플 지도와 `/admin/trips/{id}` POI preview에서 marker
  legend/swatch가 raw hex/undefined 없이 보인다.

### T-256 — Release candidate gate / `v0.2.0`

- 모든 Sprint 5 Task 완료 후 release notes를 정리한다.
- `CHANGELOG.md`, Sprint 문서, `docs/resume.md`, `docs/journal.md`를 release 상태로 갱신한다.
- N150 final smoke와 live e2e 결과를 기록한다.
- tag/Release 생성 전 main CI, N150 deploy, backup snapshot을 확인한다.

검증 케이스:

- GitHub Actions main 최신 pass.
- N150 API/DB/Web/Dagster/upstream smoke 200.
- Admin live 2000 또는 full gate 통과.
- Backup snapshot 1회와 restore staging drill 완료.

## 4. Sprint 6 / v1.0.0 후속 Task 초안

Sprint 6은 Sprint 5가 `v0.2.0`으로 닫힌 뒤 `v1.0.0` 외부 출시를 준비하는 묶음이다.
아래 Task는 Sprint 6 진입 시 별도 실행 계획으로 다시 쪼개되, 지금부터 누락 방지를 위해
백로그에 고정한다.

### T-260 — Sprint 6 상세 실행 계획 / ADR 정리

- `docs/sprints/SPRINT-6.md`를 최신 구현 상태에 맞게 재정렬한다.
- OR-Tools 최적화, category override, MCP 운영, geofencing, backup hot-swap,
  Odroid+N150 병행 운영의 ADR 필요 여부를 확정한다.
- Sprint 6 live e2e와 성능/보안 gate 기준을 문서화한다.

### T-261 — 경로 최적화 정책 / distance matrix

- POI 수 구간별 정책(10개 이하 exact, 11~20 heuristic, 20개 초과 제한/분할)을 정한다.
- PostGIS 거리, 외부 mobility API, cache TTL, 비용/호출량 제한을 문서화/구현한다.
- API: `GET /trips/{id}/days/{day_index}/distance-matrix`.

### T-262 — 스마트 정렬 API / OR-Tools

- `POST /trips/{id}/days/{day_index}/optimize`를 구현한다.
- 시작/종료 고정, 체류시간, 영업시간, 이동수단, locked POI, warning을 지원한다.
- API integration과 load test를 포함한다.

### T-263 — 스마트 정렬 UI

- `OptimizeDialog`에서 미리보기, 거리/시간 delta, warning, 적용/취소를 제공한다.
- 적용 전후 POI 순서와 지도 route line을 비교한다.
- WebSocket 동시 편집 중 적용 conflict를 처리한다.

### T-264 — Admin category mapping DB override

- 현재 read-only category mapping에서 Pinvi-owned override table로 확장할지 ADR로 결정한다.
- 도입 시 `app.category_mappings` migration, audit, rollback, JSON import/export를 구현한다.
- 지도 marker 색상 preview와 Sprint 5 T-255 parity를 재사용한다.

### T-265 — Admin notice plan 작성기

- curated/notice plan 목록, 생성, 편집, POI 추가/정렬, attachment preview를 구현한다.
- kor-travel-map detail snapshot import 계약과 Pinvi-native curated plan 책임 경계를 지킨다.

### T-266 — MCP 외부 인터페이스 운영 실증

- 기존 MCP token/API를 외부 MCP client로 실제 호출한다.
- `list_trips`, `get_trip`, `list_pois`, `search_features`, `get_user_profile`의 scope,
  rate limit, audit, token revoke를 검증한다.
- Claude Code 또는 `mcp-cli` live smoke를 문서화한다.

### T-267 — Backup/Restore UI hot-swap 완성

- Sprint 5의 snapshot/precheck/staging drill을 schema-swap UI 진행 상태로 확장한다.
- drain, restore, validate, switch, rollback, previous schema retention을 UI와 API에 표시한다.
- production 실행은 maintenance window와 별도 confirm/kill-switch를 요구한다.

### T-268 — 한국 전용 geofencing 3중 안전망

- Cloudflare WAF, nginx geo, FastAPI middleware 정책을 실제 운영에 반영한다.
- VPN 해외 노드에서 451 응답을 확인하고, 한국 IP/내부 health path 예외를 검증한다.

### T-269 — LBS / 법무 4문서 / 동의 UX

- LBS 사업자 신고 체크리스트와 법무 검토 문서 4종을 최신 UI/데이터 흐름에 맞춘다.
- 위치 동의, 철회, 감사 로그, data retention 문구를 e2e로 검증한다.

### T-270 — 성능 / 부하 / 보안 점검

- API p95, DB pool, WebSocket 동시 연결, Admin live full run, CSP/CORS/rate limit,
  Argon2/Resend webhook/security headers를 점검한다.
- N150과 Odroid 결과를 분리 기록한다.

### T-271 — Odroid + N150 병행 운영

- N150 기준 배포와 Odroid smoke를 모두 운영 runbook에 맞춘다.
- ARM image와 GHCR 배포는 제외한다. 각 노드는 운영 runbook의 로컬 checkout + 로컬 Docker build
  기준으로 smoke한다.
- backup 위치, reverse proxy, health monitor를 정리한다.

### T-272 — AI companion 별도 서비스 분리

- `kor-travel-concierge` 호출 계약, 장애 fallback, prompt/data redaction, rate limit을 정리한다.
- Pinvi repo 안에는 client contract와 Admin status만 남긴다.

### T-273 — v1.0.0 E2E / Live Gate

- 가입→여행→POI→스마트정렬→공유→동반자 실시간→Admin audit→ETL→MCP→backup hot-swap→geofence
  시나리오를 Windows Playwright와 N150/Odroid smoke로 묶는다.
- mutating live는 staging flag와 cleanup prefix를 강제한다.

### T-274 — v1.0.0 릴리즈

- `CHANGELOG.md`, release notes, tag, GitHub Release, N150/Odroid final smoke,
  backup snapshot, legal/compliance sign-off를 완료한다.

## 5. API 테스트 케이스 카탈로그

### WebSocket

- 인증 없음, invalid token, malformed sub, 권한 없음.
- owner/editor/viewer companion 연결.
- removed companion connection close.
- presence online/offline, viewing_day null/1/366/0/367/bool/string.
- cursor latitude/longitude, legacy lat/lng, out-of-range, bool, NaN류 입력.
- ping/pong, heartbeat timeout, unknown event.
- per-second/per-minute rate limit, grace close, slot 유지/반환.
- trip cap/process cap, reconnect storm.
- slow peer send timeout, disconnect idempotency.
- Trip updated, day created/updated/deleted, POI created/updated/deleted/reordered broadcast.

### ETL

- import-time side effect 없음.
- KST schedule timezone.
- idempotent materialize.
- retry exhaustion 후 failure notification 후보.
- missing external key skip/fail-fast 정책.
- dry-run job은 DB destructive change 없음.
- Admin summary degraded/down.

### Debug/Logs

- request id invalid/not found.
- multi-source partial failure.
- Authorization/cookie/token/serviceKey masking.
- upstream log down graceful degrade.
- stream reconnect/pause/resume.

### Backup/Restore

- snapshot list empty/verified/available/corrupt.
- create success/failure/timeout.
- checksum mismatch.
- disk guard fail.
- restore unknown snapshot/confirm false/script failure/advisory lock busy.
- path masking, audit success/failure.

## 6. UI / Live E2E 케이스 카탈로그

### Mock Playwright

- Trip realtime status labels: offline, connecting, open, error/reconnecting.
- presence count/viewing day render.
- domain event debounce reload.
- conflict dialog branches.
- token refresh success/failure.
- 사용자 feature map: category marker color P-01/P-07/P-13, cluster, selected ring.
- 사용자 trip/shared map: POI custom marker color, feature snapshot fallback, broken feature fallback.
- Admin map preview: Trip POI dialog, POI detail, category mapping marker preview.
- debug timeline render/empty/error.
- Loki stream append/pause/resume/fallback.
- backup create/restore dialogs and disabled production state.
- Grafana iframe visible/degraded.

### N150 Read-Only Live

- Admin route matrix render/filter/sort.
- `/admin/etl` Pinvi app-owned job rows and upstream ops rows.
- `/admin/debug/logs` masking and filter.
- `/admin/debug/request/{id}` timeline for a known non-secret request id.
- `/admin/backup` snapshot list and path masking.
- `/admin/grafana` iframe/degraded state.
- `/admin/system` WebSocket metrics/capacity.
- 사용자 `/map`, `/trips/{id}`, `/shared/{tripId}/{token}` 지도에서 marker legend/swatch가
  token palette 기준으로 표시된다.
- Admin `/admin/trips/{id}`, `/admin/pois/{id}`, `/admin/category-mapping` 지도 preview에서
  raw hex/undefined marker color가 보이지 않는다.

### Staging Mutating Live

- ephemeral Trip 생성 → 2 browser context WebSocket collaboration → cleanup.
- POI create/update/delete broadcast.
- POI marker color/icon 변경 → 상대 browser와 Admin preview에 같은 색상 반영.
- day create/rename/delete broadcast.
- companion invite/remove and connection close.
- manual backup snapshot 생성과 audit 확인.
- provider sync mutation은 upstream staging kill-switch 확인 후 retry/pause/resume만.

## 7. 운영 게이트 순서

1. 각 Task 로컬 단위 검증(WSL ext4) + Windows Playwright mock.
2. PR merge.
3. N150 deploy.
4. N150 smoke: API, DB, Web, Dagster, `kor-travel-map`.
5. 기능 묶음 live read-only e2e.
6. staging mutating live e2e.
7. release candidate full gate.

## 8. 다음 작업

T-234부터 시작한다. 단, provider sync mutation(T-247)은 upstream `kor-travel-map`
계약이 없으면 Pinvi 구현 전에 upstream PR을 먼저 만든다.
