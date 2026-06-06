# journal.md — 작업 일지 (역시간순)

가장 위가 가장 최근. 새 엔트리는 위에 append.

## 2026-06-06 (codex) — T-128 실시간 협업 백엔드 설계 + WS 계층

**작업**: Sprint 5 실시간 협업의 krtour-map 비의존 backend slice를 구현했다.

**변경**:
- `docs/decisions.md` ADR-035 — Trip WebSocket은 단일 프로세스 in-memory broker로
  시작하고, 다중 worker fan-out/durable replay는 후속 ADR로 분리했다.
- `apps/api/app/services/realtime_broker.py` — trip별 connection set, presence,
  JSON envelope broadcast, 테스트 reset/count helper를 추가했다.
- `apps/api/app/api/v1/ws.py` — `WS /ws/trips/{trip_id}` 인증(cookie/query token),
  trip 권한 확인, heartbeat/cursor/error 수신 루프를 추가했다.
- `apps/api/app/api/v1/{trips,pois}.py` — Trip/POI mutation 성공 후 `trip.updated`,
  `poi.created/updated/deleted/reordered` 이벤트를 publish한다.
- `docs/architecture/websocket-broker.md`, `docs/api/websocket.md` — broker 결정,
  close code, presence/broadcast 범위와 구현 체크리스트를 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-128 완료와 다음 비의존 후보 T-138을 반영했다.

**검증**:
- WSL2 ext4 mirror: ruff / mypy / realtime broker unit test / WS integration test /
  Trip·POI 기존 통합 테스트
- NTFS worktree: `git diff --check`

**다음**: T-138 `users` 누락 컬럼 + `security_incidents` 테이블 추가.

## 2026-06-06 (codex) — T-145 backup schema-swap 확정

**작업**: 감사 D-19 범위의 Backup/Restore 핫스왑 정책을 Odroid M1S/N150 단일 노드
예산에 맞춰 정리했다.

**변경**:
- `docs/decisions.md` ADR-022 — 신규 DB instance 방식을 폐기하고, 동일 Postgres
  database 안의 `app_restore_<ts>` → `app` schema-swap으로 확정했다.
- `docs/architecture/backup-restore.md`, `docs/runbooks/backup-restore.md` — precheck,
  restore schema 준비, validation, write drain, schema rename, rollback, previous schema
  retention(N150 7일 / Odroid 24시간)을 문서화했다.
- `docs/sprints/SPRINT-6.md` — T-111 산출물/시나리오를 schema-swap 기준으로 정정했다.
- `apps/web/app/(admin)/admin/backup/page.tsx` — Restore placeholder를 신규 DB/DB URL
  cut-over가 아니라 schema-swap future workflow로 고쳤다.
- `docs/resume.md`, `docs/tasks.md` — T-145 완료와 다음 비의존 후보 T-128을 반영했다.

**검증**:
- NTFS worktree: stale 신규 DB/DATABASE_URL cut-over 표현 검색, `git diff --check`
- WSL2 ext4 mirror: Web typecheck

**다음**: T-128 실시간 협업 백엔드 설계 + WS 계층.

## 2026-06-06 (codex) — T-144 여행/장소 검색 UX + 내보내기 설계

**작업**: 감사 D-16/D-17 범위의 사용자 여행 검색, 장소 검색 drawer, PDF/GPX/print
내보내기 설계를 문서화했다.

**변경**:
- `docs/api/trips.md` — `GET /trips` 검색 파라미터(`q`, bucket/status/date/sort)와
  `exports/print-data`, `exports/gpx`, `exports/pdf` 계약을 추가했다.
- `docs/api/features.md` — 장소 검색을 실제 경로 `GET /features/search`로 분리하고,
  통합 `GET /search`는 T-129 future bucket 설계로 정리했다.
- `docs/architecture/frontend.md`, `docs/spec/v8/03-frontend.md` — Trip search bar,
  place search drawer, export menu, print route 책임과 krtour-map unavailable UX를
  문서화했다. Naver/Kakao 검색 fallback은 쓰지 않는다.
- `docs/api/common.md`, `docs/api/README.md`, `docs/spec/v8/02-backend.md` — rate limit,
  인덱스, SPEC 적용 노트를 같은 계약으로 맞췄다.
- `docs/resume.md`, `docs/tasks.md` — T-144 완료와 다음 비의존 후보 T-145를 반영했다.

**검증**:
- NTFS worktree: 문서 stale pattern 검색, `git diff --check`

**다음**: T-145 backup 핫스왑 동일호스트 schema-swap 확정.

## 2026-06-06 (codex) — T-142 geofence/admin 정합

**작업**: 감사 D-13/D-24 범위의 geofence admin 우회와 nginx GeoIP2 계층 과잉 표현을
정리했다.

**변경**:
- `apps/api/app/middleware/geofence.py` — KR/우회 path는 그대로 빠르게 통과시키고,
  KR 외 또는 strict unknown 차단 후보일 때만 access token `sub`로 `app.users.roles`를
  조회해 admin/operator/cpo 우회를 판단하도록 변경했다. token `roles` claim은 더 이상
  신뢰하지 않는다.
- `apps/api/tests/unit/test_geofence_middleware.py` — DB-role resolver 기반 admin 우회와
  token `roles` claim 단독 우회 차단 회귀 테스트를 추가했다.
- `docs/architecture/korea-only-policy.md`, `docs/runbooks/korea-only.md` — 단일
  Cloudflare Tunnel 기본 운영은 Cloudflare WAF + FastAPI fallback이며, nginx GeoIP2는
  별도 공개 edge가 있을 때의 선택 계층으로 정리했다.
- `docs/resume.md`, `docs/tasks.md` — T-142 완료와 다음 비의존 후보 T-144를 반영했다.

**검증**:
- WSL2 ext4 mirror: ruff / mypy / geofence unit test
- NTFS worktree: stale token role claim·nginx 3중 필수 표현 검색, `git diff --check`

**다음**: T-144 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계.

## 2026-06-06 (codex) — T-147 잔여 문서 정정

**작업**: 감사 D-23/D-25 범위의 KASI rise/set 재계산 정책과 Gemini 문서 SQL 문법을
정리했다.

**변경**:
- `docs/integrations/kasi.md`, `docs/api/pois.md` — POI rise/set은 생성 당시
  `locdate`/좌표 snapshot 기준 1회 저장하며, 날짜/좌표 변경 시 자동 재조회하지 않는다고
  명시했다. 명시적 refresh action은 후속 PR 대상이다.
- `docs/integrations/gemini.md` — partial unique index를 table constraint가 아니라
  `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL` PostgreSQL 문법으로 정정했다.
- `docs/resume.md`, `docs/tasks.md` — T-147 완료와 다음 비의존 후보 T-142를 반영했다.

**검증**:
- NTFS worktree: `rg`로 미결 rise/set 문구와 invalid inline partial unique 문법 검색
- NTFS worktree: `git diff --check`

**다음**: T-142 geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리.

## 2026-06-06 (codex) — T-143 지도/소셜 문서 정정

**작업**: 감사 D-15/D-21/D-22 범위의 지도 클라이언트, 소셜 로그인 provider,
kraddr-geo geocoding 경계 문서 드리프트를 정리했다.

**변경**:
- `docs/architecture/frontend.md` — `apps/web/lib`의 폐기된 지도 어댑터 표현을
  `maplibre-vworld`로 바꾸고, 카카오맵 약관 메모가 ADR-015로 superseded됐음을 명시했다.
- `docs/architecture/map-marker-design.md` — 로그인 화면 OAuth 버튼 예시를 Google 하나로
  축소하고 Naver/Kakao는 T-122 전까지 만들지 않는다고 명시했다.
- `docs/integrations/README.md`, `docs/data-sources/README.md` — 현재 직접 OAuth
  provider는 Google이며, 주소/행정구역/geocoding은 `python-kraddr-geo` v2 REST 직접
  호출임을 반영했다.
- `docs/architecture/mcp-tools.md` — in-process geocoding 호출 표현을 v2 REST 호출
  기준으로 정정했다.

**검증**:
- NTFS worktree: stale Kakao/Naver/social/kraddr 표현 검색
- NTFS worktree: `git diff --check`

**다음**: T-147 잔여 문서 정정. krtour-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-151 미기록 ADR 백필

**작업**: Sprint 문서에 placeholder로 남아 있던 인증 토큰 / Admin RBAC / Admin audit
chain 결정을 현재 구현 기준으로 ADR에 박았다.

**변경**:
- `docs/decisions.md` — ADR-032(access JWT + httpOnly cookie), ADR-033(`users.roles[]`
  Admin RBAC), ADR-034(Admin audit hash chain)를 추가하고 다음 신규 ADR을 ADR-035로
  갱신했다.
- `CLAUDE.md`, `docs/sprints/SPRINT-1.md`, `SPRINT-2.md`, `SPRINT-3.md`,
  `SPRINT-5.md`, `SPRINT-6.md` — ADR 번호/후속 후보/구현 기준을 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-151 완료와 다음 비의존 후보 T-143을 반영했다.

**검증**:
- NTFS worktree: `rg`로 Sprint/resume/decisions의 `ADR-NNN`, stale ADR-032/T-151 포인터 확인
- NTFS worktree: `git diff --check`

**다음**: T-143 지도/소셜 문서 정정. krtour-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-150 계획/추적 문서 정합화

**작업**: 감사 P-04~21 중 T-150 범위의 sprint status, tracking 문서, ADR 참조
드리프트를 최신 main 기준으로 정리했다.

**변경**:
- `docs/sprints/SPRINT-1.md`, `SPRINT-3.md`, `SPRINT-4.md` 헤더 상태를 merged /
  in progress 기준으로 정정하고, 잘못 배정됐던 Sprint 1 ADR 참조를 실제 ADR 번호와
  T-151 백필 대상으로 분리했다.
- `docs/sprints/SPRINT-5.md`의 TripMate ETL provider asset 계획을 ADR-026/T-210c
  경계에 맞춰 `app` schema 소유 job만 남기고, feature/provider 적재는 krtour-map
  책임으로 정리했다.
- `docs/sprints/README.md` 관련 ADR 목록을 ADR-031까지 확장했다.
- `docs/resume.md`의 stale ADR 후보를 T-151/T-148 후속으로 재분류하고, 박힌 ADR
  목록을 ADR-031까지 갱신했다.
- `docs/tasks.md` 완료/다음 작업/merge history를 최신화했다.

**검증**:
- NTFS worktree: `rg`로 Sprint status / ADR 후보 / T-111 중복 / 보류 `[x]` 혼재
  상태 확인
- NTFS worktree: `git diff --check`

**다음**: T-151 미기록 ADR 백필. krtour-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-149 Gemini 책임 목록 정정

**작업**: ADR-020(`tripmate-ai-companion` 별도 repo 분리)에 맞춰, 본 저장소의 현재
책임 목록에 남아 있던 Gemini 직접 통합 표현을 AI companion 호출 계약으로 정정했다.

**변경**:
- `README.md` — 책임/외부 통합 목록에서 Gemini 직접 통합을 제거하고 AI companion
  호출 계약으로 표기했다.
- `AGENTS.md` / `CLAUDE.md` — ADR-016 동기 원칙에 따라 외부 통합 진입 문구를
  AI companion 호출 계약으로 맞췄다.
- `SKILL.md` — DO NOT 항목의 webhook 검증 대상을 Telegram/Resend/AI companion으로
  정리했다.
- `docs/integrations/README.md` — Gemini 문서를 deferred reference로 낮추고,
  AI provider 구현은 `tripmate-ai-companion`이 소유한다고 명시했다.

**검증**:
- NTFS worktree: `git diff --check`
- NTFS worktree: stale 책임 표현 검색
  (`외부 통합 .*Gemini`, `Telegram, Gemini`, `Google (OAuth + Gemini)`,
  `Gemini Deep Research (사용자 키) | 4+` 등) — 잔여 없음

**다음**: T-150 계획/추적 문서 정합화. krtour-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-123 문서 정합 일괄 정정

**작업**: 감사 A-14/C-20/C-21/P-10/P-13/P-17/P-18 범위의 저위험 정합 문제를
최신 구현 기준으로 정리했다.

**변경**:
- README/API index에 `GET /search`, `GET /health/external`을 노출하고, OAuth는
  Google만 활성 + Naver/Kakao future provider로 표현을 맞췄다.
- `POST /trips/{trip_id}/share-tokens` URL 생성을 `TRIPMATE_WEB_BASE_URL` 기반으로
  변경하고 통합 테스트를 추가했다.
- feature viewport zoom 하한을 코드/Zod와 같은 5로 문서 정정했다.
- `docs/sprints/SPRINT-4.md`의 dangling `docs/release-plan.md` 링크를 현재 추적
  문서(`sprints/README`, `tasks`, `resume`) 참조로 바꿨다.
- `docs/decisions.md`의 `python-kraddr-map` 오타를 `python-kraddr-geo`로 정정했다.
- `docs/agent-guide.md`의 구식 co-author 예시와 잔여 `Restrict force-push` bullet을
  정리했다.
- `docs/tasks.md` merge history에 PR #52/#53을 추가했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run ruff format app/api/v1/trips.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app/api/v1/trips.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_trips_api.py -q`
  — 6 passed

**다음**: T-149 Gemini 책임 목록 정정. krtour-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-121 POI Admin 목록/상세/연결 상태 관리

**작업**: krtour-map 연계가 필요 없는 admin 후속으로, TripMate 소유
`app.trip_day_pois` POI 첨부 행의 목록/상세/연결 상태 관리 기능을 구현했다.

**변경**:
- `GET /admin/pois` — `q` 검색(`feature_id`, snapshot JSON, trip 제목, owner email,
  UUID 정확 일치), `trip_id`, `has_broken_link` 필터와 owner 이메일 마스킹을 제공한다.
- `GET /admin/pois/{poi_id}` — feature snapshot, 일정/비용/메모/URL, 추가자 마스킹,
  최근 `admin_audit_log` 10건을 반환한다.
