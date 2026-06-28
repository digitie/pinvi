# Legal/Ops implementation prep gate

작성일: 2026-06-28

## 1. 목적

T-258의 산출물이다. T-256 crosswalk는 legal/ops 리뷰 gap을 Task 번호에 매핑했고,
T-257은 email deliverability/suppression 계약을 분리했다. 본 문서는 Sprint 6 진입 시
T-275~T-286을 구현 가능한 단위로 확정하고, `v1.0.0` release gate가 확인해야 할
공통 상태, runbook, 테스트, sign-off 기준을 고정한다.

공식 기준 확인:

- 개인정보보호위원회 개인정보 유출신고제도: 신고 대상이 되는 유출은 72시간 이내 신고,
  신고 내용에는 정보주체 통지 여부, 유출 항목·규모, 경위, 피해 최소화 조치, 구제절차,
  담당자 연락처가 포함된다. <https://www.pipc.go.kr/np/default/page.do?mCode=D030040000>
- 개인정보 보호법 시행령 제41조: 개인정보 열람 요구 처리기간은 10일이다.
  <https://www.law.go.kr/LSW//lsLawLinkInfo.do?chrClsCd=010202&lsId=011468&lsJoLnkSeq=900077172&print=print>
- 개인정보보호위원회 개인정보 열람 등 요구정책: 열람, 정정·삭제, 처리정지 청구는
  본인확인, 범위 확인, 제한사항 검토, 결과 통지 흐름을 가진다.
  <https://www.pipc.go.kr/np/default/page.do?mCode=D030010000>

주의: 이 문서는 구현·운영 기준이며 법률 자문이 아니다. T-274 release 전 변호사/CPO sign-off에서
법령·고시 최신성을 다시 확인한다.

## 2. T-258 결정

1. `KISA 60일 report` 표현은 폐기한다. Sprint 6 문서는 개인정보보호위원회/KISA 유출 신고
   due date를 `incident_detected_at + 72h` 기준으로 표시한다.
2. `CPO 30분 review`는 법정 기한이 아니라 Pinvi 내부 운영 SLA다. UI에는 내부 triage due와
   외부 신고/통지 due를 분리해서 보여준다.
3. DSR 열람/정정·삭제/처리정지 workflow는 기본 처리 due를 10일로 잡고, 거절·연기·부분 처리도
   결과 통지와 이의제기 안내를 가진다.
4. `v1.0.0` 기본 범위는 Web/API/Admin 운영 출시다. `apps/mobile`은 활성 track이지만 v1.0
   필수 release gate에서 제외하고, user-facing AI companion도 제외한다.
5. legal/ops 구현은 `/admin/*` 화면만으로 닫지 않는다. 각 Task는 API, UI, state transition,
   audit/evidence, runbook, mock/live or staging test, legal sign-off 항목을 함께 가져야 한다.

## 3. Sprint 6 구현 매트릭스

| Task  | 구현 표면                                                             | 상태 모델 / due date                                                                        | 증거 / 감사                                                                           | 테스트 gate                                                                 |
| ----- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| T-275 | `/admin/incidents`, `app.security_incidents`, CPO notification        | `detected` → `triage` → `notification_decision` → `reported` → `closed`; CPO 30분, 신고 72h | `admin_audit_log`, notification payload hash, KISA/PIPC 접수번호, evidence attachment | API state transition, CPO RBAC, notification/send mock, staging incident    |
| T-276 | `/admin/retention`, retention execute API, kill-switch                | `dry_run` → `approved` → `executing` → `completed`/`failed`/`rolled_back`                   | candidate snapshot, execution batch id, before/after count, chain bridge result       | dry-run vs execute, kill-switch, rollback evidence, location 6개월 archive  |
| T-277 | `/admin/email-deliverability`, Resend webhook/suppression enforcement | domain `ok/degraded`, webhook `healthy/degraded`, suppression `active/released`             | `api_call_log.provider='resend'`, suppression row, webhook event id, audit release    | duplicate webhook, out-of-order terminal status, worker suppression no-send |
| T-278 | `/admin/dsr`, user self-service request, CPO processing               | `received` → `identity_check` → `processing` → `completed`/`rejected`/`withdrawn`; 10일     | request form, identity proof metadata, result notice, export manifest                 | access/correction/delete/suspend SLA, partial/reject notice                 |
| T-279 | `/admin/moderation`, report intake, takedown/restore                  | `reported` → `reviewing` → `hidden`/`removed`/`restored`/`appealed`                         | report evidence, target snapshot, access reason, actor audit                          | report→hide→restore, share-link disable, attachment takedown                |
| T-280 | `/admin/rbac`, permission matrix, role grant/revoke                   | `grant_requested` → `active` → `revoked`; role-change session revoke                        | before/after roles, requester/approver, access token version, last-admin guard        | admin/operator/cpo matrix, last admin block, session invalidation           |
| T-281 | `/admin/users/{id}/lifecycle`, user self-delete                       | `active` → `disabled`/`pending_delete` → `deleted`/`reactivated`                            | lifecycle reason, forced logout ids, reset token id, retention link                   | force verify/reset/logout, disable/reactivate, self-delete conflict         |
| T-282 | `/admin/abuse`, rate-limit buckets, override/blocklist                | `observed` → `blocked`/`allowed` → `expired`; fail-closed visibility                        | bucket snapshot, override TTL, requester, rollback                                    | 429/503 visibility, override TTL, suspicious activity query                 |
| T-283 | threat model / penetration pass                                       | finding `blocking`/`follow_up`/`accepted_risk`                                              | threat model doc, test result, owner, due task                                        | auth/session/MCP/share/rate-limit/storage/admin negative tests              |
| T-284 | mobile v1.0 scope gate                                                | `excluded_from_v1` unless explicit user approval                                            | release note text, Sprint M-1 pointer                                                 | release checklist grep, no implicit mobile blocker                          |
| T-285 | AI companion v1.0 scope gate                                          | `user_facing_excluded`; client contract/Admin status only                                   | ADR-020 link, `kor-travel-concierge` boundary, redaction note                         | release checklist grep, no user-facing AI route in v1 gate                  |
| T-286 | cross-track review gap closure                                        | each G/R item `closed`/`sprint6`/`external_repo`/`accepted_exclusion`                       | PR/test/runbook link per gap                                                          | G-001~G-044 and R-001~R-009 coverage audit                                  |

