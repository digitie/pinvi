# 인증 API (`/auth/*`)

이메일 가입 + verify + JWT 로그인 + Google OAuth + 비밀번호 재설정.
공통 규약은 [`common.md`](./common.md). 소셜 로그인 흐름 디테일은
[`docs/integrations/social-login.md`](../integrations/social-login.md).

현재 OAuth provider는 **Google만 활성**이다. Naver/Kakao OAuth는 미래 작업으로
분리했고, 현재 `/auth/oauth/providers`에는 노출하지 않는다.

## 1. 모델

| 테이블 | 용도 |
|--------|------|
| `app.users` | 계정 (`email` UNIQUE, `password_hash` Argon2id nullable for social-only) |
| `app.user_sessions` | refresh 토큰 hash + IP/UA + 만료/폐기 |
| `app.user_email_verifications` | verify/reset 토큰 (해시만 저장) |
| `app.user_oauth_identities` | provider + provider_user_id (현재 Google sub, Naver/Kakao는 미래 작업) |
| `app.user_consents` | 4 분리 동의 (`tos`/`privacy`/`lbs_tos`/`location_collection`/...) |
| `app.oauth_login_states` | OAuth state/nonce/PKCE hash, TTL 10분 |

자세히는 `docs/data-model.md` + `docs/postgres-schema.md`.

## 2. 이메일 가입 / verify

### 2.1 `POST /auth/register`

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "MinLen8...",
  "nickname": "user-nick",
  "consents": [
    { "consent_type": "tos", "version": "v1.0" },
    { "consent_type": "privacy", "version": "v1.0" },
    { "consent_type": "lbs_tos", "version": "v1.0" },
    { "consent_type": "location_collection", "version": "v1.0" },
    { "consent_type": "marketing", "version": "v1.0" }
  ]
}
```

응답 201:

```jsonc
{
  "data": {
    "user": {
      "user_id": "uuid",
      "email": "user@example.com",
      "status": "pending_verification",
      "email_verified_at": null
    },
    "verification_email_dispatched": true
  }
}
```

- Argon2id로 `password_hash` 저장 (passlib 또는 `argon2-cffi`)
- 가입 화면에서 필수 4종 동의(`tos`, `privacy`, `lbs_tos`, `location_collection`)를
  받아 `app.user_consents`에 같은 트랜잭션으로 저장한다.
- `marketing`은 선택 동의다. `demographic_use`는 성별/생년월/거주지 입력이 있는
  프로필 보강 단계에서만 받는다.
- `app.user_email_verifications` row + Resend로 verify 메일 발송
  (`TRIPMATE_RESEND_API_KEY` 미설정 시 console-log 모드)
- Resend HTTP 오류 → `503 SERVICE_UNAVAILABLE` + 트랜잭션 롤백
  (`verification_email_dispatched: false`)

에러:

- `409 EMAIL_ALREADY_USED` — 동일 email 활성 row 있음
- `422 VALIDATION_ERROR` — 형식/길이/약한 비밀번호
- `422 VALIDATION_ERROR` — 필수 약관 동의 누락 또는 동의 항목 중복
- `429 RATE_LIMITED`

### 2.2 `POST /auth/verify-email`

```http
POST /auth/verify-email
Content-Type: application/json

{ "token": "<43-char URL-safe base64>" }
```

응답 200:

```jsonc
{
  "data": {
    "user": { "user_id": "...", "email": "...", "email_verified_at": "..." },
    "access_token_dispatched": true   // cookie도 함께 발급
  }
}
```

Set-Cookie: `tripmate_access`, `tripmate_refresh`.

- `app.user_email_verifications` 검증 (해시 비교 + `expires_at > now()` + `used_at IS NULL`)
- 성공 시 `users.email_verified_at = now()`, `users.status = 'pending_profile'`
- `used_at = now()` 마킹 (재사용 차단)
- 인증 메일 만료/사용됨 → `422 VALIDATION_ERROR` (`details.token = "expired"`)

### 2.3 `POST /auth/verify-email/resend`

```http
POST /auth/verify-email/resend
Content-Type: application/json

{ "email": "user@example.com" }
```

- 이메일 존재 여부에 관계없이 `200 OK` (계정 enumeration 차단)
- 미인증 user가 있으면 새 verify 토큰 발급 + 발송, 직전 토큰 `used_at = now()`로 폐기
- Rate limit: 분당 1회 per email

## 3. 로그인 / 로그아웃 / refresh

### 3.1 `POST /auth/login`

```http
POST /auth/login
Content-Type: application/json

