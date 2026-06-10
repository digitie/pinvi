# tasks.md — 백로그

> **2026-06-06 정합성 감사**: `docs/audit/2026-06-06-doc-impl-audit.md`에서
> 모순·불일치·누락을 전수 점검하고 후속 Task(T-123~T-151)·ADR(ADR-027~031)·결정
> (DEC-01~10)을 도출했다. 결정 결과는 `docs/decisions-needed-2026-06-06.md`,
> krtour-map 요구사항은 `docs/krtour-map-requirements.md`. 후속 백로그는 본 파일
> "감사 후속 백로그(2026-06-06)" 절.

## 진행 중

- [ ] T-060 — Sprint 4 진입 PR (지도 + 사용자 UI + `maplibre-vworld-js` 통합).
  **2026-06-10 진행**: PR-C 프론트 지도/협업 슬라이스 대부분 머지(#126~#139, 아래
  "Claude Sprint 4 PR-C 프론트 (2026-06-10)" 절). 잔여: krtour-map client 실주입(라이브러리
  ready 시) + Playwright E2E 실행(브라우저/서버 환경) + v0.1.0 tag.

## 다음 (우선순위 순)

- v0.1.0 마무리: krtour-map client 실주입(PR-D2) + E2E 실행 게이트 + tag.
- krtour-map 비의존 후보 재평가. 현재 후보: T-108 운영 배포 자동화, T-129의
  `/geo/*`·`/regions/*` slice(머지됨), T-146 location-audit outbox slice(머지됨).

## 완료

- [x] T-000 — git v1 보존 + main v2 재시작 (완료: 2026-05-25)
- [x] T-112 — TripMate MCP 외부 인터페이스 서빙 (완료: 2026-06-09) —
  `app.mcp_tokens`, `/users/me/mcp-tokens`, `/admin/mcp-tokens`, `/mcp/sse`,
  `/mcp/tools/{tool_name}`, 사용자/admin 토큰 UI, 5개 read-only tool.
- [x] T-001 — README / CLAUDE / AGENTS / SKILL (완료: 2026-05-25)
- [x] T-002 — docs/architecture / agent-guide / dev-environment (완료: 2026-05-25)
- [x] T-003 — docs/decisions (ADR-001 ~ ADR-010) (완료: 2026-05-25)
- [x] T-004 — docs/journal / resume / tasks (완료: 2026-05-25)
- [x] T-005 — docs/data-model / postgres-schema / test-strategy (완료: 2026-05-25)
- [x] T-006 — docs/krtour-map-integration (완료: 2026-05-25)
- [x] T-007 — docs/sprints/README + SPRINT-1~6 (완료: 2026-05-25)
- [x] T-008 — docs/spec/v8/ 6편 적용 노트 (완료: 2026-05-25)
- [x] T-009 — docs/design/marker-palette + 루트 DESIGN.md/airbnb-marker-palette.html 복원 (완료: 2026-05-25)
- [x] T-010 — docs/architecture/frontend.md (Next.js + Expo 공용 monorepo) (완료: 2026-05-25)
- [x] T-011 — docs/architecture/user-location.md (Geolocation + expo-location) (완료: 2026-05-25)
- [x] T-012 — docs/architecture/notice-plans.md (v1 추천 plan 이전) (완료: 2026-05-25)
- [x] T-013 — v1 자산 전수 조사 + 매핑 매트릭스 (`docs/v1-to-v2-mapping.md`) (완료: 2026-05-26)
- [x] T-014 — docs/api/ 11개 + README + common (완료: 2026-05-26)
- [x] T-015 — docs/integrations/ 9개 + README (완료: 2026-05-26)
- [x] T-016 — docs/runbooks/ 7개 + README (완료: 2026-05-26)
- [x] T-017 — docs/compliance/ 4개 + README (완료: 2026-05-26)
- [x] T-018 — docs/conventions/ 6개 + README (완료: 2026-05-26)
- [x] T-019 — docs/architecture/ 5개 추가 + data-sources/README (완료: 2026-05-26)
- [x] T-020 — AI agent 진입 절차 강화 (README/AGENTS/CLAUDE) (완료: 2026-05-26)
- [x] T-021 — `docs/integrations/maplibre-vworld.md` 신규 + Kakao 전면 교체 (ADR-015) (완료: 2026-05-26)
- [x] T-022 — `AGENTS.md` ↔ `CLAUDE.md` 동기 룰 (ADR-016 — Codex/Antigravity 대응) (완료: 2026-05-26)
- [x] T-023 — Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 5분 주기 PR 감시 (완료: 2026-05-25,
  2026-06-02부터 API key 없는 review reminder 방식)
