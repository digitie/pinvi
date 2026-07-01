# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- T-273 — codex 진행 중. 브랜치 `agent/codex-t273-admin-live-storage-state`.
  현재 범위는 `v1.0.0` Web/API/Admin E2E / live gate 중 Admin full catalog 재실행 조건 확인과
  잔여 blocker 정리다. N150 우선 + Playwright N150 runner + 불가 시 Windows fallback만 사용한다.
  현 세션에서는 N150 alias가 없고 Windows/WSL에 `PINVI_ADMIN_LIVE_*` 실행 env가 없어 browser full
  catalog 실실행이 막혔다. repo-side로 full matrix의 `PINVI_ADMIN_LIVE_STORAGE_STATE` 경로를 보강해
  credential 원문 없이 사전 인증 state로 재개할 수 있게 한다.
  운영 public DB 대상 mutating Playwright는 전용 staging Web/API 없이는 실행하지 않는다.

## v0.2.0 구현 게이트

- 완료된 T-259는 [`docs/tasks-done.md`](tasks-done.md)로 이관했다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

- [ ] T-122 — Naver/Kakao OAuth provider 구현.
