# resume.md

## 다음 한 작업 (2026-06-06 감사 후)

문서·구현 정합성 전수 감사 완료 — `docs/audit/2026-06-06-doc-impl-audit.md`.
사용자 결정 DEC-01~10 확정(`docs/decisions-needed-2026-06-06.md`). krtour-map
비의존 루프는 T-112 MCP 외부 인터페이스까지 PR/머지 완료했다. **다음 비의존 후보는
T-108 운영 배포 자동화, T-129의 `/geo/*`·`/regions/*` slice, T-146 location-audit
outbox slice를 현재 main 기준으로 재평가한다.** T-172~T-181/T-179/T-180은
krtour-map HTTP/admin 계약 연동 작업이므로 이 비의존 루프에서는 제외한다.

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

**krtour 연동 작업 unblock** (2026-06-10, `docs/reviews/2026-06-10-krtour-cross-repo-decisions.md`):
krtour `origin/main 0e45bd7`에서 ADR-048/T-216a~g 머지 확인 — **T-181 잔여(problem+json·
`meta.page`·batch `found`·`max_items`)가 대기 해제, 즉시 실행 가능**. T-179/T-180도
actionable (krtour ADR-051이 `/v1/admin/features*` change API를 전송 구간 정본으로 승인,
합의 5건은 krtour T-217c 회신 대기). 주의: **krtour admin API base는 9011 `/v1/admin/*`**
(9012는 admin UI) — T-180에서 `tripmate_krtour_map_admin_base_url` 의미 재정의 필요.

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
`TRIPMATE_RESTORE_API_TRIGGER` guard를 추가했다. `restore_backup_hotswap()`은 프로세스 내부
`asyncio.Lock`에 더해 Postgres `pg_try_advisory_lock`을 잡아 다중 워커/프로세스 동시
schema-swap을 차단한다. API restore는 swap 전 `backup.restore_hotswap_started`를 현재
canonical audit chain에 먼저 commit하고, swap 성공 reflection은
`app_previous_<restore_id>.admin_audit_log`에 append해 오래된 snapshot에 현재 admin이 없어도
success audit가 FK로 깨지지 않게 했다. `.env.example`/Settings/runbook도
`TRIPMATE_RESTORE_*` 실행 설정과 `TRIPMATE_RESTORE_APP_ROLE`을 정렬했다.

**T-112 TripMate MCP 외부 인터페이스 서빙 완료** (2026-06-09): `app.mcp_tokens` 테이블과
Argon2id-hashed `mcp_<JWT>` 토큰 발급/회수 API를 추가했다. 사용자 `/settings/mcp-tokens`와
admin `/admin/mcp-tokens`에서 원문 1회 표시, 목록 마스킹, 회수가 가능하다. `/mcp/sse`는
Bearer MCP 토큰으로 5개 read-only tool descriptor를 제공하고, `/mcp/tools/{tool_name}`은
`list_trips`, `get_trip`, `list_pois`, `search_features`, `get_user_profile`을 호출한다.
`search_features`는 krtour-map OpenAPI HTTP client 경계만 사용하며, stdio bridge/full MCP
session proxy는 후속 작업으로 분리한다.

**T-177 사용자 feature 제안 큐 완료** (2026-06-09): `app.feature_suggestions` 테이블을
추가하고 `POST /features/requests`, `GET /features/requests/{request_id}`를 TripMate
DB 큐 기반으로 실구현했다. POST는 krtour-map을 직접 호출하지 않고 즉시 201을 반환하며,
사용자별 24시간 20건 rate-limit와 pending 중복 dedup을 적용한다. 응답은
`pending/approved/rejected/added/duplicate` 상태 enum과 제안 입력값을 함께 내려준다.

**T-133 Admin priority-3 엔드포인트·페이지 완료** (2026-06-09): TripMate app DB만 읽는
`GET /admin/stats/overview`, `GET /admin/api-calls`, CPO 전용
`GET /admin/audit/location`을 추가하고 `/admin`, `/admin/api-calls`,
`/admin/audit/location` 화면을 실제 데이터 테이블로 결선했다. 위치 감사 로그는 좌표를
4자리로 마스킹하고 chain 깨짐 시 `X-Chain-Broken: true` 헤더를 반환한다. `/admin/features`
상세 편집, `/admin/etl`, seed/reset은 krtour-map 또는 운영 안전장치 결선 전 상태로
명시적으로 남긴다.

