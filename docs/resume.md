# resume.md

## 2026-06-29 (codex) — T-282 Rate-limit / abuse admin surface

Sprint 6 rate-limit/abuse 운영 표면을 구현했다. DB에는 `app.rate_limit_overrides`를 추가하고,
기존 `app.rate_limit_buckets`에 admin 조회용 `limit_name, updated_at` index를 보강했다.
`RateLimitMiddleware`는 Postgres backend에서 active `blocked` override를 `429 RATE_LIMIT_BLOCKED`로
차단하고, active `allowed` override는 TTL 동안 counter hit를 우회한다. 원문 IP/email/share token은
저장하지 않고 HMAC bucket hash와 표시용 hash label만 보존한다.

Admin API는 `/admin/abuse` 조회와 `/admin/abuse/overrides`, `/rollback` mutation을 제공한다.
조회는 `admin`/`operator`/`cpo`, mutation은 `admin` 전용이며 모든 override mutation은
`admin_audit_log`에 `rate_limit_override.*` action으로 기록된다. Web Admin에는 `/admin/abuse`
페이지와 sidebar 메뉴를 추가해 backend store 상태, fail-closed 여부, 429 bucket 수, suspicious
auth/share/storage bucket, override 생성/rollback을 처리한다.

문서는 `docs/api/admin.md`, `docs/postgres-schema.md`, `docs/data-model.md`, `docs/runbooks/admin.md`,
`CHANGELOG.md`, `docs/tasks.md`를 갱신했다. 다음 작업은 PR·CI·머지 후 T-283 Security review /
threat model / penetration pass다.

검증은 Linux에서 API ruff, strict mypy, API integration/unit targeted 테스트 9건,
`packages/schemas`, `packages/api-client`, `apps/web` typecheck, Web lint를 통과했다. Playwright는
N150 Docker runner `scripts/n150-playwright-runner.sh`로 `admin-abuse.e2e.ts` 1건을 통과했다.

## 2026-06-29 (codex) — T-281 User lifecycle admin actions

Sprint 6 사용자 lifecycle Admin workflow를 구현했다. DB status vocabulary에 `pending_delete`를
추가했고, auth/session/MCP/password reset/verify 경계에서 `pending_delete`와 `deleted`를 차단한다.
Admin `/admin/users/{user_id}`는 lifecycle 패널을 제공해 인증 메일 재발송, 세션 목록, 세션 단건/전체
강제 로그아웃, 강제 비밀번호 재설정, disable/reactivate, 삭제 대기, 즉시 익명화를 처리한다.

Admin lifecycle mutation은 모두 `access_reason`을 요구하고 `admin_audit_log`에
`user.verification_resend`, `user.session_revoke`, `user.session_revoke_all`,
`user.password_reset_force`, `user.reactivate`, `user.delete_schedule`, `user.anonymize` action을
남긴다. 세션 목록은 IP 원문 대신 `ip_hash`만 응답한다. 세션 강제 로그아웃, role 변경,
force-password-reset, disable/delete/reactivate는 `users.access_token_version`을 증가시켜 기존
access token을 즉시 무효화한다.

사용자 self-service `DELETE /users/me`는 `status='pending_delete'`, `is_active=false`,
`deleted_at=now()`로 전환하고 active session revoke + cookie clear를 수행한다. retention 실행은
`pending_delete` / `deleted` cutoff 후보를 익명화하고 최종 상태를 `deleted`로 고정한다.

검증은 Linux에서 ruff, strict mypy, API integration `test_admin_users_api.py` 10건,
`packages/schemas`, `packages/api-client`, `apps/web` typecheck, Web lint를 통과했다. Playwright는
N150 Docker runner `scripts/n150-playwright-runner.sh`로 `admin-users.e2e.ts` 6건을 통과했다.
다음 작업은 PR·CI·머지 후 T-282 Rate-limit / abuse admin surface다.

## 2026-06-29 (codex) — T-280 RBAC role grant/revoke / permission matrix

Sprint 6 Admin RBAC role grant/revoke와 permission matrix를 구현했다. `/admin/rbac/permission-matrix`
API는 `admin` / `operator` / `cpo`가 조회할 수 있는 role 설명과 endpoint 권한 matrix를 제공한다.
`/admin/rbac` 화면은 같은 matrix를 표시하고, Admin sidebar에 RBAC 메뉴를 추가했다.

사용자 상세 `/admin/users/{user_id}`에는 역할 관리 섹션을 추가했다. `admin` 권한자는
`admin` / `operator` / `cpo` role을 사유와 함께 부여·회수할 수 있고, 모든 mutation은
`admin_audit_log`에 `user.role_grant` / `user.role_revoke` action, before/after roles, request id를
남긴다. role 배열은 `user`, `admin`, `operator`, `cpo` 순서로 정규화한다. 중복 부여, 미보유 role
회수, 자기 admin 회수, 마지막 admin 회수는 각각 `409 INVALID_STATE` 또는
`403 PERMISSION_DENIED`로 차단한다.

검증은 Linux에서 API ruff, targeted mypy, `packages/schemas`, `packages/api-client`, `apps/web`
typecheck, Web lint, API integration `test_admin_users_api.py` 7건을 통과했다. Playwright는 N150
alias `n150`, `pinvi-n150`이 현재 Linux 세션에서 해석되지 않아 Windows fallback으로
`admin-users.e2e.ts` 5건을 통과했다. `docs/architecture/admin-rbac.md`, `docs/api/admin.md`,
`docs/runbooks/admin.md`, task/resume/journal, `CHANGELOG.md`를 함께 갱신했다. 다음 작업은
PR·CI·머지 후 T-281 User lifecycle admin actions다.

## 2026-06-29 (codex) — T-279 Content moderation / takedown workflow

Sprint 6 콘텐츠 신고/게시중단 workflow를 구현했다. DB에는 `app.content_reports`와
`app.content_moderation_actions`를 추가해 trip/comment/attachment/share link 신고, target snapshot,
증거 metadata, 접수/검토/숨김/게시중단/복원/반려/이의제기 상태, reviewer/resolution/appeal 시각,
조치 전후 상태를 저장한다.

사용자 self-service는 `/users/me/content-reports` API와 `/settings/moderation` 화면으로 신고
접수/조회/이의제기를 제공한다. 운영 처리는 `/admin/moderation` API/화면으로 검토, 숨김,
게시중단, 복원, 반려를 수행하며 모든 mutation은 `admin_audit_log`에
`content_moderation.*` action과 운영 사유를 남긴다. 숨김/게시중단/복원 조치는 여행 공개 상태,
soft-delete 댓글/첨부, 공유 링크 revoke 상태에 실제 반영된다. API client/schema/query key,
Admin/user mock Playwright, `docs/runbooks/content-moderation.md`, API/Admin/users/PIPA/schema/data-model
문서를 함께 갱신했다.

검증은 Linux/WSL에서 API ruff, targeted mypy, `packages/schemas`, `packages/api-client`, `apps/web`
typecheck, Web lint, API integration `test_content_moderation_api.py` 3건을 통과했다. Playwright는 N150
alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로 `admin-moderation.e2e.ts`와
`settings-moderation.e2e.ts` 2건을 통과했다. 다음 작업은 PR·CI·머지 후 T-280 RBAC role
grant/revoke / permission matrix다.

## 2026-06-28 (codex) — T-278 DSR intake workflow

Sprint 6 개인정보 권리행사 DSR workflow를 구현했다. DB에는 `app.dsr_requests`를 추가해
`access` / `correction` / `delete` / `suspend` 요청, `received` → `identity_check` →
`processing` → `completed` / `rejected` / `withdrawn` 상태, 접수 + 10일 `due_at`, 본인 확인
metadata, result notice hash, export manifest, partial response, evidence attachment id를 저장한다.
DSR 행은 원문 이메일을 저장하지 않고 `requester_email_hash`와 `requester_email_masked`만 보존한다.

사용자 self-service는 `/users/me/dsr-requests` API와 `/settings/dsr` 화면으로 접수/조회/철회를
제공한다. CPO 처리는 `/admin/dsr` API/화면으로 본인 확인, 처리 시작, 완료/거절 통지를 수행하며
모든 mutation은 `admin_audit_log`에 `dsr.*` action과 `access_reason`을 남긴다. 완료/거절은
`email_queue.template='dsr_result_notice'` row를 만들고 `result_notice_email_id`와
`result_notice_hash`로 연결한다. API client/schema/query key, Admin/user mock Playwright,
`docs/runbooks/dsr.md`, API/Admin/users/PIPA/schema/data-model 문서를 함께 갱신했다.

검증은 Linux/WSL에서 API ruff, targeted mypy, `packages/schemas`, `packages/api-client`, `apps/web`
typecheck, Web lint, API integration `test_dsr_requests_api.py` 3건을 통과했다. Playwright는 N150
alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로 `admin-dsr.e2e.ts`와
`settings-dsr.e2e.ts` 2건을 통과했다. 다음 작업은 PR·CI·머지 후 T-279 Content moderation /
takedown workflow다.

## 2026-06-28 (codex) — T-277 Email deliverability / suppression enforcement

Sprint 6 이메일 deliverability/suppression enforcement를 구현했다. DB에는
`app.email_suppressions`와 `app.resend_webhook_events`를 추가했고, `app.email_queue`는
`delivery_delayed`, `suppressed`, `last_provider_event_id`, `last_provider_event_at`을 가진다.
worker는 발송 전 `users.email_status`, active suppression source, `marketing*` template의
`marketing` consent를 확인해 차단 대상이면 Resend 호출 없이 terminal 상태와
`last_error='suppressed:<reason>'`을 남긴다.

Resend 발송은 Python SDK 직접 호출에서 `httpx` 기반 `ResendClient`로 전환했다.
`api_call_event_hooks(..., provider='resend')`를 사용하므로 `app.api_call_log`에 canonical endpoint와
status가 남고, API key는 endpoint에 저장되지 않는다. `/webhooks/resend`는 event id/`svix-id`
중복을 no-op으로 처리하고, `email.bounced` / `email.complained` / `email.suppressed` terminal
event가 `delivered`보다 우선하도록 했다. hard bounce/complaint/provider suppression은
suppression source와 연결 사용자 `email_status`를 갱신한다.

Admin에는 `GET /admin/emails/deliverability`와 `/admin/emails` 상태판을 추가했다. 상태판은 Resend
API configured/console mode, FROM domain/domain status/sending capability, webhook signature/최근 event,
queue health, suppression/user status count, SPF/DKIM/DMARC manual checklist를 raw secret 없이 표시한다.
검증은 WSL에서 ruff, strict mypy, schemas/api-client/web typecheck, Web lint, API integration 24건을
통과했다. Playwright는 N150 alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로
`admin-emails.e2e.ts` 1건을 통과했다. 다음 작업은 PR·CI·머지 후 T-278 DSR intake workflow다.

## 2026-06-28 (codex) — T-276 Retention execution / dashboard

Sprint 6 보존기간 실행 콘솔을 추가했다. DB에는 `app.retention_runs`와
`app.location_access_log_archive`를 추가했고, `location_access_log` append-only trigger는 retention
transaction의 `app.retention_location_delete_allowed=on` 설정에서만 DELETE를 허용하도록 좁혔다.
`/admin/retention` API는 summary, runs, dry-run, execute를 제공하며 execute는 기본 비활성
`PINVI_RETENTION_EXECUTE_ENABLED`, confirm phrase, cutoff 이전 pending outbox, hash-chain bridge
precheck를 통과해야 한다.

실행은 삭제 후 grace가 지난 일반 사용자 PII anonymize, OAuth identity 삭제, 만료
verification/session/OAuth transient row 삭제, 6개월 초과 위치 로그 archive 후 active row 삭제를 수행한다.
`admin_audit_log` PII 후보는 append-only 원장이라 삭제하지 않고 run result의
`skipped_admin_audit_pii_over_retention`으로 기록한다. Web Admin `/admin/retention`은 kill-switch 상태,
bounded 후보 수, dry-run/execute form, 최근 run evidence를 표시한다. API client/schema/query key,
API integration, mock Playwright, Admin/LBS/schema/runbook 문서를 함께 갱신했다.

검증은 WSL ext4 미러에서 API retention integration 3건, ruff/format, strict mypy, schemas/api-client/web
typecheck, Web lint를 통과했다. Playwright는 N150 SSH alias가 이 세션에서 연결되지 않아 Windows
fallback으로 `admin-retention.e2e.ts` 1건을 통과시켰다. 다음 작업은 PR·CI·머지 후 T-277 Email
deliverability / suppression enforcement다.

## 2026-06-28 (codex) — T-275 PIPA security incident console

Sprint 6 첫 실제 구현 태스크로 PIPA security incident workflow를 추가했다. `app.security_incidents`
상태는 `detected` → `triage` → `notification_decision` → `reported` → `closed`로 정리했고,
CPO 30분 review due, 정보주체 통지 payload hash, 개인정보보호위원회/KISA 72시간 신고 due와
접수번호, evidence attachment id를 migration/model/schema/API에 반영했다. 신규
`/admin/incidents` API는 CPO 전용 상태 전이를 `admin_audit_log`와 함께 기록하고, incident 생성 시
Admin Telegram outbox를 생성한다. 통지 조치는 `security_incident_notice` email queue row와
payload hash를 남긴다.

Web Admin에는 `/admin/incidents` 화면을 추가했다. 목록 필터(status/severity/SLA), 신규 incident
등록, triage/notification decision/notify/report/close 조치 패널을 제공하고, API client/schema/query
key와 mock Playwright 회귀 테스트를 연결했다. `docs/api/admin.md`, `docs/compliance/pipa.md`,
`docs/postgres-schema.md`, `docs/data-model.md`, `docs/runbooks/security-incidents.md`,
`CHANGELOG.md`도 같은 계약을 가리킨다.

검증은 WSL/NTFS에서 Python compileall, Prettier를 확인했고, WSL ext4 미러에서 API targeted pytest
5건, ruff check/format, strict mypy, Web typecheck/lint를 통과했다. mock Playwright는 ext4 미러의
브라우저 캐시 부재로 실행 전 실패했고, 이 세션에서 N150 SSH alias가 잡히지 않아 Windows fallback으로
`admin-incidents.e2e.ts` 1건을 통과시켰다. live 운영 데이터 조치가 아니므로 N150 live Playwright는
이 PR에서 별도 실행 대상이 아니다. 다음 작업은 PR 생성·CI·머지 후 T-276 Retention execution /
dashboard다.

## 2026-06-28 (codex) — T-259 Admin live credential / restore staging drill

N150 local-only Admin live credential을 준비하고 production Web image의 빌드타임 API origin에 맞춰
public HTTPS Web origin으로 UI login을 검증했다. API login smoke 1건과 UI login smoke 1건이
통과했고, N150 Playwright Docker runner(`mcr.microsoft.com/playwright:v1.60.0-noble`)에서
`PINVI_ADMIN_LIVE_CASE_LIMIT=200`은 207 passed (18.4m), `PINVI_ADMIN_LIVE_CASE_LIMIT=2000`은
2007 passed (3.5h)로 통과했다. full catalog 6202건은 최종 tag/Release 직전 별도 장시간 gate로
남긴다.

운영 DB role에는 `CREATEDB` 권한이 없어 N150에 disposable PostgreSQL/PostGIS staging target을
만들고 latest snapshot `backup://pinvi-app-20260628-101426.dump`로 restore staging drill을 수행했다.
checksum과 `pg_restore --list`가 통과했고, restore 후 `users_count=7`, `trips_count=5`,
`admin_audit_log_count=1`, audit chain link valid, rollback precheck guard schema unchanged를
확인했다. DB URL/password/container 세부 값은 local-only 파일에만 둔다.

이번 보강에서 Admin live e2e는 login rate-limit 알림을 만나면 동일 case 안에서 backoff 후
재시도하도록 고쳤고, request timeline live e2e는 loading 종료와 empty-state 문구 변형을 안정적으로
처리한다. 다음 작업은 이 증적 PR을 머지한 뒤 Sprint 6 실제 구현 태스크인 T-275 PIPA security
incident console로 진입하는 것이다.

## 2026-06-28 (codex) — T-259 v0.2.0 release candidate gate 부분 실행

T-259 release candidate gate 결과를 `docs/execplan/v020-release-candidate-gate.md`에
고정했다. 후보 SHA는 `98fb3c2c0d7b7e557dc7a5598f0340d530c4def2`다. N150 checkout을 최신 main으로
갱신했고, `pinvi-api`, `pinvi-web`, `pinvi-dagster` 이미지를 생성해 healthy 상태로 기동했다.
N150 내부 smoke는 API `/health`, `/health/db`, Web `/`, `/admin/login`, Dagster `/server_info`,
`kor-travel-map` `/health`/OpenAPI 모두 200을 확인했다.

backup snapshot은 `postgis/postgis:16-3.5` 일회성 컨테이너로 생성했고,
`pinvi-app-20260628-094253.dump`(126826 bytes), `.sha256`, `pg_restore --list` 검증이 통과했다.
당시 host의 `scripts/backup-db.sh`는 `pg_dump not found`로 직접 실행되지 않았다. 후속으로
`scripts/backup-db.sh`에 Docker fallback을 추가했고 API image에는 `backup-db.sh`와
`postgresql-client`를 포함했다. N150 checkout `4a1b71e`에서 보강된 script를 재실행해
`pinvi-app-20260628-101426.dump`(126826 bytes), `.sha256`, `pg_restore --list` 검증이 통과했다.

릴리스는 보류한다. PR #295 merge 후 최신 main `4a1b71e`의 API push CI가 통과했고, PR #296 merge
후 최신 main `5c0a39b` 기준 WSL ext4 clean install에서 Web lint/typecheck/build도 통과했다.
N150 host Chromium은 `libatk`/`libatspi`/`libXdamage`/`libasound` 계열 누락으로 실패했고,
Playwright 1.60.0 `install-deps --dry-run chromium`은 Ubuntu 26.04를 지원하지 않았지만,
`scripts/n150-playwright-runner.sh` Docker runner가 `mcr.microsoft.com/playwright:v1.60.0-noble`에서
malformed login smoke 1건을 통과했다. Admin live 2000/full은 credential 부재, restore staging
drill은 staging DB URL 부재로 미실행이다. 다음 작업은 N150 local-only Admin live credential과
restore staging DB를 확보한 뒤 `v0.2.0` tag/GitHub Release 생성이다. 이 차단 중 Admin live
200/2000과 restore staging drill은 같은 날짜 상단 엔트리에서 해소됐고, full catalog와 tag/Release만
남아 있다.

## 2026-06-28 (codex) — T-258 Sprint 6 legal/ops implementation prep gate

Sprint 6 legal/ops 구현 준비 gate를 `docs/execplan/legal-ops-implementation-prep-gate.md`로
고정했다. T-275~T-286은 각각 API/UI, 상태 모델, due date, evidence/audit, runbook,
test gate, sign-off 기준을 가진다. 기존 문서의 `KISA 60일 report` 표현은 폐기하고,
개인정보보호위원회/KISA 72시간 신고 기준으로 정정했다. CPO 30분 review는 법정 기한이 아니라
Pinvi 내부 운영 SLA로 분리했다.

Sprint 6 문서와 compliance index는 새 gate 문서를 참조한다. v1.0 기본 범위는 Web/API/Admin
운영 출시이며, `apps/mobile`과 user-facing AI companion은 v1.0 필수 gate에서 제외된다.
다음 작업은 T-259 Release candidate gate / `v0.2.0`이다.

## 2026-06-28 (codex) — T-257 Email deliverability / provider tracking preflight

Resend domain/webhook 공식 기준과 현재 repo 구현을 대조해
`docs/execplan/email-deliverability-provider-preflight.md`에 T-277 구현 계약을 고정했다. 현재
구현은 `app.email_queue` worker, Resend/Svix 서명 검증, queue 상태 갱신,
`/admin/emails` queue 화면까지 닫혀 있다. 반면 발송 전 suppression enforcement,
`users.email_status` 또는 별도 suppression source 갱신, webhook event dedupe/out-of-order
precedence, deliverability 상태판, `api_call_log.provider='resend'` 기록은 T-277 잔여다.

`docs/integrations/resend.md`는 stale React Email/checklist 내용을 현재 inline HTML renderer와
구현 완료/잔여 상태로 분리했다. 다음 작업은 T-258 Sprint 6 legal/ops implementation prep
gate다.

## 2026-06-28 (codex) — T-256 Review gap crosswalk / legal-ops preflight

PR #238/#264 리뷰에서 나온 legal/ops gap을
`docs/execplan/legal-ops-review-gap-crosswalk.md`에 44개 항목(G-001~~G-044)으로 고정했다.
각 gap은 T-257/T-258/T-275~~T-286 등 하나 이상의 Task로 연결했고, 이미 T-244~T-253에서
닫힌 항목은 완료 Task와 Sprint 6 재감사(T-286)를 함께 표기했다.

최근 2일 PR #265~#289의 사람 리뷰 코멘트도 확인했다. WebSocket reconnect/invalidation,
Trip conflict UX, ETL compliance SQL/failure sensor, app integrity pagination/producer 후속은
T-289~T-292로 새로 남겼다. 다음 작업은 T-257 Email deliverability / provider tracking
preflight다.

## 2026-06-28 (codex) — T-255 지도 마커 / 색상 적용 parity

지도 marker resolver를 공용 도메인 로직으로 정리했다. `@pinvi/domain`의
`resolveMarkerStyle`은 custom → server-resolved → upstream feature → feature snapshot →
category/kind fallback → `P-13` fallback 순서로 색/아이콘/source를 계산한다. 사용자 Trip 지도,
탐색 지도, Admin Trip POI preview가 같은 resolver를 사용하고, selected/broken/cluster 상태는
marker metadata와 `MakiMarker` selected/highlighted 상태로 확인한다.

mock e2e는 Trip detail/Admin trip dialog marker parity를 검증한다. live read-only spec은
`PINVI_ADMIN_LIVE_E2E=1` gate에서 `/map` marker metadata를 데이터 유무와 독립적으로 확인한다.
Linux에서 domain tests, Web typecheck/lint가 통과했고, N150 SSH alias는 현재 환경에서 해석되지
않아 Windows fallback Playwright로 mock e2e 8건 pass와 live spec 1건 skip을 확인했다.
다음 작업은 T-256 Review gap crosswalk / legal-ops preflight다.

## 2026-06-28 (codex) — T-254 Admin live e2e matrix v0.2.0 확장

Admin live read-only matrix를 v0.2.0 release gate용으로 확장했다. `admin-live-matrix.live.ts`
catalog는 6,195건 exact count로 고정해 drift를 감지한다. 신규 case는
`/admin/debug/request/{id}` captured request timeline, feature detail subpage tabs,
backup restore-lock/mutation guard, ETL app-owned job rows, Grafana dashboard selector와
WebSocket dashboard, raw secret pattern 미노출을 포함한다.

runbook은 N150 우선 실행과 `PINVI_ADMIN_LIVE_CASE_LIMIT=200` smoke, `2000` gate, full catalog
순서를 고정했다. Linux에서 Web typecheck/lint와 catalog drift 테스트가 통과했고, N150 SSH
alias는 현재 환경에서 해석되지 않아 실제 N150 live run은 미실행이다. Windows fallback runner로
catalog 테스트 1건이 통과했다. 다음 작업은 T-255 지도 마커 / 색상 적용 parity다.

