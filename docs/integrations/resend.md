# Resend 이메일 통합

TripMate transactional 이메일은 Resend 사용. 회원가입 verify / 비밀번호 재설정 /
trip 초대 / 공유 링크 알림 / 기타 시스템 알림. SPEC V8 G-6 / `docs/spec/v8/02-backend.md` §4.3.

## 1. Resend 계정 / 도메인 인증

### 1.1 무료 티어

- 월 3,000 통 / 일 100 통 / 1 도메인 / 30일 보관 (Resend 변경 가능)
- 결제 추가 시 Team plan ($26~$80) — 월 50K~250K 이벤트

### 1.2 도메인 인증 (필수)

Resend 대시보드에서 발송 도메인 등록 → DNS 3 레코드 추가:

| Type | Host | Value |
|------|------|-------|
| TXT (SPF) | `send.trip.example.com` | `v=spf1 include:amazonses.com ~all` |
| TXT (DKIM) | `resend._domainkey.trip.example.com` | Resend 제공 |
| TXT (DMARC) | `_dmarc.trip.example.com` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@trip.example.com` |

Resend "verified" 상태 확인 후 발송 시작.

`From` 주소: `TripMate <noreply@send.trip.example.com>` — **발송 전용 서브도메인**
권장 (메인 도메인 평판 보호).

## 2. 환경변수

| 환경변수 | 예시 |
|----------|------|
| `TRIPMATE_RESEND_API_KEY` | `re_...` |
| `TRIPMATE_RESEND_FROM_EMAIL` | `TripMate <noreply@send.trip.example.com>` |
| `TRIPMATE_RESEND_TIMEOUT_SECONDS` | `5` |
| `TRIPMATE_RESEND_WEBHOOK_SECRET` | (Svix secret) |
| `TRIPMATE_RESEND_WEBHOOK_ALLOW_UNSIGNED` | `false` 기본. 로컬 개발에서만 `true` |
| `TRIPMATE_WEB_BASE_URL` | dev `http://localhost:12505`, production `https://tripmate.digitie.mywire.org` |
| `TRIPMATE_EMAIL_VERIFICATION_PATH` | `/verify-email` |

미설정 시 (`TRIPMATE_RESEND_API_KEY` 빈값) → "콘솔 출력 모드" — `email_queue`에
적재되지만 발송 X, stdout에 렌더링 결과 출력. 가입은 성공하지만
`verification_email_dispatched=false`.

## 3. 큐 구조

`app.email_queue` (SPEC V8 M-6 + `docs/data-model.md`):

| 컬럼 | 비고 |
|------|------|
| `id` (uuid PK) | |
| `to_email` (CITEXT) | |
| `template` | `verify_email` / `reset_password` / `trip_invite` / `share_link_notice` / `password_changed` / `weekly_digest`(v2) |
| `payload` (jsonb) | react-email props (`verify_url`, `expires_in_hours`, ...) |
| `status` | `pending` / `sent` / `delivered` / `bounced` / `complained` / `failed` |
| `resend_id` | Resend 응답 `id` (deep link용) |
| `bounce_type` | `hard` / `soft` |
| `attempts` (int) | retry 횟수 |
| `last_error` | 마지막 실패 메시지 |
| `created_at`, `sent_at`, `delivered_at`, `bounced_at` | |

Worker:

- PostgreSQL `SKIP LOCKED` 패턴 (Redis 없음 — SPEC V8 C장)
- 5초 폴링 + 50 row batch
- 실패 시 `attempts + 1`, exponential backoff (30s / 5m / 30m / 1h / 4h)
- `attempts >= 5` → `status='failed'` + Sentry alert

## 4. 발송 코드

```python
# apps/api/app/services/email_service.py
import resend
from app.core.config import settings

resend.api_key = settings.tripmate_resend_api_key

async def enqueue_verification_email(user_id: UUID, email: str, token: str):
    await db.execute(
        """INSERT INTO app.email_queue
           (id, to_email, template, payload, status, created_at)
           VALUES (:id, :email, 'verify_email', :payload, 'pending', now())""",
        {
            "id": uuid4(),
            "email": email,
            "payload": json.dumps({
                "verify_url": f"{settings.tripmate_web_base_url}/verify-email?token={token}",
                "expires_in_hours": 24,
                "user_id": str(user_id),
            }),
        },
    )

async def process_queue():
    while True:
        rows = await db.fetch_all("""
            SELECT * FROM app.email_queue
            WHERE status = 'pending' AND scheduled_at <= now()
            ORDER BY created_at
            LIMIT 50
            FOR UPDATE SKIP LOCKED
        """)
        for row in rows:
            try:
                html = render_react_email(row.template, row.payload)
                response = resend.Emails.send({
                    "from": settings.tripmate_resend_from_email,
                    "to": [row.to_email],
                    "subject": _subject(row.template),
                    "html": html,
                    "headers": {"X-Entity-Ref-ID": str(row.id)},
                    "tags": [
                        {"name": "kind", "value": row.template},
                        {"name": "env", "value": settings.environment},
                    ],
                })
                await db.execute(
                    "UPDATE app.email_queue SET status='sent', resend_id=:rid, sent_at=now() WHERE id=:id",
                    {"id": row.id, "rid": response["id"]},
                )
            except Exception as e:
                await _handle_failure(row, e)
        await asyncio.sleep(5)
```