**T-132 trip 하위 리소스 분할 완료** (2026-06-09): `/trips/{trip_id}` delete/owner
transfer, `/copy`, day CRUD, anonymous shared view, trip/POI attachment metadata CRUD,
day distance matrix, nearest-neighbor optimize API를 추가했다. Pydantic/Zod schema와
`@tripmate/api-client` endpoint를 확장했고, 통합 테스트는 day 삭제 cascade, copy +
attachment 복제, shared view, distance matrix/optimize persist 흐름을 검증한다.

**T-111 Backup/Restore UI 핫스왑 완료** (2026-06-08): `/admin/backup` snapshot 목록에
Restore schema-swap 다이얼로그를 연결하고 `POST /admin/backup/restore-hotswap` API를
추가했다. API는 `TRIPMATE_RESTORE_HOTSWAP_SCRIPT_PATH`를 실행해 `preparing` /
`restoring` / `validating` / `draining` / `switching` phase를 반환하고 성공/실패 모두
admin audit에 남긴다. 기본 `scripts/restore-hotswap.sh`는 custom dump를 임시 restore
schema로 remap한 뒤 `TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 schema rename을
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
`search_features`는 krtour-map Python 함수/DB 직접 호출이 아니라 OpenAPI HTTP
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
`/features/{feature_id}` 라우터, krtour-map client Protocol, trip 상세 view builder가
더 이상 `feature_id`를 UUID로 파싱하지 않는다. `feature_id`는 ADR-028에 따라
krtour-map `make_feature_id` 출력을 불투명 문자열로 저장·전달한다.

**T-162 Resend webhook fail-open 잔존 완료** (2026-06-08): secret이 비어 있을 때
`TRIPMATE_ENVIRONMENT` 기본값 `development`만으로 unsigned webhook이 열리지 않도록
`TRIPMATE_RESEND_WEBHOOK_ALLOW_UNSIGNED` 명시 opt-in을 추가했다. production에서는 opt-in이
켜져도 secret 미설정 시 `503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다.

**T-131 Trip 상세 view 연결 완료** (2026-06-07): `GET /trips/{trip_id}`가 더 이상
trip 메타만 반환하지 않고 `trip_view_builder.build_trip_view`를 통해 trip/day/POI tree,
companions, share link metadata, `broken_feature_count`를 반환한다. krtour-map client가
미주입된 환경에서는 503 대신 저장된 `feature_snapshot`으로 fallback한다.

**T-127 MCP 외부 인터페이스 정본화 완료** (2026-06-07): ADR-019 외부 MCP 계약은
`docs/architecture/mcp-server.md`가 단일 진실이며, 1차 tool은 read-only 5개로 고정했다.
`list_trips.status` enum을 실제 trip status와 맞추고, 사용자/admin MCP 토큰 발급·회수
HTTP endpoint를 `docs/api/users.md` / `docs/api/admin.md` / runbook에 명시했다.

**T-161 README `/search` 앵커 정합 완료** (2026-06-07): `docs/api/features.md`의
통합 검색 heading을 `2.7 GET /search`로 안정화하고, README 링크를
`#27-get-search`로 교정했다. krtour-map 요구사항 문서의 잘못된 features.md 절 번호도
§2.7로 맞췄다.

**T-126 POI 생성 경로 단일화 완료** (2026-06-07): v2 정본 POI 생성/수정/삭제/정렬
경로는 `/trips/{trip_id}/pois` 계열로 고정했다. `docs/api/trips.md`의 오래된
`/days/{day_index}/items` 문서 블록을 정본 경로 설명으로 교체하고, 공용
`packages/api-client`에 `poiApi` wrapper를 추가했다.

**T-154 Resend webhook C-22 완결 완료** (2026-06-07): 운영성 환경에서
`TRIPMATE_RESEND_WEBHOOK_SECRET`이 비어 있거나 `whsec_` 표준 base64 형식이 아니면
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
`CF-IPCountry`만 믿지 않고 `X-TripMate-Geofence-Proxy` shared secret이 맞을 때만 country
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

