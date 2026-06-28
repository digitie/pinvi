# Resend 이메일 통합

Pinvi transactional 이메일은 Resend 사용. 회원가입 verify / 비밀번호 재설정 /
trip 초대 / 공유 링크 알림 / 기타 시스템 알림. SPEC V8 G-6 / `docs/spec/v8/02-backend.md` §4.3.

## 1. Resend 계정 / 도메인 인증

### 1.1 무료 티어

- 월 3,000 통 / 일 100 통 / 1 도메인 / 30일 보관 (Resend 변경 가능)
- 결제 추가 시 Team plan ($26~$80) — 월 50K~250K 이벤트

### 1.2 도메인 인증 (필수)

Resend 대시보드에서 발송 도메인 등록 → DNS 3 레코드 추가:

| Type        | Host                                       | Value                                                        |
| ----------- | ------------------------------------------ | ------------------------------------------------------------ |
| TXT (SPF)   | `send.pinvi.example.com`                   | `v=spf1 include:amazonses.com ~all`                          |
| TXT (DKIM)  | `resend._domainkey.send.pinvi.example.com` | Resend 제공                                                  |
| TXT (DMARC) | `_dmarc.pinvi.example.com`                 | `v=DMARC1; p=quarantine; rua=mailto:dmarc@pinvi.example.com` |

Resend "verified" 상태 확인 후 발송 시작.

`From` 주소: `Pinvi <noreply@send.pinvi.example.com>` — **발송 전용 서브도메인**
권장 (메인 도메인 평판 보호).

> T-257 감사(2026-06-28): Resend 공식 문서 기준 도메인 verified 상태, SPF/DKIM/DMARC,
> webhook event 중복/순서 보장 부재를 T-277 구현 계약으로 연결했다. 현재 repo는 queue worker,
> Svix 서명 검증, queue 상태 갱신, `/admin/emails` queue 화면까지 구현되어 있고,
> suppression enforcement, deliverability 상태판, Resend provider tracking은 T-277 잔여다.

## 2. 환경변수

| 환경변수                                    | 예시                                                                 |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `PINVI_RESEND_API_KEY`                      | `re_...`                                                             |
| `PINVI_RESEND_FROM_EMAIL`                   | `Pinvi <noreply@send.pinvi.example.com>`                             |
| `PINVI_RESEND_TIMEOUT_SECONDS`              | `5`                                                                  |
| `PINVI_RESEND_WEBHOOK_SECRET`               | (Svix secret)                                                        |
| `PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED`       | `false` 기본. 로컬 개발에서만 `true`                                 |
| `PINVI_EMAIL_OUTBOX_WORKER_ENABLED`         | `true`                                                               |
| `PINVI_EMAIL_OUTBOX_DRAIN_INTERVAL_SECONDS` | `5`                                                                  |
| `PINVI_EMAIL_OUTBOX_BATCH_SIZE`             | `50`                                                                 |
| `PINVI_WEB_BASE_URL`                        | dev `http://localhost:12805`, production `https://pinvi.example.com` |
| `PINVI_EMAIL_VERIFICATION_PATH`             | `/verify-email`                                                      |

미설정 시 (`PINVI_RESEND_API_KEY` 빈값) → "콘솔 출력 모드" — `email_queue`에
적재되지만 발송 X, stdout에 렌더링 결과 출력. 가입은 성공하지만
`verification_email_dispatched=false`.

## 3. 큐 구조

`app.email_queue` (SPEC V8 M-6 + `docs/data-model.md`):

| 컬럼                                                                  | 비고                                                                                      |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `email_id` (uuid PK)                                                  | webhook `X-Entity-Ref-ID` 값                                                              |
| `user_id`                                                             | nullable. 미가입 초대나 삭제 사용자 row는 없을 수 있다.                                   |
| `to_email`                                                            | 수신자 이메일                                                                             |
| `template`                                                            | 현재 `verify_email` / `reset_password` / `trip_invite` + generic fallback                 |
| `subject`                                                             | 발송 제목                                                                                 |
| `payload` (jsonb)                                                     | inline renderer 입력값 (`verify_url`, `expires_in_hours`, `reset_url`, `trip_title`, ...) |
| `status`                                                              | `pending` / `sent` / `delivered` / `bounced` / `complained` / `failed`                    |
| `resend_id`                                                           | Resend 응답 `id` (deep link용)                                                            |
| `bounce_type`                                                         | `hard` / `soft`                                                                           |
| `attempts` (int)                                                      | retry 횟수                                                                                |
| `last_error`                                                          | 마지막 실패 메시지                                                                        |
| `scheduled_at`, `created_at`, `sent_at`, `delivered_at`, `bounced_at` |                                                                                           |

