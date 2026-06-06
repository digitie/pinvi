# tasks.md — 백로그

> **2026-06-06 정합성 감사**: `docs/audit/2026-06-06-doc-impl-audit.md`에서
> 모순·불일치·누락을 전수 점검하고 후속 Task(T-123~T-151)·ADR(ADR-027~031)·결정
> (DEC-01~10)을 도출했다. 결정 결과는 `docs/decisions-needed-2026-06-06.md`,
> krtour-map 요구사항은 `docs/krtour-map-requirements.md`. 후속 백로그는 본 파일
> "감사 후속 백로그(2026-06-06)" 절.

## 진행 중

- [ ] T-060 — Sprint 4 진입 PR (지도 + 사용자 UI + `maplibre-vworld-js` 통합)

## 다음 (우선순위 순)

- [ ] T-150 — 계획/추적 문서 정합화(sprint status/보류·완료 재분류/ADR refs/resume "박힌 ADR" 갱신) (P-04~21)
  <!-- T-111은 아래 "Sprint 5~6 backlog"에 정본 정의(감사 P-06 중복 제거) -->

## 완료

- [x] T-000 — git v1 보존 + main v2 재시작 (완료: 2026-05-25)
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
- [x] T-101 — v1의 소셜 로그인 (Kakao/Naver/Google) v2로 이식 (Sprint 2 schema/model
  완료, 라우터 본격 구현은 Sprint 4)
- [x] T-102 — v1의 Notice plan 도메인 v2로 이식 (Sprint 2 schema/model 완료, 라우터
  Sprint 6)
- [x] T-103 — v1의 RustFS Storage API v2로 이식 (Sprint 2 완료, presigned PUT)
- [x] T-104 — v1의 Admin 콘솔 (`apps/web/app/admin/`) v2로 이식 (Sprint 3 완료, PR #11)
- [x] T-110 — Admin Grafana iframe embed
  (완료: 2026-06-05, `/admin/grafana` iframe shell + `NEXT_PUBLIC_GRAFANA_*` env +
  Web `frame-src` CSP + admin guard e2e)
- [x] T-109 — 한국 전용 geofencing FastAPI fallback
  (완료: 2026-06-05, `TRIPMATE_GEOFENCE_*` env + `CF-IPCountry` 기반 451 middleware +
  health/docs 우회 + roles claim 운영자 우회 단위 테스트)
- [x] T-115 — Backup snapshot foundation + `/admin/backup` 1차 UI
  (완료: 2026-06-06, `scripts/backup-db.sh` / `scripts/restore-db.sh` +
  `GET /admin/backup/snapshots` + `POST /admin/backup/snapshot` + admin snapshot page.
  핫스왑 restore는 T-111로 유지)
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

- [ ] T-111 — Backup/Restore UI 핫스왑 (ADR-022, Sprint 6) — `/admin/backup`
  + RestoreHotswapDialog. Sprint 5의 backup script + endpoint 위에 UI + 핫스왑
  워크플로 finalize.
- [ ] T-112 — TripMate MCP 외부 인터페이스 서빙 (ADR-019, Sprint 6) —
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
- [ ] T-125 — feature_id 문자열化(코드의 UUID 가정 제거) (C-09; ADR-028)
- [ ] T-126 — POI 생성 경로 단일화(`/trips/{id}/pois` 정본) (A-01,C-16)
- [ ] T-127 — MCP 외부 인터페이스 정본화(mcp-server.md 권위, status enum, 토큰 엔드포인트) (A-02,A-06,A-12)
- [ ] T-128 — 실시간 협업 백엔드 설계 + WS 계층(presence/충돌해소, Sprint 5) (C-03,D-05)
- [ ] T-129 — `/search` 통합 + `/geo/*`·`/regions/*` 명세·구현 (A-13,C-02,C-13)
- [ ] T-130 — `/public/*` 구현(krtour 연동 후) (C-04)
- [ ] T-131 — `GET /trips/{id}`에 `build_trip_view` 연결 (C-05)
- [ ] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize) 구현 분할 (C-06,D-06)
- [ ] T-133 — Admin priority-3 엔드포인트·페이지 실구현(or 상태 강등) (C-08,C-17)
- [ ] T-134 — `POST /auth/refresh` + `user_sessions` 영속화 (C-14)
- [ ] T-135 — POI 응답 `rise_set` 노출 (C-18)
- [ ] T-136 — Resend webhook Svix 서명 검증 (C-22)
- [ ] T-137 — notice/curated-plan 스키마 정본화(`curated_trip_plans` 분리) (D-01,D-04; ADR-029)
- [ ] T-138 — `users` 누락 컬럼 + `security_incidents` 테이블 추가 (D-02,D-03,D-09)
- [ ] T-139 — 동반자 초대 흐름 + 댓글 모델/`visibility` 정리 (D-06)
- [ ] T-140 — 여행 예산(budget/currency) 도메인 + 복사 흐름 (D-10)
- [ ] T-141 — trip↔지역 구조적 연결(POI 좌표 유도 or region code) (D-11)
- [ ] T-142 — geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리 (D-13,D-24)
- [ ] T-143 — 지도/소셜 문서 정정(Kakao 어댑터 제거, Google-only, kraddr-geo stack 추가) (D-15,D-21,D-22)
- [ ] T-144 — 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계 (D-16,D-17)
- [ ] T-145 — backup 핫스왑 동일호스트 schema-swap 확정(2×DB 폐기) (D-19)
- [ ] T-146 — location-audit async outbox + feature 캐시(N+1 제거) (D-20,D-26)
- [ ] T-147 — 잔여 문서 정정(rise/set 정책, gemini.md partial unique index 문법) (D-23,D-25)
- [ ] T-148 — SPRINT-4 backend 재작성(HTTP 경계 반영) (P-01; ADR-027)
- [x] T-149 — Gemini 책임 목록 정정(README/AGENTS/SKILL) (P-03)
- [ ] T-150 — 계획/추적 문서 정합화(sprint status/보류·완료 재분류/ADR refs/resume "박힌 ADR" 갱신) (P-04~21)
- [ ] T-151 — 미기록 ADR 백필(auth-token/RBAC/audit-chain) + SPRINT placeholder 번호 할당 (P-07,P-08)

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