## 2026-06-28 (codex) — T-253 Prometheus/Grafana 운영 가시화 게이트

Prometheus/Grafana 운영 가시화 게이트를 보강했다. observability compose profile에
blackbox exporter를 추가했고, Prometheus scrape target은 API `/metrics`, cAdvisor,
blackbox 자체, Web health, Dagster health를 분리한다. API `/metrics`는
`pinvi_api_db_pool_connections{state=...}` SQLAlchemy pool gauge를 함께 노출한다.

Grafana provisioning은 기존 Overview에 API p95/error, DB pool, WebSocket, ETL/backup
dashboard 4종을 추가했다. Admin `/admin/grafana`는 dashboard selector와
`GET /admin/grafana/health` 서버사이드 probe 기반 `정상`/`강등` 표시를 제공한다.
health probe는 `PINVI_GRAFANA_HEALTH_URL`을 우선 사용해 app compose 내부 Grafana origin을
찌를 수 있다.
mock e2e는 iframe, dashboard path, degraded 상태를 검증하고, live e2e는
`PINVI_ADMIN_LIVE_E2E=1`에서 iframe/health 상태와 secret pattern 미노출을 확인한다.

provider-health `unknown` 방지를 위해 production httpx client factory에 `ApiCallTracker`
provider tag를 연결했다. 대상은 `kor_travel_map`, `kor_travel_map_admin`,
`kor_travel_geo`, `telegram`, `google_oauth`다. `api_call_log.endpoint`는 query secret과
Telegram bot token path를 저장 전에 mask한다. Resend는 T-257 감사에서 SDK 직접 호출로 인해
provider tracking이 누락됨을 확인했고, T-277에서 `provider='resend'` 기록을 구현한다.

검증은 Linux에서 API ruff/pytest/mypy, Web typecheck/lint/Vitest, observability compose
config, Grafana dashboard JSON parse, `git diff --check`를 통과했다. Playwright는 N150 SSH
alias가 현재 환경에서 해석되지 않아 Windows fallback runner로 `admin-grafana.e2e.ts` 2건
통과와 `admin-live-grafana.live.ts` env-gated skip 1건을 확인했다. 다음 작업은 T-254 Admin
live e2e matrix v0.2.0 확장이다.

## 2026-06-28 (codex) — T-252 Backup/restore live UI e2e

`/admin/backup` snapshot 목록에 filename/snapshot id/checksum 검색, `verified`/`available`
status filter, visible count를 추가했다. production live에서 restore-hotswap을 실수로 누르지
않도록 Web 빌드타임 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1`이 없으면 Restore 버튼이
비활성화된다. 서버 측 `PINVI_RESTORE_HOTSWAP_EXECUTE` 가드는 그대로 유지한다.

Playwright는 세 층으로 분리했다. 기존 mock e2e는 list/filter/sort/manual trigger/empty/error와
restore disabled를 확인한다. `admin-live-backup.live.ts`는 N150/live read-only에서 snapshot 목록,
sort/filter, empty state, restore 잠금, raw backup path/secret pattern 미노출을 검증하고
backup POST가 발생하면 실패한다. `admin-backup-live-mutating.live.ts`는
`PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`에서만 staging snapshot 1회 생성,
`backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을 확인한다.

Linux에서 Web typecheck/lint, live catalog/skip, compose/shell 검증을 수행했다. N150 SSH alias는
현재 Linux 환경에서 해석되지 않아 실제 N150 live read-only/staging mutating run은 수행하지
못했고, mock Playwright는 Windows fallback runner에서 통과했다. 다음 작업은 T-253
Prometheus/Grafana 운영 가시화 게이트다.

## 2026-06-28 (codex) — T-251 Restore staging drill

Restore staging drill 진입점으로 `scripts/restore-staging-drill.sh`를 추가했다. 스크립트는
`PINVI_RESTORE_STAGING_DATABASE_URL`이 없으면 복구를 시작하지 않고, snapshot checksum,
`pg_restore --list`, `scripts/restore-db.sh`, staging DB health row count(`users`, `trips`,
`admin_audit_log`), admin audit chain link, rollback rehearsal 결과를
`DRILL_PHASE`/`DRILL_EVIDENCE`로 출력한다. host 절대경로는 `backup://<filename>`으로만 기록한다.

Rollback rehearsal은 기본 `precheck` guard와 선택 `drain` 모드를 지원한다. `drain`은 임시
restore schema까지 복구한 뒤 drain 미설정 실패를 유도하고 기존 `app` schema OID가 유지되는지
확인한 다음 임시 schema를 drop한다. `scripts/backup-db.sh`, `restore-db.sh`,
`restore-hotswap.sh`, `restore-staging-drill.sh`는 `.sha256` sidecar checksum 값을 실제 dump
hash와 직접 비교하도록 맞춰 snapshot을 staging 경로로 옮겨도 검증 가능하게 했다.

Linux에서 shell syntax, ruff, restore drill script unit, backup service unit을 검증했다.
N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 staging DB restore는 수행하지 못했다.
UI 변경은 없어서 Playwright는 실행하지 않았다. 다음 작업은 T-252 Backup/restore live UI e2e다.

## 2026-06-28 (codex) — T-250 Backup script / snapshot endpoint hardening

Backup script와 Admin snapshot endpoint를 보강했다. `scripts/backup-db.sh`는 schema name guard,
`PINVI_BACKUP_MIN_FREE_BYTES` disk free guard, 임시 dump 생성, sha256 sidecar 생성/검증을 수행한다.
`scripts/restore-db.sh`는 `.sha256` sidecar가 있으면 restore 전에 반드시 검증한다.

API/service는 `.sha256`이 실제 dump checksum과 일치할 때만 `status="verified"`로 표시하고,
불일치하면 `available`로 낮춘다. Admin backup/restore 응답과 audit/error message의 host 절대경로는
`backup://<filename>`으로 mask하고, DB URL credential도 mask한다. snapshot 생성 실패도
`backup.snapshot_failed` audit으로 남긴다.

Linux/WSL에서 ruff, backup service unit/API integration, strict mypy, shell syntax check를 검증했다.
UI 변경은 없어서 Playwright는 실행하지 않았다. 다음 작업은 T-251 Restore staging drill이다.

## 2026-06-28 (codex) — T-249 App-owned integrity source / known orphan fix

Pinvi app-owned integrity source를 추가했다. `app.data_integrity_violations` migration/model을
추가하고, `/admin/integrity/issues`에 `source=all|kor_travel_map|pinvi_app` filter를 붙였다.
`source=pinvi_app`는 persisted row와 Pinvi 계산 rule을 반환하고, `source=kor_travel_map`은 기존
upstream consistency issue proxy를 유지한다. `provider`/`dataset_key` filter는 upstream 전용이므로
지정 시 Pinvi app row를 제외한다.

known app issue는 broken POI feature link, invalid POI marker color, curated import source drift,
active attachment deleted target을 우선 계산한다. 기존 sort 중복 rule도 service에 포함했지만 DB
unique index가 정상 동작하는 한 일반 데이터에서는 나타나지 않는다. Pinvi app issue는 read-only로
두고, `pinvi_app:` issue action은 409 `PINVI_APP_INTEGRITY_ACTION_UNSUPPORTED`를 반환한다.

Web `/admin/integrity`는 source filter와 source column/badge를 추가했고, Pinvi app issue row는
조치 버튼 대신 read-only로 표시한다. API/admin/data-model/postgres schema 문서와 Sprint 5 추적
문서를 갱신했다.

Linux/WSL에서 ruff, API integration, strict mypy, Web/API-client/schema typecheck, Web lint,
Prettier를 검증했다. Playwright는 N150 SSH alias가 이 세션에 없어 직접 실행할 수 없었고, Windows
fallback runner에서 `admin-dedup-integrity-debug.e2e.ts` 3건이 통과했다.

다음 작업은 T-250 Backup script / snapshot endpoint hardening이다.

## 2026-06-28 (codex) — T-248 Feature detail subpages

Admin feature detail subpage를 read-only deep link로 추가했다. `GET /admin/features/{feature_id}/sources`
와 `/overrides`는 `kor-travel-map` admin detail payload에서 list만 투영하고,
`/weather-values`는 기존 feature weather card의 metrics를 Admin tab용 `items`로 반환한다. Pinvi는
`feature.*`/`provider_sync.*` 테이블을 직접 조회하지 않고, override mutation도 추가하지 않았다.

Web은 `/admin/features/{feature_id}/sources`, `/overrides`, `/weather-values` route를 추가했고,
기존 `/admin/features` detail inspector에서 세 tab으로 이동할 수 있다. mock Playwright는 direct deep
link, tab navigation, empty state, upstream error state를 확인한다. Admin live matrix에는 live weather
feature가 있을 때만 세 read-only tab route를 순회하는 guarded case를 추가했다.

Linux/WSL에서 API integration, strict mypy, Web typecheck/lint/build를 검증했다. N150 Playwright
runner는 현재 도구 컨텍스트에서 직접 사용할 수 없고 WSL Ubuntu 26.04 Chromium도 미지원이라,
mock e2e는 Windows fallback runner에서 `admin-feature-detail-subpages.e2e.ts` 1건이 통과했다.
Admin live list는 dedicated config로 6178 tests를 생성한다.

다음 작업은 T-249 App-owned integrity source / known orphan fix다.

## 2026-06-28 (codex) — T-247 Provider sync 운영 mutation 계약 정리

upstream `kor-travel-map` `openapi.json`과 router를 확인했다. provider 자체 run-now/pause/resume/reset
cursor mutation은 없고, 존재하는 운영 mutation은 import job cancel과 feature-update-request
cancel/run-now, provider refresh policy upsert다. Pinvi는 provider sync 일반 mutation을 임의로 만들지
않고, v0.2.0 범위를 import job cancel relay로 닫았다.

`POST /admin/provider-sync/import-jobs/{job_id}/cancel`을 추가했다. 권한은 `admin` 전용이고
`access_reason`은 필수다. Pinvi audit에는 `provider_import_job.cancel`을 남기며,
`kor_travel_map_reason`이 없으면 upstream reason은 `access_reason`으로 대체한다. Web
`/admin/provider-sync`는 queued/running import job에만 취소 버튼과 사유 입력 패널을 표시하고, 실패
시 row를 낙관적으로 바꾸지 않는다.

Linux/WSL에서 API unit/integration, strict mypy, Web typecheck/lint/build를 검증했다. WSL Ubuntu
26.04에서는 Playwright Chromium 설치가 미지원이라 mock e2e는 Windows fallback runner에서
`admin-etl-provider-sync.e2e.ts` 2건이 통과했다.

다음 작업은 T-248 Feature detail subpages다.

## 2026-06-28 (codex) — T-246 Debug live UI e2e 확장

`apps/web/e2e/admin-debug-live.live.ts`를 추가해 Admin debug live read-only 경로를 별도 live
suite로 고정했다. 테스트는 `/admin/debug/logs` render, sanitized polling fallback 상태,
filter query 유지, live toggle/pause, request timeline 이동, raw secret pattern 미노출을 확인한다.
운영 데이터에 matching timeline event가 없을 수 있어 summary 또는 "event 없음" alert 둘 다 정상
route render로 인정한다.

Pinvi admin client는 현재 요청의 `X-Request-Id`를 `kor-travel-map` admin/ops 호출에 전달한다.
Debug live test는 UI credential 대신 `PINVI_ADMIN_LIVE_STORAGE_STATE`도 받을 수 있어 N150에서
짧은 수명 storage state를 만들어 비밀번호 없이 실행할 수 있다.

N150에서는 브랜치 checkout을 배포해 API/Web을 재빌드·재기동하고 health를 확인했다. N150 자체
Playwright는 Ubuntu 26.04에서 Chromium 설치가 미지원이라 실행 불가했고, Windows fallback runner에서
N150 Web/API 대상 `admin-debug-live.live.ts` 1건이 통과했다.

다음 작업은 T-247 Provider sync 운영 mutation 계약 정리다.

## 2026-06-28 (codex) — T-245 Debug log polling fallback

v0.2.0 Admin debug live mode는 Loki/Promtail LogQL WebSocket 대신 sanitized polling fallback으로
닫았다. `GET /admin/debug/logs/stream/status`가 `mode="polling"`, `poll_interval_ms=5000`,
`sources=["kor_travel_map_system_logs", "kor_travel_map_api_call_logs"]`, `loki_enabled=false`,
`sse_enabled=false`를 반환한다.

Web `/admin/debug/logs`는 live toggle과 pause/resume을 제공한다. live 상태에서는 기존
`/admin/debug/logs/system`과 `/admin/debug/logs/api-calls`를 현재 filter 그대로 interval 재조회하고,
pause는 interval만 멈춘다. raw stdout/stderr, 운영 도메인/IP, secret value를 새로 노출하지 않는다.

N150 live read-only / Playwright는 T-246에서 `/admin/debug/logs`, request timeline, masking assertion과
함께 수행한다.

다음 작업은 T-246 Debug live UI e2e 확장이다.

## 2026-06-28 (codex) — T-244 Request timeline API

`GET /admin/debug/request/{request_id}`가 Pinvi request id 중심 timeline을 반환한다. 로컬 source는
`app.api_call_log`, `app.admin_audit_log`, `app.location_access_log`/outbox, `payload.request_id`가
있는 `app.email_queue`이며, upstream `kor-travel-map` sanitized system/API logs는 보조 source로만
붙는다.

응답은 source별 `ok`/`degraded`, 시간순 event, duration/status/error code/sanitized detail을
포함한다. admin audit `access_reason`/state payload, email 수신자·제목·payload·`last_error`,
위치 user id·좌표·IP hash는 노출하지 않는다. upstream 보조 source 실패는 HTTP 200
`status="partial"`로 접고, all-source not found는 404다.

Web `/admin/debug/logs`에는 request id 검색을 추가했고, `/admin/debug/request/{request_id}`는
source/event table로 timeline을 표시한다.

N150 live read-only / Playwright는 현재 브랜치가 아직 운영 배포되지 않아 수행하지 않았다.

다음 작업은 T-245 Loki/Promtail 또는 대체 log stream이다. N150 용량을 보고 Loki/Promtail과
sanitized polling/SSE 대안을 선택한다.

## 2026-06-28 (codex) — T-243 ETL live / Dagster 운영 게이트

`/admin/etl/summary`가 Pinvi Dagster `/server_info`와 `/graphql`을 읽어 live snapshot을 반환한다.
응답에는 Dagster version, repository/job/asset/schedule count, code location repository 목록,
최근 run 상태가 들어간다. GraphQL 조회 실패는 `pinvi.status=degraded`로 강등하고 static
app-owned registry와 email/Telegram/PII/location summary는 계속 반환한다. run tag 값은
Admin 응답에 싣지 않는다.

Web `/admin/etl`은 Pinvi app-owned job row마다 live/registry 상태, schedule cron/timezone,
최신 run status를 표시하고, live code location과 recent Pinvi runs 영역을 추가했다.

N150 API smoke / Playwright live는 현재 브랜치가 아직 운영 배포되지 않아 수행하지 않았다.

다음 작업은 T-244 Request timeline API다. Pinvi request id 중심 timeline과 upstream
`kor-travel-map` sanitized logs를 보조 event source로만 붙이는 경계를 유지한다.

## 2026-06-28 (codex) — T-242 Telegram system summary/outbox ETL

`pinvi_telegram_system_outbox` asset/job/schedule을 추가했다. Dagster는 15분마다
`app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped, failed,
retry exhausted, 최근 24시간 category별 retry exhausted 비율을 payload 없이 bounded metadata로
집계한다.

`/admin/etl/summary`는 같은 Telegram outbox summary를 `pinvi.telegram_outbox`로 반환하고,
Web `/admin/etl`은 due/backoff/stuck/retry exhausted, sent/skipped/failed, category별 이상률을
표시한다. 응답과 metadata에는 payload, message text, user id, chat id, token, last_error 원문을
넣지 않는다. weekly/daily 사용자 브리프 생성은 후속 `pinvi_telegram_weekly` 범위로 남겼다.

후속으로 T-243 ETL live / Dagster 운영 게이트에서 N150 Dagster code location과 app-owned job
rows, Admin ETL live UI 검증을 확장했다.

## 2026-06-28 (codex) — T-289 Linux-only 개발 환경 / ADR-051

ADR-051로 개발·git·CodeGraph는 Linux 기준, Playwright는 N150 우선 실행으로 고정했다.
ADR-024의 NTFS worktree + WSL ext4 테스트 미러 모델과 ADR-017의 Windows `git.exe`
amendment를 supersede했다.

`AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `docs/dev-environment.md`,
`docs/agent-workflow.md`, `docs/runbooks/codegraph-worktrees.md`,
`docs/agent-failure-patterns.md`, README/Sprint/task 추적 문서를 같은 기준으로 맞췄다.
현재 Codex worktree의 `.git` 포인터는 Linux `git worktree repair`로 복구했다.
`codegraph`가 처음에는 `/mnt/c/...` Windows shim으로 잡혔지만, `npm install -g --prefix
$HOME/.local @colbymchenry/codegraph`로 Linux native `~/.local/bin/codegraph`를 설치하고
`codegraph status && codegraph sync`를 통과시켰다.

PR #274(T-241)는 CI success와 inline review thread 0건을 확인한 뒤 squash merge했다.
다음 작업은 T-242 Telegram system summary/outbox ETL이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-241 `pinvi_location_log_archive` Dagster job

`pinvi_location_log_archive` asset/job/schedule을 추가했다. Dagster는 매일 KST 04:30
`app.location_access_log`의 6개월 초과 archive 후보, archive tail과 active head 사이의
hash-chain bridge 상태, 미처리 `location_audit_outbox` blocker, purpose별 후보 수를 dry-run
metadata로 집계한다.

`/admin/etl/summary`는 같은 archive dry-run summary를 `pinvi.location_log_archive`로 반환하고,
Web `/admin/etl`은 후보 수, active row 수, pending outbox, chain bridge 일치 여부를 표시한다.
응답과 metadata에는 user id, raw coordinate, IP 원문을 넣지 않는다. 실제 archive/delete/anonymize
실행은 T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

다음 작업은 T-242 Telegram system summary/outbox ETL이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-240 `pinvi_pii_retention` Dagster job

`pinvi_pii_retention` asset/job/schedule을 추가했다. Dagster는 매일 KST 04:15 `app` schema의
삭제 계정 PII, OAuth identity, 만료 verification/reset token, 오래된 session, 만료 OAuth transient
row, 6개월 초과 location/admin audit PII 후보를 dry-run metadata로 집계한다.

`/admin/etl/summary`는 같은 retention dry-run summary를 `pinvi.pii_retention`으로 반환하고,
Web `/admin/etl`은 전체 후보, 삭제 계정, session, token, location log, 권한 계정 제외 수를 표시한다.
응답과 metadata에는 user id, email, token hash, raw coordinate를 넣지 않는다. 실제
delete/anonymize/archive 실행은 T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

다음 작업은 T-241 `pinvi_location_log_archive` Dagster job이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-239 `pinvi_email_outbox` Dagster job

`pinvi_email_outbox` asset/job/schedule을 추가했다. Dagster는 15분마다 `app.email_queue`의
pending due/backoff/stuck, failed/bounced/complained, retry exhausted, 최근 24시간 template별
실패율을 PII 없이 bounded metadata로 집계한다. 실제 발송 source of truth는 기존 FastAPI lifespan
`email_outbox_worker_lifespan`으로 유지한다.

`/admin/etl/summary`는 같은 email outbox summary를 `pinvi.email_outbox`로 반환하고, Web
`/admin/etl`은 due/backoff/stuck/retry exhausted와 template 실패율을 표시한다. hard-bounce/complaint
suppression 집행과 domain verification 운영 체크는 T-257/T-277 범위로 남겼다.

다음 작업은 T-240 `pinvi_pii_retention` Dagster job이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-238 Pinvi app-owned ETL 표준 / ADR

ADR-050으로 Pinvi `apps/etl` app-owned Dagster job 표준을 고정했다. Pinvi ETL은 `app`
schema 소유 job만 담고, feature/provider 적재와 `feature` / `provider_sync` schema 작업은
`kor-travel-map` 책임으로 유지한다.

신규 job 표준은 import-time side effect 금지, `Asia/Seoul` schedule, transient failure
기본 retry/backoff, idempotency key 또는 queue claim, bounded run metadata/log, retry exhausted
failure의 `run_failure_sensor` 기반 Sentry/Telegram outbox 알림, destructive job dry-run gate다.
ETL runbook과 Dagster bridge 문서, Sprint 5 DoD, AGENTS/CLAUDE 진입 요약을 같은 기준으로 맞췄다.

검증은 Windows worktree에서 `git diff --check`로 수행했다. PR 생성 후 사용자 지시대로 Windows
Playwright e2e와 GitHub checks를 확인하고 merge한다.

다음 작업은 T-239 `pinvi_email_outbox` Dagster job이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-237 WebSocket backend hardening / metrics

Trip WebSocket backend에 close code 구조화 로그와 Prometheus gauge/counter를 추가했다.
`pinvi_api_ws_active_connections`, connection accept/reject, close code/reason, client message,
broadcast result, send timeout/error metric을 bounded label로 기록한다. `trip_id`/`user_id`는
metric label에는 넣지 않고 close 구조화 로그에만 남긴다.

회귀 테스트는 broker 단위 metric/stale-removal/cap rejection, WebSocket permission/rate-limit/
connection-cap/heartbeat-timeout close metric까지 보강했다. 문서의 rate-limit slot 반환 설명도
T-185/T-236a 구현과 맞게 close grace 동안 slot을 유지하는 것으로 정정했다.

검증은 WSL ext4 미러에서 수행했다. `ruff check` targeted, `ruff format --check` targeted,
`mypy --strict app`, `pytest -q tests/unit/test_realtime_broker.py`, `pytest -q
tests/integration/test_ws_trip_channel.py`가 통과했다.

다음 작업은 T-238 Pinvi app-owned ETL 표준 / ADR이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-236a WebSocket multi-client N150 live e2e drill

N150 live mutating Playwright로 실제 WebSocket broadcast와 reconnect 뒤 Trip snapshot reload를
검증했다. 테스트는 public Web/API를 대상으로 임시 verified 사용자를 만들고, 두 브라우저 컨텍스트가
같은 Trip을 연 상태에서 API mutation broadcast와 reconnect 이후 추가 mutation reload를 확인한다.

드릴 중 운영 drift 2건을 발견해 함께 고쳤다. 먼저 `pinvi-api`가 `uvicorn --workers 2`로 떠 있어
process-local realtime broker가 worker 간 broadcast를 전달하지 못했다. Pinvi Docker/compose 기본값을
`PINVI_API_WORKERS=1`로 맞추고, `kor-travel-docker-manager` PR #44도 같은 운영 compose 계약으로
머지했다. 다음으로 public Web origin의 CORS preflight가 로컬 origin 고정값 때문에 400으로 떨어져,
docker-manager PR #45에서 `PINVI_PUBLIC_API_URL`과 `PINVI_CORS_ALLOWED_ORIGINS`를 gitignore `.env`
주입값으로 분리했다.