## 5. React Email 템플릿

`emails/*.tsx` — 빌드 시 정적 HTML로 export 후 백엔드가 jinja2 변수 치환.

```tsx
// emails/verify-email.tsx
import { Button, Html, Head, Body, Container, Text, Heading } from '@react-email/components';

interface Props { verify_url: string; expires_in_hours: number; }

export default function VerifyEmail({ verify_url, expires_in_hours }: Props) {
  return (
    <Html>
      <Head />
      <Body style={{ fontFamily: 'sans-serif' }}>
        <Container>
          <Heading>TripMate 이메일 인증</Heading>
          <Text>아래 버튼을 클릭하여 이메일 주소를 인증하세요.</Text>
          <Button href={verify_url} style={{ background: '#FF385C', color: '#fff',
                                              padding: '12px 24px', borderRadius: '6px' }}>
            이메일 인증하기
          </Button>
          <Text style={{ color: '#666', fontSize: '14px', marginTop: '24px' }}>
            이 링크는 {expires_in_hours} 시간 후 만료됩니다.<br />
            본인이 가입하지 않았다면 이 메일을 무시하세요.
          </Text>
        </Container>
      </Body>
    </Html>
  );
}
```

템플릿 종류:

- `verify_email` — 회원가입 인증
- `reset_password` — 비밀번호 재설정
- `trip_invite` — 동반자 초대
- `share_link_notice` — 공유 링크 알림
- `password_changed` — 비밀번호 변경 알림
- `weekly_digest` (v2)

빌드:

```bash
npm --workspace emails run build
# 또는 react-email 라이브러리의 render() 함수 사용
```

## 6. Webhook (`POST /webhooks/resend`)

`TRIPMATE_RESEND_WEBHOOK_SECRET`이 설정된 환경에서는 Resend/Svix 서명 검증을 통과한
요청만 처리한다. secret이 비어 있을 때 서명 없는 webhook은
`TRIPMATE_RESEND_WEBHOOK_ALLOW_UNSIGNED=true`이고 환경이 `development` / `dev` /
`local` / `test` / `testing`인 경우에만 허용한다. 기본값은 `false`이므로
`TRIPMATE_ENVIRONMENT` 누락으로 기본 `development`가 적용되어도 webhook은 열리지 않는다.
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

처리 대상 이벤트:

| 이벤트 | 처리 |
|--------|------|
| `email.delivered` | `app.email_queue.status='delivered'`, `delivered_at=now()` |
| `email.bounced` | `status='bounced'`, `bounced_at=now()`, `bounce_type` 저장 |
| `email.complained` | `status='complained'` |

`X-Entity-Ref-ID` 헤더가 payload `data.headers`에 없으면 멱등 성공(`{"ok": true}`)으로
끝내고 상태를 갱신하지 않는다.

## 7. 발송 차단 정책

- `users.email_status = 'bounced'` (hard bounce) → 모든 발송 차단. 사용자에게
  "이메일 주소를 다시 확인해 주세요" 안내
- `users.email_status = 'complained'` (스팸 신고) → 모든 발송 차단 + admin audit
- `app.user_consents` 에서 `marketing` 동의 철회 → `template != 'marketing*'`만

## 8. 개발 / 스테이징 / 운영

| 환경 | 동작 |
|------|------|
| dev (`TRIPMATE_RESEND_API_KEY` 빈값) | 콘솔 출력 모드. queue 적재만 |
| dev (실제 키) | 실제 발송 — 본인 이메일로만 테스트 |
| staging | Resend "테스트 모드" API 키 — 실제 발송 X, API 흐름만 |
| 운영 | 실제 발송 |

E2E 테스트는 `mailpit` 컨테이너 옵션 또는 `email_queue.status` 검사로.

## 9. Admin 페이지 (`/admin/emails`)

`docs/api/admin.md` §2 + `docs/spec/v8/04-admin.md` M-2 `/admin/emails`.

- 큐 목록 (status / template / 날짜 필터)
- `resend_id` 클릭 → Resend 대시보드 deep link
- 행 액션: "재발송" (실패한 건)

## 10. AI agent 구현 체크리스트

- [x] `apps/api/app/services/email_service.py` (enqueue + SKIP LOCKED batch worker)
- [ ] `apps/api/app/webhooks/resend.py` (Svix 서명 검증)
- [ ] `emails/*.tsx` react-email 템플릿 6종 (`verify_email`, `reset_password`,
      `trip_invite`, `share_link_notice`, `password_changed`)
- [x] `app.email_queue` Alembic (Sprint 1 또는 2)
- [ ] `app.users.email_status` 컬럼 (`active` / `bounced` / `complained`)
- [ ] Worker 별도 프로세스 또는 Dagster sensor (`docs/runbooks/etl.md`)
- [ ] Resend "테스트 모드" 키로 staging 검증
- [ ] `docs/api/admin.md` `/admin/emails` 페이지 구현
- [ ] `docs/compliance/pipa.md`에 위탁자 명시
