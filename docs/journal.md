# journal.md — 작업 일지 (역시간순)

가장 위가 가장 최근. 새 엔트리는 위에 append.

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
