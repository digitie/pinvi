# Email deliverability / provider tracking preflight

작성일: 2026-06-28

## 1. 목적

T-257의 산출물이다. Sprint 5에서 email outbox와 provider health 기반은 갖췄지만,
실제 운영에서 "메일이 발송 가능한가", "bounce/complaint가 다음 발송을 막는가",
"Resend 호출이 provider health에 남는가"는 아직 닫히지 않았다. 본 문서는 T-277
구현 전에 필요한 감사 결과와 구현 계약을 고정한다.

공식 문서 기준:

- Resend Domains: 발송하려면 소유 도메인을 추가하고 verified 상태로 만들어야 하며,
  API/CLI/dashboard로 domain 목록과 상태를 조회할 수 있다.
  <https://resend.com/docs/dashboard/domains/introduction>,
  <https://resend.com/docs/api-reference/domains/list-domains>
- Resend Webhooks: bounce/complaint 등 event를 webhook으로 받고, bounced 주소 제거,
  alert, 자체 저장소 보존에 활용할 수 있다. webhook은 at-least-once delivery이며
  중복과 out-of-order를 고려해야 한다.
  <https://resend.com/docs/webhooks/introduction>
- Resend `email.bounced`: 영구 반송 이벤트이며 payload의 `data.bounce`가 type/message를 담는다.
  <https://resend.com/docs/webhooks/emails/bounced>

## 2. 현재 구현 감사

| 영역                    | 현 상태                                                                                                                                  | gap                                                                                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Queue worker            | `apps/api/app/services/email_service.py`가 `app.email_queue`를 `FOR UPDATE SKIP LOCKED`로 drain한다.                                     | recipient suppression check 없이 발송한다.                                                                                                    |
| Resend send             | `_send_email_payload()`가 Resend Python SDK `resend.Emails.send`를 직접 호출한다.                                                        | `api_call_log.provider='resend'`로 남지 않는다. SDK 전역 `resend.api_key`도 service boundary가 약하다.                                        |
| Console mode            | `PINVI_RESEND_API_KEY`가 없으면 queue row는 만들고 console log만 남긴다.                                                                 | Admin deliverability 상태판이 API key 미설정, console mode, From domain drift를 한 화면에서 보여주지 않는다.                                  |
| Webhook signature       | `apps/api/app/webhooks/resend.py`가 Svix signature를 검증하고 production secret 미설정은 fail-closed한다.                                | processed `svix-id` dedupe가 없고, out-of-order event precedence가 없다.                                                                      |
| Webhook events          | `email.delivered`, `email.bounced`, `email.complained`가 `email_queue.status`를 갱신한다.                                                | `users.email_status` 또는 별도 suppression source를 갱신하지 않는다. `email.suppressed`, `email.failed`, `email.delivery_delayed`는 미처리다. |
| User status             | `app.users.email_status` 컬럼과 Admin user detail 표시가 있다.                                                                           | worker가 이 값을 읽지 않고, reset/해제 action도 없다.                                                                                         |
| Admin emails            | `/admin/emails`는 queue list와 resend trigger를 제공한다.                                                                                | domain verified/SPF/DKIM/DMARC/FROM 상태, webhook health, suppression count가 없다. resend action이 suppression을 무시한다.                   |
| T-239 ETL               | `pinvi_email_outbox`가 pending/backoff/stuck/failed/bounced/complained와 template 실패율을 PII 없이 집계한다.                            | deliverability 원인(domain/webhook/suppression/provider tracking)과 연결되지 않는다.                                                          |
| T-253 provider tracking | `kor_travel_map`, `kor_travel_map_admin`, `kor_travel_geo`, `telegram`, `google_oauth`는 `api_call_event_hooks` provider tag를 사용한다. | Resend SDK 경로는 추적되지 않는다. Dagster/system health probe는 별도 내부 probe라 provider-health 집계 대상에서 제외한다.                    |

## 3. T-277 구현 계약

### 3.1 Deliverability read model

`GET /admin/emails/deliverability` 또는 `/admin/email-deliverability`를 추가한다.

응답 후보:

- `resend_api_configured`: `PINVI_RESEND_API_KEY` 존재 여부만 boolean으로 반환한다. key 원문과 hint는 노출하지 않는다.
- `from_email`, `from_domain`: `PINVI_RESEND_FROM_EMAIL`에서 domain만 파싱한다.
- `domain_status`: Resend `GET /domains` 결과에서 `from_domain`과 일치하는 domain의 status.
  `verified`만 정상, `pending`/`not_started`/`failed`/`temporary_failure` 등은 degraded다.
