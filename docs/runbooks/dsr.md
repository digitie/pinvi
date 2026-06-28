# DSR 권리행사 처리 런북

본 런북은 `/settings/dsr`, `/users/me/dsr-requests`, `/admin/dsr`, `app.dsr_requests`의
운영 절차다. 개인정보 열람 등 요구는 접수일 기준 10일 처리 due를 기본값으로 둔다. 2026-06-28
확인 기준: 국가법령정보센터 개인정보 보호법 시행령 제41조제4항은 열람 처리 기간을 10일로
정하고, 개인정보 포털과 개인정보보호위원회 안내도 열람·정정·삭제·처리정지 결과 회신 흐름을
제공한다.

## 상태 모델

| 상태             | 의미                                     | 다음 조치           |
| ---------------- | ---------------------------------------- | ------------------- |
| `received`       | 사용자가 `/settings/dsr` 또는 API로 접수 | CPO 본인 확인       |
| `identity_check` | CPO가 본인 확인 결과와 증적을 기록       | 처리 시작 또는 거절 |
| `processing`     | 자료 추출/정정/삭제/처리정지 검토 중     | 완료 또는 거절      |
| `completed`      | 결과 통지 완료                           | 없음                |
| `rejected`       | 거절 사유와 결과 통지 기록               | 없음                |
| `withdrawn`      | 사용자가 open 요청을 철회                | 없음                |

Open 상태는 `received`, `identity_check`, `processing`이다. `due_at < now()`이면 Admin
화면에서 overdue로 표시한다.

## 사용자 접수

- Web: `/settings/dsr`
- API:
  - `GET /users/me/dsr-requests?page_size=50`
  - `POST /users/me/dsr-requests`
  - `POST /users/me/dsr-requests/{request_id}/withdraw`

접수 행에는 원문 이메일을 저장하지 않는다. `requester_email_hash`와 `requester_email_masked`만
`app.dsr_requests`에 남기고, 결과 통지는 필요 시 `app.email_queue`의 `to_email`로 발송한다.

## CPO 처리

- Admin: `/admin/dsr`
- 조회: `GET /admin/dsr?status=&request_type=&overdue=&page_size=`
- 상태 조치:
  - `POST /admin/dsr/{request_id}/identity-check`
  - `POST /admin/dsr/{request_id}/process`
  - `POST /admin/dsr/{request_id}/complete`
  - `POST /admin/dsr/{request_id}/reject`

모든 상태 조치는 `cpo` 권한만 가능하며 `access_reason`이 필요하다. 권한 없으면 기존 Admin RBAC
정책과 같이 `404 RESOURCE_NOT_FOUND`로 숨긴다. 조치 결과는 `admin_audit_log`에
`resource_type='dsr_request'`, `action='dsr.*'`로 남긴다.

## 완료 / 거절 통지

`complete`와 `reject`는 `dsr_result_notice` email queue row를 만든다. DSR 행에는
`result_notice_hash`, `result_notice_email_id`, `result_summary`, `rejection_reason`,
`export_manifest`, `partial_response`를 남긴다.

`export_manifest`에는 파일명, masking field, 제외 사유 같은 bounded evidence만 둔다. 원문
export 파일이나 비밀번호, 운영 host, secret, 실제 외부 URL은 저장하지 않는다.

## 재시도와 장애

- `email_queue` 발송이 `suppressed`, `bounced`, `complained`, `failed`가 되면
  `/admin/emails`와 `/admin/emails/deliverability`에서 원인을 확인한다.
- 결과 통지 메일이 실패해도 `app.dsr_requests.status`는 되돌리지 않는다. CPO가 별도 채널 통지
  증적을 `evidence_attachment_id` 또는 `export_manifest`에 bounded reference로 보강한다.
- 10일 due가 임박하거나 초과한 요청은 `/admin/dsr?overdue=true`에서 우선 처리한다.

## 검증

- API integration: `tests/integration/test_dsr_requests_api.py`
- Web mock e2e: `admin-dsr.e2e.ts`, `settings-dsr.e2e.ts`
- 정적 검증: API ruff/mypy, `@pinvi/schemas`, `@pinvi/api-client`, `@pinvi/web` typecheck
