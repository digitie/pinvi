# tasks.md — 백로그

진행/예정(`[ ]`) task만 두는 백로그를 목표로 한다. 완료·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 현재 진척과 "다음 한 작업"은
[`docs/resume.md`](resume.md)가 정본이다. 작성·유지 규약은
[`docs/tasks-rule.md`](tasks-rule.md)를 따른다.

> 전환 메모(2026-06-29): `T-288-legacy-task-archive`에서 기존 `Admin 콘솔 기능 보강 프로그램`,
> `완료`, `머지 히스토리`, 완료/보류 혼재 legacy 섹션을 `docs/tasks-done.md`로 옮겼다.
> `tasks.md`에는 열린 backlog와 현재 병행 상태만 둔다.

> **2026-06-06 정합성 감사**: `docs/audit/2026-06-06-doc-impl-audit.md`에서
> 모순·불일치·누락을 전수 점검하고 후속 Task(T-123~~T-151)·ADR(ADR-027~~031)·결정
> (DEC-01~~10)을 도출했다. 완료된 감사 후속은 `docs/tasks-done.md`로 이관했고,
> 열린 항목만 본 파일에 남긴다.

## 작업 전 체크

- 병행 작업 기록, 선점 충돌 회피, 완료 이관 규칙은 `docs/tasks-rule.md` §8을 따른다.
- 신규 task 시작 전 `git fetch origin main`, 본 파일의 `진행 중` / `다음` / `최근 PR 리뷰 후속`,
  `docs/resume.md`, `docs/journal.md` 최신 항목, 열린 PR/브랜치를 확인한다.
- 다른 에이전트가 선점한 파일/도메인은 같은 PR에서 수정하지 않는다. 필요한 경우 사용자 확인 또는
  non-overlap task로 전환한다.

## 진행 중

- T-259 — Release candidate gate / `v0.2.0`.
  2026-06-28 N150 후보 배포와 smoke, backup snapshot, 최신 main API CI, Web clean manual evidence,
  N150 Playwright Docker runner smoke, Admin live 200/2000, restore staging drill은 통과했다.
  Admin live full catalog와 release note/tag/GitHub Release 생성이 남아 release/tag는 보류한다.
  `scripts/backup-db.sh`는 host `pg_dump` 부재 시 Docker fallback을 지원하도록 보강했고 N150
  재실행 증거까지 확보했다. 상세는
  `docs/execplan/v020-release-candidate-gate.md`.

- 병행 트랙 (claude, 2026-06-29) — T-291 ETL failure sensor는 PR #312로 main에 머지됐다.
  T-291 잔여는 app-owned ETL SQL 실행 수준 integration/schema-compile smoke와 audit retention
  정책 분리다. codex는 T-292에서 `apps/etl/**`, `docs/architecture/dagster-etl-bridge.md`,
  `docs/runbooks/etl.md`를 건드리지 않는다.

- 병행 후보 (claude, 2026-06-29) — T-261~T-263 경로 최적화(OR-Tools) + 스마트 정렬 API/UI
  트랙은 신규 `optimize` 모듈 중심이다. codex가 다음 task에 진입하기 전 PR/브랜치와 본 섹션을
  다시 확인한다.

## 다음 (우선순위 순)

- 다음 구현 후보: T-286 Cross-track review gap closure. T-285는 사용자 지시에 따라 현재 진행하지
  않는다.
- T-259의 남은 full catalog와 `v0.2.0` tag/Release는 최종 release gate로 분리해 유지한다.
- T-289/T-290은 PR #310으로 머지됐으므로 같은 영역을 건드릴 때는 최신 main 기준으로 다시
  CodeGraph 영향도를 확인한다.
- 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 확인한다. 2026-06-28 T-256에서
  PR #238/#264 legal/ops 리뷰와 PR #265~~#289 사람 리뷰 코멘트를 확인했고,
  후속은 `docs/execplan/legal-ops-review-gap-crosswalk.md` 및 T-289~~T-292로 연결했다.

## v0.2.0 구현 게이트 (2026-06-27)

- [ ] T-287 — Trip Day optimistic lock API / conflict UX follow-up.
      `PATCH/DELETE /trips/{trip_id}/days/{day_index}`에 `If-Match` 기준을 도입할지 결정하고,
      도입 시 API 409 회귀, day rename/delete 충돌 다이얼로그, live e2e를 추가한다.
- [ ] T-259 — Release candidate gate / `v0.2.0`.
      N150 deploy/smoke, backup snapshot, main API/Web evidence, Admin live 200/2000,
      restore staging drill은 통과했다. Admin live full catalog와 release notes/tag를 완료한다.

## 최근 PR 리뷰 후속

- [ ] T-291 — ETL compliance SQL / failure notification follow-up. (부분 완료: PR #312, claude)
      PR #271/#273 사후 리뷰의 Dagster failure sensor drift는 닫혔다. app-owned ETL SQL statement
      integration/schema-compile smoke와 audit retention 정책 분리 gap은 잔여다.
## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-260 — Sprint 6 상세 실행 계획 / ADR 정리.
- [ ] T-261 — 경로 최적화 정책 / distance matrix. (진행: claude, 2026-06-29 · codex 병행 금지)
- [ ] T-262 — 스마트 정렬 API / OR-Tools. (진행: claude, 2026-06-29 · codex 병행 금지)
- [ ] T-263 — 스마트 정렬 UI. (진행: claude, 2026-06-29 · codex 병행 금지)
- [ ] T-264 — Admin category mapping DB override.
- [ ] T-265 — Admin notice plan 작성기.
- [ ] T-266 — MCP 외부 인터페이스 운영 실증.
- [ ] T-267 — Backup/Restore UI hot-swap 완성.
- [ ] T-268 — 한국 전용 geofencing 3중 안전망.
- [ ] T-269 — LBS / 법무 4문서 / 동의 UX.
- [ ] T-270 — 성능 / 부하 / 보안 점검.
- [ ] T-271 — Odroid + N150 병행 운영. ARM image와 GHCR 배포는 제외하고 노드 로컬
      checkout/build/smoke 기준으로 진행한다.
- [ ] T-272 — AI companion 별도 서비스 분리.
- [ ] T-273 — v1.0.0 E2E / Live Gate.
- [ ] T-274 — v1.0.0 릴리즈.
- [ ] T-285 — AI companion v1.0 scope gate. (보류: 사용자 지시로 현재 진행하지 않음)
      v1.0 user-facing AI companion은 제외하고 client contract/Admin status까지만 유지한다.
- [ ] T-286 — Cross-track review gap closure.
      cross-track #238 리뷰 44개 gap과 PR #264 리뷰 항목을 Task/문서/검증 케이스로 매핑한다.

## 보류 / 미래 작업

- [ ] T-113 — `kor-travel-concierge` 별 repo 신설 (ADR-020) — T-107 후속.
      사용자가 repo 명 / provider 확정 후 진입한다.
- [ ] T-122 — Naver/Kakao OAuth provider 구현 — 미래 작업.
      현재는 사용하지 않는다. Google OAuth 안정화 후 별도 PR에서 provider별 start / callback /
      link / unlink / 버튼 활성화를 구현한다.