- `sending_capability`: Resend domain capabilities가 있으면 sending 상태를 표시한다.
- `spf_dkim_dmarc`: Resend dashboard/domain records 기준으로 operational checklist를 보여준다.
  API가 DNS record 세부 상태를 안정적으로 주지 못하면 "manual check required"로 둔다.
- `webhook_signature_configured`, `webhook_unsigned_allowed`, `webhook_health`: secret 설정, 최근 webhook 처리 시각,
  최근 signature 실패 수, 최근 bounced/complained/suppressed count.
- `queue_health`: T-239 email outbox summary 재사용.
- `suppression_health`: `users.email_status` count와 별도 suppression table count.

### 3.2 Suppression source

현재 `users.email_status`만으로는 미가입 초대 이메일, 삭제 사용자, provider가 돌려준 수신자 단위
suppression을 표현하기 어렵다. T-277은 둘 중 하나를 명시적으로 선택한다.

- 최소안: `EmailQueue.user_id`가 있는 경우만 `users.email_status`를 갱신하고, 미가입 주소는 queue row status만 남긴다.
- 권장안: `app.email_suppressions`를 추가한다. normalized email hash, reason(`hard_bounce`/`complaint`/`manual`),
  provider event id, first/last seen, released_at, released_by, audit reason을 저장한다.

발송 worker는 다음 순서로 차단한다.

1. `EmailQueue.user_id`가 있고 `users.email_status != 'active'`면 발송하지 않고 terminal skip 상태로 둔다.
2. normalized recipient가 active suppression에 있으면 발송하지 않는다.
3. marketing template은 `marketing` consent가 없으면 발송하지 않는다.

### 3.3 Webhook event model

- `svix-id` 또는 Resend event id를 보관해 at-least-once 중복을 idempotent하게 무시한다.
- event `created_at`을 저장하고 out-of-order를 허용한다.
- status precedence를 정의한다. 예: `complained`/`bounced`/`suppressed`는 `delivered`보다 terminal이다.
- `email.bounced`, `email.complained`, `email.suppressed`, `email.failed`, `email.delivery_delayed`를 처리한다.
- hard bounce와 complaint는 suppression source를 갱신하고 admin audit을 남긴다.
- webhook signature 실패와 secret 미설정은 raw payload 없이 bounded count/alert로만 노출한다.

### 3.4 Resend provider tracking

Resend 호출은 `api_call_log`에 `provider='resend'`로 남겨야 한다.

우선순위:

1. Resend REST API를 감싼 `ResendClient`를 만들고 `httpx.AsyncClient` +
   `api_call_event_hooks(..., provider='resend')`를 사용한다.
2. SDK를 유지해야 한다면 `_send_email_payload()` 주변에서 `ApiCallLog`를 명시적으로 append한다.
   이 경우 endpoint는 `https://api.resend.com/emails`처럼 secret 없는 canonical endpoint만 저장한다.

T-253에서 이미 provider tag가 붙은 대상:

- `kor_travel_map`
- `kor_travel_map_admin`
- `kor_travel_geo`
- `telegram`
- `google_oauth`

T-257 기준 잔여:

- `resend`

## 4. Admin / test gate

T-277은 다음 검증을 포함한다.

- API integration:
  - unverified/missing domain → deliverability `degraded`
  - webhook hard bounce → queue terminal status + user/suppression 갱신
  - complaint → suppression + audit
  - duplicate `svix-id` → idempotent no-op
  - delivered after bounced → terminal status가 bounced/complained/suppressed에서 되돌아가지 않음
  - worker suppression hit → Resend send 미호출
- Admin mock e2e:
  - `/admin/email-deliverability` degraded/ok state
  - domain/FROM mismatch warning
  - suppression count와 reset action 잠금/사유
  - raw API key, webhook secret, raw provider payload 미노출
- Provider tracking:
  - 실제 send path 또는 mocked send path가 `api_call_log.provider='resend'`를 남긴다.
- Live gate:
  - N150 우선. N150 runner 불가 시 Windows fallback.
  - production에서는 read-only deliverability 상태 조회만 실행하고, webhook/send mutation은 staging gate로 분리한다.

## 5. T-257 완료 기준

- T-277이 구현해야 할 deliverability/suppression/provider tracking 계약이 문서화됐다.
- Resend 문서와 repo 구현 간 drift가 `docs/integrations/resend.md`에 반영됐다.
- `docs/tasks.md`, `docs/tasks-done.md`, Sprint 5 계획, `docs/resume.md`, `docs/journal.md`가
  T-257 완료와 다음 T-258을 가리킨다.