**T-210c(ADR-045 Phase 6) TripMate 부분 완료** (2026-06-06): `apps/etl`은 `app`
schema 소유 job만 보유해 이관할 feature provider Dagster 스켈레톤이 없음 확인 +
`dagster-etl-bridge.md`/`runbooks/etl.md` phantom 스켈레톤 정합 + asset `__init__`
경계 가드. 남은 T-210d=T-066, T-210e는 krtour HTTP/OpenAPI 확정 후.

**T-152 Telegram 완료 알림 MCP 완료** (2026-06-07): 모든 agent worktree에
`mcp-telegram` 등록 + `scripts/mcp_telegram_start.py` + 로컬 `.env.mcp-telegram`
(gitignore). PR 후 `send_message`로 요약+링크 발송. GitHub secret 미사용. 실제 전송 검증.

**T-153 PR 리뷰 모니터 MCP 알림 보강** (2026-06-07): `python-krtour-map`식 MCP
진입(CodeGraph / Playwright / Sequential Thinking / Telegram)을 PR review reminder
본문과 공용 모니터 스크립트에 반영했다. PR 이벤트는 `opened` / `ready_for_review` /
`reopened` / `synchronize`에서 즉시 실행하고, 5분 schedule은 지연 가능한 보정 신호로
운영한다.