검증은 WSL ext4 미러와 Windows Playwright runner에서 수행했다. `npm -w @pinvi/web run typecheck`,
`npm -w @pinvi/web run lint`, Windows `npm -w @pinvi/web run test:e2e:live-mutating -- --workers=1`
1건이 통과했다. 운영 `ktdctl pinvi --build`는 알려진 geo source empty check 때문에 exit code 1로
끝나지만, Pinvi API/Web 컨테이너는 재생성 후 healthy이며 live e2e가 통과했다.

다음 작업은 T-237 WebSocket backend hardening / metrics다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-236 WebSocket multi-client collaboration e2e

Trip 상세 협업 mock e2e를 2~5 브라우저 컨텍스트 기준으로 확장했다. 같은 여행을 보는 두 컨텍스트가
`presence.update`와 `trip.updated` broadcast를 반영하는지, WebSocket 재연결 뒤 `poi.updated`
broadcast가 최신 HTTP snapshot reload로 이어지는지, 5개 컨텍스트 presence fan-out와 offline cleanup이
상태 문구에 반영되는지 검증한다.

테스트 Fake WebSocket은 React Strict Mode 재마운트와 재연결에서 닫힌 이전 socket이 배열에 남아도
마지막 active socket을 기준으로 서버 이벤트를 넣도록 정리했다. 이로써 dev server와 실제 브라우저
runner 조합에서 재연결 케이스가 flake 없이 통과했다.

검증은 WSL ext4 미러와 Windows Playwright runner에서 수행했다. `npm -w @pinvi/web run typecheck`,
`npm -w @pinvi/web run lint`, Windows `PLAYWRIGHT_BASE_URL=http://localhost:12805 npm -w @pinvi/web run test:e2e -- trip-collab.e2e.ts --workers=1`
5건이 통과했다.

기존 T-236 설명의 N150 staging live 검증은 별도 운영 drill 성격이 커서 T-236a로 분리했다. 다음
작업은 T-236a WebSocket multi-client N150 live e2e drill이다. 신규 Task 진입 전 최근 2일 PR 리뷰
코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-288 Task 문서 분리 정책 반영

`kor-travel-map`의 task 문서화 정책을 확인했다. 해당 저장소는 열린 task를 `docs/tasks.md`,
완료·아카이브를 `docs/tasks-done.md`, 현재 진척과 "다음 한 작업"을 `docs/resume.md`로 분리한다.
Pinvi도 같은 방식으로 `docs/tasks-rule.md`와 `docs/tasks-done.md`를 추가하고, 신규 task 진입 전
최근 2일 PR 리뷰 코멘트 확인과 task 분리 기준을 문서화했다.

최근 2일 PR 확인 결과 inline review comment는 0건이었다. 사람 top-level 리뷰 코멘트는 #238과
#264의 운영·법무 gap 리뷰 2건이며, #264에서 T-256~T-286으로 이미 반영하고 답변했다. 신규 차단
코멘트는 없다.

기존 `tasks.md`의 legacy 완료 이력 전체 이관은 `T-288-legacy-task-archive`로 분리했다. 다음 작업은
T-236 WebSocket multi-client collaboration e2e다.

## 2026-06-27 (codex) — T-235 Optimistic lock / conflict dialog

Trip 상세 화면의 Trip/POI 편집 mutation이 `409 VERSION_CONFLICT`를 단순 오류로 표시하지 않고,
최신 TripView를 다시 불러온 뒤 conflict dialog를 연다. 다이얼로그는 변경 필드별 서버 값/내 값을
비교하고, 선택한 내 값만 최신 version으로 재시도하거나 내 값 전체 LWW 덮어쓰기를 수행한다.

POI 편집기는 저장 요청 결과를 기다린 뒤 성공 시에만 닫도록 바꿔 충돌 시 사용자의 입력 draft를
유지한다. 서버 409 응답은 현재 row를 아직 details로 내려주지 않으므로, 이번 UI는 충돌 직후 상세
재조회 결과를 server value로 사용한다. Day rename/delete API에는 `If-Match`가 없어 T-287
follow-up으로 분리했다.

검증은 WSL ext4 미러와 Windows Playwright runner에서 수행했다. api-client/web/mobile typecheck,
Web lint/build, `conflictResolution.test.ts`, API 409 회귀 2건, Windows Playwright
`trip-conflict.e2e.ts` 2건이 통과했다.

다음 작업은 T-236 WebSocket multi-client collaboration e2e다.

## 2026-06-27 (codex) — T-234 WebSocket client invalidation / auth close handling

`TripRealtimeClient`가 WebSocket close code/reason을 분류하고 상태로 노출한다. `4401`은
`authApi.refresh()` 성공 후 즉시 재연결하고, `4403`은 재연결 없이 권한 상실 안내와 여행 목록 CTA를
표시한다. `4408`/`4429`는 연결 제한/rate-limit 상태와 backoff 안내를 표시한다.

`queryKeys`에 realtime domain event → TanStack Query invalidation key helper를 추가했다.
POI/day/trip 계열은 trip detail/list prefix, comment 계열은 comments key로 매핑된다. 현재 사용자
Trip 상세는 raw fetch 기반이므로 helper로 reload 대상 event를 판정하고, in-flight reload promise를
공유해 HTTP mutation reload와 WebSocket event reload가 같은 tick에 겹쳐도 1회만 요청한다.

검증은 WSL ext4 미러와 Windows Playwright runner에서 수행했다. api-client/web/mobile typecheck,
Web lint, Web build, `tripRealtimeClient.test.ts` Vitest 8건이 통과했다. Windows Playwright는 WSL
Next dev server를 대상으로 `trip-detail.e2e.ts` 3건(기본 렌더, 4403 권한 상실, 4429 backoff)을
통과했다.

다음 작업은 T-235 Optimistic lock / conflict dialog다.

## 2026-06-27 (codex) — T-233 리뷰 코멘트 반영 / legal-ops Task 보강

PR #264 리뷰 코멘트를 반영해 Sprint 5/6 상세 계획을 보강했다. Sprint 5에는 review gap
crosswalk(T-256), email deliverability/provider tracking preflight(T-257), Sprint 6 legal/ops
prep gate(T-258)를 추가하고 release candidate gate를 T-259로 조정했다.

Sprint 6에는 PIPA incident console, retention 실행/dashboard, email deliverability/suppression,
DSR intake, content moderation, RBAC grant/revoke, user lifecycle admin action, rate-limit/abuse
surface, security threat model/penetration pass, mobile v1.0 scope gate, AI companion v1.0 scope gate,
cross-track #238/#264 gap closure를 T-275~T-286으로 추가했다. `apps/mobile`은 v1.0 Web/API/Admin
출시 필수 범위에서 제외하고 Sprint M-1 별도 gate로 관리하며, user-facing AI companion은 v1.0에
포함하지 않는다고 명시했다.

PR #264 merge 후 T-234를 완료했다. 다음은 T-235 Optimistic lock / conflict dialog다.

## 2026-06-27 (codex) — T-233 Sprint 5/6 상세 Task 계획

`docs/execplan/sprint5-v020-release-plan.md`를 새로 작성해 Sprint 5 `v0.2.0` 잔여 작업을
T-234~T-259로 쪼갰다. WebSocket 후속, app-owned ETL job, request timeline/log stream,
provider sync 계약, feature detail, app integrity, backup/restore, Grafana, Admin live e2e,
사용자/Admin 지도뷰 marker palette·색상 parity, release gate를 포함한다. API 테스트 케이스와
mock/live UI e2e 카탈로그도 함께 정리했다.

Sprint 6 `v1.0.0` 후속 초안은 T-260~T-286으로 넣었다. OR-Tools 스마트 정렬, category mapping
override, Admin notice plan, MCP 운영 실증, backup hot-swap, geofencing, LBS/법무, 성능/보안,
Odroid+N150 병행 운영, AI companion 분리, v1.0 live gate와 release가 포함된다. ARM image와
GHCR 배포는 제외하고 노드 로컬 checkout/build/smoke 기준으로 정리했다.

리뷰 반영 후 PR merge를 진행하고 T-234부터 시작한다.

## 2026-06-27 (codex) — T-232 Trip WebSocket frontend client / presence 첫 연결

Trip 상세 사용자 화면에 Sprint 5 WebSocket 첫 수직 슬라이스를 연결했다. `@pinvi/api-client`는
`TripRealtimeClient`와 `tripWebSocketUrl`을 export하며, heartbeat, `ping`→`pong`, exponential
backoff reconnect, 테스트용 WebSocket constructor 주입을 지원한다. `TripDetail`은
`WS /ws/trips/{trip_id}`에 접속해 presence summary를 표시하고, POI/day/trip domain event를 짧게
debounce한 뒤 상세 데이터를 reload한다.

검증은 로컬 WSL ext4 미러에서 수행했다. `npm -w @pinvi/api-client run typecheck`,
`npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run test -- tripRealtimeClient.test.ts`,
`npm -w @pinvi/web run lint`, `npm -w @pinvi/mobile run typecheck`가 통과했다. 다음
WebSocket 후속은 TanStack Query invalidation, 공유 presence store, 401 close token refresh,
conflict dialog 구현이다.

## 2026-06-27 (codex) — T-231 v0.2.0 후보 범위 정리

`Unreleased`에 쌓인 post-v0.1.0 Admin/운영 보강을 Sprint 5 / `v0.2.0` 후보 범위로 정리했다.
이미 main에 들어온 것은 Admin 운영 화면, ETL/provider sync read view, Grafana prod URL,
dashboard/system 운영 지표, dedup/integrity action 일부, 파일/아바타/quota/operation 기능이다.

남은 `v0.2.0` 후보 gate는 WebSocket 협업, Pinvi `app` schema 소유 ETL 추가 job,
Loki/request timeline, backup/restore 1차 스테이징 훈련, release notes로 분리했다.
`CHANGELOG.md`의 `Unreleased` 제목을 `v0.2.0` 후보로 바꾸고, Sprint 5 문서와 tasks를 같은 기준으로
맞췄다. sidebar 설명도 기본 expanded + 선택적 compact icon-only 기준으로 정정했다.

## 2026-06-27 (codex) — T-230 v0.1.0 릴리즈 상태 정합화

`v0.1.0` tag와 GitHub Release가 이미 존재함을 확인했다. Release는 2026-06-13에 게시됐고,
tag는 `2f8da02345581fd3065e9d818352bc187f65b3a9`를 가리킨다. 현재 main
`d35f49e1faafa61380d9c2c0e2d6a1cb36d29108`은 post-v0.1.0 변경이므로 같은 tag를 다시 만들지
않는다.

`CHANGELOG.md`, `docs/tasks.md`, `docs/sprints/README.md`, `docs/sprints/SPRINT-4.md`,
`AGENTS.md`, `CLAUDE.md`를 실제 상태에 맞춰 정리했다. `Unreleased` 절은 v0.1.0 이후 변경으로
남기고, 다음 제품 작업은 v0.2.0 범위 정리로 둔다.

검증은 GitHub Release/tag 조회, main 최근 CI 조회, N150 smoke로 수행했다. 최신 N150 checkout은
`d35f49e`이며 API `/health`, DB health, Web `/admin/login`, Dagster `/server_info`,
`kor-travel-map` `/health`가 모두 200을 반환했다. Odroid 실제 smoke와 backup/restore 복구 훈련은
T-108 설명대로 Sprint 6 운영 게이트로 남긴다.

## 2026-06-27 (codex) — T-229 Admin 완료 감사 / 추적 문서 최신화

Admin 보강 프로그램의 코드 구현 상태를 다시 감사했다. 사용자 명시 요구사항 1~~14번은
T-216~~T-225, T-218, T-220~T-222, T-228로 해소됐고, T-227 integrity issue action까지 PR
merge와 N150 배포를 완료했다.

이번 Task는 기능 추가가 아니라 추적 문서 정합화다. `docs/execplan/admin-console-gap-plan.md`의
초기 placeholder/gap 표현을 현재 완료 상태로 갱신하고, 명시 요구사항별 완료 Task와 API/UI/e2e
증거를 표로 남겼다. `docs/tasks.md`에서는 Admin 후속 항목을 T-207~T-229 완료 상태로 정리하고,
T-216/T-228 sidebar 표현을 기본 expanded + 선택적 compact icon-only 토글로 통일했다.

검증은 문서 diff 중심으로 수행했다. 후속 T-230에서 기존 `v0.1.0` tag/Release 존재를 확인하고
릴리즈 상태 문서를 실제 상태로 정리했다.

## 2026-06-27 (codex) — T-227 Integrity issue status mutation

`kor-travel-map` 최신 main을 확인한 결과 `/v1/ops/consistency/*`는 read-only지만, 상태 조치
계약은 이미 `PATCH /v1/admin/issues/{issue_id}`로 제공되고 있었다. 따라서 upstream 신규 PR 없이
Pinvi가 기존 admin issue 계약의 `resolve` / `ignore` / `reopen`만 relay하도록 구현했다.

Pinvi API는 `POST /admin/integrity/issues/{issue_id}/action`을 추가했다. admin 전용 endpoint가
`access_reason`과 optional `kor_travel_map_reason`을 검증하고, upstream 성공 후
`integrity_issue.action` audit을 기록한다. Web `/admin/integrity`는 issue table에 해결/무시/재오픈
버튼과 reason dialog, 성공 notice, 목록 invalidate/refetch를 제공한다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. WSL에서 admin client unit
21건, admin dedup/integrity/debug integration 7건, ruff, mypy, Web/type package typecheck, 표준
Web lint가 통과했다. Windows Playwright는 WSL Next server(12805)를 대상으로
`admin-dedup-integrity-debug.e2e.ts --grep "정합성 페이지"` 1건이 통과했다.

후속: PR #259를 merge했고 N150 배포와 API/Web/Dagster/upstream smoke를 완료했다.

## 2026-06-27 (codex) — T-228 Admin sidebar 확장/축소 토글 정정

사용자 정정에 맞춰 Admin 좌측 메뉴를 아이콘 전용으로 고정하지 않고, 기본 expanded 상태에서
아이콘과 메뉴 라벨을 함께 표시하도록 되돌렸다. 데스크톱에서는 sidebar toggle button으로 compact
icon-only 상태와 expanded 상태를 전환할 수 있고, 선호 상태는 browser localStorage에 저장한다.

기존 active route 판정과 `admin-nav-*` test id는 유지했다. `/admin/trips/{trip_id}` 상세 e2e에는
sidebar 기본 expanded, toggle 후 collapsed, 다시 expanded 상태를 확인하는 assertion을 추가했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. WSL에서 Web typecheck와 lint가
통과했고, Windows Playwright는 WSL dev server를 대상으로 `admin-trips.e2e.ts`의 여행 상세 케이스
1건이 통과했다.

후속: PR merge와 N150 배포를 완료했다. 이후 T-229 완료 감사로 추적 문서를 정리했다.

## 2026-06-27 (codex) — T-215 Admin live e2e 확장 + N150 묶음 게이트

Admin live Playwright gate를 최신 구현 상태에 맞게 보강하고 N150에서 묶음 검증을 완료했다.
전체 catalog는 6176건이며, 실제 UI matrix 6173건과 로그인 검증 2건, catalog sanity 1건으로
구성된다. 이번 gate는 운영 부하를 낮추기 위해 worker 1개와 throttle을 유지하고,
`PINVI_ADMIN_LIVE_CASE_LIMIT=2000`으로 로그인 2건 + catalog 1건 + matrix 2000건, 총 2003건을
실행해 모두 통과했다(3.1h).

테스트 하네스는 운영 환경에서 드러난 세 가지 정책을 반영했다. `provider-sync`, `integrity`,
`debug/logs`처럼 한 route에 여러 AdminTable이 있는 화면은 첫 `admin-table-scroll`을 ready 기준으로
삼는다. `/admin/system`은 AdminTable route가 아니라 `admin-system-containers` ready marker로
검증하고 정렬 matrix에서 제외한다. 긴 run 도중 admin 세션이 만료되면 5분 기본 auth refresh와
route/navigation 직후 재로그인 복귀로 원래 route를 다시 검증한다.

검증은 Windows Playwright runner와 WSL ext4 미러에서 수행했다. N150 실행 전후 smoke에서 API
`/health`, `/health/db`, Web `/admin/login`, Dagster, upstream `kor-travel-map` health, Pinvi
컨테이너 healthy 상태를 확인했다. Windows에서 `npm run test:e2e:admin-live:list`는
`6176 tests in 1 file`을 반환했다. WSL ext4 미러에서 Web Prettier check, Web typecheck,
Web lint가 통과했다.

다음: T-215 PR을 만들고 merge한 뒤 N150에 한 번 더 배포한다. 그 후 v0.1.0 릴리즈 정리로
진행한다. T-227 integrity issue status/fix mutation은 upstream `kor-travel-map` mutation 계약이
추가될 때까지 보류한다.

## 2026-06-27 (codex) — T-222 System view Docker / 의존 API 상태

Admin 시스템 운영 화면을 추가했다. Pinvi API는 기존 `/admin/system/summary`를 유지하고,
신규 `GET /admin/system/detail`에서 의존 API health와 Docker collector 상태, container 목록을
함께 반환한다. Docker container 응답은 `container_id`, `name`, `image`, `state`, `status`,
`health`, compose project/service만 포함하고 raw Docker labels/env, 운영 도메인, secret은 노출하지
않는다.

Docker socket은 compose에 기본 mount하지 않는다. `PINVI_DOCKER_SOCKET_PATH`가 존재하지 않거나
권한이 없으면 `/admin/system/detail`은 실패하지 않고 `docker.status=unknown|down`과 빈
`containers`로 강등한다. 운영에서 실제 container 수집을 켜려면 별도 안전 검토 후 host-local
override로 socket 접근을 부여해야 한다.

Web `/admin/system`은 의존 API 상태 카드와 Docker collector 상태, container table을 표시한다.
Admin sidebar의 시스템 운영 그룹에 새 메뉴를 추가했고, live matrix route 목록에도 포함했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff format/check,
앱 코드 mypy, `test_admin_system_summary_api.py` 3건, Web Prettier check, typecheck, lint,
Vitest 27건, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-priority3.e2e.ts` 시스템 화면 케이스 1건이 통과했다.

다음: T-222 PR을 만들고 merge한 뒤 T-215 Admin live e2e 확장 + N150 묶음 게이트로 진행한다.

## 2026-06-27 (codex) — T-221 Dashboard 운영 현황 그래프 / 부하 / 용량

Admin `/admin` 대시보드의 운영 현황을 실제 지표 기반으로 확장했다. Pinvi API
`GET /admin/stats/overview`는 생성 시각, API 실패율, API latency P95, 최근 24시간 hourly
series, 서버 load average, 첨부 저장소 사용량, 전역/사용자 quota, 백업 경로 기준 디스크 사용량을
반환한다. 응답에는 raw 운영 경로, 운영 도메인, secret을 넣지 않는다.

Web 대시보드는 기존 system status와 통계 카드 위에 API 호출/실패, 가입/여행 생성 막대 그래프,
서버 부하, 디스크 사용률, 첨부 저장소 사용량/한도 요약을 표시한다. Docker/container 상세 상태는
T-222 System view에서 별도 화면으로 다룬다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff check,
앱 코드 mypy, `test_admin_priority3_api.py` 3건, Web Prettier check, typecheck, lint, Vitest 27건,
Web production build가 통과했다. 테스트 파일까지 포함한 mypy는 기존 fixture 인자 타입 미기재
패턴에서 실패해 앱 코드 대상으로 범위를 좁혀 확인했다. Playwright는 Windows에서 실행했고,
WSL Next 서버(12805)를 띄워 `admin-priority3.e2e.ts` 대시보드 케이스 1건이 통과했다.

다음: T-221 PR을 만들고 merge한 뒤 T-222 System view Docker / 의존 API 상태로 진행한다.

## 2026-06-27 (codex) — T-218 prod Grafana 주소 반영

Admin `/admin/grafana`의 prod public URL 주입 경로를 정리했다. Web Docker build/runtime stage가
`NEXT_PUBLIC_GRAFANA_URL`, `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`를 받도록 했고,
`infra/docker-compose.app.yml`의 app-web build args도 같은 값을 전달한다. Grafana 컨테이너는
`GF_SERVER_ROOT_URL`을 `NEXT_PUBLIC_GRAFANA_URL`과 맞춰 reverse proxy 뒤 embed/redirect origin이
같아지도록 했다.

실제 운영 도메인은 tracked 파일에 넣지 않았다. `infra/.env.prod.example`과 runbook에는
`grafana.example.com` placeholder만 추가했고, 실제 값은 gitignore된 `infra/.env.prod`에서만
다루도록 문서화했다. `/admin/grafana` URL 조합 로직은 `apps/web/lib/admin/grafana.ts`로 분리하고
prod origin/path 조합과 fallback 단위 테스트를 추가했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. Web Vitest 27건,
Web typecheck, Web lint, Web production build, compose config parse, Prettier check가 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워 `admin-grafana.e2e.ts` 1건과
admin-live catalog assertion 1건이 통과했다. PR merge 후 N150에 배포해 API/Web/Dagster/Grafana
smoke를 완료했다.

후속: T-218 PR은 merge됐고, T-221 Dashboard 운영 현황 그래프/부하/용량 상세보기를 완료했다.

## 2026-06-27 (codex) — T-214 Seed / reset dev-only 안전장치

Admin `/admin/seed`와 `/admin/reset`을 placeholder에서 dev/staging 전용 dry-run 화면으로 교체했다.
Pinvi API는 `GET /admin/seed/scenarios`, `POST /admin/seed/scenarios/{scenario_key}`,
`GET /admin/reset/status`, `POST /admin/reset`를 제공한다. production에서는 router include를 하지 않고,
endpoint guard도 404를 반환한다.

실제 DB reset/seed 실행은 노출하지 않았다. dev/staging route는 `dry_run=true`만 지원하고,
`false`는 `422 DRY_RUN_ONLY`로 거절한다. seed는 scenario별 `RUN <scenario_key>`, reset은 `RESET`
확인 문구와 `access_reason`을 요구한다. 성공한 dry-run은 `dev_seed.dry_run` 또는
`dev_reset.dry_run` audit을 남긴다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff format check,
ruff check, mypy, `test_admin_seed_reset_api.py` 4건, schemas/api-client typecheck, Web typecheck,
Web lint, schemas Vitest, Web production build가 통과했다. Playwright는 Windows에서 실행했고,
WSL Next 서버(12805)를 띄워 `admin-seed-reset.e2e.ts` 3건과 admin-live catalog assertion 1건이
통과했다. N150 live는 T-215 묶음 게이트에서 수행한다.

다음: T-214 PR을 만들고 merge한 뒤 T-218 prod Grafana 주소 반영으로 진행한다.

## 2026-06-27 (codex) — T-213 Category mapping 운영 뷰

Category mapping source of truth를 `kor-travel-map` `/v1/categories`로 결정했다. Pinvi는 category
taxonomy/`maki_icon`을 자체 DB에 저장하지 않고, 16색 마커 팔레트 fallback과 drift만 운영 화면에서
확인한다.

Pinvi API는 `GET /admin/category-mappings`를 추가했다. `include_counts`, `active_only`를 upstream에
전달하고, `q`는 code/label/path/tier/icon 로컬 필터로 적용한다. 응답은
`source_of_truth`, `mode=read_only`, active/inactive/filtered count, `db_feature_total`,
category item의 tier/db count 필드를 포함한다.

Web `/admin/category-mapping`은 placeholder에서 실제 table route로 바뀌었다. summary, 검색,
active/count filter, marker swatch preview, fallback/icon drift 표시, JSON export 초안을 제공한다.
PUT/import와 Pinvi-owned override table은 별도 ADR/migration이 필요한 후속으로 남겼다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff format check,
mypy, `test_admin_category_mappings_api.py` 2건, schemas/api-client/web typecheck, Web lint,
schemas Vitest, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-category-mapping.e2e.ts` 1건과 admin-live catalog assertion 1건이
통과했다. N150 live는 T-215 묶음 게이트에서 수행한다.