Worker:

- PostgreSQL `SKIP LOCKED` 패턴 (Redis 없음 — SPEC V8 C장)
- FastAPI lifespan에서 `email_outbox_worker_lifespan` 단일 task로 실행
- 5초 폴링 + 50 row batch
- 실패 시 `attempts + 1`, exponential backoff (30s / 5m / 30m / 1h / 4h)
- `attempts >= 5` → `status='failed'` + Sentry alert
- 여러 API worker가 동시에 떠도 `FOR UPDATE SKIP LOCKED`로 같은 row 중복 발송을 막는다.

## 4. 발송 코드

현재 구현은 `apps/api/app/services/email_service.py`가 담당한다.

- `enqueue_verification_email`, `enqueue_password_reset_email`, `enqueue_trip_invite_email`이
  `app.email_queue`에 pending row를 만든다.
- `process_pending_email_batch()`가 `FOR UPDATE SKIP LOCKED`로 row를 claim하고,
  `_send_email_row()` → `_send_email_payload()` 순서로 발송한다.
- `PINVI_RESEND_API_KEY`가 없으면 console mode로 동작하고, queue row는 `sent`로 진행될 수
  있지만 실제 provider 호출은 하지 않는다.
- 실제 발송은 현재 Resend Python SDK `resend.Emails.send`를 직접 호출한다.
- `X-Entity-Ref-ID` header에는 `EmailQueue.email_id`를 넣어 webhook이 queue row를 찾는다.

T-277 잔여:

- 발송 전 `users.email_status`와 suppression source를 확인해 hard bounce/complaint 주소를
  차단한다.
- Resend 호출을 `api_call_log.provider='resend'`로 남긴다. 권장 구현은 Resend REST API를
  감싼 `ResendClient` + `httpx.AsyncClient` + `api_call_event_hooks(..., provider='resend')`다.
- SDK를 유지한다면 SDK 호출 주변에서 canonical endpoint와 provider tag를 수동 기록한다.

## 5. 이메일 템플릿

현재는 별도 `emails/*.tsx` 패키지가 아니라 백엔드 inline HTML renderer를 사용한다.
`apps/api/app/services/email_service.py`의 `_render_template()`이 아래 템플릿을 처리한다.

- `verify_email` — 회원가입 인증
- `reset_password` — 비밀번호 재설정
- `trip_invite` — 동반자 초대
- 기타 template — generic HTML fallback

React Email 또는 정적 HTML 빌드가 필요해지면 별도 Task/ADR로 도입한다. 이 문서의
deliverability/suppression 요구사항은 현재 inline renderer에도 그대로 적용한다.

## 6. Webhook (`POST /webhooks/resend`)

`PINVI_RESEND_WEBHOOK_SECRET`이 설정된 환경에서는 Resend/Svix 서명 검증을 통과한
요청만 처리한다. secret이 비어 있을 때 서명 없는 webhook은
`PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED=true`이고 환경이 `development` / `dev` /
`local` / `test` / `testing`인 경우에만 허용한다. 기본값은 `false`이므로
`PINVI_ENVIRONMENT` 누락으로 기본 `development`가 적용되어도 webhook은 열리지 않는다.
그 외 환경에서 secret이 비어 있거나 잘못된 형식이면
`503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`로 fail-closed한다.

검증 헤더:

- `svix-id`
- `svix-timestamp`
- `svix-signature`

구현 기준:

- 서명은 JSON 파싱 전 raw body 기준으로 검증한다.
- `whsec_` secret의 표준 base64 body를 key로 사용해
  `svix-id.svix-timestamp.raw_payload` 형식의 바이트열을 HMAC-SHA256으로 서명한다.
  URL-safe base64 변형은 secret 설정 오류로 본다.
- `svix-signature`의 `v1,<base64>` 값 중 하나라도 일치하면 통과한다.
- timestamp 허용 오차는 300초다.
- 서명 검증 실패 시 `401 WEBHOOK_SIGNATURE_INVALID`.
- secret 미설정 또는 secret 형식 오류 시 `503 WEBHOOK_SIGNATURE_NOT_CONFIGURED`.