**T-136 Resend webhook Svix 서명 검증 완료** (2026-06-07): `/webhooks/resend`가
raw body 기준 Svix HMAC-SHA256 서명을 검증한다. `TRIPMATE_RESEND_WEBHOOK_SECRET`이
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
테스트 27개 green. Sprint 1~3 + Sprint 4 PR-A(#15 CI 복원) / PR-B(#16 features
API scaffolding) 머지 완료. 통합 테스트 harness(PostGIS testcontainer)가
`apps/api/tests/integration` 에 박힘 — 이후 백엔드 검증의 기반. async alembic 의
DDL 미커밋 잠재 버그도 함께 수정(`alembic/env.py`). 진행 추적 문서 정합성은
`resume.md` + `tasks.md` + `journal.md` 교차 확인이 기준(codex 2026-06-01 정리).
**개발 환경 모델 ADR-024로 확정** — NTFS worktree=git source of truth(Windows
git.exe) / WSL ext4=일회용 테스트 미러. 셋업·검증·함정 절차는
`docs/dev-environment.md`(에이전트 공통).
**Geocoding ADR-025로 확정** — 사용자 대면 geocoding(주소/좌표/행정구역)은
`kraddr-geo` v2 REST API 직접 호출(`docs/integrations/kraddr-geo.md`), feature
데이터는 krtour-map OpenAPI HTTP 계약(ADR-026). 열린 결정 8건은
`docs/architecture/geocoding-open-decisions.md`(잠정값으로 진행).
**문서 충돌 정정** (2026-06-02 codex) — `agent-guide`, `local-dev`, `architecture`
등에 남아 있던 ADR-024 이전 WSL git 모델, ADR-015 이전 Kakao/marker-wrapper 표현,
ADR-025 이전 `kraddr.geo` in-process 검색 표현을 정정.
**T-062 운영 게이트 확인/적용** (2026-06-02 codex) — GitHub Actions secret은
`0`개가 의도된 상태다. `OPENAI_API_KEY`는 쓰지 않는다. `codex-pr-review` /
`codex-pr-monitor`는 외부 API 호출 없이 review reminder만 남기도록 변경. `main`에는
repository ruleset `main-pr-only`(id `17146781`)를 적용했다(PR 필수, squash-only,
linear history, force push/deletion 차단, bypass 없음). Classic branch protection은
없다. required status check는 path-filtered workflow가 docs-only PR을 막을 수 있어
aggregate gate 설계 뒤 적용한다.
**로컬 dev 포트 고정** (2026-06-02 codex) — API `9021`, Web `9022`, Dagster `9023`.
`scripts/dev-up.sh`가 해당 포트를 점유한 프로세스를 종료하고 같은 포트로 다시 올린다.
프론트 실행은 계속 WSL ext4 미러 기준이며, Playwright e2e만 Windows에서 실행한다.
**RustFS / Docker app 포트 고정** (2026-06-03 codex) — RustFS API `9003`, console
`9004`. `scripts/docker-app.sh`가 Docker app build/up/down/status/logs/smoke를
제공하고, 시작 전 API `9021`, Web `9022`, RustFS `9003`/`9004` 점유 항목을
정리한다. `scripts/docker-app-smoke-test.sh`는 호환 wrapper다.
**krtour-map 연동 포트 고정** (2026-06-03 codex) — `python-krtour-map` 독립
프로그램의 API는 `9011`, admin은 `9012`를 기준으로 문서화한다. TripMate가 직접
소유하지 않는 서비스이므로 실행/검증은 그쪽 저장소 런북이 권위다.
**krtour-map 최신 main 계약 반영** (2026-06-04 codex) — 최신 `python-krtour-map`
`main`의 `openapi.user.json` / `openapi.json`을 확인해 ADR-026을 추가했다.
TripMate ↔ krtour-map은 더 이상 함수 직접 호출이 아니라 OpenAPI HTTP 계약(API
`9011`, admin `9012`)이다. `feature` / `provider_sync` schema 소유권은 그대로
krtour-map에 있고, TripMate는 `feature_id` + snapshot만 저장한다.
**KASI 특일/출몰시각 계약 추가** (2026-06-04 codex) — `python-kasi-api`를 통해
특일 계열 5개 dataset을 하루 1회, 과거 6개월~미래 18개월 범위로 upsert한다.
삭제는 없다. POI 생성 시에는 좌표와 방문일로 "위치별 해달 출몰시각 정보조회"를
1회 호출해 `app.trip_poi_rise_sets`에 저장한다.
**T-067 KASI 구현 완료** (2026-06-05 codex) — `apps/etl`에
`tripmate_kasi_special_days` asset과 `kasi_poi_rise_set_job`을 추가했고, API는 POI
생성 시 `app.trip_poi_rise_sets` 초기 row를 만든다. krtour-map 연계 없이
`python-kasi-api` + `DATA_GO_KR_SERVICE_KEY`만 사용한다.
**Production URL 확정** (2026-06-05 codex) — 운영 API는
`https://tripmateapi.digitie.mywire.org`, 운영 Web은
`https://tripmate.digitie.mywire.org`다. Google 승인된 JavaScript 원본은 Web origin,
OAuth redirect URI는 API origin의 `/auth/oauth/google/callback`이다. CORS는 Web
origin만 허용하고, 운영 cookie는 `TRIPMATE_ENVIRONMENT=production`으로 Secure를
강제한다.
**T-070 Sprint 2 잔여 마감** (2026-06-05 codex) — `email_queue` SKIP LOCKED
worker batch, 비밀번호 재설정 요청/확정 API, `api_call_log` httpx event hook
통합 테스트를 추가했다. `.github/workflows/api.yml`은 PR에서 `pytest
tests/integration -q`를 실행한다. Google OAuth client id는 네 TripMate worktree의
로컬 `.env`에 반영했다.
**T-063 maplibre consumer sync 완료** (2026-06-05 codex) — `maplibre-vworld-js`
PR #46(`docs/consumer-feature-catalog.md` 정합화, `build-and-test` green, merge
`f1dd74b9`)를 머지했고, TripMate §6/§11.1 snapshot과 Sprint 4 라이브러리 선행
조건을 완료 처리했다. 실제 `maplibre-vworld` dependency pin/import/e2e는 PR-C
frontend 구현에서 처리한다.
**T-065 aggregate CI gate 적용** (2026-06-05 codex) — 모든 PR에서 실행되는
`Aggregate CI gate` workflow를 추가했다. `api` / `web` / `etl`은 path filter를
유지하고, aggregate gate가 변경 파일 기준으로 필요한 check만 기다린다. `main-pr-only`
ruleset required status check는 `Aggregate CI gate`로 적용한다.
**T-071 Google OAuth 로그인 UI 연결** (2026-06-05 codex) — 로컬
`TRIPMATE_GOOGLE_OAUTH_CLIENT_ID` 반영 후 로그인 화면에서 `/auth/oauth/providers`를
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
`/features/in-bounds`와 krtour-map API `9011` 미호출을 확인했다.
**T-075 Trip / notice plan 사용자 shell** (2026-06-05 codex) — krtour-map feature
조회 없이 공용 API client에 `/trips` / `/notice-plans` 사용자 endpoint를 추가하고,
Web `/trips`와 `/notice-plans` route, 사용자 navigation shell, 빈 상태, Trip 생성,
notice plan copy action을 연결했다. Windows Playwright smoke에서 `/features/*`와
krtour-map API `9011` 미호출을 확인했다.
**T-110 Admin Grafana iframe embed** (2026-06-05 codex) — `/admin/grafana`에
anonymous viewer용 Grafana iframe shell을 추가하고 `NEXT_PUBLIC_GRAFANA_URL`,
`NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`, Web `frame-src` CSP를 문서/환경변수와 맞췄다.
Grafana 컨테이너/provisioning 본체는 Sprint 5 인프라 작업으로 남겼다.
**T-109 한국 전용 geofencing FastAPI fallback** (2026-06-05 codex) —
`TRIPMATE_GEOFENCE_*` 환경변수와 `GeofenceMiddleware`를 추가했다. 기본 비활성이고,
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
최근 audit을 표시한다. 연결 상태 변경은 TripMate 로컬 `feature_link_broken_at`만
수정하고 `poi.update_link_status` audit으로 기록한다. feature re-link는 krtour-map
client 준비 후로 유지한다.
**T-123 문서 정합 일괄 정정** (2026-06-06 codex) — README/API index의
`GET /search`·`/health/external` 누락을 보강하고, OAuth는 Google-only + Naver/Kakao
future provider 표현으로 맞췄다. share link URL은 `TRIPMATE_WEB_BASE_URL` 기반으로
수정했고, zoom 하한 5, dangling `release-plan.md` 링크, `python-kraddr-geo` 오타,
agent-guide 잔여 bullet/trailer를 정리했다.
**T-149 Gemini 책임 목록 정정** (2026-06-06 codex) — README/AGENTS/CLAUDE/SKILL과
`docs/integrations/README.md`에서 본 저장소의 현재 책임을 `AI companion 호출 계약`으로
표현했다. Gemini/Claude/Codex provider 구현은 ADR-020에 따라 별도
`tripmate-ai-companion` repo 책임이다.
**T-150 계획/추적 문서 정합화** (2026-06-06 codex) — Sprint 1/3/4/5 status를 최신
main 기준으로 맞추고, Sprint 5 ETL provider asset 계획을 krtour-map 책임으로 정정했다.
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