다음: T-213 PR을 만들고 merge한 뒤 T-214 Seed / reset dev-only 안전장치와 운영 비활성화로
진행한다.

## 2026-06-27 (codex) — T-226 Dedup verdict mutation

Admin `/admin/dedup-review` detail panel에서 pending dedup 후보를 직접 판정할 수 있게 했다.
Pinvi API는 `POST /admin/dedup-review/{review_id}/verdict`를 제공하고, `kor-travel-map`
`PATCH /v1/admin/dedup-reviews/{review_id}`로 relay한다. 요청은 `decision`, `access_reason`,
선택 `kor_travel_map_reason`, `decision=merged`일 때 필수 `master_feature_id`를 검증한다.
성공 시 `dedup_review.decide` audit을 같은 transaction에서 남기고, `X-Request-Id` UUID를 보존한다.

`kor-travel-map` 최신 OpenAPI를 확인했을 때 consistency issue/report 경로는 GET-only라,
integrity status/fix mutation은 Pinvi 단독 상태로 만들지 않고 T-227로 분리했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff format check,
mypy, focused pytest 26건, schemas/api-client/web typecheck, Web lint, schemas Vitest,
Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-dedup-integrity-debug.e2e.ts` 3건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 기능 묶음 게이트(T-215)에서 수행한다.

후속: T-226 PR은 merge됐고, T-213에서 category mapping 운영 뷰를 진행했다. T-227은 upstream
integrity mutation 계약이 추가되면 착수한다.

## 2026-06-27 (codex) — T-212 Dedup review / integrity / debug logs 운영 화면

Admin `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs`를 placeholder에서 실제
read-only 운영 조회 화면으로 교체했다. Pinvi API는 `GET /admin/dedup-review`,
`GET /admin/integrity/issues`, `GET /admin/integrity/reports`,
`GET /admin/debug/logs/system`, `GET /admin/debug/logs/api-calls`를 제공하고,
`kor-travel-map` `/v1/admin/dedup-reviews`, `/v1/ops/consistency/*`,
`/v1/ops/system-logs`, `/v1/ops/api-call-logs`를 서비스 토큰으로 proxy한다.

Web은 dedup 후보 status/search/min score 필터와 feature A/B detail panel, 정합성 issue/report
필터 table, sanitized system/API log 필터 table을 제공한다. provider sync와 새 ops route의 upstream
error mapping은 공통 helper로 합쳤다. dedup verdict와 integrity status/fix mutation은
reason/audit/idempotency/kill-switch 기준이 필요해 T-226으로 분리했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff, mypy,
admin ops focused pytest 28건, schemas/api-client/web typecheck, Web lint, schemas Vitest,
Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-dedup-integrity-debug.e2e.ts` 3건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 기능 묶음 게이트(T-215)에서 수행한다.

후속: T-212 PR은 merge됐고, T-226에서 dedup verdict mutation을 완료했다.

## 2026-06-27 (codex) — T-220 ETL / provider sync / Dagster 운영 화면

Admin `/admin/etl`과 `/admin/provider-sync`를 placeholder에서 실제 운영 조회 화면으로 교체했다.
Pinvi API는 `GET /admin/etl/summary`, `GET /admin/provider-sync`,
`GET /admin/provider-sync/import-jobs`를 제공한다. Pinvi app-owned ETL registry는 현재 실제 Dagster
정의에 맞춰 `pinvi_kasi_special_days`, `kasi_special_days_job`,
`kasi_poi_rise_set_job`, `kasi_special_days_schedule`을 노출하고, feature/provider ETL 상태는
`kor-travel-map` `/v1/ops/dagster/summary`, `/v1/ops/metrics`, `/v1/ops/providers`,
`/v1/ops/import-jobs`를 proxy한다.

Web `/admin/etl`은 Pinvi Dagster 상태, asset/job/schedule 목록, `kor-travel-map` Dagster counts,
recent runs, provider import job status filter/table을 표시한다. Web `/admin/provider-sync`는
provider/dataset key 검색과 import job status filter/table을 제공한다. upstream 일부 장애는
ETL summary 전체를 실패시키지 않고 `kor_travel_map.status=degraded|down`과 `errors[]`로 강등한다.
run-now/cancel mutation은 reason/audit/idempotency/kill-switch 기준이 필요해 후속 Task로 유지했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API `ruff check`, mypy,
admin ops focused pytest 22건, schemas/api-client/web typecheck, Web lint, schemas Vitest,
Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-etl-provider-sync.e2e.ts` 2건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 기능 묶음 게이트(T-215)에서 수행한다.

다음: T-220 PR을 만들고 merge한 뒤 T-212 Dedup review / integrity / debug logs 운영 화면으로
진행한다.

## 2026-06-27 (codex) — T-210 Pinvi feature request / upstream change request 운영 통합

Admin `/admin/features/change-requests`를 placeholder에서 실제 운영 화면으로 교체했다. Pinvi API는
`kor-travel-map` `GET /v1/admin/features/change-requests`와 `POST .../{request_id}/approve|reject`
를 proxy하고, mutation 성공 후 `feature_change_request.approve|reject` audit을 남긴다.
상태 충돌 409는 `INVALID_STATE`로 보존하고, `LOCK_BUSY` 계열 409만 retry/rate-limit로 다룬다.

Web은 변경 요청 큐를 상태/액션/검색 필터, table, detail payload inspector, reason 입력,
approve/reject action으로 운영할 수 있게 했다. mutation은 optimistic update를 적용하고 실패 시
이전 list 상태로 rollback한다. 기존 `/admin/feature-requests` 화면은 upstream `request_id`가
저장된 제안에서 변경 요청 큐로 이동하는 링크를 제공한다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API `ruff`, mypy,
admin client/feature/feature-request focused pytest 28건, schemas/api-client/web typecheck,
Web lint, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버
(12805)를 띄워 `admin-feature-change-requests.e2e.ts` + `admin-feature-requests.e2e.ts` 5건이
통과했다. N150 live API/UI/e2e는 사용자 지시에 따라 기능 묶음이 더 모인 뒤 T-215 게이트에서
진행한다.

다음: T-210 PR을 만들고 merge한 뒤 T-220(`/admin/etl` + provider sync + Dagster 운영 화면)에
진입한다.

## 2026-06-27 (codex) — T-225 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션

Admin이 여행계획, 날짜, POI를 복사·이동·삭제할 수 있는 운영 작업을 추가했다.
`/admin/trips/{trip_id}/operation-impact`, `/copy`, `/move`, `DELETE /admin/trips/{trip_id}`,
날짜 단위 `/admin/trips/{trip_id}/days/{day_index}/*`, POI 단위 `/admin/pois/{poi_id}/*`
operation endpoint가 추가됐고, 모든 mutation은 `access_reason`을 감사 로그에 남긴다.

여행계획 copy는 기존 사용자 복사 흐름을 commit 옵션으로 재사용하되 admin audit과 같은
transaction에 묶었다. 날짜/POI 이동은 대상 여행/day를 선택해 하위 POI, 첨부, 댓글을 move 또는
delete 정책으로 처리한다. 현 FK 구조상 day/POI/첨부 orphan은 허용하지 않고, impact API와 Web
dialog가 `allowed=false`와 사유를 표시한다.

Web `/admin/trips/{trip_id}`와 `/admin/pois/{poi_id}` 상세에 운영 작업 dialog를 추가했다. dialog는
대상 여행 검색, 대상 day 입력, 하위 항목 정책, 영향도 요약, reason 입력, 실행 결과, audit refresh를
포함한다. 공유 Zod schema와 `@pinvi/api-client` operation 함수도 추가했다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API ruff, mypy,
`test_admin_trips_api.py` + `test_admin_pois_api.py` 18건, schemas/api-client/web typecheck,
Web lint, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버
(12805)를 재사용해 `admin-trips.e2e.ts` + `admin-pois.e2e.ts` 8건이 통과했다.

다음: PR을 만들고 merge한 뒤 T-210(Pinvi feature request와 upstream change request 운영 통합)에
복귀한다. T-210 WIP stash는 `wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어
있다.

## 2026-06-27 (codex) — T-224 여행/날짜/POI 파일 업로드와 용량 정책

여행계획, 날짜, POI에 파일 첨부 metadata를 등록/조회/삭제할 수 있게 했다. 파일 본문은 기존
RustFS presigned PUT 흐름을 쓰고, DB에는 `app.curated_plan_attachments` metadata만 저장한다.
T-224에서 `trip_day_index`를 추가해 day target을 표현하고, 파일 용량 정책은
`app.storage_settings` 전역값과 `app.users` 사용자별 override를 함께 사용한다.

API는 `/trips/{trip_id}/days/{day_index}/attachments*`, `/trips/{trip_id}/files`,
`/users/me/files`, `/admin/files`, `/admin/settings/files`, `/admin/users/{user_id}/file-quota`를
추가했다. quota는 upload-url 발급 시 개별 파일 크기를 조기 차단하고, metadata 등록 시
개별 파일/여행계획 총량/사용자 총량을 DB attachment metadata 기준으로 검사한다. Admin 변경은
`settings.files_update`, `user.file_quota_update`, `attachment.delete` audit으로 남긴다.

Web은 사용자 `/files` 파일함, Admin `/admin/files` 파일 관리, Admin 사용자 상세의 파일 quota
override, Trip detail의 day/POI 첨부 패널을 추가했다. `/admin/trips/{trip_id}` 상세에도 해당 여행의
파일 목록과 다운로드 동선을 붙였다. 삭제는 metadata soft delete이며 RustFS orphan cleanup/reconcile은
후속 후보로 남아 있다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API `ruff`, mypy,
관련 integration 27건, schemas/api-client/web typecheck, Web lint, Web production build가 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 재사용해 신규 `admin-files.e2e.ts` /
`my-files.e2e.ts` 2건과 기존 admin/trip 관련 8건이 통과했다.

다음: PR을 만들고 merge한 뒤 T-225(여행계획/날짜/POI 복사·이동·삭제 오케스트레이션)에 진입한다.
T-210 WIP stash는 `wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어 있다.

## 2026-06-27 (codex) — T-223 사용자 아바타 / RustFS 이미지 관리

사용자와 Admin이 RustFS 기반 아바타 이미지를 볼 수 있고 업로드/교체/삭제할 수 있게 했다.
`app.users`에는 `avatar_bucket`, `avatar_storage_key`, MIME, byte size, 갱신 시각을 추가했고,
`app.storage_settings` 단일 행으로 전역 아바타 최대 업로드 크기(기본 2MiB)를 관리한다.

API는 `/users/me/avatar/upload-url`, `PUT/DELETE /users/me/avatar`,
`GET /users/me/avatar/download-url`을 제공한다. Admin은 `/admin/users/{user_id}/avatar/*`로
대상 사용자 아바타를 관리하고, `/admin/settings/avatar`에서 전역 크기 제한을 조회/변경한다.
Admin 변경은 `user.avatar_replace`, `user.avatar_delete`, `settings.avatar_update` audit으로 기록한다.

Web `/profile`에는 아바타 섹션을 추가했고, `/admin/users/{user_id}`에는 사용자 아바타 관리와
전역 제한 설정을 추가했다. presigned PUT은 기존 RustFS 흐름을 재사용하되, 아바타 endpoint는
image MIME과 전역 크기 제한을 별도로 강제한다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API `ruff`, mypy,
storage unit 9건, avatar/admin focused integration 7건, schemas/api-client/web typecheck,
Web lint, Web production build가 통과했다. Windows Playwright는 WSL Next 서버(12805)를 재사용해
`admin-users.e2e.ts` + `profile-avatar.e2e.ts` 4건이 통과했다.

다음: PR을 만들고 merge한 뒤 T-224(여행/날짜/POI 파일 업로드와 용량 정책)에 진입한다. T-210 WIP
stash는 `wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어 있다.

## 2026-06-27 (codex) — T-219 POI Admin 직접 생성

Admin POI 목록에 생성 dialog를 추가했다. 운영자는 `/admin/trips` 검색 결과에서 여행계획을
선택하고, day/sort_order, feature_id 또는 POI 이름, 좌표/주소, 마커 override, 예정 시각,
메모, 예산/실사용 금액, URL, 작업 사유를 입력해 POI를 직접 만들 수 있다. UI는 이름/좌표/주소를
`feature_snapshot`으로 조립하고, 생성 성공 시 `/admin/pois/{poi_id}` 상세 화면으로 이동한다.

백엔드는 `POST /admin/pois`를 추가했다. admin 전용이며 삭제된 trip에는 생성하지 않는다.
없는 `trip_day`는 사용자 POI 생성 흐름과 동일하게 자동 생성하고, KASI rise/set 초기 row도 생성한다.
snapshot에 지역 코드가 있고 trip primary region이 비어 있으면 `poi_snapshot` source로 보정한다.
`poi.create` audit은 POI row와 같은 transaction에 기록하며, audit 실패 시 POI 생성도 rollback된다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API focused pytest 8건,
API ruff, focused mypy, schemas/api-client/web typecheck, Web lint, Web production build가 통과했다.
Web mock e2e는 WSL Next 서버(12805)를 Windows Playwright runner가 재사용하는 방식으로
`admin-pois.e2e.ts` 3건 모두 통과했다.

다음: PR을 만들고 merge한 뒤 T-223(사용자 아바타/RustFS 이미지 관리)에 진입한다. T-210 WIP
stash는 `wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어 있다.

## 2026-06-27 (codex) — T-217 Trip Admin 직접 생성

Admin 여행 목록에 생성 dialog를 추가했다. 운영자는 `/admin/users` 검색 결과에서 owner를
마스킹 이메일/닉네임 기준으로 선택하고, 여행계획명, 날짜, 공개 범위, 상태, 지역 힌트,
행정구역 코드, 설명, 작업 사유를 입력해 여행계획을 직접 만들 수 있다. 생성 성공 시 방금 만든
`/admin/trips/{trip_id}` 상세 화면으로 이동한다.

백엔드는 `POST /admin/trips`를 추가했다. admin 전용이며 삭제/비활성 owner에는 생성하지 않는다.
`trip.create` audit은 trip row와 같은 transaction에 기록하고, owner email 원문은 응답/감사 로그에
남기지 않는다. audit append 실패 시 trip 생성도 rollback된다.

검증은 로컬 WSL ext4 미러와 Windows Playwright runner에서 수행했다. API focused pytest 7건,
API ruff, focused mypy, schemas/api-client/web typecheck, Web lint, Web production build가 통과했다.
WSL Playwright mock e2e는 Chromium 바이너리 부재로 실행 전 실패했지만, 같은 spec은 WSL Next
서버(12805)를 Windows Playwright runner가 재사용하는 방식으로 3건 모두 통과했다.

다음: PR을 만들고 merge한 뒤 T-219(POI Admin 직접 생성)에 진입한다. T-210 WIP stash는
`wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어 있다.

## 2026-06-27 (codex) — T-216 Trip Admin 상세 운영성 보강

Admin 좌측 메뉴가 현재 route와 무관하게 dashboard 선택 상태로 보일 수 있는 문제를
가장 긴 href prefix active 판정으로 고쳤고, sidebar를 icon-only compact view로 줄여 본문
공간을 확보했다. 각 메뉴 아이콘은 title/aria-label/`aria-current`를 갖는다.

`/admin/trips/{trip_id}` 상세 응답에는 이제 `days`와 `pois`가 포함된다. `days`는 날짜별
`poi_count`를 제공하고, `pois`는 `trip_day_pois` attachment의 snapshot 기반 label/주소/좌표,
일정/메모/비용/URL/추가자 정보를 제공한다. Web 상세 화면은 owner/가입 동반자/POI 추가자를
`/admin/users/{user_id}`로 연결하고, 미가입 초대자는 별도 상태로 표시한다. 상세 계획 섹션에는
day/POI 목록을 추가했으며, POI row 클릭 시 지도 preview, snapshot, 상세 metadata,
`/admin/pois/{poi_id}` 링크를 포함한 dialog를 띄운다.

추가 요청 12~14번은 범위가 커서 T-223(사용자 아바타/RustFS 이미지 관리), T-224(여행/날짜/POI
파일 업로드와 용량 정책), T-225(여행계획/날짜/POI 복사·이동·삭제 오케스트레이션)로 분리해
`docs/execplan/admin-console-gap-plan.md`와 `docs/tasks.md`에 추가했다.

검증은 로컬 WSL ext4 미러에서 수행했다. API focused pytest 4건, API ruff, focused mypy,
schemas/api-client/web typecheck, Web lint, Web production build가 통과했다. local Playwright
mock e2e는 WSL Chromium 바이너리 부재로 실행 전 실패했으며, 추가 e2e는 CI 또는 T-215 N150
묶음 게이트에서 확인한다.

T-216은 PR #242로 merge 완료했다. T-210 WIP stash는
`wip-t210-change-requests-before-admin-addendum` 이름으로 보존되어 있으며, T-223~T-225 이후
또는 우선순위 재조정 시 복원한다.

## 2026-06-27 (codex) — T-209 Admin Features read proxy / 화면 구현

`kor-travel-map` Admin 최신 계약을 확인해 Pinvi `/admin/features` read-only proxy와 Web 화면을
구현했다. upstream 계약은 `GET /v1/admin/features`(`data.items[]`,
`meta.page.next_cursor`, `meta.duration_ms`)와 `GET /v1/admin/features/{feature_id}`
(`feature/sources/issues/overrides/versions/change_requests/files`)를 사용한다.

백엔드는 `KorTravelMapAdminClient.list_features()` / `get_feature_detail()`와 FastAPI
`/admin/features`, `/admin/features/{feature_id}` router를 추가했다. 이 경로는 admin/operator
전용이며 Pinvi DB의 `feature.*` table을 직접 조회하지 않는다. Web은 기존 placeholder를 검색어,
kind/status/provider/category/issue 필터, sort/order, page_size, cursor pagination, detail inspector로
교체했다. shared Zod schema, API client, query key, live matrix, mock e2e fixture도 함께 보강했다.

검증은 로컬 WSL ext4 미러에서 수행했다. API focused pytest 15건, API ruff, schemas/api-client/web
typecheck, Web lint, schemas Vitest, admin live catalog/list(5966 cases), catalog assertion, Web
production build가 통과했다. local Playwright mock e2e는 WSL Chromium 바이너리 부재로 실행 전
실패했으며, 추가한 e2e는 CI 또는 T-215 N150 묶음 게이트에서 확인한다.

다음: PR을 만들고 merge한 뒤 T-210에서 Pinvi feature request와 upstream change request 운영 화면을
연결한다.

## 2026-06-27 (codex) — T-208 Admin IA / 상태판 보강

Admin 구현 프로그램의 첫 코드 Task인 T-208을 완료했다. sidebar를 Pinvi 운영 / 지도 데이터 /
시스템 운영 그룹으로 재정렬하고, `kor-travel-map` Admin 참고 영역인 변경 요청, dedup review,
provider sync, integrity, debug logs route를 placeholder로 추가했다. placeholder는 더 이상 단순
skeleton이 아니라 기능 gap, Task ID, 구현 범위를 표시한다.

백엔드에는 read-only `/admin/system/summary`를 추가했다. 이 endpoint는 admin/operator만
조회 가능하며 Pinvi API, DB, Web, Dagster, `kor-travel-map` API, RustFS 상태를 `ok/degraded/down/unknown`
카드 데이터로 반환한다. 응답에는 raw URL, 운영 도메인, secret을 넣지 않는다. Web 대시보드는 기존
통계 카드 위에 이 상태 보드를 표시하고, live matrix는 새 route와 대시보드 상태 카드를 검사하도록
확장했다.

검증은 로컬 WSL ext4 미러에서 수행했다. API focused pytest 9건, API ruff, schemas/api-client/web
typecheck, Web lint, admin live catalog/list, schemas Vitest, Web production build가 통과했다. N150 live
browser 실행은 사용자 지시에 따라 여러 기능이 더 모인 뒤 T-215 묶음 게이트에서 진행한다.

다음: PR을 만들고 merge한 뒤 T-209(`kor-travel-map` Admin proxy foundation + `/admin/features` 실제 화면)에
진입한다.

## 2026-06-27 (codex) — Admin 계획 리뷰 차단 이슈 반영

다른 에이전트 리뷰에서 Admin 계획 PR의 차단 이슈 2건이 확인됐다. 공개 추적 문서에 남아 있던
N150 bootstrap admin 이메일/비밀번호 조합 표현을 익명화하고, seed/reset production 정책은
`disabled 응답` 선택지를 제거해 router 미등록/404로 고정한다. 보완 권고도 반영해 dedup route는
기존 SPEC/API의 `/admin/dedup-review` 단수로 맞추고, T-209/T-211/T-212의 최신
`kor-travel-map` OpenAPI 확인 게이트와 mutation reason/audit/idempotency/kill-switch 기준을
계획에 추가했다.

다음: 이 리뷰 반영 PR을 merge한 뒤 T-208(Admin IA / 메뉴 / 대시보드 상태판 보강) 구현에
진입한다.

## 2026-06-27 (codex) — Admin 기능 보강 계획 PR

Admin 콘솔은 메뉴만 있고 기능이 비어 있는 route가 많아, 구현을 더 진행하기 전에
`docs/execplan/admin-console-gap-plan.md`로 상세 실행 계획을 먼저 정리했다. `kor-travel-map`
Admin의 feature, change request, dedup, provider sync, integrity, debug/log 화면을 참고하되,
Pinvi가 `feature` / `provider_sync` schema를 직접 소유하지 않는 책임 경계를 계획에 명시했다.

다음 순서는 이 계획 PR을 merge하고, 다른 에이전트 리뷰를 받은 뒤 T-208부터 Task 단위 PR로
진행한다. 단위 기능 테스트는 로컬 WSL ext4 미러에서 수행하고, N150은 여러 기능이 모인 뒤
묶음 live API/UI/e2e 게이트로 사용한다.

## 2026-06-27 (codex) — N150 bootstrap admin 복구

N150 운영 DB에 bootstrap 대상 계정과 admin role 사용자가 없어 Admin 로그인이 실패했다.
현재 N150에는 local-only 운영 런북의 임시 credential로 복구 검증을 완료했다.

재발 방지를 위해 API startup bootstrap admin 서비스를 추가했다. `PINVI_BOOTSTRAP_ADMIN_PASSWORD`가
설정된 환경에서만 `PINVI_BOOTSTRAP_ADMIN_EMAIL` 계정을 생성/복구하고, password hash가 바뀌면
기존 세션을 폐기한다. 운영 compose가 해당 env를 컨테이너에 전달하도록 보강했고, admin/deploy
런북과 실패 패턴 문서에 N150 확인 절차 및 PowerShell→WSL→SSH→Docker→Python 중첩 quote 금지
규칙을 남겼다.

## 2026-06-26 (claude) — 민감 배포 노트(LOCAL) + 푸시 전 보안 감사 절차

반복 배포 실수를 민감정보 포함해 gitignore된 `docs/deploy-runbook.local.md`(LOCAL ONLY)에 상세
기록하고, remote push 전 보안 감사를 AGENTS.md에 절차화했다 — **kor-travel-concierge 패턴에 정렬**
(동일 파일명/구조 + `git diff --cached` 비밀 스캔 + 런북의 "푸시 전 추가 스캔"). 이 과정에서 직전
#235가 노드 IP를 public main(deploy.md/journal.md)에 유출한 것을 발견·redact했다. `.gitignore`에
`*.local.md`/명시 항목/`.local/` 추가, `CLAUDE.md` 동기, 런북을 각 worktree에 복사. 다음: 신규 worktree
셋업 시 이 런북 복사를 기본 절차에 포함(`docs/runbooks/codegraph-worktrees.md`).

## 2026-06-26 (claude) — Pinvi 이미지 GHCR 폐지 → 로컬 빌드 전환

사용자 지시로 Pinvi 이미지를 GHCR에서 내리고 향후 push를 중단했다. N150에서 운영 중인
`ghcr.io/digitie/pinvi-{api,web}:deploy-836a18f`를 로컬 `pinvi-*:latest-main`으로 retag하고
`~/kor-travel-docker-manager/.env`를 로컬 태그로 바꿔 GHCR 의존을 제거했다(컨테이너 재생성
없이 동일 콘텐츠 유지). `~/pinvi` 빌드 소스를 `origin/main`(836a18f)으로 동기. repo에서는
`.github/workflows/docker-images.yml`(GHCR push)을 삭제하고 `docs/runbooks/deploy.md`를 실제
`ktdctl pinvi --build` 로컬 빌드 흐름으로 재작성, `infra/.env.prod.example` 이미지 태그를
로컬로 변경했다. **남은 일**: GHCR 패키지 실제 삭제는 `gh` 토큰 scope(`delete:packages`) 부족으로
보류 — 사용자가 `gh auth refresh -s delete:packages,read:packages` 후 삭제하거나 웹 UI로 내린다.
앞으로 운영 배포는 GHCR 없이 `cd ~/pinvi && git pull` → `ktdctl pinvi --build`.

## 2026-06-26 (claude) — 미인증 로그인 시 재인증 메일 재발송

이메일 인증이 안 된 계정으로 로그인하면 가입 인증(재인증) 메일을 자동 재발송하도록 구현했다
(`docs/api/auth.md` §2.3/§3.1의 기존 계약을 채움). `resend_verification_email` 서비스(cooldown
`pinvi_email_verification_resend_cooldown_seconds` 기본 60초, 직전 미사용 signup 토큰 폐기 후 신규
24h 토큰 + 메일 enqueue)를 추가하고, 로그인이 `EmailNotVerifiedError`를 잡으면 자동 호출 +
`details.verification_email_dispatched` 노출. enumeration-safe `POST /auth/verify-email/resend` 추가.
프론트 로그인 화면에 "인증 메일 다시 보내기" 버튼 + 안내. zod/api-client 스키마 동기. WSL 게이트
(ruff/format/mypy + 통합 12 pass, web typecheck/lint/build) 통과. 다음: rate-limit를 cooldown 외에
SlowAPI 한도로도 묶을지 검토(현재는 per-user cooldown만).

## 2026-06-25 (codex) — N150 Web healthcheck 포트 보정

PR #231 merge 후 N150의 Pinvi checkout을 `3c16b75`로 fast-forward하고, docker-manager
`.env`의 API/Web image tag를 `deploy-3c16b75`로 갱신해 재빌드·재기동했다. 1차 Web build는
`esbuild` `ETXTBSY`로 실패했지만 Web 단독 재시도에서 통과했다.

운영 Web/Admin/Signup route는 `12805`에서 200으로 응답했으나 Docker healthcheck가
`localhost:3000`만 확인해 Web container가 `unhealthy`로 남는 문제가 있어,
`apps/web/Dockerfile` healthcheck가 `PINVI_WEB_PORT`, `PORT`, `12805`, `3000` 후보를
검사하도록 수정했다.

## 2026-06-25 (codex) — 로컬 env / 인증 시간 / OAuth 상태

로컬 `.env`가 legacy `TRIPMATE_*` 키만 갖고 있어 현재 앱 설정(`PINVI_*`)에 Resend와
Google OAuth 값이 반영되지 않던 상태를 정리했다. 비밀값은 출력하지 않고 legacy 값을
현재 키로 복사했고, dev URL은 ADR-047 기준 Web `12805`, API `12801`, Dagster `12802`로
보정했다. Resend API key는 현재 `PINVI_RESEND_API_KEY`로 반영됐다.

access token 기본 만료 시간은 10분으로 낮췄다. Google OAuth는 client id는 있으나
client secret이 비어 있어 현 로컬 기준 비활성 상태가 맞다. provider enabled/start 판정도
client id와 secret이 모두 있을 때만 통과하도록 API/Web/mobile 계약 문서와 테스트를 맞췄다.
Admin 접근 URL은 `http://localhost:12805/admin`이다.

## 2026-06-25 (codex) — 회원가입 이메일 발송 worker 복구

회원가입 인증 메일이 `app.email_queue`에만 쌓이고 실제 발송되지 않는 문제를 수정했다.
`process_pending_email_batch` 호출자가 없던 것이 원인이며, `email_outbox_worker_lifespan`을
추가해 FastAPI startup에서 email queue drain worker가 실행되도록 `main.py`에 연결했다.
worker 설정(`PINVI_EMAIL_OUTBOX_WORKER_ENABLED`, interval, batch size)을 추가하고,
lifespan task 시작/취소 테스트와 Resend 문서/CHANGELOG/tasks/journal을 갱신했다.
WSL ext4 미러에서 email worker focused pytest, 가입/비밀번호 재설정 관련 통합 pytest
10건, 변경 API 파일 `ruff check`, 변경 app 파일 `mypy`를 통과했다.

다음 작업은 이 변경을 기존 브랜치의 `kor-travel-map` 계약 미커밋 변경과 분리해 PR 범위를
정리하는 것이다.

## 2026-06-24 (codex) — Admin live UI e2e / N150 재배포

Admin UI live e2e 전용 Playwright config와 3233개 케이스 매트릭스를 추가했다. N150에서는
`ktdctl`로 Pinvi API/Web/Dagster를 재빌드·재기동했고, 운영 Web 번들 API URL을
운영 API 도메인으로 보정했다. live 검증 중 발견한 `/auth/login` 응답 계약, backup container
path, rate-limit, 장시간 access cookie 만료 문제를 수정했고 각 수정 단위는 커밋했다.
최종 검증은 `PINVI_ADMIN_LIVE_CASE_LIMIT=2001`, worker 1, throttle 2100ms, auth refresh 600000ms
기준 N150 live authenticated run `2004 passed`(2.8h)로 완료했다. 임시 admin/session과
Playwright 결과 디렉터리 정리도 확인했다.

다음 작업은 이 브랜치를 push하고 PR을 한 번 생성한 뒤, PR CI/리뷰 결과에 따라 v0.1.0 릴리즈
직전 smoke/tag 절차로 이어가는 것이다.

## 2026-06-25 (claude) — map/geo/concierge 최신 API 계약 동기화 (ADR-049)

`kor-travel-map`/`kor-travel-geo`/`kor-travel-concierge` origin/main 최신 계약을 점검해 Pinvi를
맞췄다. (1) map: PR #533이 public `pinvi-copy`를 폐지하고 admin `detail-snapshot`(`plan`→`content`)로
옮겨, 큐레이션 import를 `KorTravelMapAdminClient.get_curated_detail_snapshot`(admin 서비스 토큰)로
이관했다. (2) geo: `/v2/regions/within-radius`가 `radius_km`+`levels[]` 요청과 level별 그룹 응답
(`sido`/`sigungu`/`emd`, `relation` contains|overlaps, `legal_dong`→`emd`)으로 바뀌어 client/router/schema를
맞췄다(consumer 없어 라우터 표면 직접 변경). (3) concierge: 직접 통합 없이 doc-only 유지가 정답
(그쪽 contract도 PinVi 직접 연결 배제) — 부정확한 doc 표현만 정정, net-new는 Sprint 6 MCP로 보류.
ADR-049 + 계약 문서 동기화. WSL 게이트(ruff/mypy/unit 169/영향 통합 10) 통과. 다음: within-radius
`relation`을 UI에서 쓸지 판단되면 표시 규칙을 정한다.

## 2026-06-24 (codex) — Web Docker image vendor/domain workspace build 복구

운영 배포용 Docker Images workflow 수동 실행에서 API image는 push됐지만 Web image가
`npm install` 중 vendored `file:` tarball을 찾지 못해 실패했다. tarball 복사 후에는 build 단계에서
`@pinvi/domain` workspace 해석이 빠진 문제가 드러났다. install 전
`apps/web/vendor/vworld-map-web-1.0.0.tgz` / `apps/mobile/vendor/vworld-map-core-1.0.0.tgz`와
`packages/domain/package.json`을 복사하도록 보강하고, `apps/web/package.json` dependency와
`next.config.mjs` transpile 대상에도 `@pinvi/domain`을 추가한다. PR merge 후 Docker Images
workflow를 다시 실행하고 운영 노드 배포를 계속한다.

## 2026-06-24 (codex) — kor-travel-geo 신규 v2 API key 계약 대응

`kor-travel-geo` 최신 v2 REST가 공개 API `key` query를 검증하므로 Pinvi geocoding client가
모든 v2 POST(`/v2/geocode`, `/v2/reverse`, `/v2/search`, `/v2/regions/within-radius`)에
`key=<PINVI_VWORLD_API_KEY>`를 붙이도록 변경했다. 별도 `PINVI_KOR_TRAVEL_GEO_API_KEY`는
두지 않고, 같은 raw key를 `kor-travel-geo`의 `KTG_VWORLD_API_KEY`로 설정해 그쪽이
공개 API key hash 저장/검증을 소유한다(ADR-048). key 미설정 시 upstream 호출 전에
geocoding unavailable로 degrade하며, Pinvi 로그에는 key 원본이나 query 포함 URL을 남기지 않는다.

## 2026-06-23 (codex) — kor-travel-map #508 계열 prod endpoint redaction 점검

`kor-travel-map` issue #508의 공개 문서 prod endpoint redaction 문제를 Pinvi에도 대입해
tracked 파일을 점검했다. #508에 기록된 실제 운영 도메인/IP 패턴 잔여는 없었고, 같은 성격의 잔여로
`docs/journal.md`의 WSL private IP와 legacy API host literal, Grafana runbook의 실제처럼
보이는 도메인 예시를 placeholder로 치환했다. 문서 변경만이라 빌드/테스트는 생략하고
tracked 검색과 `git diff --check`로 재검증했다.

## 2026-06-22 (claude) — 지도 feature 검색 abort 전파 (kor-travel-concierge #111 유사 패턴)

kor-travel-concierge #111(BFF abort 미전파)과 비슷한 패턴을 pinvi에서 점검했다. pinvi는 BFF가
없지만 apps/web·packages에 AbortSignal 사용이 0건이라, 지도 feature 검색이 빠른 pan/재검색에서
직전 요청을 취소하지 못했다. `@pinvi/api-client` feature endpoint(`inBounds`/`search`/`nearby`)에
`signal` 옵션을 추가하고(`client.request`가 upstream fetch로 전달), `FeatureMapView`·`MapSearchBox`가
`AbortController`로 직전 요청을 abort하도록 했다. `lib/abort.ts`(`isAbortError`) +
`tests/apiClientSignal.test.ts` 추가. WSL typecheck/lint/unit/test/build 통과. 다른 fetch는 폼/
react-query라 #111 패턴 아님(api-client는 이제 signal 수용).

## 2026-06-20 (codex) — Claude PR #221~#223 사후 리뷰 + 오류 복구 storage 방어

2026-06-19 이후 Claude Code PR #221~#223을 closed 포함으로 사후 리뷰했다. #221은 현재 main
기준 차단 이슈 없음, #222는 #221과 중복이면서 과거 `tripmate.etl.definitions`/3000 포트 기준이라
리뷰 코멘트 후 닫음, #223은 storage 예외 방어 누락을 후속 수정으로 확정. `error-recovery.ts`에
storage-safe `claimErrorReloadAttempt`/`clearErrorReloadAttempt`를 추가하고 `RouteError`/
`global-error`가 직접 `sessionStorage`를 만지지 않게 했다. 테스트는 reload 1회 guard와 storage
예외 방어를 보강했다.

## 2026-06-20 (claude) — Admin UI Next 기본 오류 화면 복구 보강 (kor-travel-geo T-278 #391 이식)

kor-travel-geo PR #391(T-278)을 pinvi `apps/web`에 이식했다. Admin UI가 Next 기본 전역 오류
화면으로 떨어지거나 좌측 메뉴 이동 중 RSC 실패하던 공백을 닫았다. `lib/error-recovery.ts`
신설(chunk/RSC/network 분류 + `pinvi.web.error-reload:<path>` 키), `RouteError`/`global-error`가
recoverable 오류를 같은 pathname에서 1회 hard reload로 복구. `components/navigation/
DocumentNavLink.tsx` 신설 + admin 좌측 메뉴를 document navigation으로 교체해 `_rsc` client
routing 실패를 예방. `tests/errorRecovery.test.ts` 신설. pinvi는 기존 error/global-error
boundary와 디자인 토큰을 재사용했다(kor-travel-geo raw CSS 미이식). 검증: WSL
typecheck/lint/unit/test/build, admin e2e는 goto 기반이라 영향 없음.

## 2026-06-20 (claude) — prod=ktdctl+공식도메인 / dev=127.0.0.1:12xxx host-mode + 포트 ask-before-kill + Dagster 12802 (ADR-047)

**dev/prod 분리**: 별도 지시 없으면 대상은 dev. prod는 ktdctl로 컨테이너를 올리고 공식
도메인을 적용하며, dev는 이 worktree에서 직접 `127.0.0.1`의 12xxx 포트로 띄운다(dev Docker는
host 네트워크 기본). 운영 주소(web/api/dagster/RustFS S3·콘솔)는 공개 repo에 노출하지 않고
gitignore된 `infra/.env.prod`(템플릿 `infra/.env.prod.example`)에만 둔다 — 추적 파일 23곳은
`*.example.com` placeholder로 치환. `infra/docker-compose.app.yml`을 `${VAR:-smoke기본값}`으로
parameterize + `app-dagster`(profile etl, 12802) + `apps/etl/Dockerfile`(`dagster-webserver
-p 12802`) 신설. `infra/docker-compose.yml`은 dev 기본 host 모드(RustFS 12101/12105 직접
bind). `scripts/dev-up.sh`는 127.0.0.1 bind + **포트 점유 시 새 포트로 바꾸지 않고 강제종료
여부를 사용자에게 물어 거부 시 중지**. `scripts/{deploy-node,docker-app}.sh`에 `PINVI_ENV_FILE`/
`PINVI_ENABLE_DAGSTER`. 검증: `docker compose config`(smoke/prod/dev host-mode) + dagster
컨테이너 `:12802 /server_info` 응답 + `bash -n` OK + 추적 파일 실도메인 0건.

**다음 한 작업(운영자 수동)**: ① `infra/.env.prod`의 시크릿(`change-me`)을 실제 값으로
채운다. ② GitHub repo secret `NEXT_PUBLIC_PINVI_API_URL`을 운영 API 도메인으로 설정한다.
③ reverse proxy(도메인→로컬 포트 12805/12801/12802/12101/12105)를 구성하고
`PINVI_ENV_FILE=infra/.env.prod PINVI_ENABLE_DAGSTER=1 scripts/deploy-node.sh deploy`로 기동한다.

## 2026-06-18 (codex) — Web 지도 `vworld-map-web` 전환 (T-201)

사용자 지시에 따라 `apps/web` 지도 클라이언트를 기존 `maplibre-vworld` /
`maplibre-vworld-js` tarball 의존성에서 `maplibre-vworld-react`의 Web 패키지
`vworld-map-web` + 공통 `vworld-map-core`로 전환했다(branch
`agent/codex-web-vworld-map-web`). `apps/web/vendor/vworld-map-web-1.0.0.tgz`를 추가하고,
`vworld-map-core`는 기존 `apps/mobile/vendor/vworld-map-core-1.0.0.tgz` file spec을 공유하도록
`package.json`/`package-lock.json`/`next.config.mjs`를 갱신했다.

`components/map/vworldPrimitives.tsx`가 `vworld-map-web`의 `VWorldMapView`,
`ClusterLayer`, `MakiMarker`, `Popup`, `UserLocationMarker`, `MapContextMenu`를 lazy
import하도록 바꿨고, `MapView`/`FeatureMapView`/`TripMapView`는 이 facade의 타입과
primitive만 사용한다. 기존 `maplibre-vworld/style.css`와 T-074 dev React `require` shim은
제거했다.

ADR-046을 추가하고 ADR-015를 superseded 처리했다. `AGENTS.md`/`CLAUDE.md`,
`docs/integrations/maplibre-vworld.md`, frontend architecture, compliance, sprint/runbook,
CHANGELOG, tasks를 새 기준으로 동기화했다. T-201은 완료 처리.

**검증(WSL ext4 미러)**: `npm --workspace apps/web run typecheck`,
`npm --workspace apps/web run lint`, `npm --workspace apps/web run build`,
`npm --workspace apps/web run test` 통과. `npm ls maplibre-vworld`는 empty,
`npm ls vworld-map-web vworld-map-core --workspace apps/web --depth=0` 정상. NTFS→ext4
rsync 중 기존 미러의 `.venv`/`.venv-wsl` 삭제 경고가 있었지만 Web 검증 경로에는 영향 없음.

**다음 한 작업**: PR 리뷰/머지 후 v0.1.0 릴리즈 직전 최종 smoke와 tag/GitHub Release notes를
이어간다.

## 2026-06-18 (codex) — StyleSeed 디자인 규칙 적용 + 문서화

StyleSeed `llms.txt`와 full context의 핵심 규칙을 Pinvi 디자인 기준에 맞춰 적용했다(branch
`agent/codex-styleseed-design-rules`). 새 정본 문서 `docs/design/styleseed-rules.md`를 추가했고,
`docs/architecture/frontend.md` / `DESIGN.md` / `docs/design/marker-palette.md`에 단일 accent,
semantic token, shadow 8% cap, 44px touch target, 상태 UI, reduced-motion, 마커 16색 예외를
반영했다. `packages/design-tokens`에는 motion/touch/focus용 Tailwind token과 8% shadow cap을
추가했다. Web 홈/피드백 상태 컴포넌트와 모바일 공용 UI는 surface, focus ring, semantic color,
touch target 기준으로 정리했다.

**검증**: WSL ext4 미러에서 `npm install` 후 `npm run typecheck`, `npm run lint`,
`npm --workspace apps/web run build`, `npm run test` 통과. 최초 typecheck는 미러 의존성
미설치로 실패했으며, 설치 후 재실행해 통과했다.

**다음 한 작업**: PR 리뷰/머지 후 v0.1.0 릴리즈 직전 최종 smoke와 tag/GitHub Release notes를
이어간다.

## 2026-06-17 (claude) — Admin UI 전체 테이블 TanStack Table + Virtual + Query 전환

Admin UI 테이블 15개를 `@tanstack/react-table` + `@tanstack/react-virtual` 기반 공유
`AdminTable`(정렬·sticky 헤더·가상화)로 교체하고, admin 데이터 패칭을 TanStack Query로
전환했다(branch `agent/claude-admin-tanstack-tables`). 리스트 10개 + 상세 nested 5개 전부.
헤더 클릭 정렬(클라이언트)·sticky 헤더 신규, 기존 필터/검색/페이지네이션/액션/testid는 패리티
유지. Query provider는 admin 레이아웃에만, `query-keys.ts`에 `admin` 네임스페이스. 목록 리로드
mutation은 invalidate, backup 생성은 낙관적 prepend. 단위(vitest jsdom RTL) + 신규 e2e
`admin-table.e2e.ts`(정렬/aria-sort/empty/loading/sticky/가상화) 추가.

**검증**: WSL typecheck+lint+build+vitest(15) ✅, Windows e2e `-- admin` 23 passed ✅.

**다음 한 작업**: PR 리뷰/머지 후, 필요 시 행 선택 활성화 또는 서버측 정렬 검토(현재 정렬은
클라이언트·현재 페이지 한정). 다른 route group(공개/앱)으로의 Query 도입은 별도.

## 2026-06-17 (claude) — 이슈 #215 Expo/mobile 사후 리뷰 후속 정리

이슈 #215 완료 조건의 P0 + 정책 + 문서 항목을 한 묶음으로 처리했다(branch
`agent/claude-issue-215`). 백엔드/모바일을 전문 에이전트로 병렬, 문서/ADR은 직접.

- **#209(P0)**: provider `error`도 state를 보고 모바일 딥링크(`pinvi://oauth?error=`)로 라우팅 +
  exchange code/login state를 원자적 조건부 UPDATE로 1회 소비. 통합 테스트 4건 추가.
- **#207(P0/P1)**: 1회용 share URL을 화면에 보존(selectable Text + 경고) + 해제 확인 다이얼로그.
- **#202(P1)**: 부팅 시 네트워크 실패 vs 확정 401 분리 — 네트워크면 토큰 보존 + 캐시 프로필 부팅
  (`lib/user-cache.ts`) + offline 배너.
- **VWorld 키 정책(P1)**: ADR-045(인터림 운영 제한 + 공개 배포 전 opaque token/proxy 게이트) +
  토큰 발급 감사 로그(키 미로깅).
- **문서 drift**: SDK 56 / 활성 / minSdk 24 / 설치 완료로 동기화(README/SKILL/AGENTS/CLAUDE/mobile).

**검증(WSL 미러)**: API ruff/mypy --strict(변경 파일) + pytest 30 passed(oauth 통합). 모바일/웹
typecheck(전 workspace) + web lint 모두 ✅.

**다음 한 작업**: #211 실기기 smoke(Android Dev Client APK 설치 → 로그인/지도/Google OAuth/공유
URL 복사/오프라인 부팅 확인). 이후 P2(#204/205/206 mutation rollback·클라 검증, #203 동의 gate/
파괴적 확인, mobile CI lint/expo-doctor/build gate)를 후속 묶음으로.

## 2026-06-16 (claude) — 모바일 RN 앱 인증 흐름 + 핵심 화면 구현

`apps/mobile` RN 기반(`lib/tokens.ts`·`lib/api.ts` 401 자동 refresh·`lib/auth.tsx`
`AuthProvider`·`components/ui.tsx` NativeWind 키트·네비 가드)과 화면을 구현했다:
`(auth)/login`·`signup`·`verify-email`, `(app)/profile`·`index`(home)·`map`(placeholder)·
`trips` 목록/상세·`notice-plans`·`settings`, `shared/[tripId]/[token]`. 공용
`@pinvi/api-client`에 `mobileAuthApi` 추가. (expo-implementation-plan §7 Step 2·5 완료.)

**검증**: mobile typecheck ✅, root typecheck ✅, web lint ✅, web build ✅(라우트 회귀 없음).

**모바일 앱 빌드 라운드 완료(2026-06-16)**: 인증 흐름 + 핵심 화면(home/trips 목록·상세·생성·편집·
**삭제**/notice-plans/settings 세부/shared) + trip 편집(메타·POI 재정렬·삭제·일자 추가/삭제) +
POI 필드 편집(메모/예산) + **공유 링크 생성/해제** + 모바일 CI 게이트(`mobile.yml` + aggregate
`mobile-typecheck`)까지 구현·머지. PR #202/#203/#204/#205/#206 및 trip-lifecycle PR.
trip CRUD(생성·읽기·수정·삭제)가 모바일에서 완결됐다.