- `PATCH /admin/pois/{poi_id}/link-status` — admin 전용 로컬 연결 상태 변경,
  `access_reason` 필수, `poi.update_link_status` audit 기록.
- `packages/schemas`, `packages/api-client`, Web `/admin/pois` 목록/상세 화면을
  계약에 맞춰 추가했다.
- `apps/api/tests/integration/test_admin_pois_api.py`,
  `apps/web/e2e/admin-pois.e2e.ts` — 검색/마스킹/broken filter/link status audit과
  krtour-map 미호출을 검증했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_pois_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_pois_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_pois_api.py -q`
  — 4 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... admin-pois.e2e.ts`
  — 2 passed
- WSL2 ext4 mirror: `uv run ruff format --check .`
- NTFS worktree: `git diff --check`

**다음**: T-123 문서 정합 일괄 정정. 구현 feature read와 feature re-link는 계속
krtour-map HTTP/OpenAPI 준비 후로 둔다.

## 2026-06-06 (codex) — T-120 여행계획 Admin 목록/상세/상태 관리

**작업**: krtour-map 연계가 필요 없는 admin 후속으로, TripMate 소유 여행계획의
목록/상세/상태 관리 기능을 구현했다.

**변경**:
- `GET /admin/trips` — `q` 검색(제목/지역/owner email 부분 일치, trip_id /
  owner_user_id 정확 일치), `status_filter`, `visibility_filter`, `owner_user_id`
  필터와 day/POI/companion/share count를 제공한다.
- `GET /admin/trips/{trip_id}` — owner 이메일은 마스킹하고, companion/share metadata와
  최근 `admin_audit_log` 10건을 반환한다.
- `PATCH /admin/trips/{trip_id}/status` — admin 전용 상태 변경, `access_reason`
  필수, `trip.update_status` audit 기록.
- `packages/schemas`, `packages/api-client`, Web `/admin/trips` 목록/상세 화면을
  계약에 맞춰 추가했다.
- `apps/api/tests/integration/test_admin_trips_api.py`,
  `apps/web/e2e/admin-trips.e2e.ts` — 검색/마스킹/count/status audit과 krtour-map
  미호출을 검증했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_trips_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_trips_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_trips_api.py -q`
  — 3 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... admin-trips.e2e.ts`
  — 2 passed

**다음**: T-121 POI Admin 목록/상세/연결 상태 관리. feature re-link는 krtour-map
client 준비 후로 두고, 현재는 TripMate 소유 `trip_day_pois` 영역만 다룬다.

## 2026-06-06 (claude) — T-210c(ADR-045 Phase 6) TripMate ETL 경계 정합