{ "email": "user@example.com", "password": "..." }
```

응답 200:

```jsonc
{
  "data": {
    "user": { "user_id": "...", "email": "...", "status": "active", "roles": ["user"] }
  }
}
```

Set-Cookie 두 개.

에러:

- `401 AUTH_INVALID_CREDENTIALS` — 이메일 X 또는 비밀번호 X. user enumeration 차단 위해 동일 메시지
- `401 EMAIL_NOT_VERIFIED` — body에 `verification_email_dispatched: bool`, 재발송 옵션 안내
- `403 PERMISSION_DENIED` — `users.status = 'disabled'`

### 3.2 `POST /auth/refresh`

```http
POST /auth/refresh
Cookie: tripmate_refresh=<opaque>
```

응답 200: 새 `tripmate_access` cookie + 새 `tripmate_refresh` cookie.

- 서버: `app.user_sessions` row hash 일치 + `revoked_at IS NULL` + `expires_at > now()` →
  기존 row `revoked_at=now()` + 새 session row 발급(refresh rotation)
- 폐기됨 / 만료됨 → `401 TOKEN_EXPIRED` (cookie 삭제)

### 3.3 `POST /auth/logout`

```http
POST /auth/logout
Cookie: tripmate_refresh=...
```

응답 204. 현재 `tripmate_refresh`에 해당하는 `app.user_sessions.revoked_at = now()` +
Set-Cookie로 두 cookie 삭제.

### 3.4 `GET /auth/me`

```http
GET /auth/me
Cookie: tripmate_access=...
```

응답 200:

```jsonc
{
  "data": {
    "user_id": "...",
    "email": "...",
    "nickname": "...",
    "avatar_url": "...",
    "status": "active",
    "roles": ["user"],
    "email_verified_at": "...",
    "has_password": true,
    "consents": [
      { "consent_type": "tos", "agreed_at": "...", "version": "v1.0" },
      { "consent_type": "location_collection", "agreed_at": "...", "withdrawn_at": null, "version": "v1.0" }
    ],
    "oauth_identities": [
      {
        "provider": "google",
        "provider_email": "...",
        "provider_email_verified": true,
        "display_name": "...",
        "linked_at": "...",
        "last_login_at": "..."
      }
    ]
  }
}
```

## 4. 프로필 완성

### 4.1 `POST /auth/profile/complete`

회원가입 후 동의 + 닉네임/아바타/선택 정보 입력 (status `pending_profile` → `active`).

```http
POST /auth/profile/complete
Content-Type: application/json
Cookie: tripmate_access=...

{
  "nickname": "user-nick",
  "avatar_kind": "default" | "upload",
  "avatar_attachment_id": "uuid",   // upload면 storage 먼저 거침
  "gender": "female" | "male" | "non_binary" | "no_answer",
  "birth_year_month": "199003",     // YYYYMM (선택)
  "residence_sigungu_code": "11680", // 시군구 코드 (선택)
  "consents": [
    { "consent_type": "tos", "version": "v1.0" },
    { "consent_type": "privacy", "version": "v1.0" },
    { "consent_type": "lbs_tos", "version": "v1.0" },
    { "consent_type": "location_collection", "version": "v1.0" },
    { "consent_type": "demographic_use", "version": "v1.0" },     // 선택
    { "consent_type": "marketing", "version": "v1.0" }            // 선택
  ]
}
```

- 필수 동의 4건 (`tos`, `privacy`, `lbs_tos`, `location_collection`) 누락 → `422`
- 선택 정보(`gender`, `birth_year_month`, `residence_sigungu_code`)는 `demographic_use`
  동의 있을 때만 저장. 미동의 + 입력 → `422` (UI 토스트로 처리)
- 성공 시 `users.status = 'active'`

## 5. 비밀번호 재설정

### 5.1 `POST /auth/password/reset-request`

```http
POST /auth/password/reset-request
Content-Type: application/json

{ "email": "user@example.com" }
```

응답 200 (enumeration 차단으로 항상). 메일 queue 적재는 user가 있고 이메일 인증이
끝났을 때만.

```json
{ "data": { "accepted": true } }
```

### 5.2 `POST /auth/password/reset`

```http
POST /auth/password/reset
Content-Type: application/json

{ "token": "<43-char>", "new_password": "..." }
```

- 토큰 검증 + `password_hash` 갱신 + 모든 `user_sessions` `revoked_at = now()` (로그아웃 전체)
- 응답 200, Set-Cookie 두 개 (자동 로그인)

## 6. Google OAuth

자세한 흐름은 [`docs/integrations/social-login.md`](../integrations/social-login.md).

### 6.1 `GET /auth/oauth/providers`

응답 200:

```jsonc
{
  "data": {
    "providers": [
      { "provider": "google", "enabled": true }
    ]
  }
}
```

`enabled`는 `TRIPMATE_GOOGLE_OAUTH_CLIENT_ID` 존재 여부다. Naver/Kakao는 future
provider라 설정값이 있어도 현재 응답에 포함하지 않는다.

### 6.2 `POST /auth/oauth/google/start`

```http
POST /auth/oauth/google/start
Content-Type: application/json