**2026-06-16 추가 — 지도 통합 완료(ADR-044)**: `maplibre-vworld-react` 선결 이슈는 이미 해소돼
있었고(이전 세션), 소비 중 발견한 markers color parity gap을 라이브러리 #21(PR #22)로 수정·머지.
Pinvi는 `vworld-map-{core,rn}` vendored tarball을 `apps/mobile/vendor/`에 `file:` 핀하고
`@maplibre/maplibre-react-native` config plugin을 추가했다. `(app)/map.tsx`가 server-issued 키로
실제 `VWorldMapView`(내 위치 마커 + `flyTo`)를 렌더한다. mobile typecheck 그린.

**2026-06-16 추가 — Google OAuth 완료(모바일)**: 백엔드(딥링크 1회용 code: `/mobile/auth/oauth/
google/start` + 공통 callback `pinvi://oauth?code=` + `/mobile/auth/oauth/exchange`,
`app.oauth_mobile_exchanges` 0024) + 앱(`expo-web-browser` `loginWithGoogle` + login 화면 버튼)을
머지했다. PR #209(backend)/#210(client). maplibre `markers` color parity는 라이브러리 #21(PR #22).

**EAS Dev Client 빌드**: 지도(maplibre) 단독 빌드 `2DV8...apk`(FINISHED) 확인. 지도+OAuth
(expo-web-browser) **결합 빌드** `54e933ef`를 main에서 트리거(진행 중) — 실기기 검증용 dev-client APK.