> **갱신 (2026-06-10)**: 기존에 여기 있던 "Sprint 4 PR-B2 / PR-C / PR-D" 후보는
> 모두 완료됐다(지도 UI·trip 상세·POI·협업·E2E·CI 전부 머지). 현재 비의존 후보:

우선순위 후보(krtour-map 비의존 작업 우선):

1. **T-106 Telegram 후속 슬라이스** (백엔드 완성 #160~#166 — client·target CRUD·hook·UI·outbox·trip링킹):
   - **남음**: 프론트 trip-link UI(trip 상세에서 `/trips/{id}/telegram-targets` 연결/해제),
     weekly/daily summary Dagster 스케줄(§7.1/7.2, Sprint 5 ETL — 날씨/유가는 krtour-map 의존),
     per-user 봇 토큰(vault/pgcrypto, 현재는 단일 시스템 봇), PIPA 위탁자 명시(§10).
2. **T-108 운영 배포 자동화** (Sprint 6, ADR-023) — Odroid M1S + N150 multi-platform
   Docker 빌드 + 두 노드 streaming replication.
3. **krtour 연동 unblock 작업** — T-181 잔여(problem+json·`meta.page`·batch `found`·
   `max_items`), T-179/T-180(krtour `/v1/admin/features*` change API 연동). 위 unblock 노트 참조.
4. **보류: future provider** — T-122 Naver/Kakao OAuth (현재 런타임 provider는 Google만).

## 릴리즈 로드맵

| 버전 | Sprint | ETA | 핵심 |
|------|--------|-----|------|
| `v0.1.0` | Sprint 4 | 다음 | 지도 + maplibre-vworld finalize + CI/CD 재활성 |
| `v0.2.0` | Sprint 5 | +1 | 실시간 + ETL + Grafana embed + Backup 1차 |
| `v1.0.0` | Sprint 6 | +2 | MCP 외부 인터페이스 + Backup 핫스왑 UI + Korean geofencing + Odroid+N150 |
| `v1.1.0+` | post-Sprint 6 | 후속 | PWA / 푸시 / tripmate-ai-companion (별 repo) |

## 진척도

- [x] git 흐름 정리 (v1 보존 / main 골격 재시작) — T-000
- [x] README / CLAUDE / AGENTS / SKILL — T-001
- [x] docs/architecture / agent-guide / dev-environment — T-002
- [x] docs/decisions (ADR-001 ~ ADR-010) — T-003
- [x] docs/journal / resume / tasks — T-004
- [x] docs/data-model / postgres-schema / test-strategy — T-005
- [x] docs/krtour-map-integration — T-006
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
- [x] 최신 krtour-map/kraddr-geo/KASI 계약 문서 반영 — T-068
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
- [x] 지도/소셜 문서 정정(Google-only, kraddr-geo stack) — T-143
- [x] 잔여 문서 정정(rise/set, Gemini partial unique index) — T-147
- [x] geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리 — T-142
- [x] 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계 — T-144
- [x] backup 핫스왑 동일호스트 schema-swap 확정 — T-145
- [x] 실시간 협업 백엔드 설계 + WS 계층 — T-128
- [x] `users` 누락 컬럼 문서 정합 + `security_incidents` 테이블 추가 — T-138

## 다음 ADR 후보

- T-148 이후 — Sprint 4 backend 재작성 과정에서 viewport cache / feature snapshot
  동기화 정책이 실제 구현 결정으로 필요하면 신규 ADR 작성
- Sprint 5 진입 시 — optimistic lock 세부 분리, TripMate Dagster `app` job,
  Loki/Grafana embed 정책이 구현 결정으로 필요하면 ADR-036부터 배정

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
- ADR-019: TripMate MCP 외부 인터페이스 서빙(read-only)
- ADR-020: T-107 Gemini AI Companion 별도 서비스 분리
- ADR-021: GitHub Actions CI/CD 재활성화
- ADR-022: Backup / Restore 핫스왑 정책
- ADR-023: 운영 하드웨어 확장 — Odroid M1S + N150 16GB 병행
- ADR-024: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러
- ADR-025: 사용자 대면 geocoding은 `python-kraddr-geo` v2 REST API 직접 호출
- ADR-026: TripMate ↔ `python-krtour-map`은 최신 OpenAPI HTTP 계약으로 전환
- ADR-027: krtour-map 통합은 운영급 HTTP 서비스로 확정
- ADR-028: 정규 `feature_id` 포맷은 krtour-map `make_feature_id` 출력
- ADR-029: `notice_plans` 명칭 충돌 해소 — 큐레이션은 `curated_trip_plans`
- ADR-030: 외부 API 규약 정본
- ADR-031: POI delete 정책(soft) + `trip_day_pois.feature_id` nullable
- ADR-032: 인증 토큰 기준(access JWT + httpOnly cookie)
- ADR-033: Admin 권한은 `users.roles[]` + 서버 dependency
- ADR-034: Admin 감사 로그 append-only hash chain
- ADR-035: Trip WebSocket in-memory broker

## 운영 지시

- Sprint 4 완료 전까지 새 PR은 `docs/runbooks/pr-review-sprint4.md` 기준으로
  리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리 sync → 검증 → 머지를 반복한다.
- `.github/workflows/codex-pr-review.yml`이 PR 생성·전환·새 commit 이벤트에서,
  `.github/workflows/codex-pr-monitor.yml`이 예약/수동 보정 감시에서 외부 API key 없이
  최신 head SHA review reminder 마커를 확인한다. 실제 리뷰는 에이전트 또는 사람이
  MCP 설정(CodeGraph / Playwright / Sequential Thinking / Telegram)으로 수행한다.

## 차단 사유 / 결정 대기

- required status check는 `Aggregate CI gate`로 적용
- Sprint 4 backlog 중 merge 완료 / 미완료 구분을 `tasks.md`에 재기록 필요
