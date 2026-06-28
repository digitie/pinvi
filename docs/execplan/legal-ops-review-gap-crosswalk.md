# Legal/Ops 리뷰 gap crosswalk

작성일: 2026-06-28

## 1. 목적

이 문서는 PR 리뷰에서 나온 운영·법정 gap이 백로그에서 사라지지 않도록
리뷰 코멘트와 Task 번호를 1:1 이상으로 연결하는 정본이다. T-256의 산출물이며,
Sprint 5 release gate와 Sprint 6 진입 계획이 이 문서를 참조한다.

원자료:

- PR #238 `docs: Admin 콘솔 보강 계획 정리` 리뷰 코멘트
  (`2026-06-26`, Admin 운영·법정 표면 감사)
- PR #264 `docs: plan sprint 5 and 6 tasks` 리뷰 코멘트
  (`2026-06-27`, Sprint 5/6 계획 감사)
- 최근 2일 PR #265~#289 issue comment 점검
  (`2026-06-27`~`2026-06-28`, WebSocket/ETL/Admin integrity 사후 리뷰 포함)
- `docs/compliance/pipa.md`, `docs/compliance/lbs-act.md`,
  `docs/sprints/SPRINT-5.md`, `docs/sprints/SPRINT-6.md`, `docs/tasks.md`

## 2. Task 연결 원칙

- T-256은 crosswalk 작성과 문서 정합만 닫는다. 구현은 하지 않는다.
- T-257은 email deliverability / provider tracking preflight다.
- T-258은 Sprint 6 legal/ops 구현 준비 gate다.
- T-259는 `v0.2.0` release candidate gate다.
- T-275~T-286은 Sprint 6 legal/ops와 scope gate 구현 묶음이다.
- T-286은 이 문서의 사본이 아니라, Sprint 6 구현 중 실제 gap closure 상태를 다시 검증하는
  후속 감사 Task다.

## 3. #238/#264 legal-ops gap 44개 매핑

| ID    | 리뷰 gap                                                                           | 대응 Task                  | release gate                     |
| ----- | ---------------------------------------------------------------------------------- | -------------------------- | -------------------------------- |
| G-001 | PIPA 침해사고 콘솔 `/admin/incidents` 부재                                         | T-275                      | v1.0 전 구현                     |
| G-002 | 이상 IP, admin bulk export, audit chain 깨짐 등 incident 자동 트리거 부재          | T-275, T-283               | v1.0 전 구현                     |
| G-003 | CPO 30분 검토, 정보주체 통지, KISA 60일 report 상태/메일 흐름 부재                 | T-275                      | v1.0 전 구현                     |
| G-004 | LBS 위치 감사 화면이 IA/role matrix/live matrix에서 고아화될 위험                  | T-258, T-269, T-286        | Sprint 6 진입 전 설계            |
| G-005 | 위치 감사 chain on-demand verify 액션 부재                                         | T-276, T-283               | v1.0 전 구현                     |
| G-006 | 위치 감사 6개월 archive/delete 실행과 chain bridge 정책 부재                       | T-276                      | v1.0 전 구현                     |
| G-007 | 규제기관 제출용 위치 확인자료 export 부재                                          | T-276, T-278               | v1.0 전 구현                     |
| G-008 | RBAC role grant/revoke API/UI 부재                                                 | T-280                      | v1.0 전 구현                     |
| G-009 | role 변경 시 session revoke와 `access_token_version` bump 정책 부재                | T-280, T-281               | v1.0 전 구현                     |
| G-010 | 마지막 admin 강등 차단, CPO 부여/회수 제약, per-action matrix 부재                 | T-258, T-280               | Sprint 6 진입 전 설계            |
| G-011 | UGC 신고 큐 `content_reports` 부재                                                 | T-279                      | v1.0 전 구현                     |
| G-012 | comment hide/delete admin action 부재                                              | T-279                      | v1.0 전 구현                     |
| G-013 | share link 강제 회수, public trip 강제 비공개, attachment takedown 부재            | T-279                      | v1.0 전 구현                     |
| G-014 | Resend domain/FROM verified, SPF/DKIM/DMARC 운영 패널 부재                         | T-257, T-277               | T-257 preflight, v1.0 구현       |
| G-015 | hard-bounce/complaint suppression, `users.email_status` enforcement 부재           | T-277                      | v1.0 전 구현                     |
| G-016 | Resend webhook 서명/마지막 수신/실패율 health 부재                                 | T-257, T-277, T-283        | T-257 preflight                  |
| G-017 | Pinvi 자체 debug logs와 upstream map logs route 경계 drift                         | T-244, T-245, T-246, T-286 | T-244~T-246 완료, T-286 재감사   |
| G-018 | X-Request-Id timeline과 Sentry deep-link/PII masking 연결 필요                     | T-244, T-245, T-283        | T-244~T-245 완료, 보안 점검 후속 |
| G-019 | `kor-travel-map` admin/ops route map drift, provider run-now 부재                  | T-247, T-286               | T-247 완료, T-286 재감사         |
| G-020 | upstream cursor pagination을 Pinvi proxy/Web hook이 보존해야 함                    | T-210, T-247, T-286        | 구현별 완료, T-286 재감사        |
| G-021 | approve/reject/cancel/merge mutation의 idempotency key 원칙 필요                   | T-210, T-247, T-286        | 구현별 완료, T-286 재감사        |
| G-022 | upstream admin security none이므로 Pinvi proxy RBAC/audit가 유일 authZ 경계        | T-283, T-286               | v1.0 보안 점검                   |
| G-023 | category mapping DB override SoT/ADR 구현 필요                                     | T-260, T-264               | Sprint 6                         |
| G-024 | 파괴적 admin action 권한 매트릭스 부재                                             | T-258, T-280               | Sprint 6 진입 전 설계            |
| G-025 | sidebar가 role-aware item filtering을 해야 함                                      | T-280, T-286               | v1.0 전 구현                     |
| G-026 | force-resend-verify 라우터/UI 부재                                                 | T-281                      | v1.0 전 구현                     |
| G-027 | user sessions 목록, 단일/전체 forced logout 부재                                   | T-281                      | v1.0 전 구현                     |
| G-028 | force-password-reset이 기존 password hash를 무효화해야 함                          | T-281                      | v1.0 전 구현                     |
| G-029 | `DELETE /users/me`와 삭제 유예 lifecycle 부재                                      | T-281, T-276               | v1.0 전 구현                     |
| G-030 | admin reactivate, purge-now, anonymize workflow 부재                               | T-281, T-276               | v1.0 전 구현                     |
| G-031 | DSR intake, SLA, evidence, 완료 통지 workflow 부재                                 | T-278                      | v1.0 전 구현                     |
| G-032 | consent viewer / privacy tab / 보존 시계 운영 화면 부재                            | T-278, T-281               | v1.0 전 구현                     |
| G-033 | retention last_run/overdue dashboard와 kill-switch 부재                            | T-276                      | v1.0 전 구현                     |
| G-034 | admin PII 1000+ row bulk-read/export abuse trigger 부재                            | T-275, T-282               | v1.0 전 구현                     |
| G-035 | Telegram system outbox / target admin 운영면 부재                                  | T-258, T-260, T-286        | Sprint 6 계획 확정               |
| G-036 | provider health가 `unknown`으로 남지 않도록 provider tag 배선 필요                 | T-253, T-257               | T-253 일부 완료, Resend는 T-257  |
| G-037 | rate-limit store fail-closed / 429·503 가시성, abuse admin surface 부재            | T-282                      | v1.0 전 구현                     |
| G-038 | active alerts surface 부재                                                         | T-258, T-282, T-283        | Sprint 6 계획 확정               |
| G-039 | backup schedule due, restore dry-run verify, download, janitor, mirror status 부재 | T-267, T-259               | v0.2 RC 확인, Sprint 6 구현      |
| G-040 | runtime config, maintenance/read-only mode, feature flag 운영면 부재               | T-258, T-260               | Sprint 6 계획 확정               |
| G-041 | auth events / login history 운영 조회 부재                                         | T-281, T-283               | v1.0 전 구현                     |
| G-042 | app integrity가 orphan POI / curated import drift를 명시 근거로 가져야 함          | T-249, T-292               | T-249 완료, pagination 후속      |
| G-043 | external launch 전 threat model / penetration 1차 점검 부재                        | T-283                      | v1.0 전 완료                     |
| G-044 | mobile과 user-facing AI companion의 v1.0 포함/제외 범위 모호                       | T-284, T-285               | Sprint 6 scope gate              |