**남은 것(외부/운영 선결)**:

- **결합 EAS 빌드 완료 확인** + Android 기기 설치 후 `expo start --dev-client`로 지도/OAuth 실동작 smoke.
- **Google Console**: 모바일 OAuth가 실제로 동작하려면 운영 callback(`pinvi-api.example.com/auth/oauth/google/callback`)이
  승인된 redirect_uri에 있어야 하고, dev에선 공개 터널이 필요하다(코드는 완성).
- **POI 추가** — feature 검색 UI(지도/feature 흐름 종속). **push/offline** — `expo-notifications` +
  백엔드 푸시 토큰 endpoint(미구현). naver/kakao OAuth.

**다음 한 작업**: `54e933ef` 결합 빌드가 끝나면 APK로 지도/Google 로그인을 실기기 smoke한다.

## 2026-06-15 Codex 작업 메모 — 모바일 Expo Dev Client 기준선

사용자 지시에 따라 `apps/mobile`의 모바일 기준을 Expo Dev Client + EAS Build로
명확히 고정했다.

- ADR-043을 추가했다. 모바일은 Expo Go를 사용하지 않고, Expo Dev Client development build와
  EAS Build profile을 기준으로 둔다.
- `apps/mobile/package.json`, `app.json`, `eas.json`, `lib/config.ts`를 정렬했다.
- React Native New Architecture는 `newArchEnabled: true`로 유지하고, Android 최소 SDK는
  `expo-build-properties`의 `minSdkVersion: 23`으로 박았다.
- 모바일 VWorld key는 앱에 번들하지 않고, 앱 설정에는 Pinvi API의 server-issued token endpoint만
  두도록 문서화했다.
- `CLAUDE.md` / `AGENTS.md` / `SKILL.md`, 루트 README, frontend 아키텍처, VWorld 통합 문서,
  data-policy, `apps/mobile/README.md`, `CHANGELOG.md`, `docs/journal.md`를 동기화했다.

**검증**: Windows에서 `apps/mobile/package.json`, `apps/mobile/app.json`,
`apps/mobile/eas.json` JSON parse, 모바일 변경 TS 파일 syntax transpile, `git diff --check`
통과. 수정 파일 대상 검색에서 Expo Go용 기본 실행 스크립트와 모바일 public VWorld key 값
잔여가 없음을 확인했다. `apps/mobile`은 아직 root workspace 밖의 비활성 스캐폴드라 전체
`tsc -p apps/mobile`은 Expo/RN/@pinvi 의존성 미설치로 모듈 해석 단계에서 실패하며,
`npm install`/Expo 실행은 Sprint M-1 활성화 때 수행한다.

**다음 한 작업**: v0.1.0 릴리즈 직전 main 기준 최종 CI/수동 smoke와 tag/GitHub
Release notes 생성을 이어간다.

## 2026-06-15 Codex 작업 메모 — Pinvi 웹 favicon/app icon 설정

사용자가 제공한 Pinvi favicon/app icon SVG를 기준으로 웹 정적 아이콘 자산과 Next.js
metadata를 설정했다.

- `apps/web/public/favicon.svg`, generated `favicon.ico`, `apple-touch-icon.png`,
  `icons/pinvi-app-icon.svg`, 192px/512px PNG, `site.webmanifest`를 추가했다.
- `apps/web/app/layout.tsx`에서 favicon SVG/ICO, Apple touch icon, manifest,
  Apple web app metadata, `theme-color`를 내보내도록 연결했다.
- `CHANGELOG.md`와 `docs/journal.md`에 v0.1.0 polish 변경으로 기록했다.

**검증**: Windows에서 PNG/ICO 크기와 512px/180px 아이콘 시각 확인. WSL ext4 mirror에서
`npm --workspace apps/web run lint`, `npm --workspace apps/web run typecheck`,
`npm --workspace apps/web run build`, `npm --workspace apps/web run test`(62 passed) 통과.
Next build 산출물 head에 favicon/manifest/Apple touch icon/theme-color 링크가 포함되는 것도
확인했다.

**다음 한 작업**: v0.1.0 릴리즈 직전 main 기준 최종 CI/수동 smoke와 tag/GitHub
Release notes 생성을 이어간다.

## 2026-06-13 Codex 작업 메모 — docker-manager 포트 대역 정렬

`kor-travel-docker-manager`의 target registry를 정본으로 Pinvi 로컬 포트와 참조 서비스 포트를
재배정했다.

- 새 ADR-042를 추가하고 ADR-037 포트값은 superseded로 표시했다.
- Pinvi API/Web/Dagster는 `12801` / `12805` / `12802`다.
- `kor-travel-map` API/Admin API는 `12701`, `kor-travel-geo` API는 `12501`을 기본값으로 둔다.
- Grafana/cAdvisor/Prometheus는 `12205` / `12301` / `12401`이고, RustFS는 host
  `12101`/`12105`에서 container `9000`/`9001`로 매핑한다.
- `CLAUDE.md` / `AGENTS.md`, env example, API settings, Web defaults, Playwright e2e,
  compose, dev/smoke/deploy scripts, runbook/API/integration 문서를 같은 정책으로 정렬했다.
- Docker 1차 실행 경로는 `ktdctl srv --build`, Pinvi repo의 `scripts/docker-app.sh`는
  폴백/smoke 경로다.

**검증**: WSL ext4 mirror에서 compose config 2종, shell `bash -n`, API focused pytest
26 passed, web lint/typecheck/build/Vitest 62 passed 통과. Windows Playwright 포트 표면 e2e
20 passed. 전체 e2e는 기존 auth mock 한계로 43 passed / 9 failed(`/login` redirect).
`scripts/dev-up.sh`로 API `12801`, Web `12805`, Dagster `12802` 기동 및 health/Web 200 확인.
Windows `git diff --check` 통과.

**다음 한 작업**: PR merge 후 main 기준 서비스가 계속 `12801` / `12805` / `12802`에서
떠 있는지 재확인하고, 필요하면 `kor-travel-docker-manager` 쪽 `PINVI_*` env cutover 후
`ktdctl srv --build`로 통합 기동을 재검증한다.

## 2026-06-13 Codex 작업 메모 — v0.1.0 릴리즈 준비 + T-195/T-108

사용자 요청 순서대로 v0.1.0 릴리즈 준비, public/API 공통 rate-limit, 운영 배포 자동화
foundation을 진행했다.

- `CHANGELOG.md`를 추가해 `v0.1.0` GitHub Release notes 초안을 준비했다. tag/GitHub
  Release 생성은 PR merge 후 main commit에서 수행해야 하므로 아직 만들지 않았다.
- ADR-038을 추가했다. production/staging rate-limit는 Postgres
  `app.rate_limit_buckets` fixed-window bucket, dev/test/smoke는 memory backend를 쓴다.
- `RateLimitMiddleware`를 전역 적용했다. `/public/*` IP 60/min, 인증 사용자
  user/token 60/min, auth low 5/min, OAuth 10/min, storage upload 30/min,
  shared-token 60/min 정책을 적용한다.
- T-108 foundation으로 당시 API/Web image workflow, compose image override,
  `scripts/deploy-node.sh`, N150/Odroid doctor scripts, 노드별 배포 runbook을 추가했다.
  이후 2026-06-26 운영 결정으로 GHCR/multi-arch image 배포는 폐기하고 노드 로컬
  checkout + 로컬 Docker build 기준으로 전환했다.
- ADR-039를 추가해 운영 노드 간 DB live sync를 사용하지 않기로 확정하고, 관련
  runbook/doctor 점검 코드를 제거했다.

**검증**: WSL ext4 mirror에서 API 전체 pytest 342 passed/1 skipped, API
ruff/format/mypy, web lint/typecheck/build/Vitest 62 passed + schemas 6 passed, ETL 3 passed

- ruff/format/mypy, shell `bash -n`, dev/app compose config 통과. Windows git에서
  `git diff --check` 통과.

**다음 한 작업**: PR 생성 후 리뷰/merge. PR merge 뒤 main에서 `v0.1.0` tag와
GitHub Release를 생성한다.

## 2026-06-13 Codex 작업 메모 — T-199 런타임 계약/외부 서비스명 hard cutover

호환 별칭 없이 런타임 계약을 `Pinvi` / `pinvi`와 새 외부 서비스명으로 정리했다.

- env/settings/cookie/패키지/문서의 런타임 prefix는 `PINVI_*` / `pinvi_*`만 남겼다.
- 개발 DB명·사용자·compose 이름은 `pinvi` / `pinvi-*`, RustFS bucket은 `pinvi-media`로
  맞췄다. `kor-travel-geo` 로컬 디렉터리는 `data/juso`만 있어 별도 DB/RustFS 설정 원본은 없었다.
- `kor-travel-map` / `kor_travel_map`, `kor-travel-geo` / `kor_travel_geo`,
  `kor-travel-concierge` 이름을 코드·테스트·문서에 반영했다.
- Admin import route는 `/admin/notice-plans/imports/kor-travel-map-curated-features`,
  Kor Travel Map service token header는 `X-Kor-Travel-Map-Service-Token`만 사용한다.

**검증**: API 전체 pytest 336 passed/1 skipped, API ruff+mypy, ETL 3 passed+ruff+mypy,
web lint/typecheck/Vitest 62 passed, Playwright e2e 52 passed, observability compose config 2종,
`git diff --check` 통과.

**다음 한 작업**: v0.1.0 릴리즈 전 최종 CI/수동 smoke와 Release notes 정리.

## 2026-06-13 Codex 작업 메모 — T-198 프로젝트명/GitHub repo Pinvi 변경

프로젝트 표시명과 GitHub repo 식별자를 `Pinvi` / `pinvi`로 정렬했다.

- README/AGENTS/CLAUDE/SKILL 정체성 표와 GitHub 저장소 값을 `pinvi`로 변경했다.
- npm root/workspace package는 `pinvi`, `@pinvi/*`로 변경하고 lockfile을 정규화했다.
- API/ETL pyproject 이름은 `pinvi-api`, `pinvi-etl`로 바꿨다.
- ETL 패키지는 `apps/etl/pinvi` / `pinvi.etl`로 이전하고 Dagster asset/resource도
  `pinvi_kasi_special_days`, `PinviDatabaseResource`로 정리했다.
- 런타임 계약 rename은 후속 T-199에서 호환 별칭 없이 `PINVI_*` / `pinvi_*` 기준으로 hard cutover했다.

**검증**: API unit 162 passed/1 skipped, ETL 3 passed, API/ETL ruff+mypy,
web lint/typecheck/Vitest, observability compose config, `git diff --check` 통과.

**다음 한 작업**: T-199 런타임 계약 hard cutover까지 같은 브랜치에서 완료했다.

## 2026-06-13 Codex 작업 메모 — T-197 Prometheus 성능 모니터링

Prometheus 기반 API 성능 계측과 관측 스택 profile을 Pinvi에 추가했다.

- FastAPI에 `GET /metrics`와 `PrometheusMetricsMiddleware`를 연결했다.
  `pinvi_api_http_requests_total`, `pinvi_api_http_request_duration_seconds`,
  `pinvi_api_http_requests_in_progress`를 노출한다.
- metric label은 raw URL 대신 FastAPI route template을 사용해 cardinality를 제한한다.
- Docker API 이미지는 Uvicorn worker 2개 기준 `PROMETHEUS_MULTIPROC_DIR`를 사용한다.
- `infra/docker-compose*.yml`에 `observability` profile로 Prometheus `12401`,
  cAdvisor `12301`, Grafana `12205`를 추가했다(ADR-042 기준).
- Grafana datasource/dashboard provisioning과 `/admin/grafana` 기본 URL `12205` 정렬을 완료했다.

**검증**: 단위 테스트 162 passed, ruff, mypy, web lint/typecheck, compose config 통과.

**다음 한 작업**: 필요 시 실제 `observability` profile을 올려 Prometheus target `UP`과
Grafana dashboard 렌더링을 수동 smoke한다.

## 2026-06-12 Codex 작업 메모 — T-211/T-223d kor_travel_map curated import 연결

kor-travel-map T-223c copy snapshot 계약을 Pinvi가 소비하도록 연결했다.

- `KorTravelMapAdminClient.get_curated_detail_snapshot()`가
  `GET /v1/admin/curated-features/{curated_feature_id}/detail-snapshot`을
  (admin base :12701, 헤더 `X-Kor-Travel-Map-Service-Token`) 호출한다 (ADR-049).
- `POST /admin/notice-plans/imports/kor-travel-map-curated-features`를 추가했다. `mode`는
  `create` / `upsert` / `refresh`를 지원하고, 응답에는 `source_version` / `source_etag` /
  복사·재사용 POI 수를 포함한다.
- `curated_trip_plans`에 `source_system`, `source_curated_feature_id`,
  `source_curated_feature_version`, `source_etag`, `source_imported_at`을 추가하고,
  `curated_plan_pois`에 source item 추적 컬럼을 추가했다.
- kor-travel-map import는 feature-backed POI를 재사용하고, 없는 item만 새 LexoRank 뒤에 append한다.
- `kor-travel-concierge` 잔여 설정(`PINVI_AGENT_API_BASE_URL`, 12401 예약)을 제거했다.
  `kor-travel-concierge`는 Pinvi curated trip plan 생성 흐름에 관여하지 않는다.

**다음 한 작업**: kor-travel-map 작업 순서로 돌아가 T-223의 남은 항목을 계속 진행한다.

## 2026-06-12 Codex 작업 메모 — T-130 `/public/*` kor_travel_map public view 소비

kor-travel-map T-222b가 `/v1/public/beaches*`, `/v1/public/festivals*` user OpenAPI 표면을
제공하게 되어, Pinvi T-130을 소비 측에서 연결했다.

- `apps/api/tests/contract/kor-travel-map-openapi-user.json`을 최신 kor_travel_map `openapi.user.json`으로
  교체하고, drift gate가 public 6개 경로와 beach/festival/marker schema 필드를 확인하게 했다.
- `KorTravelMapClient`에 public beaches/festivals 목록·상세·marker 호출을 추가했다. 목록형 응답은
  kor_travel_map `meta.page.next_cursor/total`을 Pinvi `meta.cursor/total`로 투영한다.
- `apps/api/app/api/v1/public.py`와 `apps/api/app/schemas/public.py`를 추가해 인증 없는
  `/public/beaches*`, `/public/festivals*`를 열었다. 응답에는
  `Cache-Control: public, max-age=300`을 붙인다.
- `packages/schemas/src/public.ts`와 `@pinvi/api-client` `publicApi`를 추가했다.
- 앱 내부 공통 rate-limit 미들웨어는 아직 없으므로 T-195로 분리했다. 현재 public API는 kor_travel_map
  upstream 한도와 edge/CDN 제한을 전제로 먼저 연다.

**다음 한 작업(당시)**: kor-travel-map 쪽 순서로 돌아가 **T-223b** provider 보강을 진행한다.
Pinvi T-211(`curated_features` import)은 2026-06-12 T-223d로 완료했다.

## 다음 한 작업 (2026-06-06 감사 후)

문서·구현 정합성 전수 감사 완료 — `docs/audit/2026-06-06-doc-impl-audit.md`.
사용자 결정 DEC-01~10 확정(`docs/decisions-needed-2026-06-06.md`). kor-travel-map
연동 cutover와 §7 합의 반영까지 PR/머지 완료해 **v0.1.0 기능 게이트(라이브 feature
read + 지도 UI + CI/CD + drift gate)는 충족**했다. 남은 릴리즈 작업은 최종 CI/수동
smoke 확인, `v0.1.0` tag, GitHub Release notes다. 다음 구현 후보는 **T-108 운영 배포
자동화**이며, T-129/T-146은 이미 머지 완료했다.

**2026-06-12 상태 정합 + ADR-036 반영 (codex)**: `trip_day_pois.feature_id`는
ADR-031대로 nullable로 정렬하고, `curated_plan_pois.feature_id`도 nullable 유지한다.
curated trip plan은 POI 묶음이며, kor-travel-map import가 feature를 제공할 때만 같은 plan의
feature-backed POI를 찾아 재사용하고 없으면 새 POI를 생성한다(ADR-036).
가짜 `curated:<id>` feature id fallback은 제거한다. 생성 소스는 Pinvi-native
큐레이션과 kor-travel-map `curated_features` 1:1 import가 모두 정식이며, kor_travel_map import는
2026-06-12 T-223d로 구현했다.