- [x] T-030 — Sprint 1 monorepo 루트 + packages/* skeleton (완료: 2026-05-26)
- [x] T-031 — Sprint 1 apps/api FastAPI + Alembic + Auth 뼈대 (완료: 2026-05-26)
- [x] T-032 — Sprint 1 apps/web Next.js + auth 화면 (완료: 2026-05-26)
- [x] T-033 — Sprint 1 apps/etl Dagster placeholder (완료: 2026-05-26)
- [x] T-034 — Sprint 1 infra/docker-compose + scripts + CI workflow 3개 (완료: 2026-05-26)
- [x] T-035 — Sprint 1 PR 생성 (완료: 2026-05-26)
- [x] T-050 — Sprint 3 진입 PR (Admin 콘솔 + RBAC + audit chain integration + seed) (완료: 2026-05-26)
- [x] T-061 — Sprint 4 진행 추적 문서 정합화 (`resume.md` / `tasks.md` / `journal.md`) (완료: 2026-06-01)
- [x] T-062 — GitHub Actions secret / branch protection 적용 상태 확인 (완료:
  2026-06-02, Actions secret 0개 정책 확인 + `main-pr-only` ruleset 적용)
- [x] T-064 — 최신 main 기준 문서 충돌 정정 (ADR-015/024/025 반영) (완료: 2026-06-02)
- [x] T-068 — 최신 krtour-map/kraddr-geo/KASI 계약 문서 반영 (완료: 2026-06-04,
  ADR-026 + KASI 특일/출몰시각 저장 계약)
- [x] T-069 — production API/Web URL + OAuth/CORS 보안 문서화 (완료: 2026-06-05,
  API `https://tripmateapi.digitie.mywire.org`, Web `https://tripmate.digitie.mywire.org`)
- [x] T-067 — KASI 특일/POI 출몰시각 Dagster 구현 (완료: 2026-06-05,
  `app.kasi_special_days` / `app.trip_poi_rise_sets` + Dagster asset/job)
- [x] T-070 — Sprint 2 잔여 마감: `email_queue` SKIP LOCKED worker +
  비밀번호 재설정 메일 흐름, `api_call_log` 미들웨어 통합 테스트,
  `api.yml` integration step 추가 (완료: 2026-06-05)
- [x] T-063 — `maplibre-vworld-js` 선행 PR 및 consumer sync 체크리스트 정리
  (완료: 2026-06-05, `maplibre-vworld-js` PR #46 merge `f1dd74b9` +
  TripMate `docs/integrations/maplibre-vworld.md` §6/§11.1 sync)
- [x] T-065 — 항상 실행되는 aggregate CI gate 설계 후 required status check 적용
  (완료: 2026-06-05, `.github/workflows/aggregate-ci.yml` + `main-pr-only` ruleset
  required status check `Aggregate CI gate`)
- [x] T-071 — Google OAuth 로그인 UI + API client 연결
  (완료: 2026-06-05, `/auth/oauth/google/start` envelope 응답, provider 목록 기반
  로그인 버튼, PKCE verifier 재생성)
- [x] T-072 — Google OAuth callback 실패 redirect UX
  (완료: 2026-06-05, callback 실패 303 `/login?error=...` redirect +
  로그인 화면 code 기반 인라인 메시지)
- [x] T-073 — Google OAuth profile 연결/해제 UI
  (완료: 2026-06-05, `/auth/me` OAuth identity 노출 + `/profile` Google 연결/해제 +
  소셜-only unlink 차단)
- [x] T-074 — PR-C frontend 지도 shell
  (완료: 2026-06-05, `maplibre-vworld` `f1dd74b9...` tarball pin + `/trips/map-shell`
  `VWorldMap` import + Windows Playwright e2e, krtour-map feature 조회 제외)
- [x] T-075 — Trip 대시보드 / notice plan 사용자 shell
  (완료: 2026-06-05, `/trips` / `/notice-plans` 사용자 route + navigation + 빈 상태 +
  API client 연결, `/features/*` / krtour-map API `9011` 미호출 e2e)
- [x] T-100 — v1의 Resend 이메일 통합 v2로 이식 (Sprint 2 완료, PR #10)
- [x] T-101 — v1의 소셜 로그인 기반 schema/model v2 이전 (현재 활성은 Google-only,
  Naver/Kakao provider 구현은 T-122 미래 작업)
- [x] T-102 — v1의 Notice plan 도메인 v2로 이식 (Sprint 2 schema/model 완료, 라우터
  Sprint 6)
- [x] T-103 — v1의 RustFS Storage API v2로 이식 (Sprint 2 완료, presigned PUT)
- [x] T-104 — v1의 Admin 콘솔 (`apps/web/app/admin/`) v2로 이식 (Sprint 3 완료, PR #11)
- [x] T-110 — Admin Grafana iframe embed
  (완료: 2026-06-05, `/admin/grafana` iframe shell + `NEXT_PUBLIC_GRAFANA_*` env +
  Web `frame-src` CSP + admin guard e2e)
- [x] T-109 — 한국 전용 geofencing FastAPI fallback
  (완료: 2026-06-05, `TRIPMATE_GEOFENCE_*` env + `CF-IPCountry` 기반 451 middleware +
  health/docs 우회 + DB roles 운영자 우회 단위 테스트. T-142에서 token roles claim 신뢰 제거)
- [x] T-115 — Backup snapshot foundation + `/admin/backup` 1차 UI
  (완료: 2026-06-06, `scripts/backup-db.sh` / `scripts/restore-db.sh` +
  `GET /admin/backup/snapshots` + `POST /admin/backup/snapshot` + admin snapshot page.
  핫스왑 restore는 T-111에서 완료)
- [x] T-116 — OAuth provider 범위 Google-only 정리
  (완료: 2026-06-06, `/auth/oauth/providers`가 Google만 반환. Naver/Kakao는 future
  provider로 보류)
- [x] T-117 — 회원가입 약관 동의 화면 + `user_consents` 저장 보강
  (완료: 2026-06-06, `POST /auth/register` 필수 4종 동의 요구 +
  `app.user_consents` 동시 저장 + `/signup` 필수/선택 동의 UI + e2e)
- [x] T-118 — Google OAuth 계정 매칭 / profile 연결 UX 보강
  (완료: 2026-06-06, 같은 이메일 자동 연결 금지 + `OAUTH_ACCOUNT_LINK_REQUIRED` /
  `OAUTH_EMAIL_UNVERIFIED` 안내 + profile link-mode 충돌 redirect + Naver/Kakao 제외 e2e)
- [x] T-119 — 회원 관리 Admin 보강
  (완료: 2026-06-06, `/admin/users` `q` 검색 + 상태 필터 결합, 상세 기본 이메일
  마스킹, 사유 기반 원본 조회 audit, 최근 audit UX + 통합/e2e 테스트)
- [x] T-120 — 여행계획 Admin 목록/상세/상태 관리
  (완료: 2026-06-06, `/admin/trips` 검색 + 상태/공개범위 필터, 상세 companion/share
  metadata, 상태 변경 `trip.update_status` audit, Web 목록/상세 + 통합/e2e 테스트)
- [x] T-121 — POI Admin 목록/상세/연결 상태 관리
  (완료: 2026-06-06, `/admin/pois` 검색 + `feature_link_broken_at` 필터, 상세
  snapshot/일정/비용/최근 audit, 연결 상태 변경 `poi.update_link_status` audit,
  Web 목록/상세 + 통합/e2e 테스트. feature re-link는 krtour-map client 준비 후)
- [x] T-123 — 문서 정합 일괄 정정
  (완료: 2026-06-06, README/API index의 `GET /search`·`/health/external` 보강,
  OAuth Google-only/future provider 표현 정리, share link URL을
  `TRIPMATE_WEB_BASE_URL` 기반으로 수정, zoom 하한 5 정합, dangling
  `release-plan.md` 링크 제거, `python-kraddr-geo` 오타 정정, agent-guide 잔여
  bullet/trailer 정리)
- [x] T-149 — Gemini 책임 목록 정정
  (완료: 2026-06-06, README/AGENTS/CLAUDE/SKILL 및 integrations index의 현재 책임
  표현을 ADR-020 기준 `AI companion 호출 계약`으로 정리. Gemini/Claude/Codex provider
  구현은 별도 `tripmate-ai-companion` repo 책임)
- [x] T-150 — 계획/추적 문서 정합화
  (완료: 2026-06-06, Sprint 1/3/4/5 status를 최신 main과 맞추고, Sprint 5 ETL
  provider asset 목록을 krtour-map 책임으로 정정, `resume.md` ADR-031까지 박힌 ADR
  목록 갱신, T-111 중복/보류·완료 혼재 상태 점검, merge history PR #55 추가)
- [x] T-152 — Telegram 완료 알림 MCP (모든 agent)
  (완료: 2026-06-07, krtour-map PR #229 패턴 미러. `scripts/mcp_telegram_start.py` +
  `mcp-telegram` 서버를 claude/codex/antigravity/gemini MCP 설정에 등록 +
  `.env.mcp-telegram` gitignore + AGENTS/CLAUDE/SKILL/runbook 정책. GitHub secret 미사용
  (T-062 유지). 실제 전송 검증 완료. PR 후 `send_message`로 요약+링크 발송 규칙.)
- [x] T-153 — PR 리뷰 모니터 MCP 알림 보강
  (완료: 2026-06-07, `scripts/pr_review_monitor.py`로 PR 이벤트/예약 감시 로직 단일화,
  `synchronize`/`reopened` 즉시 알림 추가, 알림 본문에 `python-krtour-map`식 MCP 진입
  CodeGraph/Playwright/Sequential Thinking/Telegram 기준 반영. GitHub secret 미사용.)

## 보류

- [ ] T-066 — krtour-map OpenAPI HTTP client 구현 + drift gate (보류:
  krtour-map이 운영급 HTTP 서비스를 **신설**해야 진입 — ADR-027/DEC-01=B 확정,
  `docs/krtour-map-requirements.md`. v0.1.0 게이트가 여기 의존 — DEC-06)
- [ ] ~~T-107~~ — **Gemini 통합 — 보류 (deferred)**. 별 repo
  `tripmate-ai-companion`으로 분리 (ADR-020). 본 저장소는 호출 컨트랙트 문서만
  (`docs/integrations/ai-companion.md`, Sprint 6 진입 시).
- [ ] T-108 — 운영 배포 자동화 (Sprint 6) — **Odroid M1S + N150 16GB 양쪽**
  (ADR-023). multi-platform Docker 빌드 + 두 노드 streaming replication.
- [ ] T-122 — Naver/Kakao OAuth provider 구현 — **미래 작업**
  (현재는 사용하지 않음. Google OAuth 안정화 후 별도 PR에서 provider별 start /
  callback / link / unlink / 버튼 활성화)

### Sprint 5~6 (v0.2.0 / v1.0) 신규 backlog

- [x] T-111 — Backup/Restore UI 핫스왑 (ADR-022, Sprint 6) — `/admin/backup`
  + RestoreHotswapDialog. Sprint 5의 backup script + endpoint 위에 UI + 핫스왑
  워크플로 finalize.
- [x] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize)
  구현 분할 (완료: 2026-06-09, trip delete/transfer, copy, day CRUD, shared view,
  trip/POI attachment metadata, distance matrix, nearest-neighbor optimize API +
  schemas/api-client/tests)
- [x] T-112 — TripMate MCP 외부 인터페이스 서빙 (ADR-019, Sprint 6) —
  `apps/api/app/mcp/` + `/mcp/sse` + 토큰 발급 / 회수 UI + 5개 read-only tool.
- [ ] T-113 — `tripmate-ai-companion` 별 repo 신설 (ADR-020) — T-107 후속.
  사용자가 repo 명 / provider 확정 후 진입.
- [x] T-114 — GitHub Actions CI/CD 복원 (ADR-021, Sprint 4) — workflow 파일 복원 완료.
  운영 확인은 T-062에서 완료. required status check 후속은 T-065.

### 감사 후속 백로그 (2026-06-06)

> 출처: `docs/audit/2026-06-06-doc-impl-audit.md` §8.1. 괄호 안은 감사 증거 ID.
> 다수가 ADR-027~031 / DEC-01~10 확정에 의존한다.

- [x] T-123 — 문서 정합 일괄 정정(README index/머지표/오타/dangling link/OAuth·share 문서화) (A-14,C-20,C-21,P-10,P-13,P-17,P-18)
- [ ] T-124 — `/features/*` 코드↔문서 계약 정렬(in-bounds 파라미터·응답, trips 페이지네이션, 필드명) (C-07,C-10,C-11,C-15)
- [x] T-125 — feature_id 문자열化(코드의 UUID 가정 제거) (C-09; ADR-028)
- [x] T-126 — POI 생성 경로 단일화(`/trips/{id}/pois` 정본) (A-01,C-16)
- [x] T-127 — MCP 외부 인터페이스 정본화(mcp-server.md 권위, status enum, 토큰 엔드포인트) (A-02,A-06,A-12)
- [x] T-128 — 실시간 협업 백엔드 설계 + WS 계층(presence/충돌해소, Sprint 5) (C-03,D-05)
- [x] T-129 — `/search` 통합 + `/geo/*`·`/regions/*` 명세·구현 (A-13,C-02,C-13) (완료: 2026-06-09): kraddr-geo v2 REST client(`apps/api/app/clients/kraddr_geo.py`, ADR-025) + config + `GET /geo/{geocode,reverse,search}` + `GET /regions/{within-radius,covering-point}`(`api/v1/geo.py`) + **통합 `GET /search`**(feature[krtour]+address[kraddr]+내 POI[DB], 소스별 graceful degrade, `api/v1/search.py`, C-13) + frontend Zod(`packages/schemas/src/geo.ts`) + 계약/통합 테스트. 좌표 매핑(`lon`/`lat`)·router cutover(T-173)는 별개.
- [ ] T-130 — `/public/*` 구현(krtour 연동 후) (C-04)
- [x] T-131 — `GET /trips/{id}`에 `build_trip_view` 연결 (C-05)
- [x] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize) 구현 분할 (C-06,D-06)
- [x] T-133 — Admin priority-3 엔드포인트·페이지 실구현(or 상태 강등) (C-08,C-17)
- [x] T-134 — `POST /auth/refresh` + `user_sessions` 영속화 (C-14)
- [x] T-135 — POI 응답 `rise_set` 노출 (C-18)
- [x] T-136 — Resend webhook Svix 서명 검증 (C-22)
- [x] T-137 — notice/curated-plan 스키마 정본화(`curated_trip_plans` 분리) (D-01,D-04; ADR-029)
- [x] T-138 — `users` 누락 컬럼 + `security_incidents` 테이블 추가 (D-02,D-03,D-09)
- [x] T-139 — 동반자 초대 흐름 + 댓글 모델/`visibility` 정리 (D-06)
- [x] T-140 — 여행 예산(budget/currency) 도메인 + 복사 흐름 (D-10)
- [x] T-141 — trip↔지역 구조적 연결(POI 좌표 유도 or region code) (D-11)
- [x] T-142 — geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리 (D-13,D-24)
- [x] T-143 — 지도/소셜 문서 정정(Kakao 어댑터 제거, Google-only, kraddr-geo stack 추가) (D-15,D-21,D-22)
- [x] T-144 — 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계 (D-16,D-17)
- [x] T-145 — backup 핫스왑 동일호스트 schema-swap 확정(2×DB 폐기) (D-19)
- [x] T-146 — location-audit async outbox + feature 캐시(N+1 제거) (D-20,D-26) (완료: 2026-06-09). **D-20**: `app.location_audit_outbox`(migration 0017) + 미들웨어 요청경로 fast append + 단일 writer `drain_location_audit_outbox`(advisory xact lock) + 백그라운드 worker. **D-26**: `services/feature_cache.py` process-local TTL/LRU 캐시 — `trip_view_builder`가 miss만 krtour 재조회(반복 trip view hotspot 완화), config `tripmate_feature_cache_*`. 단위/통합 테스트(캐시 hit/miss/LRU/TTL + 2-build cache-hit).
- [x] T-147 — 잔여 문서 정정(rise/set 정책, gemini.md partial unique index 문법) (D-23,D-25)
- [ ] T-148 — SPRINT-4 backend 재작성(HTTP 경계 반영) (P-01; ADR-027)
- [x] T-149 — Gemini 책임 목록 정정(README/AGENTS/SKILL) (P-03)
- [x] T-150 — 계획/추적 문서 정합화(sprint status/보류·완료 재분류/ADR refs/resume "박힌 ADR" 갱신) (P-04~21)
- [x] T-151 — 미기록 ADR 백필(auth-token/RBAC/audit-chain) + SPRINT placeholder 번호 할당 (P-07,P-08)

### krtour-map ADR-045 Phase 6 (TripMate 몫) 대응

krtour-map의 ADR-045 standalone 계획 Phase 6(T-210a~e) 중 TripMate 저장소가
처리할 항목 매핑:

- [x] **T-210c (TripMate 부분)** — `apps/etl` ETL 경계 정합 (완료: 2026-06-06).
  코드 측은 이관할 feature/provider Dagster **스켈레톤이 없음**(apps/etl은 KASI 등
  `app` schema 소유 job만 보유) → 이관/삭제 불필요. 문서 측 phantom 스켈레톤
  (`dagster-etl-bridge.md`/`runbooks/etl.md`가 미존재 파일 나열)을 현재 구현 vs
  계획으로 정합화 + `assets/__init__.py` 경계 가드 docstring 추가.
- [x] **T-210b (TripMate 부분)** — 문서 OpenAPI HTTP supersede: ADR-026(T-068) +
  ADR-027(감사 PR #47)로 사실상 완료(architecture/krtour-map-integration/etl 문서 전환).
- [ ] **T-210d** = 본 저장소 **T-066**(httpx OpenAPI client) — krtour-map 운영 HTTP
  서비스 신설(DEC-01=B) 대기.
- [ ] **T-210e** — frontend `openapi-typescript` codegen + Zod mirror + CI diff 게이트
  (krtour-map OpenAPI 산출물 확정 후).

### Codex PR 사후 리뷰 후속 (2026-06-07)

정본 종합: `docs/reviews/2026-06-07-codex-pr-review.md` (PR #50~#71 codex 20건 리뷰).
긴급성 [높음] 항목만 backlog로 승격:

- [x] T-154 — **resend webhook C-22 완결**: secret 미설정 fail-closed + `_decode_svix_secret`
  표준 base64 교정(운영 서명 mismatch 버그) (PR #70; C-22 재오픈)
- [x] T-155 — admin `access_reason` PII를 query→header/body 전환(URL 로깅 제거) (PR #50)
- [x] T-156 — 비밀번호 재설정 시 기존 refresh session 전부 폐기 (PR #71)
- [x] T-157 — geofence fallback에 Cloudflare 발신 검증(header spoof + nginx 강등 우회 차단) (PR #60)
- [x] T-158 — Trip WebSocket rate limit + cursor 증폭 차단 + broadcast backpressure + 연결 수 캡 (PR #63)
- [x] T-159 — 응답 money 필드 Zod 타입 정합(`Decimal`→string vs `z.number()` 파싱 reject) (PR #67)
- [x] T-160 — admin 상태변경 status+audit 단일 트랜잭션(원자성, 해시체인) — #50/#52/#53 횡단 (PR #53)
- [x] T-161 — README `GET /search` 앵커 `#26`→`#27` 등 [중간] 정합 일괄 (PR #54 외)

[중간]/[낮음] 세부는 종합 문서 §1 참조(필요 시 개별 task로 분해).

### Codex PR 사후 리뷰 2라운드 후속 (2026-06-08)

정본 종합: `docs/reviews/2026-06-08-codex-pr-review.md` (PR #73~#83 codex 11건 리뷰).
직전 [높음] T-154~T-161은 모두 구현 확인(✅). 이번 라운드 신규 [높음] 없음 — 아래는
잔존 [중간](보안/무결성/가용성) 승격분:

- [x] T-162 — resend 운영 fail-open 잔존: 환경 문자열 게이트(기본 `development`)를 opt-in
  플래그 또는 prod secret 강제로 반전 (PR #74)
- [x] T-163 — 비밀번호 재설정 시 access JWT(15분) 무효화(token version/jti denylist) +
  refresh 회전 race(row lock/조건부 UPDATE) (PR #76)
- [x] T-164 — geofence outage 풋건 startup 가드 + shared-secret 외 IP allowlist/mTLS 방어심화 (PR #77)
- [x] T-165 — WS rate-limit grace 슬롯 점유 cap 우회 차단 + `publish_event` broadcast 비동기 분리 (PR #78)
- [x] T-166 — admin 감사 hash-chain head 직렬화(prev_hash unique/advisory lock) (PR #80)
- [x] T-167 — money 표현 통일(admin union→decimal-string) + `packages/schemas` round-trip 테스트 (PR #79)
- [x] T-168 — storage `AttachmentResponse` 필드 호환 정책을 notice-plans와 통일 (PR #73)
- [x] T-169 — MCP `list_trips` bucket/cursor parity + search_features HTTP 표현 정리 (PR #83)

[낮음] 세부는 종합 문서 §1 참조.

### krtour-map 연동(붙이기) 작업 (2026-06-08)

정본 계약: `docs/integrations/krtour-map-rest-api.md`. krtour-map이 운영 HTTP API(포트
9011, `openapi.user.json`)를 **이미 구축**했으므로(ADR-026/027/DEC-01=B 충족), 이제 TripMate가
실제 연결한다. 권장 순서 A→B→C 먼저, 이후 D~H 병행.

- [x] T-170 — [A] httpx client 신설 (완료: 2026-06-09, `apps/api/app/clients/krtour_map.py`
  — features in-bounds/get/batch/nearby/search/weather/categories/healthz + 도메인 예외
  + 재시도(transient 백오프) + 서비스 토큰 헤더 + lifespan/dependency + MockTransport 계약
  테스트 10개. 라우터 cutover/stub 제거는 T-173)
- [x] T-171 — [B] config 배선 (완료: 2026-06-09, `Settings`에 `tripmate_krtour_map_*` 필드
  추가 + `.env.example`/`apps/api/.env.example` 블록. 기존엔 필드 없어 env silently ignored)
- [ ] T-172 — [C] feature_id 문자열 정합 마감(#87/T-125 후속, 잔여 uuid 캐스트·`@version` 가정 제거)
- [ ] T-173 — [D] 응답 셰입 정렬(name/평면 lon,lat/구조화 address/weather metric 그룹핑/cluster 셰입)
- [ ] T-174 — [E] 클러스터링 서버 위임(`cluster_unit`) + `services/cluster_query.py`(feature schema 직접 SQL — 경계 위반) 제거
- [ ] T-175 — [F] `GET /trips/{id}`에 trip_view_builder 연결 + `POST /v1/features/batch`(string, cap 200, 응답 `{found,missing}`) 배선. inactive feature는 `found`+status로 옴 — "철회/폐업" 표시 분기(krtour D-12)
- [ ] T-176 — [G] 검색/날씨/카테고리/근접 라우터 실연결
- [x] T-177 — [H1] 사용자 feature 제안 큐(DEC-05 확정): `app.feature_suggestions` + `POST /features/requests`(즉시 201) + `GET /features/requests/{id}` 실구현(C-12 실체화) + rate-limit/dedup. krtour 직접 호출 X (완료: 2026-06-09)
- [ ] T-179 — [H2] Admin 검사/승인 → krtour **feature change**(DEC-05) — **actionable**(K-15 = krtour PR #317로 구현, krtour ADR-051(2026-06-10)이 이 흐름을 전송 구간 정본으로 승인): `/admin/feature-requests` 검사 + approve/reject 시 krtour `POST/PATCH/DELETE /v1/admin/features*` 호출, 결과 `feature_id`/`request_id`/state를 `feature_suggestions`에 저장, RBAC(admin/operator)+audit. 합의 5건(review_mode 등)은 krtour T-217c 회신으로 확정. 재적재와 무관
- [ ] T-180 — krtour **admin HTTP client(API 9011 `/v1/admin/*`)**: §2.9 feature change(`POST/PATCH/DELETE /v1/admin/features*`) + 운영자 재적재(`/v1/admin/feature-update-requests`) proxy 호출 client. T-170 user client와 base 동일(9011), 경로/토큰 정책만 분리 — **9012는 krtour admin UI(Next.js)라 API base 아님**: `tripmate_krtour_map_admin_base_url` 기본값(9012)/의미 재정의 + 서비스 토큰 + MockTransport 계약 테스트. (T-179 의존)
- [ ] T-178 — [공통] 에러/저하 정책(503 FEATURE_SERVICE_UNAVAILABLE + snapshot fallback, Retry-After 존중)
- [~] T-181 — [표준 추종] ADR-048 외부 `/v1` hard cutover — **라이브 계약분 완료(2026-06-09)**: krtour `origin/main`(`openapi.user.json` title `krtour-map-user 0.2.0-dev`, krtour PR #318/#319/#321)이 외부 `/v1` clean cut + batch `/tripmate/features/batch`→`/v1/features/batch`(#318) + 파라미터 개명(`search` bbox CSV→`min_lon/min_lat/max_lon/max_lat`, `page_size`/`cursor`)을 머지함. **T-170 client(`apps/api/app/clients/krtour_map.py`) 일괄 교체 완료** — 전 feature/category 경로 `/v1` prefix(`/health`만 비버전), batch 경로/검색 파라미터 갱신 + MCP `_search_features` 호출부 + MockTransport 계약 테스트. **잔여 — 대기 해제(2026-06-10, krtour `0e45bd7` T-216a~g 머지 확인)**: ① problem+json(`_error_code`를 top-level `code` 파싱으로) ② envelope payload/meta 분리(`meta.page.next_cursor` threading) ③ batch 응답 `items`→**`found`** 교체(현재 전 결과 silent-missing) ④ in-bounds `limit`→`max_items` — **즉시 실행 가능**. frontend codegen은 T-210e.
- [x] T-182 — [결정] DEC-07 좌표 필드명 정렬(ADR-048 B) (완료: 2026-06-09): **`lon`/`lat` 채택**(krtour 정렬·terse). `Coord`(Pydantic) + `CoordSchema`(Zod) `longitude`/`latitude`→`lon`/`lat`, 전 API 요청/응답·query 파라미터(geo)·ws presence.cursor 출력·frontend(useUserLocation/locationAdapter 출력)·전 테스트·docs/api 예시 일괄 정렬. 외부 krtour DTO/snapshot tolerant reader·브라우저 Geolocation `position.coords.*`·KASI DB 컬럼은 keep.

### Codex PR 3라운드 사후 리뷰 후속 (2026-06-09, `docs/reviews/2026-06-09-codex-pr-review.md`)

- [x] T-183 — [높음] #100 backup hotswap 무결성/가용성: `scripts/restore-hotswap.sh`
  GRANT 복원 + FK 적재순서(`session_replication_role=replica`), `services/backup_service.py`
  restore_id ms/uuid + 프로세스 내부 lock + DB `pg_try_advisory_lock`, API-trigger self-kill
  drain 회피, cut-over audit previous-schema reflection 보강. **완료: 2026-06-09.**
- [x] T-184 — [중간] #101/#85 trip 권한·PII·첨부검증·shared rate limit: companion 쓰기권한
  read-only 강제(day/attachment/optimize), `invited_email` PII 비-owner 마스킹, 첨부 metadata
  입력검증(`public_url` 서버파생/bucket allowlist), shared GET throttle. **완료: 2026-06-09,
  PR #109.**
- [x] T-185 — [중간] #91 websocket: `api/v1/ws.py` grace 윈도우 raw 소켓 누수(FD/mem DoS)
  차단, `services/realtime_broker.py` per-connection `send_json` 직렬화. **완료: 2026-06-09,
  PR #109.**
- [x] T-186 — [중간] #96 trip list cursor: offset→keyset(`updated_at`,`trip_id`) 전환,
  무필터 기본 bucket 의미 회귀 점검, `q` strip 재검증, `ilike` `%`/`_` 이스케이프.
  **완료: 2026-06-09, PR #109.**
- [x] T-187 — [중간] #90/#107: `middleware/geofence.py` mTLS 단일헤더 약점 →
  network CIDR 병행 강제/문서화, `api/v1/admin/audit.py` 위치감사 chain 풀스캔 →
  반환 윈도우만 검증. **완료: 2026-06-09, PR #109.**
- [x] T-188 — [중간] #108 후속: `POST /features/requests`에 `type`(new_place|correction|closure) + `target_feature_id` 노출(테이블·모델은 갖췄으나 API 미노출 → new_place만 가능했음). correction/closure는 target 필수·new_place는 금지(422), dedup 유니크 키에 type+target 포함(마이그레이션 0015), 응답 노출, frontend Zod + 회귀 테스트. (완료 2026-06-09, PR #108 리뷰 반영)
- [x] T-189 — [낮음 묶음] 리뷰 잔여 정리(2026-06-09): (a) 사용자 제안 kind를 `place`/`event`로 좁힘(#108 — notice/price/weather/route/area는 운영 데이터, `FeatureSuggestionKind` + Zod) (b) 제안 rate-limit이 `rejected`/`duplicate` 제외하고 `pending`/`approved`/`added`만 카운트(거절 다수 사용자 정당 제안 차단 방지). **잔여(후속)**: `app.feature_suggestions.requester_user_id` FK RESTRICT의 PIPA 파기 정책(사용자 hard-delete 시 익명화/cascade — T-142 인접), #99 `poi_rise_set_to_dict` model_validate·#93 money quantize(저위험 가설, 미반영).

### Claude PR 사후 리뷰 후속 (2026-06-10, `docs/reviews/2026-06-10-claude-pr-review.md`)

- [x] T-190 — [높음] #116 location-audit outbox 인증 주체/요청 ID 정합: 인증 의존성이
  `request.state.user_id`를 저장하고, 미들웨어는 spoof 가능한 `X-User-Id` 대신 state 값을 사용.
  `RequestIdMiddleware`의 생성 request id도 state/extensions에 보존하며, `/features/requests`
  body 좌표를 outbox에 남김. **완료: 2026-06-10.**
- [x] T-191 — [높음] #120/#121 trip/POI 첨부 metadata storage ref 검증:
  `bucket == TRIPMATE_RUSTFS_BUCKET` + `user-uploads/{trip_attachment|poi_attachment}/{current_user_id}/`
  prefix만 허용, 위반 시 `422 INVALID_ATTACHMENT_STORAGE_REF`. **완료: 2026-06-10.**
- [x] T-192 — [높음] #123 admin 큐레이션 첨부 metadata storage ref 검증:
  `user-uploads/{curated_plan_attachment|curated_poi_attachment}/{admin_user_id}/` prefix만 허용.
  **완료: 2026-06-10.**
- [x] T-193 — [중간] #123 `/storage/upload-urls` curated 목적 admin gate:
  `curated_plan_attachment` / `curated_poi_attachment` presigned 발급은 admin만 허용하고
  비권한은 404로 숨김. **완료: 2026-06-10.**
- [x] T-194 — [중간] #119 `/features/nearby` query `lon`/`lat` 정렬:
  legacy `lng`를 거부하고 krtour/DEC-07 정본 `lon`으로 통일. **완료: 2026-06-10.**

### Claude T-105 첨부 도메인 + RustFS (2026-06-10)

- [x] T-105 — Trip/POI/admin 첨부 도메인 완성. 하드닝(개수 제한+재정렬, #120), presigned
  download URL(#121), `/admin/rustfs/*` 객체 관리 boto3(#122), admin 큐레이션 첨부 §5.3/5.4(#123).
  부수: test-harness 잠재 버그 수정(`core/deps.py` get_db 동적 세션팩토리 참조). **완료: 2026-06-10.**
- [x] RustFS presigned 실서명 활성화(#125) — `make_upload_url`/`make_download_url` boto3 SigV4
  query auth(public endpoint, path-style). presigned + admin 경로 전부 실서명/실호출. **완료: 2026-06-10.**

### Claude Sprint 4 PR-C 프론트 (2026-06-10)

> 검증: web build / `tsc --noEmit` / `next lint` / vitest. 실 지도·업로드 E2E(VWorld 키 +
> RustFS + 브라우저)는 별도 인프라 게이트.

- [x] 지도 실 feature 로딩 + 16색 팔레트(#126) — viewport→`/features/in-bounds`, `markerPalette`/`featureBounds`.
- [x] trip `[tripId]` 메인 지도 + POI 사이드패널 양방향(#127) — `tripMapPoints`, `TripMapView`.
- [x] 지도 검색/내 위치/우클릭 메뉴(#128) — `MapSearchBox`/`UserLocationMarker`/`MapContextMenu`.
- [x] POI 추가/재정렬(D&D)/마커 편집/삭제(#129) — `poiRank`, optimistic lock.
- [x] 위치 동의 흐름(LBS/PIPA) + day CRUD(#130) — `userApi.getConsents/putConsents/withdrawConsent`.
- [x] 마커 우클릭 편집 + 설정 동의 철회 페이지(#131).
- [x] notice-plan copy 다이얼로그(#132).
- [x] trip 공유 링크 관리(#133) / 첨부 업로드 presigned PUT(#134) / feature 제안 폼(#135).
- [x] trip 댓글(#136) / 동반자 초대·관리(#137) / 일자 동선 최적화(#138) / POI 상세 편집(#139).
- [x] `maplibre-vworld` 핀 v0.1.3 동기화(최신, src/dist 무변경 docs 릴리스). **완료: 2026-06-10.**

## 머지 히스토리 (참고)

| PR | 제목 | merge 일 | 비고 |
|----|------|---------|------|
| PR #9 | Sprint 1 진입 PR | 2026-05-26 | T-030 ~ T-035 |
| PR #10 | Sprint 2 진입 PR | 2026-05-26 | 사용자/Trip/POI/동의/Storage |
| PR #11 | Sprint 3 진입 PR | 2026-05-26 | Admin + RBAC + audit chain |
| PR #14 | docs: Sprint 4~6 plan + ADR-018~023 | 2026-05-27 | 릴리즈 마일스톤 정리 |
| PR #15 | ci: GitHub Actions workflow 복원 (Sprint 4 PR-A) | 2026-06-05 | T-114/T-065 |
| PR #16 | feat: 백엔드 features API + krtour-map Protocol + cluster + trip view (PR-B) | 2026-06-05 | T-060 일부 (client는 stub — 감사 C-01) |
| PR #52 | feat: add admin trip management | 2026-06-06 | T-120 |
| PR #53 | feat: add admin POI management | 2026-06-06 | T-121 |
| PR #54 | docs: fix T-123 consistency gaps | 2026-06-06 | T-123 |
| PR #55 | docs: align Gemini responsibility boundary | 2026-06-06 | T-149 |
| PR #56 | docs: align tracking docs with merged work | 2026-06-06 | T-150 |
| PR #57 | docs: backfill auth rbac audit ADRs | 2026-06-06 | T-151 |
| PR #58 | docs: align map social kraddr docs | 2026-06-06 | T-143 |
| PR #59 | docs: fix rise set and gemini SQL docs | 2026-06-06 | T-147 |
| PR #60 | fix: use db roles for geofence admin bypass | 2026-06-06 | T-142 |
| PR #61 | docs: define trip search and export UX | 2026-06-06 | T-144 |
| PR #62 | docs: finalize backup schema-swap restore | 2026-06-06 | T-145 |
| PR #63 | feat: add trip realtime websocket broker | 2026-06-06 | T-128 |
| PR #64 | feat: add security incidents schema | 2026-06-06 | T-138 |
| PR #65 | feat: add trip companion comments flow | 2026-06-06 | T-139 |
| PR #67 | feat: add trip budget constraints | 2026-06-06 | T-140 |
| PR #69 | feat: add trip primary region | 2026-06-07 | T-141 |
| PR #70 | feat: verify resend webhook signatures | 2026-06-07 | T-136 |
| PR #71 | feat: persist refresh sessions | 2026-06-07 | T-134 |
| PR #120~#123 | feat: T-105 첨부 도메인(하드닝/download URL/rustfs boto3/admin 큐레이션) | 2026-06-10 | T-105 |
| PR #125 | feat: RustFS presigned 실서명 활성화 | 2026-06-10 | storage |
| PR #126~#131 | feat: Sprint 4 PR-C 지도 프론트(실데이터/trip맵/검색·위치·우클릭/POI편집/동의·day/잔여) | 2026-06-10 | T-060 |
| PR #132~#135 | feat: notice copy / 공유 링크 / 첨부 업로드 / feature 제안 | 2026-06-10 | T-060 |
| PR #136~#139 | feat: 댓글 / 동반자 / 동선 최적화 / POI 상세 편집 | 2026-06-10 | T-060 |
