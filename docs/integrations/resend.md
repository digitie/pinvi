# Resend 이메일 연동

TripMate는 회원가입 이메일 인증 메일 발송에 Resend Email API를 사용한다. 현재 구현은 `POST /auth/register`에서 인증 token을 만들고, Resend 설정이 있을 때 인증 메일을 발송한다. 사용자가 `/verify-email?token=...` 화면을 열면 프론트엔드가 `POST /auth/verify-email`을 호출해 계정을 `active`로 전환한다.

관련 코드:

- `apps/api/app/services/email_delivery.py`
- `apps/api/app/api/routes/auth.py`
- `apps/web/app/verify-email/page.tsx`

## 현재 플랜 기준

2026-05-13 기준 Resend 공식 가격 페이지의 Free 플랜은 `$0/mo`, 월 3,000 email, 일 100 email, 1개 domain, 30일 data retention을 제공한다. 운영 전에는 [Resend pricing](https://resend.com/pricing)을 다시 확인한다.

## 필요한 Resend 준비물

1. Resend 계정과 team을 준비한다.
2. 발송 domain을 추가한다. Resend는 소유한 domain 사용을 요구하며, `mail.example.com` 같은 발송용 subdomain을 권장한다. DNS에는 Resend가 제시하는 SPF, DKIM record를 추가하고, DMARC는 선택적으로 추가한다. 상세 기준은 [Managing Domains](https://resend.com/docs/dashboard/domains/introduction)를 따른다.
3. 발신 주소를 정한다. 예: `TripMate <no-reply@mail.example.com>`.
4. API key를 만든다. 회원가입 인증 메일 발송만 필요하므로 가능하면 `Sending access`와 해당 domain 제한을 사용한다. API key는 생성 시 한 번만 볼 수 있으므로 바로 secret store나 `.env`에 저장한다. API key 관리는 [Resend API keys](https://resend.com/docs/dashboard/api-keys/introduction)를 따른다.
5. API 호출은 `https://api.resend.com/emails`에 `Authorization: Bearer re_...` header를 붙여 수행한다. Resend는 직접 HTTP 요청에 `User-Agent`도 요구하므로 TripMate는 `TripMate API/<version>` header를 보낸다. Email API body의 핵심 필드는 `from`, `to`, `subject`, `html` 또는 `text`이며 상세는 [Send Email](https://resend.com/docs/api-reference/emails/send-email)을 따른다.

## TripMate 환경 변수

API 설정은 `TRIPMATE_` prefix를 사용한다.

| 이름 | 필수 | 예시 | 설명 |
| --- | --- | --- | --- |
| `TRIPMATE_RESEND_API_KEY` | 운영 필수 | `re_xxxxxxxxx` | Resend API key. 서버에만 둔다. |
| `TRIPMATE_RESEND_FROM_EMAIL` | 운영 필수 | `TripMate <no-reply@mail.example.com>` | 인증 메일 발신자. Resend에서 검증된 domain을 사용한다. |
| `TRIPMATE_WEB_BASE_URL` | 필수 | `https://tripmate.example.com` | 인증 링크 base URL. 로컬 기본값은 `http://localhost:3001`이다. |
| `TRIPMATE_EMAIL_VERIFICATION_PATH` | 선택 | `/verify-email` | 인증 링크 path. |
| `TRIPMATE_RESEND_TIMEOUT_SECONDS` | 선택 | `5` | Resend API HTTP timeout. |

인증 관련 JWT 설정:

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `TRIPMATE_JWT_SECRET_KEY` | `tripmate-local-jwt-secret-change-me` | 운영에서는 반드시 긴 random secret으로 교체한다. |
| `TRIPMATE_ACCESS_TOKEN_MINUTES` | `15` | access token 만료 시간. |
| `TRIPMATE_REFRESH_TOKEN_DAYS` | `7` | refresh token 만료 일수. |

## 로컬 개발 동작

`TRIPMATE_RESEND_API_KEY` 또는 `TRIPMATE_RESEND_FROM_EMAIL`이 없으면 회원가입은 성공하지만 메일은 발송하지 않고 응답의 `verification_email_dispatched`가 `false`가 된다. 이 경우 원문 인증 token은 DB에 저장하지 않으므로 로컬에서 실제 인증 링크를 확인하려면 Resend 설정을 넣어야 한다. 메일 발송 없이 테스트 계정을 활성화해야 하면 관리자 사용자 화면에서 이메일 인증 완료와 `active` 상태를 수동으로 설정한다.

## 실패 처리

- Resend 설정이 누락된 경우: 회원가입은 유지하고 `verification_email_dispatched=false`를 반환한다.
- Resend API가 HTTP 오류를 반환하거나 timeout이 발생한 경우: `POST /auth/register`는 `503 Service Unavailable`을 반환하고 가입 transaction은 commit하지 않는다.
- 인증 token이 만료, 재사용, 불일치 상태인 경우: `POST /auth/verify-email`은 `422 Unprocessable Entity`를 반환한다.

## 운영 체크리스트

- Free 플랜의 일 100 email 제한을 초과할 가능성이 있으면 유료 플랜 또는 별도 제한/큐잉을 검토한다.
- API key는 브라우저 코드, 로그, Git에 노출하지 않는다.
- 운영 API key는 `Sending access`와 domain scope를 우선 사용한다.
- DNS 변경 후 Resend dashboard에서 domain status가 `verified`인지 확인한다.
- `TRIPMATE_WEB_BASE_URL`이 실제 public HTTPS URL인지 확인한다.
- 가입 폭주와 재발송 기능을 넣을 때는 rate limit, idempotency key, audit log를 함께 설계한다.