**Claude 세션: 프론트 폼 a11y 스윕 + T-106 Telegram 백엔드 완성** (2026-06-10, `agent/claude-*`, PR #151~#166):

- **폼 접근성 스윕 #151~#159** — 재사용 컴포넌트 `FormField`/`FormTextArea`/`FormSelect` +
  `validateForm`(Zod→필드별 한국어 메시지 + firstField) + `useDialogAutoFocus`(모달 포커스 이동/복원)를
  앱 전반에 적용: 공개 인증(login/signup), trip 생성·profile-complete, 모달 3종(TripEdit/NoticePlanCopy/
  FeatureRequest), PoiEditor inline, admin 로그인·액션모달·mcp-tokens, list filter select(`for` 연결)+
  error `role=alert`, settings/mcp-tokens. App Router 방어선(#151 error/global-error/not-found/loading).
- **T-106 Telegram 통합 (백엔드 완성, #160·161·163·164·165·166)**:
  - #160 client `TelegramClient`(verify/send) + §5 실패 분류 + §9 token 마스킹.
  - #161 `/users/me/telegram-targets` CRUD + `app.telegram_targets`(0018, soft delete). **단일 시스템 봇** 모델
    (원시 토큰 DB 저장 X, §1).
  - #163 신규 trip / 동반자 초대 알림 hook(메시지 빌더 + send, 응답 비차단).
  - #164 `/settings/telegram` target 관리 UI(`telegramApi` + 등록/검증/삭제) + settings 서브내비.
  - #165 outbox 재시도(§8) — `app.telegram_system_notification_outbox`(0019) + SKIP LOCKED drain worker
    (backoff 30s/5m/30m/1h/4h, lifespan). hook을 enqueue로 전환.
  - #166 trip↔target 링킹(§6.5/6.6) — `app.trip_telegram_targets`(0020, ≤3) + `/trips/{id}/telegram-targets`.
- **T-106 남은 후속**: weekly/daily summary Dagster 스케줄(§7.1/7.2, Sprint 5 ETL), 프론트 trip-link UI,
  per-user 봇 토큰(vault), PIPA 위탁자 명시(§10 체크리스트).

**kor_travel_map 연동 작업 unblock** (2026-06-10, `docs/reviews/2026-06-10-kor_travel_map-cross-repo-decisions.md`):
kor_travel_map `origin/main 0e45bd7`에서 ADR-048/T-216a~g 머지 확인 — **T-181 잔여(problem+json·
`meta.page`·batch `found`·`max_items`)가 대기 해제, 즉시 실행 가능**. T-179/T-180도
actionable (kor_travel_map ADR-051이 `/v1/admin/features*` change API를 전송 구간 정본으로 승인,
합의 5건은 kor_travel_map T-217c 회신 대기). 주의: **kor_travel_map admin API base는 ADR-042 이후
12701 `/v1/admin/*`**이며, `pinvi_kor_travel_map_admin_base_url`도 12701을 기본값으로 둔다.

**Claude PR 사후 리뷰 후속 완료** (2026-06-10): 2026-06-08 00:00 KST 이후 Claude가 올린
PR #84/#88/#95/#97/#98/#102~#106/#109/#110/#113~#123 총 23건을 closed 포함 재검토했다
(`docs/reviews/2026-06-10-claude-pr-review.md`). 기존 PR에는 GitHub Actions MCP 리뷰 알림만
있고 상세 리뷰 코멘트는 없어 각 PR에 Codex 사후 리뷰 코멘트를 게시했다. 코드 후속은
T-190~T-194로 반영: location-audit이 인증된 `request.state.user_id`/request id를 쓰게 하고
`X-User-Id` spoof를 버렸으며 `/features/requests` body 좌표도 outbox에 보존한다.
trip/POI/admin curated 첨부 metadata는 서버가 발급한
RustFS bucket + `user-uploads/{purpose}/{user_id}/` prefix만 허용한다. `/storage/upload-urls`
의 `curated_*` purpose는 admin 전용으로 막고, `/features/nearby` query를 `lon`/`lat`로
정렬했다.

**T-183 Backup hotswap 잔여 보강 완료** (2026-06-09): API-triggered
`restore-hotswap`이 자기 API/Web 프로세스를 멈추는 drain command를 실행하지 못하도록
`PINVI_RESTORE_API_TRIGGER` guard를 추가했다. `restore_backup_hotswap()`은 프로세스 내부
`asyncio.Lock`에 더해 Postgres `pg_try_advisory_lock`을 잡아 다중 워커/프로세스 동시
schema-swap을 차단한다. API restore는 swap 전 `backup.restore_hotswap_started`를 현재
canonical audit chain에 먼저 commit하고, swap 성공 reflection은
`app_previous_<restore_id>.admin_audit_log`에 append해 오래된 snapshot에 현재 admin이 없어도
success audit가 FK로 깨지지 않게 했다. `.env.example`/Settings/runbook도
`PINVI_RESTORE_*` 실행 설정과 `PINVI_RESTORE_APP_ROLE`을 정렬했다.

**T-112 Pinvi MCP 외부 인터페이스 서빙 완료** (2026-06-09): `app.mcp_tokens` 테이블과
Argon2id-hashed `mcp_<JWT>` 토큰 발급/회수 API를 추가했다. 사용자 `/settings/mcp-tokens`와
admin `/admin/mcp-tokens`에서 원문 1회 표시, 목록 마스킹, 회수가 가능하다. `/mcp/sse`는
Bearer MCP 토큰으로 5개 read-only tool descriptor를 제공하고, `/mcp/tools/{tool_name}`은
`list_trips`, `get_trip`, `list_pois`, `search_features`, `get_user_profile`을 호출한다.
`search_features`는 kor-travel-map OpenAPI HTTP client 경계만 사용하며, stdio bridge/full MCP
session proxy는 후속 작업으로 분리한다.

**T-177 사용자 feature 제안 큐 완료** (2026-06-09): `app.feature_suggestions` 테이블을
추가하고 `POST /features/requests`, `GET /features/requests/{request_id}`를 Pinvi
DB 큐 기반으로 실구현했다. POST는 kor-travel-map을 직접 호출하지 않고 즉시 201을 반환하며,
사용자별 24시간 20건 rate-limit와 pending 중복 dedup을 적용한다. 응답은
`pending/approved/rejected/added/duplicate` 상태 enum과 제안 입력값을 함께 내려준다.

**T-133 Admin priority-3 엔드포인트·페이지 완료** (2026-06-09): Pinvi app DB만 읽는
`GET /admin/stats/overview`, `GET /admin/api-calls`, CPO 전용
`GET /admin/audit/location`을 추가하고 `/admin`, `/admin/api-calls`,
`/admin/audit/location` 화면을 실제 데이터 테이블로 결선했다. 위치 감사 로그는 좌표를
4자리로 마스킹하고 chain 깨짐 시 `X-Chain-Broken: true` 헤더를 반환한다. `/admin/features`
상세 편집, `/admin/etl`, seed/reset은 kor-travel-map 또는 운영 안전장치 결선 전 상태로
명시적으로 남긴다.

**T-132 trip 하위 리소스 분할 완료** (2026-06-09): `/trips/{trip_id}` delete/owner
transfer, `/copy`, day CRUD, anonymous shared view, trip/POI attachment metadata CRUD,
day distance matrix, nearest-neighbor optimize API를 추가했다. Pydantic/Zod schema와
`@pinvi/api-client` endpoint를 확장했고, 통합 테스트는 day 삭제 cascade, copy +
attachment 복제, shared view, distance matrix/optimize persist 흐름을 검증한다.

**T-111 Backup/Restore UI 핫스왑 완료** (2026-06-08): `/admin/backup` snapshot 목록에
Restore schema-swap 다이얼로그를 연결하고 `POST /admin/backup/restore-hotswap` API를
추가했다. API는 `PINVI_RESTORE_HOTSWAP_SCRIPT_PATH`를 실행해 `preparing` /
`restoring` / `validating` / `draining` / `switching` phase를 반환하고 성공/실패 모두
admin audit에 남긴다. 기본 `scripts/restore-hotswap.sh`는 custom dump를 임시 restore
schema로 remap한 뒤 `PINVI_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 schema rename을
수행한다.

**T-135 POI `rise_set` 응답 노출 완료** (2026-06-08): POI 생성/수정/정렬 응답과
`GET /trips/{trip_id}` 상세 POI에 `rise_set`을 노출한다. `app.trip_poi_rise_sets` row가
있으면 `pending_date` / `pending_coord` / `pending_fetch` / `success` / `failed` 상태와
출몰시각 필드를 내려주고, row가 없으면 `null`이다. Trip 상세 builder는 POI ID 목록으로
`trip_poi_rise_sets`를 batch 조회해 N+1을 피한다.

**T-169 MCP list_trips/search_features parity 완료** (2026-06-08): 사용자 `GET /trips`가
bucket/q/status/visibility/date range/sort/opaque cursor를 받도록 보강하고 `meta.cursor` /
`meta.has_more`를 반환한다. API client는 기존 `list()` 배열 반환을 유지하면서 `listPage()`로
cursor meta를 노출한다. MCP `list_trips` 문서는 같은 query 계약을 따르도록 정리했고,
`search_features`는 kor-travel-map Python 함수/DB 직접 호출이 아니라 OpenAPI HTTP
`GET /features/search` 경유임을 명시했다.

**T-168 storage AttachmentResponse 호환 정책 완료** (2026-06-08): storage
`AttachmentResponse`가 신규 `curated_plan_id` / `curated_poi_id`와 `/notice-plans` 호환
alias `notice_plan_id` / `notice_poi_id`를 함께 제공하도록 Pydantic/Zod schema를 맞췄다.
한쪽만 들어오면 같은 값으로 정규화하고, 두 값이 불일치하면 reject한다.

**T-167 money 표현 통일 완료** (2026-06-08): admin POI detail Zod money 필드를
`string | number` union에서 `NonNegativeDecimalStringSchema`로 통일했다. `packages/schemas`
Vitest round-trip 테스트를 추가해 admin/POI/trip-view/notice-plan 응답 money가 decimal string으로
유지되고 number/exponential/negative 표현은 거부되는지 검증한다.

**T-166 admin 감사 hash-chain head 직렬화 완료** (2026-06-08):
`app.admin_audit_log.prev_hash`에 unique constraint를 추가하고, `append_admin_audit()`가
마지막 row 조회 전 PostgreSQL transaction-level advisory lock을 획득해 병렬 admin action도
하나의 chain head로 직렬화한다. 동시 append 회귀와 fork insert 거부 테스트를 추가했다.

**T-165 WebSocket cap/grace + broadcast 비동기 분리 완료** (2026-06-08):
client message rate 초과 connection은 `RATE_LIMITED` error 전송 직후 broker에서 제거해
close grace 동안 trip/process cap slot을 점유하지 않는다. Trip/POI HTTP mutation route는
`publish_event_nowait`로 broadcast task만 예약하고 fan-out 완료를 응답 경로에서 기다리지 않는다.

**T-164 geofence outage guard + defense-in-depth 완료** (2026-06-08): strict geofence
(`enabled && block_unknown`)에서 trusted country-header signal이 하나도 없으면 API startup이
실패한다. shared secret 단독 strict 모드는 warning을 남기고, country header 신뢰에는 선택적
proxy CIDR allowlist 또는 mTLS verified header를 함께 요구할 수 있게 했다.

**T-163 비밀번호 재설정 access JWT 무효화 + refresh race 보강 완료** (2026-06-08):
`users.access_token_version`을 access JWT `token_version` claim과 대조해 reset 전 access
JWT를 즉시 거부한다. password reset 성공 시 token version 증가 + refresh session 일괄
revoke + 새 session 발급으로 정렬했고, refresh rotation은 기존 row lock으로 같은 refresh
token 동시 재사용이 새 session을 둘 이상 만들지 못하게 했다.

**T-125 feature_id 문자열화 완료** (2026-06-08): feature read 응답 schema,
`/features/{feature_id}` 라우터, kor-travel-map client Protocol, trip 상세 view builder가
더 이상 `feature_id`를 UUID로 파싱하지 않는다. `feature_id`는 ADR-028에 따라
kor-travel-map `make_feature_id` 출력을 불투명 문자열로 저장·전달한다.

**T-162 Resend webhook fail-open 잔존 완료** (2026-06-08): secret이 비어 있을 때
`PINVI_ENVIRONMENT` 기본값 `development`만으로 unsigned webhook이 열리지 않도록
`PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED` 명시 opt-in을 추가했다. production에서는 opt-in이
켜져도 secret 미설정 시 `503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다.

**T-131 Trip 상세 view 연결 완료** (2026-06-07): `GET /trips/{trip_id}`가 더 이상
trip 메타만 반환하지 않고 `trip_view_builder.build_trip_view`를 통해 trip/day/POI tree,
companions, share link metadata, `broken_feature_count`를 반환한다. kor-travel-map client가
미주입된 환경에서는 503 대신 저장된 `feature_snapshot`으로 fallback한다.

**T-127 MCP 외부 인터페이스 정본화 완료** (2026-06-07): ADR-019 외부 MCP 계약은
`docs/architecture/mcp-server.md`가 단일 진실이며, 1차 tool은 read-only 5개로 고정했다.
`list_trips.status` enum을 실제 trip status와 맞추고, 사용자/admin MCP 토큰 발급·회수
HTTP endpoint를 `docs/api/users.md` / `docs/api/admin.md` / runbook에 명시했다.

**T-161 README `/search` 앵커 정합 완료** (2026-06-07): `docs/api/features.md`의
통합 검색 heading을 `2.7 GET /search`로 안정화하고, README 링크를
`#27-get-search`로 교정했다. kor-travel-map 요구사항 문서의 잘못된 features.md 절 번호도
§2.7로 맞췄다.

**T-126 POI 생성 경로 단일화 완료** (2026-06-07): v2 정본 POI 생성/수정/삭제/정렬
경로는 `/trips/{trip_id}/pois` 계열로 고정했다. `docs/api/trips.md`의 오래된
`/days/{day_index}/items` 문서 블록을 정본 경로 설명으로 교체하고, 공용
`packages/api-client`에 `poiApi` wrapper를 추가했다.

**T-154 Resend webhook C-22 완결 완료** (2026-06-07): 운영성 환경에서
`PINVI_RESEND_WEBHOOK_SECRET`이 비어 있거나 `whsec_` 표준 base64 형식이 아니면
`503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다. dev/test/local만 unsigned
webhook을 허용한다.

**T-155 Admin access reason URL 로깅 제거 완료** (2026-06-07): PII 원본 이메일 reveal은
더 이상 `access_reason` query를 받지 않는다. 한국어 자유 텍스트 사유가 header 제약에
걸리지 않도록 `POST /admin/users/{user_id}/reveal-pii` + JSON body로만 audit 사유를
허용한다.

**T-156 비밀번호 재설정 session 폐기 완료** (2026-06-07): reset password 성공 시
기존 active refresh session을 모두 revoke하고, reset 완료 응답으로 발급되는 새 session만
active로 남도록 `revoke_active_user_sessions` helper와 다중 session 회귀 테스트를 정렬했다.

**T-157 geofence fallback 발신 검증 완료** (2026-06-07): FastAPI geofence strict 모드는
`CF-IPCountry`만 믿지 않고 `X-Pinvi-Geofence-Proxy` shared secret이 맞을 때만 country
header를 신뢰한다. 직접 접근 spoof는 `UNKNOWN`으로 처리되어 `block_unknown=true`에서
451로 차단된다.

**T-158 Trip WebSocket guard 완료** (2026-06-07): `WS /ws/trips/{trip_id}`에
per-connection message rate limit(초당 5/분당 60), `presence.cursor` 좌표 검증/정본
`longitude`/`latitude` broadcast, trip/process 연결 수 cap, broker send timeout 기반 stale
connection 제거를 추가했다.

**T-159 money 응답 Zod 타입 정합 완료** (2026-06-07): `packages/schemas`의 POI /
추천 plan POI 응답 money 필드를 Pydantic `Decimal` JSON 직렬화와 맞춰 nonnegative decimal
string으로 받도록 바꿨다. 요청 schema의 number 입력은 유지했다.

**T-160 admin 상태+audit 원자성 완료** (2026-06-07): 사용자 force verify/disable,
여행 상태 변경, POI link-status 변경은 업무 상태 변경과 `admin_audit_log` append를 같은
DB 트랜잭션에서 commit한다. audit append 실패 시 상태, 버전, session revoke가 함께
rollback되는 회귀 테스트를 추가했다.

**T-210c(ADR-045 Phase 6) Pinvi 부분 완료** (2026-06-06): `apps/etl`은 `app`
schema 소유 job만 보유해 이관할 feature provider Dagster 스켈레톤이 없음 확인 +
`dagster-etl-bridge.md`/`runbooks/etl.md` phantom 스켈레톤 정합 + asset `__init__`
경계 가드. 남은 T-210d=T-066, T-210e는 kor_travel_map HTTP/OpenAPI 확정 후.

**T-152 Telegram 완료 알림 MCP 완료** (2026-06-07): 모든 agent worktree에
`mcp-telegram` 등록 + `scripts/mcp_telegram_start.py` + 로컬 `.env.mcp-telegram`
(gitignore). PR 후 `send_message`로 요약+링크 발송. GitHub secret 미사용. 실제 전송 검증.

**T-153 PR 리뷰 모니터 MCP 알림 보강** (2026-06-07): `kor-travel-map`식 MCP
진입(CodeGraph / Playwright / Sequential Thinking / Telegram)을 PR review reminder
본문과 공용 모니터 스크립트에 반영했다. PR 이벤트는 `opened` / `ready_for_review` /
`reopened` / `synchronize`에서 즉시 실행하고, 5분 schedule은 지연 가능한 보정 신호로
운영한다.

**T-136 Resend webhook Svix 서명 검증 완료** (2026-06-07): `/webhooks/resend`가
raw body 기준 Svix HMAC-SHA256 서명을 검증한다. `PINVI_RESEND_WEBHOOK_SECRET`이
있으면 `svix-id`/`svix-timestamp`/`svix-signature` 누락, v1 signature 불일치,
timestamp 300초 허용 오차 초과를 `401 WEBHOOK_SIGNATURE_INVALID`로 거부한다.

**T-134 auth refresh/session 영속화 완료** (2026-06-07): 로그인/이메일 verify/
비밀번호 재설정/OAuth callback이 `app.user_sessions`에 refresh token SHA-256 hash를
저장한다. `POST /auth/refresh`는 기존 refresh session을 revoke하고 새 access/refresh
cookie와 새 session row를 발급한다. `POST /auth/logout`은 현재 refresh session을
revoke하고 cookie를 삭제한다.

**T-137 notice/curated-plan 스키마 정본화 완료** (2026-06-07): 추천 여행 템플릿
DB/ORM을 `app.curated_trip_plans` / `app.curated_plan_pois` /
`app.curated_plan_attachments`로 정본화했다. `/notice-plans` API 경로와
`notice_plan_id` / `notice_poi_id` 응답 필드는 Sprint 4 호환 alias로 유지한다.

## 현재 상태

**Sprint 2 핵심 DoD 마감 완료** (2026-06-01). OAuth G-4 + Notice copy + 통합
테스트 27개 green. Sprint 1~~3 + Sprint 4 PR-A(#15 CI 복원) / PR-B(#16 features
API scaffolding) 머지 완료. 통합 테스트 harness(PostGIS testcontainer)가
`apps/api/tests/integration` 에 박힘 — 이후 백엔드 검증의 기반. async alembic 의
DDL 미커밋 잠재 버그도 함께 수정(`alembic/env.py`). 진행 추적 문서 정합성은
`resume.md` + `tasks.md` + `journal.md` 교차 확인이 기준(codex 2026-06-01 정리).
**개발 환경 모델 ADR-024로 확정** — NTFS worktree=git source of truth(Windows
git.exe) / WSL ext4=일회용 테스트 미러. 셋업·검증·함정 절차는
`docs/dev-environment.md`(에이전트 공통).
**Geocoding ADR-025로 확정** — 사용자 대면 geocoding(주소/좌표/행정구역)은
`kor-travel-geo` v2 REST API 직접 호출(`docs/integrations/kor-travel-geo.md`), feature
데이터는 kor-travel-map OpenAPI HTTP 계약(ADR-026). 열린 결정 8건은
`docs/architecture/geocoding-open-decisions.md`(잠정값으로 진행).
**문서 충돌 정정** (2026-06-02 codex) — `agent-guide`, `local-dev`, `architecture`
등에 남아 있던 ADR-024 이전 WSL git 모델, ADR-015 이전 Kakao/marker-wrapper 표현,
ADR-025 이전 `kor_travel_geo` in-process 검색 표현을 정정.
**T-062 운영 게이트 확인/적용** (2026-06-02 codex) — GitHub Actions secret은
`0`개가 의도된 상태다. `OPENAI_API_KEY`는 쓰지 않는다. `codex-pr-review` /
`codex-pr-monitor`는 외부 API 호출 없이 review reminder만 남기도록 변경. `main`에는
repository ruleset `main-pr-only`(id `17146781`)를 적용했다(PR 필수, squash-only,
linear history, force push/deletion 차단, bypass 없음). Classic branch protection은
없다. required status check는 path-filtered workflow가 docs-only PR을 막을 수 있어
aggregate gate 설계 뒤 적용한다.
**로컬 dev 포트 고정** (2026-06-02 codex) — API `12501`, Web `12505`, Dagster `9023`.
`scripts/dev-up.sh`가 해당 포트를 점유한 프로세스를 종료하고 같은 포트로 다시 올린다.
프론트 실행은 계속 WSL ext4 미러 기준이며, Playwright e2e만 Windows에서 실행한다.
**RustFS / Docker app 포트 고정** (2026-06-03 codex) — RustFS API `12101`, console
`12105`. `scripts/docker-app.sh`가 Docker app build/up/down/status/logs/smoke를
제공하고, 시작 전 API `12501`, Web `12505`, RustFS `12101`/`12105` 점유 항목을
정리한다. `scripts/docker-app-smoke-test.sh`는 호환 wrapper다.
**kor-travel-map 연동 포트 고정** (2026-06-03 codex, 2026-06-12 갱신) —
`kor-travel-map` 독립 프로그램의 API/Admin API는 `12301`을 기준으로 문서화한다.
Pinvi가 직접 소유하지 않는 서비스이므로 실행/검증은 그쪽 저장소 런북이 권위다.
**kor-travel-map 최신 main 계약 반영** (2026-06-04 codex) — 최신 `kor-travel-map`
`main`의 `openapi.user.json` / `openapi.json`을 확인해 ADR-026을 추가했다.
Pinvi ↔ kor-travel-map은 더 이상 함수 직접 호출이 아니라 OpenAPI HTTP 계약(API/Admin API
`12301`)이다. `feature` / `provider_sync` schema 소유권은 그대로
kor-travel-map에 있고, Pinvi는 `feature_id` + snapshot만 저장한다.
**KASI 특일/출몰시각 계약 추가** (2026-06-04 codex) — `python-kasi-api`를 통해
특일 계열 5개 dataset을 하루 1회, 과거 6개월~~미래 18개월 범위로 upsert한다.
삭제는 없다. POI 생성 시에는 좌표와 방문일로 "위치별 해달 출몰시각 정보조회"를
1회 호출해 `app.trip_poi_rise_sets`에 저장한다.
**T-067 KASI 구현 완료** (2026-06-05 codex) — `apps/etl`에
`pinvi_kasi_special_days` asset과 `kasi_poi_rise_set_job`을 추가했고, API는 POI
생성 시 `app.trip_poi_rise_sets` 초기 row를 만든다. kor-travel-map 연계 없이
`python-kasi-api` + `DATA_GO_KR_SERVICE_KEY`만 사용한다.
**Production URL 확정** (2026-06-05 codex) — 운영 API는
`https://pinvi-api.example.com`, 운영 Web은
`https://pinvi.example.com`다. Google 승인된 JavaScript 원본은 Web origin,
OAuth redirect URI는 API origin의 `/auth/oauth/google/callback`이다. CORS는 Web
origin만 허용하고, 운영 cookie는 `PINVI_ENVIRONMENT=production`으로 Secure를
강제한다.
**T-070 Sprint 2 잔여 마감** (2026-06-05 codex) — `email_queue` SKIP LOCKED
worker batch, 비밀번호 재설정 요청/확정 API, `api_call_log` httpx event hook
통합 테스트를 추가했다. `.github/workflows/api.yml`은 PR에서 `pytest
tests/integration -q`를 실행한다. Google OAuth client id는 네 Pinvi worktree의
로컬 `.env`에 반영했다.
**T-063 maplibre consumer sync 완료** (2026-06-05 codex) — `maplibre-vworld-js`
PR #46(`docs/consumer-feature-catalog.md` 정합화, `build-and-test` green, merge
`f1dd74b9`)를 머지했고, Pinvi §6/§11.1 snapshot과 Sprint 4 라이브러리 선행
조건을 완료 처리했다. 실제 `maplibre-vworld` dependency pin/import/e2e는 PR-C
frontend 구현에서 처리한다.
**T-065 aggregate CI gate 적용** (2026-06-05 codex) — 모든 PR에서 실행되는
`Aggregate CI gate` workflow를 추가했다. `api` / `web` / `etl`은 path filter를
유지하고, aggregate gate가 변경 파일 기준으로 필요한 check만 기다린다. `main-pr-only`
ruleset required status check는 `Aggregate CI gate`로 적용한다.
**T-071 Google OAuth 로그인 UI 연결** (2026-06-05 codex) — 로컬
`PINVI_GOOGLE_OAUTH_CLIENT_ID` 반영 후 로그인 화면에서 `/auth/oauth/providers`를
조회해 Google 버튼을 활성화한다. `/auth/oauth/google/start`는 envelope 응답으로
authorize URL을 반환하고, PKCE verifier는 DB 평문 저장 없이 `state` + 서버 secret으로
재생성한다.
**T-072 Google OAuth 실패 UX** (2026-06-05 codex) — Google callback 실패는 API JSON
오류 대신 Web `/login?error=...`로 303 redirect한다. 로그인 화면은 `error` code를
고정 한국어 메시지로 매핑하고, 임의 `error_description`은 화면에 그대로 노출하지 않는다.
**T-073 Google OAuth profile 연결/해제 UI** (2026-06-05 codex) — `/auth/me`가
`has_password`와 `oauth_identities`를 반환하고, `/profile`에서 Google 연결 상태 확인,
연결 시작, 해제를 수행한다. 소셜-only 계정은 비밀번호 설정 전 Google 해제를 409로
차단한다.
**T-074 PR-C frontend 지도 shell** (2026-06-05 codex) —
`maplibre-vworld`를 `digitie/maplibre-vworld-js` commit `f1dd74b9...`의 GitHub
archive tarball로 pin하고
`/trips/map-shell`에서 `VWorldMap` / `ClusterLayer` / `MakiMarker` / `Popup`을
실제 import한다. feature 조회는 연결하지 않았고, Windows Playwright smoke에서
`/features/in-bounds`와 kor-travel-map API `12301` 미호출을 확인했다.
**T-075 Trip / notice plan 사용자 shell** (2026-06-05 codex) — kor-travel-map feature
조회 없이 공용 API client에 `/trips` / `/notice-plans` 사용자 endpoint를 추가하고,
Web `/trips`와 `/notice-plans` route, 사용자 navigation shell, 빈 상태, Trip 생성,
notice plan copy action을 연결했다. Windows Playwright smoke에서 `/features/*`와
kor-travel-map API `12301` 미호출을 확인했다.
**T-110 Admin Grafana iframe embed** (2026-06-05 codex) — `/admin/grafana`에
anonymous viewer용 Grafana iframe shell을 추가하고 `NEXT_PUBLIC_GRAFANA_URL`,
`NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`, Web `frame-src` CSP를 문서/환경변수와 맞췄다.
Grafana 컨테이너/provisioning 본체는 Sprint 5 인프라 작업으로 남겼다.
**T-109 한국 전용 geofencing FastAPI fallback** (2026-06-05 codex) —
`PINVI_GEOFENCE_*` 환경변수와 `GeofenceMiddleware`를 추가했다. 기본 비활성이고,
활성 시 `CF-IPCountry` 기반으로 KR 외 요청을 451로 차단한다. health/docs 우회와
access token `sub` → `app.users.roles` DB 조회 기반 운영자 우회를 포함한다.
**T-115 Backup snapshot foundation** (2026-06-06 codex) — `scripts/backup-db.sh` /
`scripts/restore-db.sh`, `GET /admin/backup/snapshots`,
`POST /admin/backup/snapshot`, Web `/admin/backup` snapshot 목록/수동 trigger를
추가했다. Sprint 5 1차 snapshot foundation이며, 핫스왑 schema-swap cut-over와
`RestoreHotswapDialog`는 T-111에서 완료했다.
**T-116 OAuth provider 범위 정리** (2026-06-06 codex) — 현재 OAuth provider는
Google만 활성이다. `/auth/oauth/providers`는 Google만 반환하고, Naver/Kakao는 미래
작업(T-122)으로 보류한다.
**T-117 회원가입 약관 동의** (2026-06-06 codex) — `POST /auth/register`가 필수
4종 동의(`tos`, `privacy`, `lbs_tos`, `location_collection`)를 요구하고,
가입 트랜잭션 안에서 `app.user_consents`에 저장한다. `/signup` 화면은 필수 전체
동의와 선택 `marketing` 동의를 제공하고, 필수 동의 전 제출을 막는다.
**T-118 Google OAuth 계정 매칭 UX** (2026-06-06 codex) — Google OAuth login은
같은 이메일의 로컬 계정을 자동 연결하지 않고 `OAUTH_ACCOUNT_LINK_REQUIRED`로
안내한다. profile link-mode 충돌은 `/profile`로 돌아와 사용자 메시지를 표시한다.
Naver/Kakao는 계속 T-122 미래 작업이다.
**T-119 회원 관리 Admin 보강** (2026-06-06 codex) — `/admin/users` 목록은 `q`
검색과 상태 필터를 함께 적용하고, 상세는 기본 이메일 마스킹 상태로 응답한다.
`reveal=true` + 사유가 있을 때만 원본 이메일을 반환하며 `user.reveal_pii` audit과
최근 audit 목록을 상세 UI에 표시한다.
**T-120 여행계획 Admin 목록/상세/상태 관리** (2026-06-06 codex) —
`/admin/trips` 목록은 `q` 검색, 상태/공개범위/owner 필터와 day/POI/companion/share
count를 제공한다. 상세는 companion/share metadata와 최근 audit을 표시하고, 상태
변경은 `access_reason` 필수 + `trip.update_status` audit으로 기록한다.
**T-121 POI Admin 목록/상세/연결 상태 관리** (2026-06-06 codex) —
`/admin/pois` 목록은 `q` 검색, `trip_id`, `has_broken_link` 필터와 owner 이메일
마스킹을 제공한다. 상세는 `feature_snapshot`, 일정/비용/메모/URL, 추가자 마스킹,
최근 audit을 표시한다. 연결 상태 변경은 Pinvi 로컬 `feature_link_broken_at`만
수정하고 `poi.update_link_status` audit으로 기록한다. feature re-link는 kor-travel-map
client 준비 후로 유지한다.
**T-123 문서 정합 일괄 정정** (2026-06-06 codex) — README/API index의
`GET /search`·`/health/external` 누락을 보강하고, OAuth는 Google-only + Naver/Kakao
future provider 표현으로 맞췄다. share link URL은 `PINVI_WEB_BASE_URL` 기반으로
수정했고, zoom 하한 5, dangling `release-plan.md` 링크, `kor-travel-geo` 오타,
agent-guide 잔여 bullet/trailer를 정리했다.
**T-149 Gemini 책임 목록 정정** (2026-06-06 codex) — README/AGENTS/CLAUDE/SKILL과
`docs/integrations/README.md`에서 본 저장소의 현재 책임을 `AI companion 호출 계약`으로
표현했다. Gemini/Claude/Codex provider 구현은 ADR-020에 따라 별도
`kor-travel-concierge` repo 책임이다.
**T-150 계획/추적 문서 정합화** (2026-06-06 codex) — Sprint 1/3/4/5 status를 최신
main 기준으로 맞추고, Sprint 5 ETL provider asset 계획을 kor-travel-map 책임으로 정정했다.
`resume.md`의 박힌 ADR 목록은 ADR-031까지 갱신했고, stale ADR 후보는 T-151/T-148
후속으로 재분류했다.
**T-151 미기록 ADR 백필** (2026-06-06 codex) — 인증 토큰(ADR-032), Admin
RBAC(ADR-033), Admin audit hash chain(ADR-034)을 구현 기준으로 박고, Sprint 문서의
남은 번호 미배정 placeholder를 번호 없는 후속 후보/구현 기준으로 정리했다.
**T-143 지도/소셜 문서 정정** (2026-06-06 codex) — `frontend.md`의 폐기된 지도
어댑터 표현, 로그인 디자인 문서의 Naver/Kakao 버튼 예시, 통합/data-source 인덱스의
OAuth provider 범위, MCP 문서의 in-process geocoding 호출 표현을 최신 기준으로 정리했다.
**T-147 잔여 문서 정정** (2026-06-06 codex) — KASI rise/set은 POI 생성 당시
snapshot 기준으로 1회 저장하고 날짜/좌표 변경 시 자동 재조회하지 않는다고 명시했다.
`docs/integrations/gemini.md`의 partial unique index는 PostgreSQL `CREATE UNIQUE INDEX
... WHERE deleted_at IS NULL` 문법으로 고쳤다.
**T-142 geofence/admin 정합** (2026-06-06 codex) — FastAPI geofence admin 우회를
토큰 `roles` claim이 아니라 access token `sub` → `app.users.roles` DB 조회 기준으로
바꾸고, Cloudflare Tunnel 기본 운영에서 nginx GeoIP2는 선택 계층임을 문서화했다.
**T-144 여행/장소 검색 UX + 내보내기 설계** (2026-06-06 codex) — `GET /trips` 검색
파라미터, `/features/search` 장소 검색 경계, future `/search` bucket 설계,
print/PDF/GPX 내보내기 계약과 Web 컴포넌트 책임을 문서화했다.
**T-145 backup schema-swap 확정** (2026-06-06 codex) — ADR-022 핫스왑 restore에서
신규 DB instance 방식을 폐기하고, 동일 Postgres database의 `app_restore_<ts>` →
`app` schema-swap 정책으로 확정했다. cut-over는 near-zero downtime(30~90초 목표)
write drain + schema rename + API/Web restart다.
**T-128 실시간 협업 백엔드 설계 + WS 계층** (2026-06-06 codex) — ADR-035로 단일
프로세스 in-memory WebSocket broker 모델을 확정하고, `WS /ws/trips/{trip_id}` 인증/
권한/presence 및 Trip/POI mutation broadcast를 구현했다. 수평 확장 broker는 후속 ADR
대상이다.
**T-138 사용자/보안 스키마 보강** (2026-06-06 codex) — 실제 코드에는 이미 반영된
`users.password_hash/nickname/gender/birth_year_month/residence_sigungu_code/email_status`
문서 drift를 고치고, PIPA 침해 대응 foundation인 `app.security_incidents` 모델,
Alembic 0007, 통합 테스트를 추가했다.
**T-139 동반자/댓글 정합 보강** (2026-06-06 codex) — owner-only 동반자 초대/삭제,
기존 user 이메일 매칭, `trip_invite` email_queue 적재, `app.trip_comments` 모델/
Alembic 0008, 로그인 사용자 댓글 API, 공유 토큰 owner-only 경계와 `comment`
visibility 의미를 구현했다.
**T-140 여행 예산 정합 보강** (2026-06-06 codex) — `trip_day_pois`/`notice_pois`
예산 금액 nonnegative와 currency 대문자 3글자 제약을 추가하고, POI create/update가
`budget_amount`/`actual_amount`/`currency`/`user_url`을 실제 저장하도록 연결했다.
추천 plan copy는 `budget_amount`/`currency`를 보존한다.
**T-141 trip↔지역 구조적 연결** (2026-06-07 codex) — `app.trips`에
`primary_region_code`/`primary_region_source`를 추가하고, Trip API/Admin/Zod schema가
구조화 지역 키를 반환하도록 맞췄다. POI `feature_snapshot`의 region code는 비어 있는
trip primary region을 `poi_snapshot` source로 보강한다.

## 다음 한 작업

> **갱신 (2026-06-28, codex)**: T-240 `pinvi_pii_retention` Dagster job을 완료했다.
> 다음 작업은 **T-241 `pinvi_location_log_archive` Dagster job**이다. 기능 구현 Task는 단위
> 검증을 로컬 WSL ext4 미러에서 수행하고, PR 생성 후 사용자 지시대로 e2e/CI 확인과 merge까지
> 진행한다. 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.

> **갱신 (2026-06-16, claude)**: Expo/web 공용 코드 정리 — `apps/web/lib` 순수 로직 16개 +
> 마커 스타일을 `@pinvi/domain`(신설)으로 모음, markerPalette↔design-tokens 중복 통합. 검증
> typecheck/Vitest 68/build/lint/e2e 52 전부 green. maplibre-vworld-react 이슈 9건 등록
> (digitie/maplibre-vworld-react #2~#10). Expo 앱 추가구현 계획은
> `docs/architecture/expo-implementation-plan.md`로 정리했다. maplibre 이슈 #3(키 주입 훅)
> 해소에 맞춰 **백엔드 `GET /mobile/vworld/token`(server-issued VWorld 키) + 인증 dep Bearer
> 수용을 구현**했다. **모바일 기준 Expo SDK를 53 → 56으로 상향**(ADR-043 갱신). **Sprint M-1
> 활성화 완료(2026-06-16)**: `apps/mobile`을 root workspaces 등록 + Expo SDK 56 의존성 설치
> (`package-lock.json` 갱신, 535 packages), `apps/mobile` typecheck 통과, 전 workspace
> typecheck/lint/web build/Vitest 68 green. (web CI `npm ci`가 이제 Expo 트리 설치 — ADR-041
> 활성화.) **EAS 빌드 준비 완료**: `expo-doctor` 21/21(newArchEnabled 제거/metro/react 단일화).
> **EAS Android development build 성공(2026-06-16)**: EXPO_TOKEN으로 EAS 프로젝트
> `@digitie/pinvi` 생성(projectId app.json 기록), 1차 빌드는 minSdk 23<24(SDK 56 요구)로 실패 →
> **minSdk 24 수정 후 재빌드 성공**(build `c195bd46`, APK 산출
> `expo.dev/artifacts/eas/gGm7b6xYaS3aKLxTn0YIhA-KqHW46HNQZUBensU4gl8.apk`).
> **다음 단계**: dev client(APK) 설치 → 인증 화면 → 지도(maplibre `tileUrlTransform` +
> `/mobile/vworld/token` 결선) → 핵심 화면.

> **갱신 (2026-06-13, claude)**: Expo `apps/mobile` 구조 스캐폴드(ADR-041) + Docker
> 진입 경로 docker-manager화(ADR-040)를 한 PR로 머지했다. Expo 다음 단계는 **Sprint M-1
> 활성화** — `apps/mobile`을 root workspaces에 등록 + `npm install`/`expo install` + 화면
> 구현 + EAS (`apps/mobile/README.md`). Docker는 `kor-travel-docker-manager` 기동이 1차,
> `scripts/docker-app.sh`가 폴백(`docs/runbooks/docker-app.md` §0).

> **갱신 (2026-06-10)**: 기존에 여기 있던 "Sprint 4 PR-B2 / PR-C / PR-D" 후보는
> 모두 완료됐다(지도 UI·trip 상세·POI·협업·E2E·CI 전부 머지). 현재 비의존 후보:

우선순위 후보(kor-travel-map 비의존 작업 우선):

1. ~~**T-106 Telegram 알림 채널**~~ — **Sprint-4 스코프 완료** (#160~#168: client·target CRUD·알림 hook·
   관리 UI·outbox·trip 링킹·trip-link UI). **남은 후속(별 스코프)**: weekly/daily summary Dagster(§7,
   Sprint 5 ETL — 날씨/유가 kor_travel_map 의존), per-user 봇 토큰 vault(현재 단일 시스템 봇).
2. **T-108 운영 배포 자동화** (Sprint 6, ADR-023/ADR-039) — Odroid M1S + N150
   노드 로컬 checkout/build + backup/restore 기반 수동 대체 운영.
3. **kor_travel_map 연동 cutover — ✅ 완료** — T-181(client, #170) + **T-173/174/176/178**(feature read
   라우터 cutover, #171) + **T-175**(trip view batch + `etl_bridge` 제거, #172) + **T-180**(admin
   HTTP client + admin base 12301 정정, #173) + **T-179 백엔드**(`/admin/feature-requests`
   검토→승인/거절 + kor_travel_map change API 릴레이 + audit, #174) + **T-179 web UI**(검토 큐 화면 + 승인/거절,
   2026-06-11). **남은 cross-repo 의존**: §7 합의 5건(review_mode/idempotency/출처태깅/admin인증/
   closure)은 kor_travel_map T-217c 회신 대기 — Pinvi는 문서화된 기본값으로 동작, 확정 시 호출부 조정.
4. **보류: future provider** — T-122 Naver/Kakao OAuth (현재 런타임 provider는 Google만).
5. **T-211 kor_travel_map `curated_features` import — 계약 대기**: Pinvi-native 큐레이션은
   유지하면서, kor_travel_map curated feature 1건을 Pinvi curated plan 1건으로 1:1 복사하는
   후속 흐름. 상세 REST path/schema/idempotency/refresh 정책 확정 후 구현.

## 릴리즈 로드맵

| 버전      | Sprint        | ETA                   | 핵심                                                                     |
| --------- | ------------- | --------------------- | ------------------------------------------------------------------------ |
| `v0.1.0`  | Sprint 4      | released (2026-06-13) | 지도 + `vworld-map-web` + live feature read + CI/CD 재활성               |
| `v0.2.0`  | Sprint 5      | +1                    | 실시간 + ETL + Grafana embed + Backup 1차                                |
| `v1.0.0`  | Sprint 6      | +2                    | MCP 외부 인터페이스 + Backup 핫스왑 UI + Korean geofencing + Odroid+N150 |
| `v1.1.0+` | post-Sprint 6 | 후속                  | PWA / 푸시 / kor-travel-concierge (별 repo)                              |

## 진척도

- [x] git 흐름 정리 (v1 보존 / main 골격 재시작) — T-000
- [x] README / CLAUDE / AGENTS / SKILL — T-001
- [x] docs/architecture / agent-guide / dev-environment — T-002
- [x] docs/decisions (ADR-001 ~ ADR-010) — T-003
- [x] docs/journal / resume / tasks — T-004
- [x] docs/data-model / postgres-schema / test-strategy — T-005
- [x] docs/kor-travel-map-integration — T-006
- [x] docs/sprints/README + SPRINT-1 ~ SPRINT-6 — T-007
- [x] docs/spec/v8/ 6편 적용 노트 — T-008
- [x] docs/design/marker-palette + 루트 DESIGN.md / airbnb-marker-palette.html 복원 — T-009
- [x] docs/architecture/frontend.md (Next.js + Expo 공용 monorepo) — T-010
- [x] docs/architecture/user-location.md (Geolocation + expo-location) — T-011
- [x] docs/architecture/notice-plans.md (v1 추천 plan 도메인 이전) — T-012
- [x] v1 자산 전수 조사 + 매핑 매트릭스 (`docs/v1-to-v2-mapping.md`) — T-013
- [x] docs/api/ 11개 신규 (auth/users/trips/pois/features/notice-plans/storage/admin/public/regions/health/websocket + README + common) — T-014
- [x] docs/integrations/ 9개 신규 (resend/social-login/gemini/telegram/kakao-map/sentry/loki + README) — T-015
- [x] docs/runbooks/ 7개 신규 (local-dev/docker-app/etl/admin/file-storage/odroid-docker + README) — T-016
- [x] docs/compliance/ 4개 신규 (lbs-act/pipa/data-policy + README) — T-017
- [x] docs/conventions/ 6개 신규 (coding-style/database/testing/geospatial/normalization + README) — T-018
- [x] docs/architecture/ 5개 추가 (map-marker-design/youtube-travel-intelligence/mcp-tools/dagster-etl-bridge/api-contract) — T-019
- [x] AI agent 진입 절차 강화 (README/AGENTS/CLAUDE) — T-020
- [x] Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 5분 주기 PR 감시 — T-023
- [x] Sprint 1 진입 PR (apps + packages scaffolding) — T-030
- [x] GitHub Actions secret / branch protection 적용 상태 확인 — T-062
- [x] 최신 main 기준 문서 충돌 정정 — T-064
- [x] 최신 kor-travel-map/kor-travel-geo/KASI 계약 문서 반영 — T-068
- [x] production API/Web URL + OAuth/CORS 보안 문서화 — T-069
- [x] KASI 특일/POI 출몰시각 Dagster 구현 — T-067
- [x] Sprint 2 잔여 마감(email queue/reset/api_call_log/integration CI) — T-070
- [x] Google OAuth profile 연결/해제 UI — T-073
- [x] PR-C frontend 지도 shell dependency pin/import/e2e — T-074
- [x] Trip / notice plan 사용자 shell — T-075
- [x] Admin Grafana iframe embed — T-110
- [x] 한국 전용 geofencing FastAPI fallback — T-109
- [x] Backup snapshot foundation + `/admin/backup` 1차 UI — T-115
- [x] OAuth provider 범위 Google-only 정리 — T-116
- [x] 회원가입 약관 동의 화면 + `user_consents` 저장 보강 — T-117
- [x] Google OAuth 계정 매칭 / profile 연결 UX 보강 — T-118
- [x] 회원 관리 Admin 검색/상세 audit UX 보강 — T-119
- [x] 여행계획 Admin 목록/상세/상태 관리 — T-120
- [x] POI Admin 목록/상세/연결 상태 관리 — T-121
- [x] 문서 정합 일괄 정정 — T-123
- [x] Gemini 책임 목록 정정 — T-149
- [x] 계획/추적 문서 정합화 — T-150
- [x] 미기록 ADR 백필(auth-token/RBAC/audit-chain) — T-151
- [x] 지도/소셜 문서 정정(Google-only, kor-travel-geo stack) — T-143
- [x] 잔여 문서 정정(rise/set, Gemini partial unique index) — T-147
- [x] geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리 — T-142
- [x] 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계 — T-144
- [x] backup 핫스왑 동일호스트 schema-swap 확정 — T-145
- [x] 실시간 협업 백엔드 설계 + WS 계층 — T-128
- [x] `users` 누락 컬럼 문서 정합 + `security_incidents` 테이블 추가 — T-138

## 다음 ADR 후보

- Sprint 5 진입 시 — optimistic lock 세부 분리, Pinvi Dagster `app` job,
  Loki/Grafana embed 정책이 구현 결정으로 필요하면 ADR-037부터 배정

## 박힌 ADR

- ADR-001 ~ ADR-009: v2 시작 결정
- ADR-010: SPEC V8 채택
- ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조
- ADR-012: 사용자 위치 정보 획득 (Geolocation + expo-location)
- ADR-013: Notice plan 도메인 v1 → v2 이전 + 명명 분리
- ADR-014: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리
- ADR-015: 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- ADR-016: AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책
- ADR-017: CodeGraph 인덱스 + agent별 고정 worktree 운영
- ADR-018: 한국 전용 서비스 — geofencing 안전망
- ADR-019: Pinvi MCP 외부 인터페이스 서빙(read-only)
- ADR-020: T-107 Gemini AI Companion 별도 서비스 분리
- ADR-021: GitHub Actions CI/CD 재활성화
- ADR-022: Backup / Restore 핫스왑 정책
- ADR-023: 운영 하드웨어 확장 — Odroid M1S + N150 16GB 병행
- ADR-024: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러
- ADR-025: 사용자 대면 geocoding은 `kor-travel-geo` v2 REST API 직접 호출
- ADR-026: Pinvi ↔ `kor-travel-map`은 최신 OpenAPI HTTP 계약으로 전환
- ADR-027: kor-travel-map 통합은 운영급 HTTP 서비스로 확정
- ADR-028: 정규 `feature_id` 포맷은 kor-travel-map `make_feature_id` 출력
- ADR-029: `notice_plans` 명칭 충돌 해소 — 큐레이션은 `curated_trip_plans`
- ADR-030: 외부 API 규약 정본
- ADR-031: POI delete 정책(soft) + `trip_day_pois.feature_id` nullable
- ADR-032: 인증 토큰 기준(access JWT + httpOnly cookie)
- ADR-033: Admin 권한은 `users.roles[]` + 서버 dependency
- ADR-034: Admin 감사 로그 append-only hash chain
- ADR-035: Trip WebSocket in-memory broker
- ADR-036: Curated trip plan 자체 큐레이션 + kor_travel_map `curated_features` import + nullable feature link
- ADR-037: 로컬 고정 포트 재배정 (5432/12101/12105/12301/12501/12505)
- ADR-038: HTTP rate limit은 운영에서 Postgres 고정-window 버킷 사용
- ADR-039: 운영 노드 간 Postgres streaming replication 미사용
- ADR-040: Docker 빌드/실행은 kor-travel-docker-manager 1차 + `scripts/docker-app.sh` 폴백
- ADR-041: Expo `apps/mobile` 구조 스캐폴드 — 활성화는 Sprint M-1
- ADR-042 ~ ADR-048: 로컬 포트 재정렬, Expo/mobile 지도 기준, Web `vworld-map-web`,
  운영 도메인 비노출, `kor-travel-geo` v2 공개 API key 재사용 계약

## 운영 지시

- Sprint 4 완료 전까지 새 PR은 `docs/runbooks/pr-review-sprint4.md` 기준으로
  리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리 sync → 검증 → 머지를 반복한다.
- `.github/workflows/codex-pr-review.yml`이 PR 생성·전환·새 commit 이벤트에서,
  `.github/workflows/codex-pr-monitor.yml`이 예약/수동 보정 감시에서 외부 API key 없이
  최신 head SHA review reminder 마커를 확인한다. 실제 리뷰는 에이전트 또는 사람이
  MCP 설정(CodeGraph / Playwright / Sequential Thinking / Telegram)으로 수행한다.

## 차단 사유 / 결정 대기

- required status check는 `Aggregate CI gate`로 적용
- T-130 `/public/*`은 완료. 앱 내부 공통 rate-limit 미들웨어만 T-195 후속.
