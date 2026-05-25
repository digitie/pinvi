# resume.md

## 현재 상태

v2 설계 단계 (Sprint 1 진입 직전). 코드 작성 금지. 문서/계약/ADR만.

`main`은 v2 골격이 박힌 상태. `v1`은 직전 9개월 작업 보존.

## 다음 한 작업

사용자 review → 본 v2 골격을 origin main에 push. 그 후 Sprint 1 진입 승인 시
`apps/{api,web,etl}` scaffolding 첫 PR.

## 진척도

- [x] git 흐름 정리 (v1 보존 / main 골격 재시작) — T-000
- [x] README / CLAUDE / AGENTS / SKILL — T-001
- [x] docs/architecture / agent-guide / dev-environment — T-002
- [x] docs/decisions (ADR-001 ~ ADR-009) — T-003
- [x] docs/journal / resume / tasks — T-004
- [x] docs/data-model / postgres-schema / test-strategy — T-005
- [x] docs/krtour-map-integration — T-006
- [x] docs/sprints/README + SPRINT-1 — T-007
- [ ] Sprint 1 진입 PR (apps scaffolding) — T-010 (대기)

## 다음 ADR 후보

- ADR-010: 인증 토큰 모델 (cookie session vs JWT)
- ADR-011: Admin RBAC 모델 (roles + permission matrix)
- ADR-012: 소셜 로그인 provider 정책 (Kakao / Naver / Google)
- ADR-013: RustFS 버킷 분리 정책 (app vs feature-media)
- ADR-014: Telegram / Resend / Gemini 통합 경계
- ADR-015: Next.js App Router vs Pages Router (App Router 잠정)
- ADR-016: 지도 클라이언트 (`maplibre-vworld-js` import 정책)

## 차단 사유 / 결정 대기

- 사용자 review 후 v2 골격 main push.
- Sprint 1 진입 승인 시 `apps/` scaffolding PR 시작.
