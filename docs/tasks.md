# tasks.md — 백로그

## 진행 중

- [ ] T-060 — Sprint 4 진입 PR (지도 + 사용자 UI + `maplibre-vworld-js` 통합)

## 다음 (우선순위 순)

- [ ] T-110 — Admin Grafana iframe embed (ADR-022 보조, Sprint 5) — krtour-map
  비의존 운영 UI 후보

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

## 보류

- [ ] T-066 — krtour-map OpenAPI HTTP 전환 구현 + drift gate (보류:
  krtour-map OpenAPI/client 연동 의존)
- [x] T-100 — v1의 Resend 이메일 통합 v2로 이식 (Sprint 2 완료, PR #10)
- [x] T-101 — v1의 소셜 로그인 (Kakao/Naver/Google) v2로 이식 (Sprint 2 schema/model
  완료, 라우터 본격 구현은 Sprint 4)
- [x] T-102 — v1의 Notice plan 도메인 v2로 이식 (Sprint 2 schema/model 완료, 라우터
  Sprint 6)
- [x] T-103 — v1의 RustFS Storage API v2로 이식 (Sprint 2 완료, presigned PUT)
- [x] T-104 — v1의 Admin 콘솔 (`apps/web/app/admin/`) v2로 이식 (Sprint 3 완료, PR #11)
- [ ] ~~T-107~~ — **Gemini 통합 — 보류 (deferred)**. 별 repo
  `tripmate-ai-companion`으로 분리 (ADR-020). 본 저장소는 호출 컨트랙트 문서만
  (`docs/integrations/ai-companion.md`, Sprint 6 진입 시).
- [ ] T-108 — 운영 배포 자동화 (Sprint 6) — **Odroid M1S + N150 16GB 양쪽**
  (ADR-023). multi-platform Docker 빌드 + 두 노드 streaming replication.

### Sprint 5~6 (v0.2.0 / v1.0) 신규 backlog

- [ ] T-109 — 한국 전용 geofencing 3중 안전망 (ADR-018, Sprint 6) —
  Cloudflare WAF + nginx geo + FastAPI middleware. KR 외 IP → 451.
- [ ] T-111 — Backup/Restore UI 핫스왑 (ADR-022, Sprint 6) — `/admin/backup`
  + RestoreHotswapDialog. Sprint 5의 backup script + endpoint 위에 UI + 핫스왑
  워크플로 finalize.
- [ ] T-112 — TripMate MCP 외부 인터페이스 서빙 (ADR-019, Sprint 6) —
  `apps/api/app/mcp/` + `/mcp/sse` + 토큰 발급 / 회수 UI + 5개 read-only tool.
- [ ] T-113 — `tripmate-ai-companion` 별 repo 신설 (ADR-020) — T-107 후속.
  사용자가 repo 명 / provider 확정 후 진입.
- [x] T-114 — GitHub Actions CI/CD 복원 (ADR-021, Sprint 4) — workflow 파일 복원 완료.
  운영 확인은 T-062에서 완료. required status check 후속은 T-065.

## 머지 히스토리 (참고)

| PR | 제목 | merge 일 | 비고 |
|----|------|---------|------|
| PR #9 | Sprint 1 진입 PR | 2026-05-26 | T-030 ~ T-035 |
| PR #10 | Sprint 2 진입 PR | 2026-05-26 | 사용자/Trip/POI/동의/Storage |
| PR #11 | Sprint 3 진입 PR | 2026-05-26 | Admin + RBAC + audit chain |
| PR #14 | docs: Sprint 4~6 plan + ADR-018~023 | 2026-05-27 | 릴리즈 마일스톤 정리 |