**작업**: krtour-map ADR-045 Phase 6의 T-210c("TripMate `apps/etl` 레거시 Dagster
이관/삭제") 중 TripMate가 지금 처리할 수 있는 부분을 수행했다.

**확인**: `apps/etl`은 이미 `app` schema 소유 job만 보유(KASI 특일 asset +
`kasi_poi_rise_set_job` + DB/KASI resource). feature/provider 적재 Dagster 코드는
**없음** → krtour-map으로 이관/삭제할 레거시 스켈레톤 자체가 없다(코드 측 T-210c는 N/A).

**변경(문서 phantom 스켈레톤 정합 + 코드 가드)**:
- `docs/architecture/dagster-etl-bridge.md` §2 — 미존재 파일(`sensors.py`,
  `tripmate_kasi_poi_rise_set/telegram_weekly/email_outbox/pii_retention/
  location_log_archive`) 나열을 "현재 구현 vs 계획(미구현)"으로 정합. §3.1 asset명을
  `kasi_special_days_daily` → 실제 `tripmate_kasi_special_days`로 정정.
- `docs/runbooks/etl.md` §2 — 동일하게 구현/계획 분리 + T-210c 경계 노트.
- `apps/etl/tripmate/etl/assets/__init__.py` — "feature/provider asset 추가 금지,
  krtour-map 소유(ADR-003/026/045 T-210c)" 가드 docstring 추가.
- `docs/tasks.md` — krtour-map ADR-045 Phase 6 TripMate 몫 매핑(T-210b/c 완료,
  T-210d=T-066 대기, T-210e 대기).

## 2026-06-06 (codex) — T-119 회원 관리 Admin 보강

**작업**: krtour-map과 무관한 admin 후속으로, 회원 목록 검색과 상세 PII reveal audit
UX를 보강했다.

**변경**:
- `GET /admin/users` — `q` 검색(이메일/닉네임 부분 일치, user_id 정확 일치)과
  `status_filter`를 함께 적용한다.
- `GET /admin/users/{user_id}` — 기본 응답은 이메일을 마스킹하고, `reveal=true` +
  사유가 있을 때만 원본 이메일을 반환하며 `user.reveal_pii` audit을 남긴다.
- `AdminUserDetail` / Web schema / API client — `email_revealed`, `recent_audit`,
  reveal 조회 파라미터를 추가했다.
- `/admin/users` UI — 검색 입력 + 상태 필터 결합 조회를 추가했다.
- `/admin/users/{user_id}` UI — 원본 보기 사유 입력 dialog와 최근 audit 표를 추가했다.
- `apps/api/tests/integration/test_admin_users_api.py`,
  `apps/web/e2e/admin-users.e2e.ts` — 검색/마스킹/reveal audit과 krtour-map 미호출을
  검증했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_users_api.py -q`
  — 2 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... admin-users.e2e.ts`
  — 2 passed

**다음**: T-120 여행계획 Admin 목록/상세/상태 관리.

## 2026-06-06 (codex) — T-118 Google OAuth 계정 매칭 UX

**작업**: krtour-map과 무관한 인증 UX 후속으로, Google OAuth의 같은 이메일 자동
연결을 제거하고 명시 연결 안내/충돌 메시지를 보강했다. Naver/Kakao는 계속 T-122
미래 작업으로 둔다.

**변경**:
- `apps/api/app/services/oauth_google.py` — 같은 이메일 로컬 계정이 있으면
  `OAUTH_ACCOUNT_LINK_REQUIRED`를 발생시켜 자동 연결하지 않는다. Google 이메일
  인증 불확실성은 `OAUTH_EMAIL_UNVERIFIED`로 거부한다.
- `apps/api/app/api/v1/oauth.py` — link-mode callback 실패는 `/login`이 아니라
  state의 `return_to`(`/profile`)로 redirect한다.
- `apps/web/app/(auth)/login/page.tsx`, `apps/web/app/(auth)/profile/page.tsx` —
  계정 매칭/연결 충돌 메시지를 code 기반으로 표시한다.
- `apps/api/tests/integration/test_oauth_google.py`,
  `apps/web/e2e/oauth-account-match.e2e.ts` — 자동 연결 금지, profile 충돌 redirect,
  Naver/Kakao 미노출 e2e를 보강했다.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `docs/tasks.md`,
  `docs/resume.md` — OAuth 매칭 계약과 다음 비의존 후보(T-119)를 반영했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_oauth_google.py -q`
  — 18 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... oauth-account-match.e2e.ts`
  — 2 passed

**다음**: T-119 회원 관리 Admin 보강.

## 2026-06-06 (codex) — T-117 회원가입 약관 동의

**작업**: krtour-map과 무관한 가입 UX/컴플라이언스 후보로, 회원가입 단계에서
필수 약관 동의를 받고 `app.user_consents`에 저장하도록 보강했다.

**변경**:
- `apps/api/app/schemas/auth.py`, `packages/schemas/src/auth.ts` —
  `RegisterRequest`에 `consents` 배열을 추가하고 필수 4종 동의 누락/중복을 검증한다.
- `apps/api/app/services/user_registration.py`, `apps/api/app/api/v1/auth.py` —
  가입 트랜잭션 안에서 `UserConsent` row를 생성한다.
- `apps/api/app/core/errors.py` — Pydantic validator의 `ctx.error` 객체가 표준
  validation 응답 직렬화를 깨지 않도록 JSON-safe 변환을 추가했다.
- `apps/web/app/(auth)/signup/page.tsx` — 필수 전체 동의, 필수 4종 체크박스,
  선택 `marketing` 동의를 추가하고 필수 동의 전 제출을 막는다.
- `docs/api/auth.md`, `docs/compliance/lbs-act.md`, `docs/tasks.md`, `docs/resume.md`
  — 회원가입 동의 계약과 다음 비의존 후보(T-118)를 반영했다.

**검증**:
- WSL2 ext4 mirror:
  `uv run pytest -s tests/unit/test_schemas.py tests/integration/test_register_consents.py -q`
  — 9 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_schemas.py tests/integration/test_register_consents.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/unit/test_schemas.py tests/integration/test_register_consents.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... signup-consents.e2e.ts`
  — 1 passed

**다음**: T-118 Google OAuth 계정 매칭 UX 보강. Naver/Kakao OAuth는 T-122 미래
작업으로 유지한다.

## 2026-06-06 (claude) — 문서·구현 정합성 전수 감사 + krtour-map 요구사항 명세

**작업**: Sprint 1~4 중 계획 변경·Task 분절로 누적된 모순·불일치·누락을 문서 전체 +
`apps/` 코드 + `python-krtour-map`(HEAD `b775c74`) 대조로 전수 점검했다. 5개 병렬
감사(계획/프로세스, 외부 API, 코드 vs 문서, 기능/도메인, krtour-map 저장소)를 종합.

**핵심 발견**: TripMate(ADR-026, HTTP 9011)와 krtour-map(in-process 함수 라이브러리,
HTTP는 인증 없는 debug-UI 8087뿐)의 **통합 모델이 정반대**이며, ADR-026이 참조한
krtour 산출물(`krtour-map-admin` 패키지·`openapi.user.json`·`/tripmate/features/batch`)
이 **실재하지 않음**을 확인. 그 외 외부 API 규약 혼재(envelope/pagination/좌표/datetime),
feature read 전 경로 미연결(C-01 client stub), `notice_plans` 명칭 충돌, PIPA `users`
컬럼·`security_incidents` 테이블 누락, 실시간/검색/내보내기/동반자 초대 부재 등.

**신규 문서**:
- `docs/audit/2026-06-06-doc-impl-audit.md` — 감사 종합(증거 ID P/A/C/D, 병합 매핑표
  T-123~151 / ADR-027~031).
- `docs/krtour-map-requirements.md` — krtour-map 에이전트용 요구사항(능력별 왜/언제 +
  현재 상태 + 격차표 K-1~14).
- `docs/decisions-needed-2026-06-06.md` — 결정 DEC-01~10 + 사용자 결정 기록.

**사용자 결정**: DEC-01=운영급 HTTP 서비스(B), DEC-03=`curated_trip_plans` 분리,
DEC-06=krtour 연동까지 v0.1.0 대기, DEC-07=API 규약 제안 기본값+`/v1`. 나머지는 저위험
권고 기본값 채택.

**반영**: `decisions.md` ADR-027~031 추가, `common.md` 정본 규약(ADR-030),
`krtour-map-integration.md` 실재성 정정, `sprints/README.md` status·v0.1.0 게이트,
`tasks.md` 감사 후속 백로그 + 머지표, `notice-plans.md`/`data-model.md` 정정 노트.

## 2026-06-06 (codex) — T-100~T-104 backlog 상태 정정

**작업**: 완료된 T-100~T-104가 `docs/tasks.md`의 `보류` 섹션에 남아 실제 상태와
다르게 읽히던 문서 구조를 정리했다.

**변경**:
- `docs/tasks.md` — T-100~T-104를 `완료` 섹션으로 옮기고 `보류`에는 실제
  보류/미래 항목만 남겼다.
- `docs/agent-guide.md` — `tasks.md` 형식 예시의 T-100 번호를 예시용 T-900으로
  바꿔 실제 backlog와 충돌하지 않게 했다.

**검증**:
- `git diff --check`

**다음**: T-066은 krtour-map OpenAPI/client 의존으로 계속 보류한다.

## 2026-06-06 (codex) — T-115 Backup snapshot foundation + T-116 Google-only OAuth

**작업**: krtour-map과 무관한 운영/인증 후보로 ADR-022 Sprint 5 backup snapshot
foundation을 구현하고, 현재 OAuth provider 범위를 Google-only로 정리했다.

**변경**:
- `scripts/backup-db.sh`, `scripts/restore-db.sh` — TripMate 소유 `app` schema custom
  dump / restore 스크립트 추가. backup은 `.dump`와 `.sha256`을 생성한다.
- `apps/api/app/services/backup_service.py`,
  `apps/api/app/api/v1/admin/backup.py` — snapshot 목록 조회와 수동 snapshot 생성
  endpoint(`GET /admin/backup/snapshots`, `POST /admin/backup/snapshot`) 추가.
- `packages/schemas`, `packages/api-client`, `apps/web/app/(admin)/admin/backup/page.tsx`
  — admin backup snapshot 목록 / 수동 trigger UI와 client schema 연결.
- `apps/api/app/api/v1/oauth.py`, `apps/web/app/(auth)/login/page.tsx` — 현재 provider
  응답과 UI를 Google만 활성으로 고정. Naver/Kakao는 T-122 미래 작업으로 분리.
- `.env.example`, `docs/api/{admin,auth}.md`,
  `docs/{architecture,runbooks}/backup-restore.md`,
  `docs/integrations/social-login.md`, `docs/tasks.md`, `docs/resume.md` — backup
  환경변수, API/runbook, Google-only OAuth 정책, 신규 비의존 backlog 반영.

**검증**:
- WSL2 ext4 mirror:
  `uv run pytest -s tests/unit/test_backup_service.py tests/integration/test_oauth_google.py::test_providers_endpoint_exposes_google_only_for_now -q`
  — 4 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_backup_service.py tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/unit/test_backup_service.py tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... admin-backup.e2e.ts`
  — 1 passed
- NTFS worktree: `git diff --check`

**다음**: T-117 회원가입 약관 동의 화면 + `user_consents` 저장 보강부터 진행한다.
Naver/Kakao OAuth는 현재 사용하지 않고 T-122 미래 작업으로 둔다.

## 2026-06-05 (codex) — T-109 한국 전용 geofencing FastAPI fallback

**작업**: krtour-map과 무관한 보안/운영 후보로 ADR-018의 3차 FastAPI fallback을
구현했다.

**변경**:
- `apps/api/app/middleware/geofence.py` — 기본 비활성 geofence middleware 추가.
  활성 시 `CF-IPCountry` 기반으로 허용 국가(`KR`) 외 요청을 451로 차단한다.
- `apps/api/app/core/config.py`, `.env.example` — `TRIPMATE_GEOFENCE_*` 환경변수 추가.
- `apps/api/app/main.py` — Geofence middleware를 API middleware stack에 연결.
- `apps/api/tests/unit/test_geofence_middleware.py` — 비활성 허용, KR 허용, 비KR 차단,
  health 우회, unknown strict 차단, roles claim 기반 admin 우회를 검증.
- `docs/runbooks/korea-only.md`, `docs/architecture/korea-only-policy.md`,
  `resume.md`, `tasks.md` — 현재 FastAPI fallback 계약과 운영 우회 한계를 반영.

**검증**:
- WSL2 ext4 mirror: `uv run pytest -s tests/unit/test_geofence_middleware.py -q` — 6 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_geofence_middleware.py && uv run ruff check app tests/unit/test_geofence_middleware.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`

**다음**: T-111 Backup/Restore UI 핫스왑은 krtour-map 비의존이지만 운영 데이터 보호
범위라 ADR-022와 backup runbook을 먼저 확인한다.

## 2026-06-05 (codex) — T-110 Admin Grafana iframe embed

**작업**: krtour-map과 무관한 운영 UI 후보로 `/admin/grafana` iframe shell을 먼저
연결했다.

**변경**:
- `apps/web/app/(admin)/admin/grafana/page.tsx` — Grafana iframe, 새로고침, 새 창
  action, embed origin 표시를 추가했다.
- `apps/web/app/(admin)/admin/layout.tsx` — Admin navigation에 Grafana 항목 추가.
- `apps/web/next.config.mjs` — `/admin/grafana`에 Grafana origin 대상 `frame-src`
  CSP를 추가했다.
- `.env.example`, `docs/runbooks/grafana-admin-embed.md` —
  `NEXT_PUBLIC_GRAFANA_URL`, `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`를 명시했다.
- `apps/web/e2e/admin-grafana.e2e.ts` — admin guard 뒤에서 iframe shell이 렌더링되고
  krtour-map API `9011`을 호출하지 않음을 검증한다.

**검증**:
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run lint --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... admin-grafana.e2e.ts`
  — 1 passed

**다음**: T-109 geofencing은 krtour-map 비의존이지만 보안/운영 정책 범위라
ADR-018과 `docs/runbooks/korea-only.md`를 먼저 확인한다.

## 2026-06-05 (codex) — T-075 Trip / notice plan 사용자 shell

**작업**: krtour-map feature 조회 없이 TripMate 자체 Trip / notice plan API만으로
사용자 shell을 연결했다.

**변경**:
- `packages/api-client/src/endpoints/trips.ts`,
  `packages/api-client/src/endpoints/notice-plans.ts` — `GET /trips`,
  `POST /trips`, `GET /notice-plans`, `POST /notice-plans/{id}/copy` 등 사용자
  endpoint client를 추가했다.
- `apps/web/app/(app)/layout.tsx`, `apps/web/components/app/AppShell.tsx` — 사용자
  앱 공통 navigation shell을 추가했다.
- `apps/web/app/(app)/trips/page.tsx`,
  `apps/web/components/trips/TripDashboard.tsx` — Trip 목록, bucket 필터, 빈 상태,
  간단 생성 form을 연결했다.
- `apps/web/app/(app)/notice-plans/page.tsx`,
  `apps/web/components/notice-plans/NoticePlanShelf.tsx` — 추천 여행 목록, category
  필터, 내 여행으로 copy action을 연결했다.
- `apps/web/e2e/user-shells.e2e.ts` — API 응답을 Playwright route mock으로 고정하고
  `/features/*`와 krtour-map API `9011` 미호출을 검증했다.

**검증**:
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace packages/api-client`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run lint --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 ... @playwright/test ... map-shell.e2e.ts user-shells.e2e.ts`
  — 3 passed

**다음**: krtour-map client 의존 T-066은 계속 보류한다. 남은 비의존 후보는 Sprint
5~6 backlog 중 운영/관리 UI 범위(T-110 등)를 별도 task로 선별한다.

## 2026-06-05 (codex) — T-074 PR-C frontend 지도 shell

**작업**: krtour-map feature 조회를 연결하지 않고, Sprint 4 PR-C의 지도 shell을
TripMate Web에 먼저 붙였다.

**변경**:
- `apps/web/package.json` / `package-lock.json` — `maplibre-vworld`를
  `digitie/maplibre-vworld-js` commit `f1dd74b9...`의 GitHub archive tarball에
  pin하고 `maplibre-gl`, Playwright dev dependency를 추가했다.
- `apps/web/components/map/MapView.tsx` — `VWorldMap`, `ClusterLayer`,
  `MakiMarker`, `Popup`을 dynamic import로 연결하고 정적 서울 샘플 포인트만 렌더링한다.
  `/features/in-bounds` 또는 krtour-map API `9011` 호출은 하지 않는다.
- `apps/web/app/(app)/trips/map-shell/page.tsx` — `/trips/map-shell` 지도 shell route
  추가.
- `apps/web/playwright.config.ts`, `apps/web/e2e/map-shell.e2e.ts` — Windows
  Playwright smoke로 shell 렌더링과 krtour-map 비호출을 검증.
- `apps/web/next.config.mjs` — `maplibre-vworld` transpile 대상 추가. 라이브러리 dist의
  development JSX runtime이 `require("react")`를 호출하는 dev-only 문제는
  `MapView`의 React require shim으로 보완했다. production build는 정상 통과.
- `docs/integrations/maplibre-vworld.md`, `resume.md`, `tasks.md` — PR-C pin/import/e2e
  상태와 다음 비의존 후속을 갱신.

**검증**:
- WSL2 ext4 mirror: `npm run lint --workspace apps/web`
- WSL2 ext4 mirror: `npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror: `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://172.26.51.35:9022 npx -y @playwright/test@1.60.0 test map-shell.e2e.ts`
  — 1 passed

**다음**: krtour-map client 의존 T-066은 계속 보류하고, Trip 대시보드 / notice plan
사용자 shell처럼 feature 조회 없이 가능한 PR-C 후속을 진행한다.

## 2026-06-05 (codex) — T-073 Google OAuth profile 연결/해제 UI

**작업**: krtour-map과 무관한 Google OAuth profile 연결/해제 흐름을 Web UI까지
연결했다.

**변경**:
- `/auth/me` — 현재 사용자 응답에 `has_password`와 `oauth_identities`를 포함한다.
- `/auth/oauth/google/link` — 로그인된 사용자용 link state를 발급하고 `user_id`를
  state row에 저장한다.
- `DELETE /auth/oauth/google` — `password_hash`가 없는 소셜-only 계정은 409로 해제
  차단.
- `@tripmate/schemas` / `@tripmate/api-client` — OAuth identity schema,
  `linkGoogleOAuth`, `unlinkGoogleOAuth`, 204 no-content client 처리 추가.
- `apps/web/app/(auth)/profile/page.tsx` — Google 연결 상태, 연결 시작, 해제 UI 추가.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `resume.md`, `tasks.md` —
  현재 계약과 진행 상태 반영.

**검증**:
- `apps/api`: `python -m pytest -s tests/integration/test_oauth_google.py -q` — 14 passed
- `apps/api`: `ruff format --check app tests/integration/test_oauth_google.py`
- `apps/api`: `ruff check app tests/integration/test_oauth_google.py`
- `apps/api`: `mypy --strict app`
- `apps/web`: `npm run build --workspace apps/web`
- root: `npm run typecheck --workspaces --if-present`
- NTFS worktree: `git diff --check`

**다음**: krtour-map client 의존 T-066은 계속 보류하고, PR-C frontend 지도 shell 중
feature 조회를 제외한 범위를 진행한다.

## 2026-06-05 (codex) — T-072 Google OAuth callback 실패 UX

**작업**: Google OAuth callback 실패가 API JSON 오류로 남지 않고 Web 로그인 화면으로
돌아오도록 정리했다.

**변경**:
- `/auth/oauth/google/callback` — provider 거부, 필수 query 누락, state 검증 실패,
  token/userinfo 실패, 매칭 실패를 `/login?error=...&error_description=...` 303
  redirect로 변환.
- `apps/web/app/(auth)/login/page.tsx` — `error` query를 고정 한국어 메시지로 매핑해
  인라인 표시. 임의 `error_description`은 화면에 직접 노출하지 않는다.
- `test_oauth_google.py` — invalid state / provider denied redirect 회귀 테스트 추가.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `resume.md`, `tasks.md` —
  현재 Google callback 실패 UX 반영.

**검증**: PR 전 API OAuth integration, API lint/typecheck, web lint/typecheck/build를
재실행한다.

**다음**: Google OAuth profile 연결/해제 UI는 별도 비의존 후속으로 진행한다.

## 2026-06-05 (codex) — T-071 Google OAuth 로그인 UI

**작업**: 로컬 Google OAuth client id를 반영한 뒤, 로그인 화면에서 Google OAuth
authorize URL 발급 흐름을 시작할 수 있게 연결했다.

**변경**:
- `/auth/oauth/google/start` — 공통 API client가 읽을 수 있도록 envelope 응답
  (`data.authorize_url`)으로 정리.
- `oauth_google.issue_login_state` / `consume_login_state` — PKCE verifier를 DB 평문
  저장 없이 `state` + 서버 secret으로 재생성해 callback 토큰 교환에 전달.
- `@tripmate/schemas` / `@tripmate/api-client` — OAuth provider 목록과 Google start
  schema/client 메서드 추가.
- `apps/web/app/(auth)/login/page.tsx` — `/auth/oauth/providers` 조회 후 Google 버튼
  활성화, 클릭 시 `authorize_url`로 top-level navigation.
- `apps/web/eslint.config.mjs` — `FlatCompat.baseDirectory`를 file URL이 아닌 절대
  디렉터리 경로로 고쳐 Windows/CI lint 경로 해석을 안정화.

**검증**: `test_oauth_google.py`에 start envelope와 PKCE verifier 재생성 회귀 테스트를
추가했다. 전체 로컬 검증은 PR 전 WSL ext4 미러에서 실행한다.

**다음**: Google OAuth callback 실패 redirect UX와 profile 연결/해제 UI는 별도
비의존 후속으로 분리한다.

## 2026-06-05 (codex) — T-065 aggregate CI gate

**작업**: path-filtered `api` / `web` / `etl` workflow를 유지하면서 docs-only PR도
막히지 않도록 항상 실행되는 aggregate required check를 추가했다.

**변경**:
- `.github/workflows/aggregate-ci.yml` — 모든 PR에서 `Aggregate CI gate` job 실행.
  변경 파일을 기준으로 필요한 check(`lint-typecheck-test`, `lint-typecheck-build`,
  `sanity`)를 GitHub Checks API로 polling한다.
- `.github/workflows/README.md`, `docs/agent-guide.md`, `docs/decisions.md`,
  `docs/sprints/SPRINT-4.md` — required status check 정책을 `Aggregate CI gate`
  하나로 정리.
- `docs/tasks.md`, `docs/resume.md` — T-065 완료와 다음 작업 정리.

**검증**: 로컬 `python3` PyYAML 파싱과 `git diff --check` 통과. `node`/`actionlint`는
현재 WSL PATH에 없어 PR CI에서 workflow 실행으로 최종 확인한다. PR merge 후
`main-pr-only` ruleset에 required status check `Aggregate CI gate`를 적용한다.

**다음**: krtour-map 의존 작업은 계속 보류하고, 남은 비의존 frontend/운영 작업 범위를
재확인.

## 2026-06-05 (codex) — T-063 maplibre consumer sync

**작업**: `maplibre-vworld-js` 선행 PR 상태와 TripMate consumer sync 체크리스트를
정리했다. 라이브러리 저장소에서 PR #46을 생성해 `docs/consumer-feature-catalog.md`
를 T-033~T-037 실제 구현 상태와 맞췄고, `build-and-test` 통과 후 squash merge했다.

**변경**:
- `docs/integrations/maplibre-vworld.md` — §6 snapshot을 PR #37/#46 기준으로 갱신,
  §11.1에 TripMate consumer sync 결과와 남은 frontend pin/import/e2e 체크 추가.
- `docs/sprints/SPRINT-4.md` — 라이브러리 선행 PR 조건을 완료 처리.
- `docs/tasks.md`, `docs/resume.md` — T-063 완료와 다음 작업 T-065 반영.

**검증**:
- `maplibre-vworld-js` PR #46: `build-and-test` green, merge `f1dd74b9`.
- TripMate: 문서 전용 변경. `git diff --check` 통과.

**다음**: krtour-map 비의존 작업으로 T-065 aggregate CI gate 설계/적용.

## 2026-06-05 (codex) — T-070 Sprint 2 잔여 마감

**작업**: krtour-map과 연계하지 않는 Sprint 2 잔여를 마감. `email_queue`
SKIP LOCKED worker batch, 비밀번호 재설정 요청/확정 API, `api_call_log` httpx event
hook 통합 테스트, API CI integration step을 추가했다.

**변경**:
- `apps/api/app/services/email_service.py` — outbox enqueue + `process_pending_email_batch`
  (`FOR UPDATE SKIP LOCKED`) + verify/reset HTML 렌더링.
- `/auth/password/reset-request`, `/auth/password/reset` — enumeration-safe reset 요청,
  token 검증, `password_hash` 갱신, `user_sessions.revoked_at` 처리, cookie 재발급.
- `tests/integration/test_{password_reset_flow,email_queue_worker,api_call_logging}.py`
  신규.
- `.github/workflows/api.yml` — PR에서 `pytest tests/integration -q` 실행.
- Google OAuth client id는 `/mnt/f/dev/tripmate`, `tripmate-codex`,
  `tripmate-claude`, `tripmate-antigravity`의 로컬 `.env`에 반영.

**검증**:
- `apps/api`: `uv run pytest -s tests/unit -q` — 56 passed
- `apps/api`: `uv run pytest -s tests/integration -q` — 35 passed
- `apps/api`: `uv run ruff format --check . && uv run ruff check .`
- `apps/api`: `uv run mypy --strict app`

**다음**: 본 PR 머지 후 krtour-map 의존 T-066은 계속 보류하고, T-063 또는 T-065처럼
비의존 작업부터 진행.

## 2026-06-05 (codex) — T-067 KASI Dagster/DB/POI 연동 구현

**작업**: krtour-map과 연계하지 않는 KASI 범위를 먼저 구현. `python-kasi-api`와
`DATA_GO_KR_SERVICE_KEY`를 기준으로 특일 계열 upsert asset, POI별 해·달 출몰시각
one-shot Dagster job, API POI 생성 시 fetch 대기 row 생성을 추가했다.

**변경**:
- `app.kasi_special_days`, `app.trip_poi_rise_sets` Alembic migration + ORM 모델.
- POI 생성 시 trip 시작일 기반 `locdate`, feature snapshot 좌표를 읽어
  `pending_date` / `pending_coord` / `pending_fetch` 상태 row 생성.
- `apps/etl` Dagster definitions에 `tripmate_kasi_special_days` asset,
  `kasi_poi_rise_set_job`, `TripmateDatabaseResource`, `KasiResource` 추가.
- KASI/ETL/API 문서와 `docs/tasks.md` / `docs/resume.md` 상태 갱신.

**검증**:
- `apps/api`: `uv run pytest -s tests/unit/test_kasi_service.py -q`
- `apps/api`: `uv run pytest -s tests/integration/test_kasi_poi_rise_set.py -q`
- `apps/api`: `uv run ruff check app tests/unit/test_kasi_service.py tests/integration/test_kasi_poi_rise_set.py`
- `apps/api`: `uv run mypy app`
- `apps/etl`: `uv run pytest -s tests -q`
- `apps/etl`: `uv run ruff check .`
- `apps/etl`: `uv run mypy tripmate`

**다음**: 본 PR 머지 후 사용자의 최신 지시에 따라 krtour-map 의존 T-066은 보류하고,
T-070(Sprint 2 잔여 마감) 또는 T-065(aggregate CI gate) 같은 비의존 작업부터 진행.

## 2026-06-05 (codex) — production API/Web URL + OAuth 보안 문서화

**작업**: 사용자 지시로 production API/Web 공개 URL을 문서와 환경변수 예시에
명시하고, 관련 보안 처리(OAuth callback, Google JavaScript origin, CORS, CSP,
Secure cookie, open redirect 방지)를 함께 정리.

**결정**:
- API production URL: `https://tripmateapi.digitie.mywire.org` (내부/host port
  `9021`)
- Web production URL: `https://tripmate.digitie.mywire.org` (내부/host port `9022`)
- Google 승인된 JavaScript 원본: `https://tripmate.digitie.mywire.org`
- Google redirect URI:
  `https://tripmateapi.digitie.mywire.org/auth/oauth/google/callback`

**보안 처리**:
- CORS 허용 origin은 Web origin만. API origin과 wildcard는 허용하지 않는다.
- OAuth `return_to`는 상대 경로 또는 `TRIPMATE_WEB_BASE_URL` 하위 경로만 허용해
  open redirect를 차단한다.
- 운영은 `TRIPMATE_ENVIRONMENT=production`으로 cookie `Secure` 속성을 강제한다.
- reverse proxy / Cloudflare Tunnel은 `X-Forwarded-Proto=https`를 보존하고 HTTP를
  HTTPS로 redirect한다.

## 2026-06-04 (codex) — 최신 krtour-map/kraddr-geo/KASI 계약 반영

**작업**: 사용자가 지시한 대로 `python-krtour-map` 최신 `main`을 별도 clean clone으로
받아 `openapi.user.json` / `openapi.json` / `docs/tripmate-rest-api.md`를 확인했다.
`python-kraddr-geo` 최신 `main`의 `openapi.json` / `llm-summary.md`와
`python-kasi-api`의 특일·출몰시각 함수도 확인해 TripMate 문서에 반영했다.

**핵심 결정**:
- ADR-026 추가 — TripMate ↔ krtour-map은 더 이상 함수 직접 호출이 아니라 최신
  OpenAPI HTTP 계약을 사용한다. API `9011`, admin `9012`.
- ADR-002는 `superseded by ADR-026`으로 변경. `feature` / `provider_sync` schema
  책임은 ADR-003 그대로 krtour-map 소유.
- kraddr-geo v2 최신 표면에 `/v2/regions/within-radius`, `point_precision`,
  `distance_m`, `include_geometry`, admin RustFS/ops 경로를 문서화했다.
- KASI는 `python-kasi-api`와 `DATA_GO_KR_SERVICE_KEY`를 사용한다. 별도 `KASI_*`
  API key는 만들지 않는다.

**KASI 계약**:
- 특일 정보는 하루 1회 Dagster job으로 과거 6개월~미래 18개월 월 범위를 조회해
  `app.kasi_special_days`에 upsert한다. 별도 삭제는 없다.
- POI 생성 시 좌표와 방문일로 "위치별 해달 출몰시각 정보조회"를 1회 호출하고
  `app.trip_poi_rise_sets`에 저장한다. 정기 재조회는 없다.

**후속**:
- T-066 — krtour-map OpenAPI HTTP client 구현 + drift gate.
- T-067 — KASI Dagster job / POI 생성 enqueue 구현.

## 2026-06-03 (codex) — RustFS 9003/9004 + Docker app 스크립트

**작업**: 사용자 지시로 RustFS 저장소 포트를 API `9003`, console `9004`로 고정하고,
krtour-map 독립 프로그램 포트를 API `9011`, admin `9012`로 문서화. 또한
`python-kraddr-geo`의 `scripts/docker_app.sh` 패턴을 참고해 TripMate Docker app
build/run/smoke 스크립트를 추가.

**변경**:
- `infra/docker-compose.yml`, `infra/docker-compose.app.yml` — RustFS 내부/host API
  포트를 `9003`, console 포트를 `9004`로 통일. API/Dagster 내부 endpoint도
  `rustfs:9003` / `app-rustfs:9003`로 정렬.
- `scripts/docker-app.sh` 신규 — `build`, `up`, `down`, `reset`, `status`,
  `logs`, `migrate`, `smoke` 지원. 시작 전 API `9021`, Web `9022`, RustFS
  `9003`/`9004` 점유 컨테이너/프로세스를 정리.
- `scripts/docker-app-smoke-test.sh` — `scripts/docker-app.sh smoke` 호환 wrapper로
  단순화.
- `.env.example`, `package.json`, `README.md`, `SKILL.md`,
  `docs/runbooks/{docker-app,file-storage,etl,README}.md`, `docs/api/storage.md` —
  RustFS 포트와 Docker app 실행 방법 동기화.
- `AGENTS.md`, `CLAUDE.md` — 고정 포트 정책에 RustFS `9003`/`9004`와 Docker app
  스크립트 사용 원칙, krtour-map `9011`/`9012` 포트 추가.
- `docs/krtour-map-integration.md`, `.env.example` — krtour-map API/Admin base URL을
  `9011`/`9012`로 정리하고 예전 debug UI 포트 언급 제거.

**검증**: WSL ext4 미러에 sync 후 `scripts/docker-app.sh smoke --keep-running` 통과.
이미지 빌드, RustFS `/health/live`, Alembic `upgrade head`, API `/health`, API
`/health/db`, Web `/`, RustFS health 응답을 확인했다. Postgres 초기화 race는
Alembic 재시도 루프로 흡수했고, `lsof`가 9022 리스너를 못 잡는 경우를 위해
`fuser` fallback을 보강했다.

## 2026-06-02 (codex) — 로컬 dev 포트 9021/9022/9023 고정

**작업**: 사용자 지시로 로컬 개발 포트 원칙을 고정. API는 `9021`, Web은 `9022`,
Dagster는 `9023`을 항상 사용한다. 해당 포트가 점유되어 있으면 종료하고 같은 포트로
다시 올린다.

**변경**:
- `scripts/dev-up.sh` / `scripts/dev-down.sh` 신규 — 9021/9022/9023 점유 프로세스
  정리 후 API/Web/Dagster dev server 기동.
- `apps/web/package.json` — `next dev` / `next start`를 9022로 고정.
- `.env.example`, `apps/api/app/core/config.py`, `apps/web/**`, `apps/web/Dockerfile` —
  API/Web dev URL 기본값을 9021/9022로 정렬.
- `infra/docker-compose.yml` — Dagster UI host port 9023.
- `infra/docker-compose.app.yml`, `scripts/docker-app-smoke-test.sh` — Docker smoke
  host port도 API 9021 / Web 9022로 정렬.
- `README.md`, `SKILL.md`, `docs/runbooks/{local-dev,README,docker-app,etl}.md`,
  `docs/api/*`, `docs/integrations/*` 등 기존 개발 포트 참조를 새 규칙으로 정정.

**검증 예정**: WSL ext4 미러에 sync 후 `scripts/dev-up.sh`로 포트 점유 종료 +
재기동 확인. 실행 결과는 본 PR 코멘트/최종 보고에 기록.

## 2026-06-02 (codex) — T-062 GitHub Actions secret / branch protection 점검

**작업**: T-062 진행. GitHub Actions secret, branch protection/ruleset, 최근 Actions
실패를 `gh`로 실제 확인하고, 사용자 지시 "API key 안 씀 / 앞으로도 안 씀"과
"프론트엔드 실행은 WSL, e2e Playwright만 Windows"를 운영 문서와 workflow에 반영.

**실측**:
- Actions repository secret은 `0`개. 이는 정책과 일치. `OPENAI_API_KEY`는 등록하지
  않고 앞으로도 사용하지 않는다.
- classic `main` branch protection은 없음(REST 404).
- repository ruleset은 없었으나, `main-pr-only`(id `17146781`)를 적용:
  PR 필수, squash-only, required linear history, force push 차단, branch deletion
  차단, bypass 없음(`current_user_can_bypass=never`).
- 최근 `api` / `web` / `etl` workflow는 PR 또는 push에서 성공 이력 있음.
- 기존 `Codex PR Review` 실패는 `openai/codex-action@v1`의
  `/home/runner/.codex/<run>.json` server info 파일 누락. API key를 쓰지 않는 정책과
  충돌하므로 action 호출을 제거.

**변경**:
- `.github/workflows/codex-pr-review.yml`, `codex-pr-monitor.yml` — 외부 API 호출 없는
  review reminder / head SHA 마커 댓글 workflow로 변경.
- `.github/workflows/README.md`, `docs/runbooks/secrets.md`,
  `docs/runbooks/pr-review-sprint4.md` — API key 미사용, ruleset 실제 상태, required
  status check 보류 사유 기록.
- `AGENTS.md`, `CLAUDE.md`, `docs/dev-environment.md`, `docs/runbooks/local-dev.md` —
  `apps/web` dev/lint/typecheck/build/Vitest는 WSL ext4 미러, Playwright 브라우저
  e2e만 Windows에서 실행하도록 정리.
- `docs/decisions.md` ADR-021 amendment — API key 미사용 + 프론트 실행 경계 반영.
- `docs/tasks.md`, `docs/resume.md` — T-062 완료, 후속 T-065(aggregate CI gate 후
  required status check 적용) 추가.

**후속**: required status check는 현재 `api` / `web` / `etl` path filter 때문에
docs-only PR이 `Expected` 대기에 갇힐 수 있어 바로 적용하지 않음. 항상 실행되는
aggregate gate 설계 후 T-065에서 적용.

## 2026-06-02 (codex) — 최신 main 기준 문서 충돌 정정

**작업**: 최신 `origin/main`(PR #27 이후)에서 문서를 다시 검토하고 ADR-024 개발
환경 모델, ADR-015 지도 클라이언트, ADR-025 geocoding 경계와 충돌하는 잔여 표현을
정정.

**변경 파일**:
- `README.md`, `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `docs/agent-guide.md`
- `docs/runbooks/local-dev.md`, `docs/runbooks/README.md`, `docs/runbooks/etl.md`
- `docs/architecture.md`, `docs/api/features.md`
- `docs/conventions/coding-style.md`, `docs/conventions/testing.md`
- `docs/sprints/SPRINT-1.md`, `docs/sprints/SPRINT-4.md`
- `docs/spec/v8/00-infrastructure.md`
- `docs/execplan/doc-review-2026-06-02.md`, `docs/resume.md`, `docs/tasks.md`

**결정**: 신규 ADR은 만들지 않음. 기존 accepted ADR-015/024/025를 문서 전반에
적용하는 정합성 수정.

**발견**: `docs/runbooks/local-dev.md`와 `docs/agent-guide.md`에 ADR-024 이전의
"WSL 미러에서 git/commit" 모델과 "코드 작성 금지 단계" 문구가 남아 있었다.
`docs/architecture.md`에는 React 18 / Kakao SDK / `@krtour/map-marker-react` 시절
표현이 남아 있었고, 진입 문서에는 ADR-023 이전의 Odroid 단일 노드 표기가 남아
있었다.

**다음**: PR 머지 후 실제 다음 작업은 `docs/resume.md`의 Sprint 2 잔여 마감 또는
Sprint 4 PR-B2(features client readiness) 후보 중 선택.

## 2026-06-02 (claude) — geocoding을 kraddr-geo v2 REST 직접 호출로 (ADR-025)

**작업**: krtour-map / kraddr-geo 문서를 확인하고, TripMate geocoding을 kraddr-geo
v2 REST API 직접 접근으로 문서화 (사용자 지시 "geocoding 관련 기능은 kraddr geo v2
api에 직접 접근"). 문서화만, 코드 변경 없음.

**핵심 발견(경계)**: TripMate 외부 데이터 의존이 두 갈래인데 문서가 이를 뭉뚱그려
region/주소를 krtour-map 함수 경유로 서술하고 있었다.
1. Feature 데이터(place/event/weather/...) → krtour-map **함수 직접 호출**(ADR-002).
2. Geocoding/주소/행정구역 → **kraddr-geo v2 REST HTTP 직접**(사용자 지시).
   kraddr-geo는 이미 `POST /v2/{geocode,reverse,search}` candidate 표면 제공, krtour-map도
   자기 ETL 적재 때 이 v2를 HTTP로 쓴다(그쪽 ADR-006) → v2가 geocoding 공식 표면.

**신규/변경**:
- ADR-025 신설 — 사용자 대면 geocoding은 kraddr-geo v2 REST 직접. feature는 종전
  함수 호출 유지. region도 v2(reverse `include_region` / search `type=district`)로
  수렴. VWorld/juso 직접 호출 금지(kraddr-geo 내부). 다음 ADR 025→026.
- `docs/integrations/kraddr-geo.md` 신규 — v2 3개 endpoint 정확한 req/resp, 좌표
  `(lon,lat)`·코드 규약, httpx client 주입+lifespan, `/geo/*` 노출 endpoint, 캐싱·
  rate-limit, 위치 감사(`/geo/reverse`), 에러 graceful degrade, 사용처 매핑, AI agent
  구현 체크리스트, 환경변수.
- `docs/architecture/geocoding-open-decisions.md` 신규 — 사용자 판단 대기 8건
  (D1 regions 처리 / D2 fallback=api / D3 캐시 / D4 quantize / D5 within-radius /
  D6 MCP / D7 network·auth / D8 precision 활용). 각 잠정 기본값으로 구현 막지 않음.
- `docs/api/regions.md` 정정(krtour-map 경유 → kraddr-geo v2), `user-location.md`
  역지오코딩 region label + `reverse_geocode` purpose 추가, `krtour-map-integration.md`
  경계 명시. CLAUDE/AGENTS 인덱스에 geocoding 행.

**의사결정 별도화**: 사용자 지시대로 열린 결정은 `geocoding-open-decisions.md`에
모으고 잠정값으로 진행(되돌리기 비용 있는 선택만 가시화).

**다음**: 본 PR 머지 → Sprint 4 PR-B2(features) 또는 geocoding `/geo/*` 구현 시
본 문서 기준. open-decisions D1~D8은 사용자 확정 시 ADR로 박음.


## 2026-06-01 (claude) — 에이전트 환경 문서를 python-kraddr-geo에 정렬

**작업**: 개발 환경 문서 구조를 별 저장소 `python-kraddr-geo`의 성숙한 3-doc 패턴에
맞춰 정렬 (사용자 지시 "python kraddr geo에 맞춰").

**배경**: ADR-024로 환경 모델은 확정했으나, kraddr-geo는 그 위에 (1)
`dev-environment.md`(reference) + (2) `agent-workflow.md`("무엇을 치는가" 런북) +
(3) `agent-failure-patterns.md`(반복 실패 카탈로그) 3단 구조 + `agent/<agent>-idle`
idle 브랜치 컨벤션을 갖고 있었다. tripmate는 (1)만 있고 idle 브랜치는 `-init`이었다.

**신규/정렬**:
- `docs/agent-failure-patterns.md` 신규 — kraddr-geo 패턴 포팅 + 이번 세션 실측:
  WSL git on NTFS worktree 포인터 혼용, 명령 런처/대량 병렬 backlog, MSYS `grep`의
  `\n` 오해석(정상 문서를 손상으로 오판 → ripgrep/`od -c` 교차검증), async alembic
  미커밋 + pytest-asyncio 루프/풀.
- `docs/agent-workflow.md` 신규 — 두 위치 표 + 함정 먼저(git.exe/PATH/TMP) + 작업
  루프 + 붙여넣기 체크리스트. 스크립트(`agent_env.sh` 등) 대신 수동 명령(사용자
  결정: 스크립트 없이 문서 절차만).
- **idle 브랜치 `agent/<agent>-init` → `-idle`** (kraddr-geo 통일). worktree 생성을
  Windows git.exe로 하라는 caveat 추가(WSL 생성 시 `/mnt/f` 포인터 사고).
- AGENTS.md worktree 표에 idle branch 열 추가, AGENTS/CLAUDE/dev-environment/
  agent-guide §10에서 신규 2개 문서 cross-link. agent-guide §10의 구 모델 문구
  (양방향 sync) 교체.

**검증**: 내부 링크 점검(깨진 참조 0), `-init` 잔존 0, 신규 문서 2개 + 수정 5개.

**다음**: 본 PR 머지 → 각 에이전트가 `docs/agent-workflow.md` 따라 진입.


## 2026-06-01 (claude) — 개발 환경 모델 확정 (ADR-024)

**작업**: NTFS git + WSL 개발/테스트 환경에서 에이전트(특히 codex)가 반복적으로
헤매던 문제의 근본 원인을 잡고, 따라 할 수 있는 절차로 문서화 (사용자 지시,
`python-kraddr-geo` 문서 참고).

**근본 원인**: `docs/dev-environment.md`가 구 모델(ADR-004: "WSL ext4가 표준 작업
위치 / Git source of truth는 ext4 / 양방향 rsync")을 그대로 서술하는데, ADR-017 +
AGENTS/CLAUDE는 신 모델(NTFS worktree + Windows git.exe)을 말해 **문서 간 모순**이
있었다. 그래서 에이전트가 "어디서 commit?"을 헤맸다. 실제 증거:
- codex worktree `.git` = `gitdir: /mnt/f/dev/tripmate/.git/worktrees/tripmate-codex`
  (WSL 생성), claude worktree = `gitdir: F:/dev/tripmate/.git/worktrees/tripmate-geo-claude`
  (Windows 생성, 게다가 stale `-geo-` 이름). 환경 혼용 시 `fatal: not a git
  repository` / `prunable` → 잘못된 prune으로 worktree 삭제 위험.

**결정·문서**:
- **ADR-024 신설** — NTFS worktree = git source of truth(Windows git.exe) / WSL ext4
  = 일회용 테스트 미러(단방향 rsync, commit 금지). ADR-004의 source-of-truth 주장만
  supersede(디스크/경로는 유지). 다음 ADR 번호 024→025.
- **`docs/dev-environment.md` 전면 재작성** — §0에 codex가 겪은 함정 4종(포인터
  혼용 / source 모호 / WSL PATH 오염 / TMP=Windows Temp)과 대책, §1~§12에 레이아웃·
  worktree·미러 rsync·셋업·PATH·검증 게이트·DB·체크리스트. `python-kraddr-geo`와
  동일 패턴.
- **AGENTS.md / CLAUDE.md 동기**(ADR-016) — 모순됐던 "Git source of truth는 ext4"
  문구 교체, 진입 절차표·§7 인덱스에 dev-environment 행 추가.
- **`docs/runbooks/codegraph-worktrees.md`** — §3.6 Windows/WSL git 포인터 함정 +
  `git worktree repair` 복구 절차 추가, ADR-024 참조.

**검증**: 내부 문서 링크 점검(깨진 참조 0), ADR 번호 정합(024 박힘/다음 025),
AGENTS↔CLAUDE 동기 확인.

**사용자 액션 권장(문서 밖)**: claude worktree의 stale 포인터(`tripmate-geo-claude`)는
trunk에서 `git worktree repair F:\dev\tripmate-claude`로 교정하면 깔끔하다.

**다음**: 본 PR 머지 → 각 에이전트가 `docs/dev-environment.md` 따라 미러 재셋업.


## 2026-06-01 (claude) — Sprint 2 핵심 DoD 마감

**작업**: Sprint 2 잔여 구현 — Google OAuth(G-4 안전 매칭) + Notice plan → trip
copy(ADR-013) + 통합 테스트 harness/스위트 (사용자 지시 "Sprint 2 완료").

**컨텍스트**: Sprint 2 코드는 머지돼 있었으나 (1) OAuth service/route, (2) Notice
plan service/route/copy, (3) `tests/integration` 이 비어 있었음 — 모델/스키마/
마이그레이션은 이미 존재. 본 작업이 service+route+test 계층을 채움.

**신규**:
- `app/services/oauth_google.py` — G-4 안전 매칭(기존 identity 로그인 / Google
  `email_verified=true` + 동일 이메일 로컬계정 → 안전 연결 / 미인증 → 비연결 신규,
  provider-namespaced email 로 UNIQUE 충돌 회피) + state·PKCE + HTTP 분리.
- `app/api/v1/oauth.py` — `/auth/oauth/google/{start,callback}` + `/providers` + unlink.
- `app/services/notice_plan.py` — published listing/상세 + `copy_plan_to_trip`
  (notice_pois → trip_day_pois, LexoRank append, plan_poi_attachments 복제) + seed helper.
- `app/api/v1/notice_plans.py` — listing / 상세 / `POST /{id}/copy`.
- `app/api/v1/users.py` — `PUT /users/me/consents`, `DELETE /.../{type}` REST endpoint.
- `tests/integration/` — conftest harness + 7개 파일 27 테스트.

**부수 버그 수정**:
- **`alembic/env.py`** — async 마이그레이션이 DDL 트랜잭션을 커밋하지 않던 잠재
  버그(`AsyncConnection` 가 commit 없이 롤백). `connection.commit()` 추가.
  testcontainer 로 실제 테이블 생성 검증 중 발견 — CI 는 exit code 만 봐서 미검출.
- `services/poi.py` — sort_order UNIQUE 위반 → `SortOrderConflictError`(409).

**검증** (WSL ext4 미러 + Docker PostGIS, git=Windows git.exe — ADR-017):
- `pytest tests/unit` → 53 passed
- `pytest tests/integration` → **27 passed** (postgis/postgis:16-3.5-alpine)
- `ruff check` / `ruff format --check` / `mypy --strict app` → 통과

**잔여(후속)**: 위치 감사 자동 적재 e2e(`/features/in-bounds` — Sprint 4 krtour
client 의존), `email_queue` SKIP LOCKED worker + 비밀번호 재설정, `api_call_log`
미들웨어 통합 테스트. 상세 `docs/sprints/SPRINT-2.md` "잔여" 절.

**교훈**: testcontainers + async alembic 은 마이그레이션이 실제로 커밋되는지
(테이블 count) 까지 확인할 것 — exit code 만으로는 부족. pytest-asyncio
function-loop 에서는 엔진을 함수 스코프 + NullPool 로 만들어야 "another operation
in progress" / "Future attached to different loop" 를 피한다.

**다음**: 본 PR 머지 → 실질 다음은 Sprint 4 PR-B2 (krtour client + 위치 감사 e2e)
또는 PR-C (프론트엔드) — `docs/resume.md`.


## 2026-06-01 (claude)

**작업**: 문서 정합성 점검 + git 실행 정책 / `.codegraph` ignore 명시 (PR #19, #20).

**컨텍스트**: 사용자의 "문서 정합성 확인 + 보완 + git Windows 버전 명시 +
`.codegraph` gitignore" 지시. Windows worktree(`F:/dev/tripmate-claude`, NTFS)에서
작업.

**반영 (유효)**:
- **git 실행 정책** — Windows worktree(NTFS)에서 git 명령은 Windows 버전
  git(`git.exe`) 사용, WSL git으로 `/mnt/f` NTFS 경로 조작 금지. pytest/docker/
  npm은 기존대로 WSL ext4 미러(ADR-004) 유지. `CLAUDE.md` worktree 블록 +
  `AGENTS.md` worktree/WSL 섹션 + `docs/decisions.md` ADR-017 amendment(2026-05-31)에
  동기 반영 (ADR-016 준수).
- **`.codegraph/` ignore** — `.gitignore`에 이미 반영(71~72행, ADR-017 후속)됨을
  확인. 변경 불필요 — ADR-017 amendment에 명시.
- **`docs/decisions.md`** — ADR-017 블록 안에 잘못 들어가 있던 `다음 신규 =
  ADR-024.` 중복 라인 제거. 정식 `## 다음 ADR 번호` 섹션(파일 끝)은 유지.
- **`CLAUDE.md` §5** — "가장 중요한 5개" → "6개" (실제 6개 룰 나열에 맞춰 정정).

**정정 기록 (중요)**: PR #19/#20 작업 중 "literal `\n` 직렬화 손상 10개 문서"로
오판해 변환을 수행했으나, **실제 손상이 아니었음**. 원인은 Windows MSYS `grep`이
`\n` 패턴을 개행으로 해석해 정상 문서를 손상으로 표시한 도구 아티팩트.
ripgrep / `od -c` / Read 교차검증 결과 모든 문서는 처음부터 정상 마크다운이며
실내용 변경 없음. 따라서 PR #19/#20 커밋 메시지의 "literal \n 복구" 문구는
부정확 — 실질 변경은 위 git 정책 / 중복 제거 / 카운트 정정뿐. 또한 #19에 실수로
포함된 임시 스크립트 `_verify.js`는 #20에서 제거.

**교훈**: NTFS worktree에서 텍스트 패턴 검사는 MSYS `grep` 대신 ripgrep(Grep
도구)을 쓴다. `\n` 같은 메타문자 카운트는 도구별 해석 차이가 크므로 `od -c` /
Read로 교차검증 후 판단한다.

**후속**: 본 PR(journal) 머지 + 머지된 로컬 브랜치 정리.

## 2026-06-01 10:20 (codex)

**작업**: 기준 문서 정합성 복구. Sprint 상태, 진입 절차, backlog 추적 문서의
시점 불일치를 정리.

**컨텍스트**: `README.md`는 여전히 "Sprint 1 진입 직전 / 문서 전용"으로 남아
있었고, `AGENTS.md`는 코드 작성 금지 규칙을 현재형으로 유지했다. 반면 실제
저장소에는 Sprint 1~3 산출물, Sprint 4 workflow, features API 구현이 이미 있다.
`resume.md`와 `tasks.md`도 최신 `journal.md`보다 과거 시점을 가리켰다.

**갱신 파일**:
- `docs/execplan/doc-sync-2026-06-01.md` — 문서 정합성 복구 범위 기록
- `README.md` — 현재 상태를 Sprint 4 기준선으로 갱신, 진입 순서 정리
- `AGENTS.md` — stale한 "코드 작성 금지"를 현재 단계 정책으로 교체
- `CLAUDE.md` — 현 단계 설명을 Sprint 4 준비/진행으로 갱신
- `SKILL.md` — quick start 주석과 첫 5분 진입 프로토콜 정합화
- `docs/agent-guide.md` — 도구별 1차 진입 파일 기준으로 프로토콜 재정렬
- `docs/resume.md` — PR-A/T-030 등 stale 항목 제거, 다음 작업 재기록
- `docs/tasks.md` — Sprint 4 backlog 중심으로 재정렬, 완료/진행 항목 수정
- `docs/architecture/frontend.md` — `apps/web/lib/kakao.ts` 구 경로 참조 제거

**결정**: 최신 기준선은 "Sprint 1~3 머지 완료 + Sprint 4 준비/진행"으로 본다.
진행 추적은 `resume.md` 단독이 아니라 `resume.md` + `tasks.md` + `journal.md`
교차 확인이 필요하다.

**발견**: 문서 drift의 대부분은 상태 문구가 실제 merge 이후 갱신되지 않은 데서
생겼다. 신규 ADR보다 상태 추적 문서의 정기 정리가 먼저 필요하다.

**다음**: secret / branch protection 실제 적용 여부를 확인하고 Sprint 4 open item을
merge 상태 기준으로 다시 쪼갠다.

## 2026-05-27 16:30 (claude)

**작업**: worktree 이름 prefix `geo-` → `tripmate-` 변경 (ADR-017 amendment).

**컨텍스트**: 사용자 지시. `geo-claude` / `geo-codex` / `geo-antigravity` →
`tripmate-claude` / `tripmate-codex` / `tripmate-antigravity`. 경로 예시도
`F:/dev/tripmate-<agent>` + WSL `~/tripmate-workspaces/tripmate-<agent>`.

**갱신 파일** (정의 문서 4개 — journal 과거 엔트리는 사실 기록이라 유지):
- `docs/decisions.md` — ADR-017 본문 + amendment 노트
- `docs/runbooks/codegraph-worktrees.md` — 전 구간 경로/이름
- `AGENTS.md` — worktree 표 + DO NOT
- `CLAUDE.md` — 머리 박스 + DO NOT #6

**후속**: 본 PR 머지 후 trunk에서 실제 worktree 디렉터리 rename —
`git worktree move ../tripmate-geo-claude ../tripmate-claude`.


## 2026-05-27 16:00 (claude)

**작업**: Sprint 4 진입 PR-B — 백엔드 features API + lifespan + cluster_query +
trip_view_builder.

**컨텍스트**: PR-A (#15) 머지 후 후속. `python-krtour-map` 라이브러리 client는
아직 Sprint 2 라이브러리측 placeholder (실 구현 없음) — TripMate는 Protocol 정의 +
lazy import 패턴으로 인터페이스 박음. 실 client 주입은 라이브러리 ready 시 후속 PR-B2.

**신규 / 갱신**:

- `apps/api/app/etl_bridge/__init__.py` 신규 디렉토리
- `apps/api/app/etl_bridge/krtour_map.py` 신규 — `KrtourMapClient` Protocol (8 메서드)
  + `krtour_map_lifespan` FastAPI lifespan (lazy import, 라이브러리 미주입 시 503)
  + `KrtourMapClientDep` 의존성 alias
- `apps/api/app/schemas/feature.py` 신규 — Coord / BBox / FeatureSummary /
  FeatureCluster / FeaturesInBoundsResponse / FeatureDetail / WeatherTimepoint /
  FeatureWeatherCard / FeatureRequestCreate / FeatureRequestResponse
- `apps/api/app/api/v1/features.py` 신규 — 6 endpoint (in-bounds / nearby /
  search / get / weather / POST requests)
- `apps/api/app/services/cluster_query.py` 신규 — zoom → mode (sido / sigungu /
  dbscan / individual) + 각 모드 PostGIS raw SQL. TripDayPoi `attachment_id` PK +
  `(trip_id, day_index)` FK 정합
- `apps/api/app/services/trip_view_builder.py` 신규 — `app.trips ↔ feature.feature`
  batch join (N+1 회피) + `feature_link_broken_at` 처리
- `apps/api/app/main.py` — lifespan 합성 (기존 + krtour_map_lifespan)
- `apps/api/app/api/v1/__init__.py` — features router 등록
- `packages/schemas/src/feature.ts` 신규 — Zod 11개 schema, 한국 범위 검증 (ADR-018)
- `packages/api-client/src/endpoints/feature.ts` 신규 — 6 endpoint client
- 테스트: `tests/unit/test_feature_schemas.py` (Pydantic validation) +
  `tests/unit/test_cluster_query.py` (zoom → mode 매트릭스)

**제약 / 책임 분리**:
- TripMate는 wrapper 만들지 않음 (ADR-005) — Protocol은 type contract라 OK
- 라이브러리 client는 lifespan에서 lazy import — placeholder 상태에서는
  ImportError → `None` 으로 두고 503 fallback
- 사용자 데이터 (trip / poi) join은 TripMate 책임, feature 데이터는 라이브러리
  batch 호출

**다음**: 본 PR 머지 → Sprint 4 PR-C (프론트엔드 — apps/web/components/map/* +
지도 lib) → PR-D (라이브러리 PR sync + E2E + v0.1.0 tag).

## 2026-05-27 15:00 (claude)

**작업**: Sprint 4 진입 PR-A — GitHub Actions workflow 5개 복원 (ADR-021).
Sprint 1~3 동안 비활성이었던 CI/CD 부활.

**컨텍스트**: PR #14 (Sprint 4~6 plan)에서 ADR-021로 결정 박힘. 본 PR이 실제
workflow YAML을 복원하는 첫 단계. Sprint 4 본격 코드 구현 (features API + 지도
UI) 은 후속 PR.

**복원 / 신규**:

- `.github/workflows/api.yml` 복원 — ruff + format check + mypy --strict +
  pytest + alembic upgrade (PostGIS service container)
- `.github/workflows/web.yml` 복원 — npm ci + lint + typecheck + build
- `.github/workflows/etl.yml` 복원 — ruff + pytest (placeholder, Sprint 5 본격)
- `.github/workflows/codex-pr-review.yml` 복원 — PR open/ready_for_review 자동
  Codex 리뷰 + 코멘트 (`docs/runbooks/pr-review-sprint4.md`)
- `.github/workflows/codex-pr-monitor.yml` 복원 — 5분 cron으로 review 마커
  없는 PR 재리뷰
- `.github/workflows/README.md` 신규 — workflow 인덱스 + branch protection
  설정 안내
- `docs/runbooks/secrets.md` 신규 — GitHub Actions secret 카탈로그
  (`OPENAI_API_KEY` 등, 2026-06-02 사용자 지시로 API key 미사용 정책에 의해 superseded)

**복원 source**: `git show dd11f04~1:.github/workflows/<file>` — Sprint 1 머지
직전 (커밋 `dd11f04` "chore: remove GitHub Actions workflows") 의 직전 상태.

**다음**: PR 머지 → 사용자가 GitHub UI에서 (1) `OPENAI_API_KEY` secret 등록 +
(2) branch protection 활성 → Sprint 4 본격 코드 PR (PR-B 백엔드 / PR-C 프론트엔드).
이 다음 행동은 2026-06-02 T-062에서 superseded: API key는 쓰지 않고, `main-pr-only`
repository ruleset을 적용했다.



## 2026-05-27 13:30 (claude)

**작업**: Sprint 4~6 plan 정밀화 + 릴리즈 마일스톤 (v0.1.0 / v0.2.0 / v1.0.0)
+ ADR-018~023 6건 박음. AI agent가 본 문서들만 보고 자율 진행 가능하도록 상세화.

**컨텍스트**: 사용자 8개 지시 일괄 반영:

1. 외부 인터페이스 MCP 서버 — 마지막 Sprint (Sprint 6, v1.0)에 포함 (ADR-019)
2. 지도 = `maplibre-vworld-js` — 공통 기능 라이브러리 PR / TripMate 전용 분리 명시,
   v0.1.0 게이트 (Sprint 4)
3. GitHub Actions CI/CD 재활성 — Sprint 4 진입 시 (ADR-021, 이전 비활성 결정 뒤집기)
4. T100~T106, T108 진행, T107 보류 — Gemini 별 repo로 분리 (ADR-020)
5. T108 하드웨어 확장 — N150 16GB / NVMe 1TB / Ubuntu 26.04 + Odroid 병행 (ADR-023)
6. 한국 전용 geofencing — Cloudflare WAF + nginx geo + FastAPI middleware 3중
   안전망 (ADR-018)
7. Backup/Restore + UI — 핫스왑 패턴 (ADR-022)
8. Admin Grafana iframe embed — `/admin/grafana` (Sprint 5)

**신규 / 갱신 파일**:

- `docs/decisions.md` — ADR-018 ~ ADR-023 6건 박음
- `docs/sprints/README.md` — 릴리즈 마일스톤 표 + Sprint 1~3 머지 표시
- `docs/sprints/SPRINT-4.md` — v0.1.0 closure + CI/CD 재활성 + §5 라이브러리
  PR / TripMate 전용 분류 + §6 v0.1.0 절차 + §7 workflow 복원
- `docs/sprints/SPRINT-5.md` — Grafana embed + Backup/Restore 1차 + v0.2.0 tag
- `docs/sprints/SPRINT-6.md` — MCP 외부 인터페이스 + Backup UI 핫스왑 + T108
  Odroid+N150 + Korean geofencing + T-107 defer + E2E 9 시나리오 (기존 6 + 3
  신규) + v1.0.0 tag
- `docs/tasks.md` — T-100~T-106 상태 갱신 + T-107 deferred + T-108 확장 +
  신규 T-109~T-114 backlog
- `docs/architecture/mcp-server.md` 신규 — ADR-019 1차 reference
- `docs/architecture/korea-only-policy.md` 신규 — ADR-018 1차 reference
- `docs/architecture/backup-restore.md` 신규 — ADR-022 1차 reference
- `docs/runbooks/mcp-server.md` 신규 — 토큰 발급 / 운영 / 트러블슈팅
- `docs/runbooks/korea-only.md` 신규 — Cloudflare WAF + nginx geo 설정 +
  GeoIP 갱신
- `docs/runbooks/backup-restore.md` 신규 — backup / restore / 핫스왑 절차
- `docs/runbooks/grafana-admin-embed.md` 신규 — Grafana iframe + CSP
- `docs/runbooks/README.md` — 새 runbook 5개 인덱스 갱신
- `docs/integrations/maplibre-vworld.md` — §6에 책임 분류 (라이브러리 PR / TripMate
  전용 / 분류 변경 절차) 추가
- `CLAUDE.md` — 현 단계 갱신 + §7 인덱스에 4개 신규 문서 추가
- `AGENTS.md` — 릴리즈 로드맵 표 신설

**다음**: PR 생성. 머지 후 사용자 결정 — Sprint 4 진입 PR 시작 (지도 + CI/CD
복원).

## 2026-05-26 23:30 (claude)

**작업**: ADR-017 박음 — CodeGraph 인덱스 + agent별 고정 worktree 운영. 별 PR로
분리 (Sprint 3 admin PR과 무관).

**컨텍스트**: 사용자 지시:

- Claude Code / OpenAI Codex / Google Antigravity 2.0 세 도구가 동시 편집 →
  고정 worktree로 격리 (`geo-claude` / `geo-codex` / `geo-antigravity`).
- 작업마다 worktree 새로 만들지 않고 **브랜치만** 새로 (`git fetch && git
  switch -c agent/<agent>-<task> main`).
- `colbymchenry/codegraph`로 의미 인덱스 — worktree마다 1회 `codegraph init -i`,
  이후 task 시작 시 `codegraph sync`.
- `.codegraph/`는 `.gitignore`.

**신규 / 갱신**:

- `docs/decisions.md` — ADR-017 박음
- `docs/runbooks/codegraph-worktrees.md` 신규 — 1회 setup + task 흐름 + 도구별
  메모 + trunk 관계
- `docs/runbooks/README.md` — 인덱스 갱신
- `.gitignore` — `.codegraph/` 추가
- `CLAUDE.md` — 머리 호환성 박스에 worktree 정책 추가 + DO NOT #6 (trunk 직접
  편집 금지) + §7 빠른 문서 검색에 runbook 추가
- `AGENTS.md` — "개발 환경 정책" 머리에 Worktree + CodeGraph 섹션 + 브랜치 명명
  컨벤션 갱신 (`agent/<agent>-<task>`)

**다음**: PR 생성 후 머지 → 실제 codegraph 설치 + geo-claude worktree 생성 +
init -i 실행.

## 2026-05-26 22:00 (claude)

**작업**: Sprint 3 진입 — Admin RBAC + audit chain + 사용자 목록/상세 + force-verify/disable + 이메일 큐 + 감사 로그 chain 검증 + 13페이지 frontend skeleton.

**Backend** (`apps/api/app/`):
- `core/rbac.py` — `require_role()` 의존성. 미권한 → **404** (존재 자체 숨김, SPEC V8 M-4)
- `services/admin_audit.py` — `append_admin_audit()` (prev_hash + content_hash 자동 계산, append-only trigger 호환)
- `services/admin_users.py` — `force_verify` / `disable_user` / `list_users` / `mask_email`
- `schemas/admin.py` — AdminUserSummary (마스킹) / AdminUserDetail (정식) / AdminActionRequest (사유 필수) / AdminAuditEntry / AdminPagedResponse
- `api/v1/admin/users.py` — GET `/admin/users` (page/limit/status_filter), GET `/admin/users/{id}`, POST `{id}/force-verify`, POST `{id}/disable`
- `api/v1/admin/audit.py` — GET `/admin/audit` + GET `/admin/audit/verify-chain` (cpo 권한 전용)
- `api/v1/admin/emails.py` — GET `/admin/emails` (status_filter) + POST `{id}/resend`
- `api/v1/__init__.py` — `admin_router` 통합

**Frontend** (`apps/web/`):
- `app/(admin)/admin/layout.tsx` — 사이드바 13개 + `/auth/me` RBAC guard (admin/operator/cpo 외 → /admin/login)
- `app/(admin)/admin/login/page.tsx` — admin role 검증 후 router push
- `app/(admin)/admin/page.tsx` — 대시보드 8 카드 placeholder
- `app/(admin)/admin/users/page.tsx` — DataTable + status filter + pagination
- `app/(admin)/admin/users/[user_id]/page.tsx` — 상세 + force-verify/disable 다이얼로그 (access_reason 필수)
- `app/(admin)/admin/emails/page.tsx` — DataTable + status filter + 재발송 버튼
- `app/(admin)/admin/audit/page.tsx` — DataTable + chain 검증 버튼
- `app/(admin)/admin/{trips,features,pois,etl,api-calls,feature-requests,category-mapping,seed,reset}/page.tsx` — Placeholder (Sprint 4~6 결선)
- `components/admin/{AdminPage,DataTable,Placeholder}.tsx` — 공통 chrome

**packages**:
- `packages/schemas/src/admin.ts` — Admin Zod 스키마 + envelope
- `packages/api-client/src/endpoints/admin.ts` — listUsers/getUser/forceVerify/disableUser/listAudit/verifyChain/listEmails/resendEmail
- `packages/design-tokens/{tailwind-preset.cjs,src/colors.ts}` — `error-bg` / `success-text` / `success-bg` 시맨틱 색 추가

**테스트**: `tests/unit/test_admin_users.py` (mask_email), `tests/unit/test_admin_audit_hash.py` (chain 안정성/연결).

**제약 유지**: GitHub CI/CD 없음 (local WSL only). main 직접 push 금지 (PR-only).

---

## 2026-05-26 17:00 (claude)

**작업**: Sprint 2 진입 — 도메인 API + DB + 4 분리 동의 + Resend webhook + 위치 감사 + Storage presigned.

**신규 Alembic** (`apps/api/alembic/versions/20260602_*`):
- `0001_trips_and_share` — `trips` + `trip_companions` + `trip_share_links`
- `0002_pois_collate_c` — `trip_days` + `trip_day_pois` (`sort_order TEXT COLLATE "C"`, SPEC V8 E-6 Critical)
- `0003_audit_chain` — `location_access_log` + `admin_audit_log` (content_hash chain + append-only trigger)
- `0004_email_queue_and_api_log` — `email_queue` + `api_call_log` + `user_oauth_identities` + `oauth_login_states`
- `0005_notice_plans_and_attachments` — `notice_plans` + `notice_pois` + `plan_poi_attachments` (단일 테이블 4 대상)

**신규 모델**: trip / trip_day / poi / companion / share_link / audit / email_queue / api_call_log / oauth_identity / notice_plan / attachment

**신규 Pydantic schema**: trip / poi / consent / share_link / notice / storage / oauth.
**신규 Zod schema** (공용): trip / poi / notice-plan / storage.

**신규 services**:
- `hash_chain` — content_hash + GENESIS_HASH
- `lexorank` — between/before/after (POI sort_order, COLLATE "C" 일관)
- `trip` — CRUD + 동반자 + 공유 토큰 발급/revoke + optimistic lock
- `poi` — CRUD + reorder + sort_order conflict 처리
- `consent` — 4 분리 동의 + demographic 부작용 (`gender`/`birth_year_month`/`residence_sigungu_code` NULL)
- `rustfs_storage` — presigned PUT URL 생성 (실서명은 Sprint 5)

**신규 미들웨어**:
- `location_audit` — 좌표 query 자동 detect + `app.location_access_log` chain 적재
- `api_call_logging` — httpx event_hook → `app.api_call_log`

**신규 라우터**:
- `/trips` + `/trips/{id}` (CRUD, If-Match) + `/trips/{id}/share-tokens`
- `/trips/{id}/pois` (CRUD) + `/trips/{id}/pois/reorder` (LexoRank batch)
- `/users/me/profile/complete` + `/users/me/consents` + withdraw
- `/storage/upload-urls` (presigned PUT)
- `/webhooks/resend` (Svix 서명은 Sprint 5에 실 검증)

**프론트**:
- `apps/web/lib/locationAdapter.ts` — `navigator.geolocation` LocationAdapter
- `apps/web/app/(auth)/profile-complete/page.tsx` — 4 분리 동의 UI + (선택) demographic 항목

**단위 테스트**: hash_chain (chain link 검증) / lexorank / consent schema (필수 동의 누락 / demographic 부작용) / storage keys

**보류 (Sprint 2 후속 PR 또는 Sprint 3 시작 PR로 분리)**:
- Google / Naver / Kakao OAuth start/callback 라우터 (모델·schema·migration 박혀 있음)
- Resend Webhook Svix 서명 (Sprint 5)
- Notice plan copy 흐름 (라우터 미작성, schema·model만)
- 통합 테스트 (PostGIS testcontainer + Alembic + httpx ASGI) — DoD pytest sanity는 단위만

**다음**: PR push + 머지 대기 → Sprint 3 (Admin 콘솔 + RBAC + audit chain integration + seed) 진입.

## 2026-05-26 13:00 (claude)

**작업**: 지도 클라이언트를 내부 라이브러리 `maplibre-vworld-js`로 전환
(ADR-015) + AI 에이전트 도구 다중 지원 (`AGENTS.md` ↔ `CLAUDE.md` 동기 정책,
ADR-016).

**컨텍스트**: 사용자 두 요청:

1. "kakao map 쪽은 내부 라이브러리인 maplibre-vworld-js로 대체. 관련 내용 변경
   하고, 추가로 maplibre-vworld-js에 필요한 기능을 정리한 문서를 만들 것."
2. "CLAUDE.md 외 codex와 antigravity 에서도 대응할 수 있도록 AGENTS.md도 항상
   함께 수정."

`maplibre-vworld-js`는 사용자가 보유한 내부 라이브러리 (`F:\dev\maplibre-vworld-js`,
Antigravity 2.0 + Gemini 3.1 Pro로 작성). VWorld + MapLibre GL JS 선언형 React
통합. `VWorldMap` / `ClusterLayer` / `PolygonArea` / `RouteLine` / `Popup` +
도메인 마커 (`PlaceMarker` / `PriceMarker` / `WeatherMarker`) generic primitive
제공 (이후 리팩터로 `MarkerClusterer` → `ClusterLayer`, `MapPopup` → `Popup`
이름 변경, TripMate 전용 wrapper / 팔레트는 라이브러리에서 제거).

**신규 파일**:

- `docs/integrations/maplibre-vworld.md` — 라이브러리 식별자 + 환경변수 +
  사용 패턴 + 16색 매핑 + 라이브러리 보강 필요 카탈로그 (§6)

**갱신 (Kakao → maplibre-vworld-js)**:

- `docs/integrations/kakao-map.md` — 폐기 표시 + 이전 가이드 표
- `docs/integrations/README.md` — 인덱스
- `docs/architecture/frontend.md` — 스택 표
- `docs/architecture/map-marker-design.md` — Mapbox token 정책
- `docs/architecture/user-location.md` — `setCenter` / `flyTo` → 선언형 prop
- `docs/api/features.md` — zoom 7~19 (VWorld 한계) / Kakao 한도 → VWorld 한도
- `docs/api/common.md` — CSP `connect-src` VWorld 추가
- `docs/spec/v8/00-infrastructure.md` — CSP
- `docs/spec/v8/03-frontend.md` — 스택 채택 표
- `docs/spec/v8/05-execution.md` — A-1 #4 결정 정정
- `docs/sprints/SPRINT-4.md` — 지도 어댑터 / ADR 후보 → ADR-015
- `docs/runbooks/docker-app.md` — 환경변수
- `docs/compliance/data-policy.md` — Kakao Map TOS → VWorld
- `docs/compliance/pipa.md` — 위탁자 (VWorld 추가, Kakao는 OAuth만)
- `docs/conventions/geospatial.md` — Kakao lat-lng 어댑터 폐기
- `docs/integrations/sentry.md` / `loki.md` — Kakao 언급 정정
- `docs/data-sources/README.md` — 지도 SDK 항목
- `docs/compliance/README.md` — provider 목록
- `README.md` — 의존 라이브러리

**ADR 추가**:

- **ADR-015** 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- **ADR-016** AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책

**진입 가이드 강화**:

- `AGENTS.md` 머리 — "AI 에이전트 도구 지원 — `AGENTS.md` 단일 진실" 섹션 +
  도구별 1차 진입 표 (Claude / Codex / Antigravity / Cursor)
- `CLAUDE.md` 머리 — 호환성 안내 추가
- `SKILL.md` 머리 — 도구별 진입 안내
- `docs/agent-guide.md` 머리 — 동기 룰 + §7.1 PR 체크리스트에 동기 항목 추가

**결정**:

- 라이브러리에 `wrapper class` 만들지 않음 (ADR-005 mirror) — 부족 기능 발견
  시 `maplibre-vworld-js` 저장소에 PR
- 좌표 변환 어댑터 (`apps/web/lib/coordAdapter.ts`) 제거 — VWorld는 GeoJSON
  순서 `(lng, lat)` 그대로
- Kakao Local 검색 / 모빌리티 길찾기는 라이브러리 함수 (`python-krtour-map.search`)
  또는 OR-Tools 직선 거리로 대체

**다음**: PR 생성.

## 2026-05-26 02:00 (claude)

**작업**: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리 + AI agent
friendly 보강 (ADR-014).

**컨텍스트**: 사용자 요청. v2 골격 + SPEC V8 + frontend/location/notice 반영
이후, v1의 9개월 운영 자산을 빠짐없이 v2 문서로 가져오고 문서 일관성 정리.

**v1 전수 조사** (`docs/v1-to-v2-mapping.md`):

- v1 docs/ 84개 (api/architecture/data-sources/decisions/execplan/integrations/
  runbooks/skills/PROJECT_BRIEF), apps/api 80+, apps/web 30+, scripts 13, infra 2
- ✅ / 🚚 / 📋 / ⛔ / 🆕 상태로 매핑

**신규 작성** (본 PR — ~30 파일):

- `docs/api/` 11개: README / common / auth / users / trips / pois / features /
  notice-plans / storage / admin / public / regions / health / websocket
- `docs/integrations/` 9개: README / resend / social-login / gemini / telegram /
  kakao-map / sentry / loki
- `docs/runbooks/` 7개: README / local-dev / docker-app / etl / admin /
  file-storage / odroid-docker
- `docs/compliance/` 4개: README / lbs-act / pipa / data-policy
- `docs/conventions/` 6개: README / coding-style / database / testing /
  geospatial / normalization
- `docs/architecture/` 5개 추가: map-marker-design / youtube-travel-intelligence /
  mcp-tools / dagster-etl-bridge / api-contract
- `docs/data-sources/README.md` — cross-ref 인덱스
- `docs/v1-to-v2-mapping.md` — 매핑 매트릭스

**기존 문서 갱신**:

- `README.md` — 문서 인덱스 전면 강화 (역할별 그룹)
- `AGENTS.md` — "AI Agent 작업 진입 절차" 섹션 신규 + 작업 종류별 진입 문서표
- `CLAUDE.md` — §7 빠른 문서 검색 표 추가
- `docs/decisions.md` — ADR-014 박음

**결정**:

- v1 자산 cherry-pick X — 본 문서 + schema 정합성 기준으로 재작성 (특히
  notice_plans Sprint 2 재작성 결정 — ADR-013 mirror)
- v1의 `apps/api/app/etl/`, `dagster_etl/`, `core/{kex,kto}.py`,
  `services/krtour_map_*` 는 모두 폐기 (ADR-005 / ADR-006 mirror)
- v1 `docs/data-sources/*` 8개는 모두 라이브러리 위임 — 본 저장소는 인덱스만
- `pyXyz` 짧은 alias 사용 금지 (canonical `python-xyz-api`만)
- AI agent 진입 절차를 AGENTS.md / CLAUDE.md에 명시

**일관성 점검**:

- TripMate vs `python-krtour-map` 책임 분담을 모든 신규 문서에 명시
- WSL 미러 모델 (ADR-004)이 모든 runbook에 일관 반영
- 환경변수 `TRIPMATE_*` prefix 일관
- 좌표 lon-lat 순서 일관
- 시간 KST aware 일관
- audit log chain (content_hash) 일관
- 동의 4 분리 일관

**다음**: PR 작성 후 사용자 review.

## 2026-05-25 23:51 (codex)

**작업**: PR #9 Sprint 1 scaffolding CI 실패 리뷰 및 수정.

**변경 파일**:

- `apps/api/**` — ruff/mypy strict 실패 정리, JWT `expires_minutes=0` 만료 버그 수정,
  bootstrap admin password 기본값 제거, Alembic version table 생성 전 schema 보장
- `apps/etl/tests/test_definitions.py` — Dagster `Definitions.resolve_asset_graph()`
  API에 맞게 테스트 갱신
- `packages/*/src` — workspace source 패키지를 Next가 직접 transpile할 수 있도록
  내부 TS import의 `.js` 확장자 제거
- `apps/web/app/(auth)/verify-email/page.tsx`, `apps/web/next.config.mjs` — App Router
  Suspense boundary와 Next 15 config 경고 정리
- `package-lock.json`, `.github/workflows/web.yml` — Linux Node 컨테이너에서 lockfile
  생성 후 CI를 `npm ci` + cache 흐름으로 고정

**결정**: lockfile은 Windows npm이 아니라 Linux Node 컨테이너에서 생성한다. CI는
`npm ci`로 재현 가능한 설치를 강제한다.

**발견**: API unit test가 `expires_minutes=0`을 기본 만료 시간으로 처리하는 실제
토큰 만료 버그를 잡았다.

**다음**: 수정 commit push 후 PR #9 CI 재실행 확인.

## 2026-05-25 23:30 (claude)

**작업**: Frontend 스택 상세 + Expo 공용 패키지 + 위치 정보 사양 + v1 notice POI
도메인 보강.

**컨텍스트**: 사용자 요청 3가지:

1. Frontend는 React/Next.js/TanStack Query/Zod/Zustand/RHF/shadcn/ui/Tailwind 기반
   임을 상세 명시. DESIGN.md / palette HTML의 색상톤·UX 따름. 추후 Expo 대응을
   위해 주요 로직 + 데이터 정의 코드를 Next.js / Expo 공용으로 작성. Expo 프론트
   구성도 명시.
2. v1에서 notice POI 관련 문서/코드 확인해서 보강.
3. 웹/앱에서 사용자 위치 정보 획득을 기능 사양에 명시.

v1 탐색 결과: `notice_plans` 도메인은 SPEC V8 D-10의 `notice` feature와 **완전히
다른 개념**. v1 `notice_plans`는 Admin이 작성한 **추천 여행 plan** (사용자가 자기
trip으로 copy 가능). 같은 단어를 쓰는 두 개념이 v2에서 혼동되지 않도록 명명을
분리.

**신규 파일**:

- `docs/architecture/frontend.md` — Next.js + Expo 공용 monorepo 구조,
  `packages/{schemas,api-client,state,design-tokens,hooks,i18n}`, shadcn/ui +
  Tailwind 통합, Airbnb 톤 디자인 토큰, 컴포넌트별 가이드, React Native
  Compatibility 룰
- `docs/architecture/user-location.md` — `navigator.geolocation` /
  `expo-location` 어댑터 추상화, `useUserLocation` 공용 hook, 4 분리 동의
  연계, content_hash chain 적재, fallback chain, UI 가이드
- `docs/architecture/notice-plans.md` — 추천 여행 plan 도메인 (v1에서 가져옴),
  `notice_plans` + `notice_pois` + `plan_poi_attachments` 단일 테이블 4 대상,
  copy 흐름, RustFS 정합, "notice plan ≠ notice feature" 명명 분리

**갱신**:

- `docs/decisions.md` — ADR-011 (Frontend 스택 + Expo 공용), ADR-012 (위치
  정보), ADR-013 (Notice plan 이전 + 명명 분리)
- `docs/spec/v8/03-frontend.md` — 스택 표 갱신 (shadcn/ui 명시) + 새 문서
  cross-reference
- `docs/sprints/SPRINT-1.md` — `packages/*` skeleton 등록 항목 박음
- `docs/sprints/SPRINT-2.md` — notice_plans / plan_poi_attachments Alembic,
  공용 schema/api-client/state/hooks 활성화, 4 분리 동의 UI + 위치 audit
- `docs/sprints/SPRINT-4.md` — 사용자 notice plan listing + copy 다이얼로그 +
  지도 "내 위치로 이동" 버튼
- `docs/sprints/SPRINT-6.md` — Admin notice plan 작성기 UI
- `README.md`, `SKILL.md` — 새 문서 cross-reference + 도메인 어휘
  (Notice plan / Notice feature / Plan POI attachment)
- `docs/architecture.md` §2.2 — Frontend 섹션을 새 `architecture/frontend.md`
  로 위임 + 공용 패키지 + 위치 hook 명시

**v1에서 확인한 자산** (`v1` 브랜치):

- `apps/api/alembic/versions/20260521_0027_notice_plans.py`
- `apps/api/alembic/versions/20260522_0028_plan_poi_attachments.py`
- `apps/api/app/models/trip.py` (`NoticePlan`, `NoticePoi`, `PlanPoiAttachment`)
- `apps/api/app/schemas/notice.py`
- `apps/api/app/services/notice_plan.py` (copy 흐름)
- `apps/api/app/services/plan_poi_attachment.py`
- `apps/api/app/api/routes/notice.py`
- `apps/api/tests/test_notice_plans_api.py`
- `docs/architecture/plan-poi-attachments.md`

**결정**:

- shadcn/ui + Tailwind 채택 — DESIGN.md Airbnb 톤을 컴포넌트 레벨에서 customizing
- `packages/*` 공용 패키지를 v1.0 단계부터 박아 Expo 추가 비용 최소화
- 좌표 서버 전송 시 audit chain 자동 적재. 좌표 정밀도는 UI에 4자리 (~10m) 까지만
- v1 notice plan 도메인은 cherry-pick 안 함 — schema 정합성 위해 재작성 (Sprint 2)
- "notice plan" (TripMate) vs "notice feature" (라이브러리) 명명 명시 분리

**다음**: PR #5에 추가 커밋 후 push. Sprint 1 진입 승인 시 `apps/` + `packages/`
scaffolding.

## 2026-05-25 22:27 (codex)

**작업**: Sprint 4까지 새 PR을 리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리
sync → 검증 → 머지하는 운영 지시를 문서화하고 자동 리뷰 프롬프트 및 5분 주기
PR 감시 workflow 보강.

**변경 파일**:

- `.github/workflows/codex-pr-review.yml` — PR 자동 리뷰 프롬프트를 장기 설계 관점,
  기반 라이브러리 sync, 상세 코멘트 구조 중심으로 보강 + head SHA 리뷰 마커 추가
- `.github/workflows/codex-pr-monitor.yml` — 5분마다 열린 PR을 감시하고 최신 head
  SHA 리뷰 마커가 없으면 Codex 리뷰 코멘트 작성
- `docs/runbooks/pr-review-sprint4.md` — Sprint 4까지 반복할 PR 운영 runbook 신규
- `AGENTS.md`, `CLAUDE.md`, `docs/agent-guide.md` — 새 PR 운영 지시 cross-reference
- `docs/resume.md`, `docs/tasks.md` — 운영 지시와 완료 항목 반영

**결정**: 변경량 최소화보다 Sprint 1~4 장기 설계 정합성을 우선한다. 올바른 수정
위치가 기반 라이브러리이면 TripMate wrapper로 덮지 않고 라이브러리 PR → 머지 →
TripMate sync 순서로 처리한다.

**발견**: Codex 앱의 자동화/모니터 도구는 현재 노출되지 않았고, GitHub PR 조작
도구만 노출된다. 따라서 지속 감시는 GitHub Actions schedule workflow로 구현했다.

**다음**: 새 PR이 올라오면 `docs/runbooks/pr-review-sprint4.md` 절차로 리뷰와
수정/머지 진행.

## 2026-05-25 22:00 (claude)

**작업**: SPEC V8 6편 반영 + v1 자산 일부 복원.

**컨텍스트**: 사용자가 외부 docx 6편(`spec_v8_0_infrastructure` ~ `spec_v8_5_execution`)
제공하면서 "TripMate에 반영할 것들도 문서화"와 "v1에서 색상맵 html과 DESIGN.md를
v2로 끌고 와" 지시. SPEC V8은 v1 시점에 작성되었지만 후속 메모(M~R)에 이미
`python-krtour-map` 책임 분리가 반영되어 있어, 본 저장소의 v2 골격(ADR-001~009)과
정합되게 적용 노트만 작성하면 됨.

**신규 파일**:

- `docs/spec/v8/README.md` — 6편 인덱스 + 책임 매핑
- `docs/spec/v8/00-infrastructure.md` — Odroid M1S, RustFS, Sentry, Loki, 위치정보법
- `docs/spec/v8/01-data.md` — 7 Feature, PostGIS, Record Linkage (라이브러리 위임)
- `docs/spec/v8/02-backend.md` — FastAPI 스택, JWT/OAuth, Resend, OR-Tools
- `docs/spec/v8/03-frontend.md` — Next.js 15, 16색 팔레트, 우클릭, 실시간
- `docs/spec/v8/04-admin.md` — 13 페이지, RBAC, audit chain, debug 콘솔
- `docs/spec/v8/05-execution.md` — 결정 6건, Sprint 1~6
- `docs/design/marker-palette.md` — P-01~P-16 + 카테고리 매핑
- `docs/sprints/SPRINT-2.md` — 도메인 API + DB
- `docs/sprints/SPRINT-3.md` — Admin 데이터 디버그 (Sprint 4 전)
- `docs/sprints/SPRINT-4.md` — 지도 + 사용자 UI
- `docs/sprints/SPRINT-5.md` — 실시간 + ETL + Loki
- `docs/sprints/SPRINT-6.md` — 일정 최적화 + LBS 신고 + 법무

**복원 (v1 → v2)**:

- `airbnb-marker-palette.html` (저장소 루트, 색상 시각 reference)
- `DESIGN.md` (저장소 루트, Airbnb 디자인 토큰 가이드 — 브랜드 확정 전 임시)

**갱신**:

- `docs/decisions.md` ADR-010 추가 (SPEC V8 채택)
- `docs/sprints/README.md` — Sprint 2~6 인덱스 추가
- `docs/sprints/SPRINT-1.md` — SPEC V8 cross-ref §8

**결정**:

- SPEC V8 N-7.2의 "ext4 직접 작업본 + NTFS export" 모델은 ADR-004로 정정 유지
- SPEC V8 D~E (feature schema)는 `python-krtour-map`이 소유 (ADR-003)
- SPEC V8 M-14의 `users.role` RBAC를 따름 (`is_admin BOOLEAN` 정정)
- LBS 사업자 신고는 Sprint 6에 박음 (출시 전 필수)
- Sprint 3 (Admin) ≺ Sprint 4 (지도) 순서 유지

**발견**: SPEC V8 원본의 후속 메모(2026-05-16 ~ 05-20)가 이미 `python-krtour-map`
분리와 wrapper 금지 원칙을 명시 — v2 골격의 ADR-001/002/003/005와 자연스럽게
정합. 별도 충돌 해소 불필요.

**다음**: PR 갱신 (`docs/bootstrap-v2-skeleton` 브랜치에 추가 커밋 후 push).

## 2026-05-25 19:30 (claude)

**작업**: v2 재시작 — v1 보존 + main 골격 재작성.

**컨텍스트**: 사용자 지시. v1은 9개월 운영하면서 책임 경계가 흐려지고 WSL/NTFS
작업 흐름이 두 번 흔들렸다. 사용자 결정으로 (1) `codex/wsl-test-mirror-docs`
브랜치의 unstaged 변경을 마지막 v1 commit으로 박음, (2) v1 브랜치를 main과 동일
시점에서 분기 + origin push, (3) main에서 모든 추적 파일 git rm + 캐시/빌드 정리,
(4) `python-krtour-map`의 문서 구조(README/CLAUDE/AGENTS/SKILL/docs/) 패턴을 본
저장소 컨텍스트로 미러링.

**변경 파일** (신규):

- `.gitignore` — `python-krtour-map` 패턴 + TripMate dataset/refdocs 보존 정책
- `.gitattributes` — text=auto eol=lf + binary 분류
- `README.md` — 정체성, 빠른 시작, 문서 지도
- `CLAUDE.md` — 1쪽 진입 요약 (Claude Code 우선 진입)
- `AGENTS.md` — 작업 룰, 식별자, 책임 경계
- `SKILL.md` — 도메인 어휘, DO NOT 20항, 자주 묻는 작업
- `docs/architecture.md` — 큰 그림, 의존 방향, TripMate ↔ krtour-map
- `docs/agent-guide.md` — 결정·기록 5종, ADR 규약, PR 워크플로
- `docs/dev-environment.md` — WSL 미러 단일 모델, rsync 절차, 부트스트랩
- `docs/decisions.md` — ADR-001 ~ ADR-009 (v2 시작 결정)
- `docs/journal.md` — 본 파일
- `docs/resume.md` — 다음 한 작업
- `docs/tasks.md` — 백로그
- `docs/data-model.md` — app 도메인 (사용자/여행계획/POI 첨부)
- `docs/postgres-schema.md` — app schema DDL/인덱스 골격
- `docs/test-strategy.md` — 단위/통합/e2e 경계
- `docs/krtour-map-integration.md` — DI helper 패턴 + Dagster asset 사용
- `docs/sprints/README.md` — Sprint 1~N 개요
- `docs/sprints/SPRINT-1.md` — 코드 작성 단계 진입 PR plan

**삭제**:

- `.codex/`, `.dockerignore`, `AGENTS.md`(구), `DESIGN.md`, `README.md`(구),
  `airbnb-marker-palette.html`, `apps/`, `config/`, `docs/`(구), `infra/`,
  `package-lock.json`, `package.json`, `scripts/`, `skills/`
- (보존) `.gitattributes`, `.gitignore` (재작성), `.claude/`, `.env`, `dataset/`,
  `refdocs/` (`.gitignore` 보호 항목)

**Git 흐름**:

1. `codex/wsl-test-mirror-docs` 브랜치의 unstaged 변경 16개 → `bc83fb1 Mirror docs
   back to WSL test mirror workflow` 커밋 + origin push.
2. `main`을 codex tip(`bc83fb1`)으로 fast-forward.
3. `v1` 브랜치 생성(main의 현재 시점) + origin push.
4. main에서 v2 골격 신규 작성 (본 PR).

**ADR 적용**:

- ADR-001 — v1 보존 + v2 재시작
- ADR-002 — TripMate ↔ `python-krtour-map` 함수 직접 호출
- ADR-003 — schema 책임 분담 (`app`/`ops` = TripMate, `feature`/`provider_sync`
  = `python-krtour-map`)
- ADR-004 — WSL 미러 단일 모델
- ADR-005 — provider 어댑터 wrapper 금지
- ADR-006 — Dagster code location 분리 (`apps/etl`)
- ADR-007 — PR-only workflow + main branch protection
- ADR-008 — Postgres extension `x_extension` schema 분리
- ADR-009 — 한국어 문서 정책

**다음**:

- 사용자 review → v2 골격 PR로 main에 push (현재 작업 디렉토리에서 작성된 결과).
- Sprint 1 진입 승인 시 `apps/{api,web,etl}` + `infra/` + `packages/` scaffolding
  첫 PR (`docs/sprints/SPRINT-1.md` 참고).
- v1의 자산(Resend 통합, 소셜 로그인, Notice plan, RustFS Storage API 등)은 v2에서
  한 건씩 ADR로 결정하고 가져온다.