{ "return_to": "/trips", "mode": "login" }
```

- `mode`: `login` 기본. `/start`의 `mode=link`는 `400 OAUTH_LINK_REQUIRES_AUTH`로
  거부하며, 기존 user 연결은 6.4의 `/link` endpoint를 사용한다.
- `return_to`: TripMate 내부 경로만 허용 (allowlist), `/`로 시작
- 응답 200: `{ "data": { "authorize_url": "https://accounts.google.com/..." } }`
- 클라이언트는 `authorize_url`로 top-level navigation
- `app.oauth_login_states` row 생성 (state/nonce/PKCE hash, TTL 10분). PKCE verifier는
  `state`와 서버 secret으로 재생성하므로 DB에는 hash만 남긴다.

### 6.3 `GET /auth/oauth/google/callback`

```http
GET /auth/oauth/google/callback?code=...&state=...
```

처리:

1. `state` hash 검증 + `expires_at > now()` + `consumed_at IS NULL`
2. `code` → Google access token 교환
3. Google userinfo 호출 → `provider_user_id`, `email`, `email_verified`
4. `app.user_oauth_identities` 조회/upsert
5. 로그인 / 신규 가입 분기:
   - 기존 identity(`provider + provider_user_id`) 있음 → 해당 user 로그인
   - 기존 identity 없음 + 같은 이메일 로컬 계정 있음 → 자동 연결 금지,
     `OAUTH_ACCOUNT_LINK_REQUIRED`
   - 기존 identity 없음 + Google `email_verified=true` + 신규 이메일 → provider-only user 생성
   - Google 또는 TripMate 이메일 인증 불확실 → `OAUTH_EMAIL_UNVERIFIED`
   - Naver/Kakao → 미래 작업. 현재 callback route 없음.

응답:

- 성공: 303 → `${return_to}` + Set-Cookie 두 개
- 실패: 303 → `${TRIPMATE_WEB_BASE_URL}/login?error=<code>&error_description=...`
  - `mode=link` state 소비 뒤의 실패는 `return_to`(기본 `/profile`)로 redirect한다.
  - 현재 Google 구현: `OAUTH_ACCOUNT_LINK_REQUIRED` / `OAUTH_CALLBACK_INVALID` /
    `OAUTH_EMAIL_UNVERIFIED` / `OAUTH_PROVIDER_DENIED` / `OAUTH_STATE_INVALID` /
    `OAUTH_PROVIDER_ERROR`
  - Naver/Kakao 후속 구현 시 provider별 세부 code를 추가한다.

### 6.4 `POST /auth/oauth/google/link`

기존 user 계정에 provider 연결 (이미 로그인 상태).

```http
POST /auth/oauth/google/link
Content-Type: application/json
Cookie: tripmate_access=...

{ "return_to": "/profile" }
```

응답 200: `{ "data": { "authorize_url": "..." } }`. 클라이언트가 top-level
navigation.

### 6.5 `DELETE /auth/oauth/google`

```http
DELETE /auth/oauth/google
Cookie: tripmate_access=...
```

- 비밀번호 설정돼 있어야 (`password_hash IS NOT NULL`) — 소셜-only는 거부
- `app.user_oauth_identities` row 삭제 + `admin_audit_log`/`app` audit 기록
- 응답 204

## 7. 탈퇴

### 7.1 `DELETE /auth/me`

```http
DELETE /auth/me
Cookie: tripmate_access=...
Content-Type: application/json

{ "confirm": "DELETE" }
```

- 리더인 trip이 있으면 `410 GONE` + `{"error": {"code": "TRIPS_OWNED",
  "details": {"trip_ids": [...]}}}` 안내 ("trip 이관 또는 삭제 먼저")
- 성공: `users.status = 'deleted'`, PII 마스킹 잡 schedule, 모든 session revoke,
  `app.admin_audit_log` + `app.user_consents` `withdrawn_at` 일괄 갱신

## 8. 작업 체크리스트 (AI agent)

새 인증 endpoint 추가 시:

- [ ] `apps/api/app/schemas/auth.py` Pydantic 추가
- [ ] `packages/schemas/src/auth.ts` Zod 추가
- [ ] `apps/api/app/services/auth/<feature>.py` 비즈니스 로직
- [ ] `apps/api/app/api/v1/auth.py` 라우터
- [ ] 통합 테스트 `apps/api/tests/integration/test_auth_<feature>.py`
- [ ] (OAuth) `apps/api/app/services/oauth/<provider>.py` httpx 호출
- [ ] (이메일) `apps/api/app/services/email_service.py` template + queue
- [ ] Sentry `before_send` PII 마스킹 확인 (이메일/비밀번호/token)
- [ ] Rate limit 적용
- [ ] 본 문서 + `common.md` 표준 에러 코드 갱신
