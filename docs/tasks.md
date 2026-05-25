# tasks.md — 백로그

## 진행 중

- (없음)

## 다음 (우선순위 순)

- [ ] T-010 — Sprint 1 진입 PR (`apps/{api,web,etl}` + `infra/` + `packages/`
      scaffolding). 사용자 승인 후 시작. 자세히는 `docs/sprints/SPRINT-1.md`.
- [ ] T-011 — ADR-010 인증 토큰 모델 (cookie session vs JWT)
- [ ] T-012 — ADR-011 Admin RBAC 모델
- [ ] T-013 — ADR-012 소셜 로그인 provider 정책
- [ ] T-014 — ADR-013 RustFS 버킷 분리 정책

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
- [x] T-023 — Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 자동 리뷰 프롬프트 (완료: 2026-05-25)

## 보류

- [ ] T-100 — v1의 Resend 이메일 통합 v2로 이식 (Sprint 2 후보)
- [ ] T-101 — v1의 소셜 로그인 (Kakao/Naver/Google) v2로 이식 (Sprint 2 후보)
- [ ] T-102 — v1의 Notice plan 도메인 v2로 이식 (Sprint 2 후보)
- [ ] T-103 — v1의 RustFS Storage API v2로 이식 (Sprint 2 후보)
- [ ] T-104 — v1의 Admin 콘솔 (`apps/web/app/admin/`) v2로 이식 (Sprint 3 후보)
- [ ] T-105 — v1의 Trip + POI Attachment 도메인 v2로 이식 (Sprint 3 후보)
- [ ] T-106 — Telegram 통합 (Sprint 4 후보)
- [ ] T-107 — Gemini 통합 (Sprint 4 후보)
- [ ] T-108 — Odroid M1S 배포 자동화 (Sprint 5 후보)

## 머지 히스토리 (참고)

| PR | 제목 | merge 일 | 비고 |
|----|------|---------|------|
| (v2의 첫 PR — 본 골격) | docs: bootstrap v2 skeleton + SPEC V8 reflect | (대기) | T-000 ~ T-009 묶음 |
