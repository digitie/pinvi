# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- T-273 — codex 진행 중. 브랜치 `agent/codex-t273-v100-e2e-live-gate`.
  범위는 `v1.0.0` Web/API/Admin E2E / live gate 정리와 실행 자산 보강이다. T-271 제거 기준에 따라
  Odroid 병행 운영 smoke는 blocker로 재도입하지 않고, N150 우선 + Playwright N150 runner + 불가 시
  Windows fallback만 사용한다.
  현재 PR 범위는 기존 e2e/live 스크립트 inventory를 바탕으로 `scripts/verify-v100-live-gate.sh`와
  `docs/runbooks/v100-live-gate.md`를 추가하고, staging mutating phase와 운영 read-only phase를
  분리해 다음 실제 gate 실행의 충돌 위험을 낮추는 것이다.

## v0.2.0 구현 게이트

- 완료된 T-259는 [`docs/tasks-done.md`](tasks-done.md)로 이관했다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

- [ ] T-122 — Naver/Kakao OAuth provider 구현.