현재 처리 대상 이벤트:

| 이벤트             | 처리                                                       |
| ------------------ | ---------------------------------------------------------- |
| `email.delivered`  | `app.email_queue.status='delivered'`, `delivered_at=now()` |
| `email.bounced`    | `status='bounced'`, `bounced_at=now()`, `bounce_type` 저장 |
| `email.complained` | `status='complained'`                                      |

`X-Entity-Ref-ID` 헤더가 payload `data.headers`에 없으면 멱등 성공(`{"ok": true}`)으로
끝내고 상태를 갱신하지 않는다.

T-277 잔여:

- `svix-id` 또는 Resend event id dedupe를 저장해 at-least-once delivery 중복을 무시한다.
- event `created_at` 기준 out-of-order precedence를 둔다. 예: `bounced`/`complained`는
  `delivered`보다 우선인 terminal 상태다.
- `email.suppressed`, `email.failed`, `email.delivery_delayed`를 처리한다.
- hard bounce와 complaint는 `users.email_status` 또는 별도 suppression source를 갱신하고
  admin audit을 남긴다.

## 7. 발송 차단 정책

아래는 T-277 목표 정책이다. T-257 감사 기준 현재 worker는 아직 이 정책을 강제하지 않는다.

- `users.email_status = 'bounced'` (hard bounce) → 모든 발송 차단. 사용자에게
  "이메일 주소를 다시 확인해 주세요" 안내
- `users.email_status = 'complained'` (스팸 신고) → 모든 발송 차단 + admin audit
- `app.user_consents` 에서 `marketing` 동의 철회 → `template != 'marketing*'`만

미가입 초대, 삭제 사용자, provider 단위 suppression을 표현하려면 `users.email_status`만으로는
부족하다. T-277 권장안은 `app.email_suppressions`를 추가해 normalized email hash, reason,
provider event id, first/last seen, release audit을 보관하는 것이다.

## 8. 개발 / 스테이징 / 운영

| 환경                              | 동작                                                  |
| --------------------------------- | ----------------------------------------------------- |
| dev (`PINVI_RESEND_API_KEY` 빈값) | 콘솔 출력 모드. queue 적재만                          |
| dev (실제 키)                     | 실제 발송 — 본인 이메일로만 테스트                    |
| staging                           | Resend "테스트 모드" API 키 — 실제 발송 X, API 흐름만 |
| 운영                              | 실제 발송                                             |

E2E 테스트는 `mailpit` 컨테이너 옵션 또는 `email_queue.status` 검사로.

## 9. Admin 페이지

`docs/api/admin.md` §2 + `docs/spec/v8/04-admin.md` M-2 `/admin/emails`.

현재 구현:

- `/admin/emails` 큐 목록 (status filter, limit)
- 행 액션: "재발송" (row를 pending으로 되돌림)

T-277 목표:

- `/admin/emails/deliverability` 또는 `/admin/email-deliverability` 상태판
- Resend API key configured 여부, `From` domain, domain status, SPF/DKIM/DMARC checklist
- webhook signature configured/unsigned opt-in, 최근 webhook 처리 상태
- pending/backoff/stuck/failed/bounced/complained queue health
- `users.email_status`와 suppression count, reset/release action의 audit trail

## 10. AI agent 구현 체크리스트

- [x] `apps/api/app/services/email_service.py` (enqueue + SKIP LOCKED batch worker)
- [x] `apps/api/app/webhooks/resend.py` (Svix 서명 검증 + queue 상태 갱신)
- [x] backend inline HTML 템플릿 3종 (`verify_email`, `reset_password`, `trip_invite`) + generic fallback
- [x] `app.email_queue` Alembic (Sprint 1 또는 2)
- [x] `app.users.email_status` 컬럼 (`active` / `bounced` / `complained`)
- [x] FastAPI lifespan email outbox worker (`email_outbox_worker_lifespan`)
- [x] Admin `/admin/emails` queue page
- [ ] Resend provider tracking (`api_call_log.provider='resend'`)
- [ ] suppression enforcement (`users.email_status` 또는 `app.email_suppressions`)
- [ ] deliverability Admin 상태판
- [ ] webhook event dedupe/out-of-order precedence
- [ ] Resend "테스트 모드" 키로 staging 검증
- [ ] `docs/compliance/pipa.md`에 위탁자 명시