## 4. 최근 PR 사후 리뷰 후속

최근 2일 PR #265~#289 issue comment를 확인했다. #287~#289에는 bot reminder 외 별도
사람 리뷰 코멘트가 없었고, #265~#286의 actionable 후속은 아래 Task로 남긴다.

| ID    | 원천 PR | 후속                                                                              | 대응 Task    | 비고                            |
| ----- | ------- | --------------------------------------------------------------------------------- | ------------ | ------------------------------- |
| R-001 | #265    | WebSocket `4401` refresh tight loop 방지, retry jitter, 수동 재연결 UX            | T-289        | T-234 후속                      |
| R-002 | #265    | `tripRealtimeInvalidationKeys`를 실제 TanStack Query invalidation에 배선          | T-289        | TripDetail reload-only 한계     |
| R-003 | #266    | Trip conflict field whitelist drift, 409 envelope current row, dialog focus/Esc   | T-290        | T-287 day conflict와 별개       |
| R-004 | #271    | Dagster `run_failure_sensor`와 문서 현재형 drift 정리                             | T-291        | T-242/T-243 관련                |
| R-005 | #273    | ETL SQL statement integration/schema-compile smoke와 audit retention 정책 분리    | T-291, T-276 | compliance job 런타임 실패 방지 |
| R-006 | #274    | location archive 실제 실행 전 `log_id` 연속 prefix 경계로 archive 후보 산정       | T-276        | dry-run 이후 실행 gate          |
| R-007 | #283    | `/admin/integrity?source=all` pagination이 upstream issue를 굶기지 않게 수정      | T-292        | 운영 기본 뷰 결함               |
| R-008 | #283    | `app.data_integrity_violations` producer/upsert test 또는 read-ahead infra 문서화 | T-292        | persisted source 후속           |
| R-009 | #283    | Admin integrity action modal Esc/focus/overlay 접근성 보강                        | T-292        | UI 품질 후속                    |

## 5. 완료 기준

T-256 완료 기준:

- G-001~G-044가 하나 이상의 Task로 매핑돼 있다.
- R-001~R-009가 열린 후속 Task로 매핑돼 있다.
- `docs/tasks.md`, `docs/sprints/SPRINT-5.md`, `docs/sprints/SPRINT-6.md`,
  `docs/resume.md`, `docs/journal.md`가 이 문서를 같은 정본으로 참조한다.
- 본 문서는 실제 운영 도메인, IP, SSH target, credential, secret 값을 포함하지 않는다.