## 4. 공통 구현 규칙

- 모든 legal/ops mutation은 `access_reason`과 actor role을 요구한다.
- CPO 전용 route는 존재 자체를 숨기는 404 정책을 유지하되, 내부 audit에는 denied event를 남긴다.
- 상태 변경은 append-only evidence를 남긴다. 원문 PII payload는 저장하지 않고 hash, bounded summary,
  storage object reference로 분리한다.
- Admin table은 due date, overdue, owner, next action을 한 화면에서 보여준다.
- destructive action은 precheck, confirm phrase, dry-run preview, rollback/undo 가능성 설명을 가진다.
- API response와 admin log에는 secret, token, raw provider payload, unmasked email list를 노출하지 않는다.
- live e2e는 read-only를 기본으로 하고, mutation은 staging flag와 cleanup prefix를 요구한다.

## 5. Runbook checklist

Sprint 6 구현 PR은 아래 runbook 또는 동등 문서 갱신을 포함한다.

| Task        | runbook / 문서                                                                                             | 필수 체크리스트                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| T-275       | `docs/runbooks/security-incidents.md`, `docs/compliance/pipa.md`                                           | incident 생성 기준, CPO 30분 triage, 72시간 신고/통지 due, evidence, closing checklist       |
| T-276       | `docs/runbooks/retention-execution.md`, `docs/compliance/lbs-act.md`, `docs/architecture/user-location.md` | dry-run/execute 차이, kill-switch, location 6개월 archive/delete, chain bridge, rollback     |
| T-277       | `docs/integrations/resend.md`, `docs/execplan/email-deliverability-provider-preflight.md`                  | domain verified, SPF/DKIM/DMARC, webhook health, suppression release, provider tracking      |
| T-278       | `docs/runbooks/dsr.md`, `docs/compliance/pipa.md`                                                          | 접수, 본인확인, 10일 due, 결과 통지, 거절/부분 처리, export masking                          |
| T-279       | `docs/runbooks/content-moderation.md` 또는 Sprint 6 동등 문서                                              | 신고 접수, 임시 숨김, takedown, restore, appeal, share-link disable                          |
| T-280~T-281 | `docs/architecture/admin-rbac.md`, `docs/runbooks/admin.md`                                                | role matrix, grant/revoke, last admin block, forced logout/reset, self-delete/retention 충돌 |
| T-282~T-283 | `docs/runbooks/admin.md`, threat model 문서                                                                | rate-limit fail-closed, abuse override, penetration finding 분류, accepted risk 승인         |
| T-284~T-285 | `docs/sprints/SPRINT-6.md`, `CHANGELOG.md`, release notes                                                  | mobile 제외 문구, user-facing AI companion 제외 문구, 별도 track 링크                        |
| T-286       | `docs/execplan/legal-ops-review-gap-crosswalk.md`                                                          | G-001~G-044, R-001~R-009 각각 구현 PR/test/runbook 링크 또는 명시적 제외 사유                |

## 6. Release gate

T-274 `v1.0.0` release 전 아래를 모두 확인한다.

- T-275~T-282의 API/UI/runbook/test가 완료됐다.
- T-283 threat model 결과에 `blocking` finding이 남아 있지 않다.
- T-284/T-285 제외 범위가 `CHANGELOG.md`, GitHub Release notes, Sprint 6 종료 문서에 같은 문구로 들어간다.
- PIPA/LBS/법무 4문서 sign-off가 T-275~T-282 운영 표면을 포함한다.
- N150 우선 smoke/live gate를 실행하고, N150 Playwright가 불가한 경우만 Windows runner fallback을 기록한다.
- 운영 도메인, IP, SSH target, credential, secret 값은 추적 문서에 들어가지 않는다.

## 7. T-258 완료 기준

- T-275~T-286의 구현 표면, 상태 모델, 증거, 테스트 gate가 누락 없이 매핑됐다.
- 기존 `KISA 60일 report` 문구가 `72시간 신고` 기준으로 정정됐다.
- Sprint 6 DoD와 release checklist에 legal/ops sign-off, mobile 제외, user-facing AI companion 제외가 명시됐다.
- `docs/tasks.md`, `docs/tasks-done.md`, Sprint 5/6 문서, `docs/resume.md`, `docs/journal.md`가
  T-258 완료와 다음 T-259를 가리킨다.
