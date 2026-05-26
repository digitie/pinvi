# resume.md

## 현재 상태

**Sprint 3 PR 작성 중.** Sprint 2 머지 완료 (`feat/sprint-2-domain` → main).
Sprint 3 본 PR은 Admin 콘솔: RBAC dep + admin_audit chain + 사용자 목록/상세 +
force-verify/disable + 이메일 큐 + 감사 로그 chain 검증 + 13페이지 frontend skeleton.

## 다음 한 작업

Sprint 3 PR push → 머지 대기 → Sprint 4 (지도 + maplibre-vworld + 사용자 UI) 진입.

운영 지시 변경: **GitHub CI/CD 사용 금지** — 검증은 local WSL only.
`.github/workflows/`는 모두 삭제됨.

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
- [x] Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 자동 리뷰 프롬프트 + 5분 주기 PR 감시 — T-023
- [ ] Sprint 1 진입 PR (apps + packages scaffolding) — T-030 (대기)

## 다음 ADR 후보 (Sprint 진입 시 박음)

- ADR-014 (Sprint 1): 인증 토큰 모델 (cookie session vs JWT) — SPEC V8 02-backend §1 잠정 JWT 15m/7d
- ADR-015 (Sprint 1): Admin RBAC `roles TEXT[]` 모델 (SPEC V8 M-14 정정 반영)
- ADR-016 (Sprint 2): 소셜 로그인 provider (Google 우선, Kakao/Naver는 v2)
- ADR-017 (Sprint 2): `email_queue` worker 패턴 (PostgreSQL `SKIP LOCKED`)
- ADR-018 (Sprint 4): viewport 클러스터링 (zoom < 7/11/14)
- ADR-019 (Sprint 5): WebSocket broker 모델 (단일 프로세스 in-memory)
- ADR-020 (Sprint 6): OR-Tools 일정 최적화 분기 (POI ≤10/11-20/20+)

## 박힌 ADR

- ADR-001 ~ ADR-009: v2 시작 결정
- ADR-010: SPEC V8 채택
- ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조
- ADR-012: 사용자 위치 정보 획득 (Geolocation + expo-location)
- ADR-013: Notice plan 도메인 v1 → v2 이전 + 명명 분리
- ADR-014: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리
- ADR-015: 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- ADR-016: AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책

## 운영 지시

- Sprint 4 완료 전까지 새 PR은 `docs/runbooks/pr-review-sprint4.md` 기준으로
  리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리 sync → 검증 → 머지를 반복한다.
- `.github/workflows/codex-pr-monitor.yml`이 5분마다 열린 PR을 감시하고, 최신 head
  SHA 리뷰 마커가 없는 PR을 다시 리뷰한다.

## 차단 사유 / 결정 대기

- 사용자 review 후 SPEC V8 반영분 push
- Sprint 1 진입 승인 시 `apps/` scaffolding PR 시작
