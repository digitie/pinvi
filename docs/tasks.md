# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- 열린 PR #227 — map marker tuning과 tracking 문서를 건드리는 오래된 PR이다. 다음 task에서 map
  marker 파일을 수정하기 전 최신 상태를 다시 확인한다.
- T-291-etl-sql-tests — `apps/etl/**`와 audit retention 정책을 건드리는 잔여 task다. 이 영역은
  별도 선점 확인 없이 같은 PR에 섞지 않는다.

## 다음 우선순위

- 신규 task 진입 전 최신 PR/브랜치, `docs/resume.md`, `docs/journal.md` 최신 항목을 확인하고
  unclaimed Sprint 6 구현 task로 이동한다.
- T-259는 최종 release gate로만 유지한다.
- T-285는 사용자 지시에 따라 현재 진행하지 않는다.

## v0.2.0 구현 게이트

- [ ] T-287 — Trip Day optimistic lock API / conflict UX follow-up.
      `PATCH/DELETE /trips/{trip_id}/days/{day_index}`에 `If-Match` 기준을 도입할지 결정하고,
      도입 시 API 409 회귀, day rename/delete 충돌 다이얼로그, live e2e를 추가한다.
- [ ] T-259 — Release candidate gate / `v0.2.0`.
      남은 범위: Admin live full catalog, release notes, tag, GitHub Release.

## 최근 PR 리뷰 후속

- [ ] T-291-etl-sql-tests — app-owned ETL SQL 실행 테스트 + audit retention 정책 분리.
      T-291에서 분리한 잔여. etl Postgres fixture로 asset 원시 SQL을 실행하는
      integration/schema-compile smoke를 추가하고, `pii_retention`의 append-only hash-chain
      `admin_audit_log` location cutoff 후보 카운트 정책을 자체 보존정책으로 분리한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-260 — Sprint 6 상세 실행 계획 / ADR 정리.
- [ ] T-265 — Admin notice plan 작성기.
- [ ] T-266 — MCP 외부 인터페이스 운영 실증.
- [ ] T-267 — Backup/Restore UI hot-swap 완성.
- [ ] T-268 — 한국 전용 geofencing 3중 안전망.
- [ ] T-269 — LBS / 법무 4문서 / 동의 UX.
- [ ] T-270 — 성능 / 부하 / 보안 점검.
- [ ] T-271 — Odroid + N150 병행 운영.
      ARM image와 GHCR 배포는 제외하고 노드 로컬 checkout/build/smoke 기준으로 진행한다.
- [ ] T-272 — AI companion 별도 서비스 분리.
- [ ] T-273 — v1.0.0 E2E / Live Gate.
- [ ] T-274 — v1.0.0 릴리즈.
- [ ] T-285 — AI companion v1.0 scope gate. (보류: 사용자 지시로 현재 진행하지 않음)
      v1.0 user-facing AI companion은 제외하고 client contract/Admin status까지만 유지한다.
- [ ] T-286 — Cross-track review gap closure.
      cross-track #238 리뷰 44개 gap과 PR #264 리뷰 항목을 Task/문서/검증 케이스로 매핑한다.

## 보류 / 미래 작업

- [ ] T-113 — `kor-travel-concierge` 별 repo 신설 (ADR-020).
      사용자가 repo 명 / provider 확정 후 진입한다.
- [ ] T-122 — Naver/Kakao OAuth provider 구현.
      현재는 사용하지 않는다. Google OAuth 안정화 후 별도 PR에서 provider별 start / callback /
      link / unlink / 버튼 활성화를 구현한다.
