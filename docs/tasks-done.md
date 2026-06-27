# tasks-done.md — 완료·아카이브

완료된 task와 머지 이력을 보관한다. 열린 작업은 `docs/tasks.md`, 현재 진척과
"다음 한 작업"은 `docs/resume.md`가 정본이다. 작성 규약은 `docs/tasks-rule.md`를
따른다.

## 2026-06-28

- [x] T-236a — WebSocket multi-client N150 live e2e drill.
      N150 live mutating Playwright에서 실제 WebSocket broadcast/reconnect 뒤 Trip snapshot reload를
      검증했다. 첫 실패로 `pinvi-api` worker 2개와 process-local realtime broker 충돌을 확인해
      Pinvi compose 기본 worker를 1로 낮추고, `kor-travel-docker-manager` PR #44에서 운영 compose도
      `PINVI_API_WORKERS=1` 기본값으로 맞췄다. 두 번째 실패로 public Web/API CORS 주입 drift를 확인해
      docker-manager PR #45에서 `PINVI_PUBLIC_API_URL`/`PINVI_CORS_ALLOWED_ORIGINS`를 gitignore `.env`
      주입값으로 분리했다. 최종 Windows Playwright live mutating e2e 1건이 통과했다.

- [x] T-236 — WebSocket multi-client collaboration e2e.
      Trip 상세 mock Playwright e2e에 2개 브라우저 컨텍스트 presence/broadcast reload,
      재연결 후 최신 snapshot 반영, 5개 컨텍스트 presence fan-out와 offline cleanup 검증을
      추가했다. Fake WebSocket은 React Strict Mode 재마운트와 재연결에서 마지막 active socket을
      기준으로 서버 이벤트를 주입하도록 정리했다. N150 staging live 검증은 작업 크기를 분리해
      T-236a로 남겼다.

- [x] T-288 — Task 문서 분리 정책 반영.
      `kor-travel-map`의 `tasks.md`/`tasks-done.md`/`resume.md` 분리 정책을 확인하고,
      Pinvi에 `docs/tasks-rule.md`와 본 파일을 추가했다. 신규 task 진입 전 최근 2일 PR
      리뷰 코멘트 확인, task 분리 기준, 완료 후 `tasks-done.md` 아카이브 규칙을 고정했다.
      기존 `tasks.md`의 legacy 완료 이력 전체 이관은 `T-288-legacy-task-archive`로 분리했다.

- [x] T-235 — Optimistic lock / conflict dialog.
      Trip/POI 409 conflict UX, LWW/수동 병합, server/my value 선택과 API/Vitest/Windows
      Playwright 회귀 테스트를 구현했다. Day API는 현재 `If-Match` 계약이 없어 T-287로
      분리했다.

- [x] T-234 — WebSocket client invalidation / auth close handling.
      WebSocket close code/reason 분류, 4401 refresh 재연결, 4403 권한 상실 안내,
      4408/4429 backoff 안내, realtime invalidation key와 duplicate reload 방지를 구현했다.

- [x] T-233 — Sprint 5/6 상세 Task 계획.
      `docs/execplan/sprint5-v020-release-plan.md`에 Sprint 5 `v0.2.0` 잔여 구현
      Task와 Sprint 6 `v1.0.0` 후속 Task 초안을 정리하고, PR 리뷰에서 지적된 법무/운영
      gap을 T-256~T-286으로 보강했다.

- [x] T-232 — Trip WebSocket frontend client / presence 첫 연결.
      `@pinvi/api-client`에 `TripRealtimeClient`와 `tripWebSocketUrl`을 추가하고,
      사용자 Trip 상세 화면을 `WS /ws/trips/{trip_id}` presence/reload 흐름에 연결했다.

## Legacy

- 기존 `docs/tasks.md`의 `Admin 콘솔 기능 보강 프로그램`, `완료`, `머지 히스토리`,
  그리고 완료/보류가 섞인 하위 legacy 섹션은 `T-288-legacy-task-archive`에서
  단계적으로 이관한다.
