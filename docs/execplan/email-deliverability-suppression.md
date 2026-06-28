# Email deliverability / suppression enforcement 실행 기록

작성일: 2026-06-28

## 1. 범위

T-277은 T-257 preflight의 구현 작업이다. 목표는 Resend 발송 경로가 실제 운영에서 다음
조건을 만족하는 것이다.

- 발송 전 `users.email_status`, provider suppression source, `marketing` consent를 확인한다.
- Resend webhook은 at-least-once delivery를 전제로 event id / `svix-id` 중복을 무시한다.
- hard bounce / complaint / provider suppression은 다음 발송을 막는다.
- Admin은 `/admin/emails`에서 deliverability, webhook, queue, suppression 상태를 볼 수 있다.
- Resend REST 호출은 `api_call_log.provider='resend'`로 남는다.

## 2. 구현

- DB: `app.email_suppressions`, `app.resend_webhook_events`를 추가하고
  `app.email_queue.status`에 `delivery_delayed`, `suppressed`를 추가했다.
- Worker: `process_pending_email_batch()`가 발송 전 suppression decision을 계산한다. 차단되면
  Resend 호출 없이 queue row를 terminal 상태로 바꾸고 `last_error='suppressed:<reason>'`을 남긴다.
- Resend client: Python SDK 직접 호출을 `httpx.AsyncClient` 기반 `ResendClient`로 바꿨다.
  `api_call_event_hooks(..., provider='resend')`를 사용해 provider tracking을 남긴다.
- Webhook: `email.delivered`, `email.delivery_delayed`, `email.failed`, `email.bounced`,
  `email.complained`, `email.suppressed`를 처리한다. `bounced` / `complained` / `suppressed`는
  `delivered`보다 우선하며, 같은 event id는 no-op이다.
- Admin: `GET /admin/emails/deliverability`와 `/admin/emails` 상태판을 추가했다.

## 3. 검증

- API integration:
  - worker suppression hit는 Resend 호출 없이 terminal 상태로 남는다.
  - webhook hard bounce는 queue, user email status, suppression source를 갱신한다.
  - duplicate event는 idempotent no-op이다.
  - delivered after bounced는 terminal 상태를 되돌리지 않는다.
  - deliverability API는 degraded/config/count를 raw secret 없이 반환한다.
  - Resend client는 `api_call_log.provider='resend'`를 남긴다.
- Web mock e2e:
  - `/admin/emails` deliverability 상태판과 `suppressed` filter를 렌더링한다.

## 4. 후속

- Resend 테스트 모드 key를 사용하는 staging live 검증.
- manual suppression release action과 release audit UI.
- 개인정보처리방침/위탁 고지 문서의 최종 법무 리뷰.
