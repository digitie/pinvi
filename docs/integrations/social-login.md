# 소셜 로그인 — Google / Naver / Kakao

`/login` 화면 OAuth 버튼 + 안전 매칭 정책. SPEC V8 G-4 + ADR-013 (v1 decisions
`20260508-social-login-provider-identity`).

## 1. 정책

- TripMate 로그인 식별자는 `users.email` (변경 없음)
- 소셜 identity는 `app.user_oauth_identities` 별도 테이블 — `users`에 병합 X
- provider access / refresh / id token 원본 **장기 저장 X** — profile fetch 후
  즉시 폐기
- 이메일이 같다고 **자동 연결 X** — 명시 사유 (`account_link_required` 에러 코드)
- provider별 신뢰 신호:
  - Google: `email_verified=true` 필수
  - Naver: `email_verified` 없음 → TripMate 자체 verify 메일 발송
  - Kakao: `is_email_valid && is_email_verified` 필수
- 신규 provider-only user는 `password_hash=NULL` 허용 (`users.password_hash` nullable)
- Admin 로그인 화면에는 소셜 버튼 X (별도 admin 이메일/비밀번호 흐름)

## 2. 환경변수

| 환경변수 | 비고 |
|----------|------|
| `TRIPMATE_GOOGLE_OAUTH_CLIENT_ID` | Google Cloud Console |
| `TRIPMATE_GOOGLE_OAUTH_CLIENT_SECRET` | |
| `TRIPMATE_NAVER_OAUTH_CLIENT_ID` | NAVER Developers |
| `TRIPMATE_NAVER_OAUTH_CLIENT_SECRET` | |
| `TRIPMATE_KAKAO_OAUTH_REST_API_KEY` | Kakao Developers |
| `TRIPMATE_KAKAO_OAUTH_CLIENT_SECRET` | (Kakao는 REST API key + 별도 client secret) |
| `TRIPMATE_OAUTH_STATE_TTL_SECONDS` | `600` (10분) |
| `TRIPMATE_OAUTH_HTTP_TIMEOUT_SECONDS` | `5` |
| `TRIPMATE_WEB_BASE_URL` | redirect base |
| `TRIPMATE_OAUTH_CALLBACK_BASE_URL` | provider 콘솔에 등록한 callback URL의 base |

미설정 시 (`CLIENT_ID` 빈값) → 해당 provider 비활성 (`GET /auth/oauth/providers`
응답에서 `enabled: false`).

## 3. Provider별 endpoint

### 3.1 Google

| 항목 | 값 |
|------|-----|
| 인증 | `https://accounts.google.com/o/oauth2/v2/auth` |
| 토큰 교환 | `https://oauth2.googleapis.com/token` |
| Userinfo | `https://openidconnect.googleapis.com/v1/userinfo` |
| Scope | `openid email profile` |
| ID 키 | `sub` |
| 이메일 verified 필드 | `email_verified` (bool) |

### 3.2 Naver

| 항목 | 값 |
|------|-----|
| 인증 | `https://nid.naver.com/oauth2.0/authorize` |
| 토큰 교환 | `https://nid.naver.com/oauth2.0/token` |
| Userinfo | `https://openapi.naver.com/v1/nid/me` |
| Scope | (지정 안 함, 기본) |
| ID 키 | `response.id` |
| 이메일 verified 필드 | **없음** → TripMate가 별도 verify 발송 |

### 3.3 Kakao

| 항목 | 값 |
|------|-----|
| 인증 | `https://kauth.kakao.com/oauth/authorize` |
| 토큰 교환 | `https://kauth.kakao.com/oauth/token` |
| Userinfo | `https://kapi.kakao.com/v2/user/me` |
| Scope | `account_email profile_nickname` (+`openid` if OIDC mode) |
| ID 키 | `id` |
| 이메일 verified 필드 | `kakao_account.is_email_valid && is_email_verified` |

## 4. DB 모델

### 4.1 `app.user_oauth_identities`

```sql
CREATE TABLE app.user_oauth_identities (
  identity_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  provider              varchar(32) NOT NULL,         -- 'google' | 'naver' | 'kakao'
  provider_user_id      varchar(255) NOT NULL,
  provider_email        varchar(320),
  provider_email_verified boolean,
  display_name_snapshot varchar(120),
  linked_at             timestamptz NOT NULL DEFAULT now(),
  last_login_at         timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_user_id),                 -- 같은 provider 계정 중복 가입 차단
  UNIQUE (user_id, provider)                           -- 한 user는 provider 당 1개
);
```

### 4.2 `app.oauth_login_states`

```sql
CREATE TABLE app.oauth_login_states (
  state_hash               varchar(128) PRIMARY KEY,
  nonce_hash               varchar(128),
  pkce_code_verifier_hash  varchar(128),
  provider                 varchar(32) NOT NULL,
  mode                     varchar(16) NOT NULL,       -- 'login' | 'link'
  return_to_path           varchar(255),
  user_id                  uuid REFERENCES app.users(user_id),  -- mode='link'면 채움
  expires_at               timestamptz NOT NULL,
  consumed_at              timestamptz,
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX oauth_login_states_active_idx
  ON app.oauth_login_states (expires_at)
  WHERE consumed_at IS NULL;
```

## 5. 흐름

### 5.1 신규 가입 (Google `email_verified=true`)

```
사용자가 /login에서 [Google로 시작] 클릭
  ↓ API가 authorize_url 발급
POST /auth/oauth/google/start { return_to: "/trips", mode: "login" }
  ↓
서버: state/nonce/PKCE 생성, hash 저장 (10분 TTL), authorize_url 반환
  ↓ top-level navigation
https://accounts.google.com/o/oauth2/v2/auth?client_id=...&response_type=code&scope=openid+email+profile&...&state=...
  ↓ 사용자 Google 동의
GET /auth/oauth/google/callback?code=...&state=...
  ↓
서버:
  1. state hash 검증 + consumed_at NULL + expires_at > now()
  2. POST oauth2.googleapis.com/token → access_token + id_token
  3. GET userinfo → { sub, email, email_verified, name }
  4. email_verified=false → 거부 (error_redirect: email_unverified)
  5. user_oauth_identities (google, sub) 검색
     - 있음: 그 user_id로 로그인
     - 없음 + email로 user 검색:
       - 있음 + user.email_verified=true → "account_link_required" (자동 연결 X)
       - 있음 + user.email_verified=false → "email_unverified" (먼저 자체 인증)
       - 없음 → 신규 user 생성 (password_hash=NULL, email_verified=true)
  6. user_oauth_identities row 생성 + last_login_at
  7. Set-Cookie 두 개 + 302 → return_to
```

### 5.2 신규 가입 (Naver)

- email_verified 필드 없음 → TripMate 자체 verify 메일 발송 후 그 link 클릭으로 활성화
- 신규 user는 일단 `status='pending_verification'`으로 생성
- verify 후 `status='active'`

### 5.3 기존 계정에 provider 연결 (mode=link)

```
사용자 로그인 상태에서 /profile에서 [Google 연결] 클릭
  ↓
POST /auth/oauth/google/link { return_to: '/profile' }
  ↓ 응답에 redirect_url
  ↓ 클라이언트가 top-level navigation
... (above flow with mode=link, user_id 포함된 state) ...
  ↓ callback
  - 같은 provider+sub로 다른 user에 이미 연결 → "account_link_required" (충돌)
  - 같은 user에 다른 sub로 이미 연결 → "account_link_required"
  - 신규 → user_oauth_identities row 생성
```

### 5.4 해제

`DELETE /auth/oauth/{provider}`:

- `password_hash IS NOT NULL` 검사 (소셜-only는 거부 — 로그인 수단 사라짐)
- row 삭제 + audit log
- 응답 204

## 6. 에러 redirect 코드

callback 실패 시 `/login?error=<code>&error_description=<msg>` 으로 302:

| code | 의미 |
|------|------|
| `provider_disabled` | 환경변수 미설정 |
| `provider_denied` | 사용자가 provider 측에서 거부 |
| `state_invalid` | state hash 불일치 / consumed |
| `state_expired` | TTL 초과 |
| `provider_profile_failed` | userinfo 호출 실패 |
| `email_required` | provider 응답에 email 없음 |
| `email_unverified` | Google/Kakao verified=false |
| `account_link_required` | 자동 연결 차단 |
| `oauth_temporary_failure` | 5xx / 네트워크 / timeout |

UI는 한국어 메시지로 변환해 토스트 또는 인라인 에러 표시.

## 7. 보안

### 7.1 state / nonce / PKCE

- state: 32 bytes URL-safe random → `state_hash` 저장 (`sha256`)
- nonce (OIDC): 32 bytes random → ID token 검증
- PKCE: `code_verifier` 64 bytes → `code_challenge = base64url(sha256(verifier))`
- TTL 10분 (`expires_at`)
- 사용 후 `consumed_at = now()` — 재사용 차단

### 7.2 return_to allowlist

- 내부 경로만 허용: `^/[a-zA-Z0-9/_-]+$`
- 외부 URL 차단 (open redirect 방지)
- 기본값 `/trips`

### 7.3 토큰 로그 차단

- provider access / refresh / id token은 응답 받은 즉시 메모리 폐기
- structlog / Sentry `before_send`에서 정규식 마스킹
- `app.api_call_log`에 endpoint URL만 (query에 token 있으면 strip)

## 8. UI 가이드

### 8.1 버튼 (DESIGN.md / `airbnb-marker-palette.html` 참고)

순서: **Google → Naver → Kakao** (`SPEC V8` 결정).

| Provider | 색상 | 텍스트 |
|----------|------|--------|
| Google | 흰 배경 + Google 로고 + `Sign in with Google` | 회색 텍스트 |
| Naver | `#03C75A` 녹색 + 흰 텍스트 | "네이버 로그인" |
| Kakao | `#FEE500` 노랑 + 검정 텍스트 | "카카오 로그인" |

- 너비: full-width on mobile, min-height 48px
- radius: 8px (DESIGN.md `radii.sm`)
- 클릭은 **top-level navigation** (`window.location.href = ...`) — `fetch` 금지

### 8.2 provider 로고 / brand asset

- 공식 brand asset을 self-host (`apps/web/public/oauth-icons/`)
- 외부 CDN hotlink 금지
- 로고 라이선스 준수 (Google brand guidelines, Naver / Kakao 가이드)

### 8.3 Admin 로그인

별도 `/admin/login` 화면. 이메일 + 비밀번호만. 소셜 버튼 X.

## 9. Local 개발 callback URI

| Provider | 콘솔에 등록 |
|----------|-------------|
| Google | `http://localhost:9021/auth/oauth/google/callback` |
| Naver | `http://localhost:9021/auth/oauth/naver/callback` |
| Kakao | `http://localhost:9021/auth/oauth/kakao/callback` |

Docker smoke: `http://127.0.0.1:9021/auth/oauth/{provider}/callback` (추가).

## 9.1 Production OAuth / JavaScript origin

운영 URL:

| 항목 | 값 |
|------|----|
| API base | `https://tripmateapi.digitie.mywire.org` |
| Web origin | `https://tripmate.digitie.mywire.org` |

Google Cloud Console 등록값:

| 설정 | 값 |
|------|----|
| 승인된 JavaScript 원본 | `https://tripmate.digitie.mywire.org` |
| 승인된 리다이렉션 URI | `https://tripmateapi.digitie.mywire.org/auth/oauth/google/callback` |

Naver/Kakao provider 콘솔도 같은 원칙을 따른다:

| Provider | 운영 callback |
|----------|---------------|
| Google | `https://tripmateapi.digitie.mywire.org/auth/oauth/google/callback` |
| Naver | `https://tripmateapi.digitie.mywire.org/auth/oauth/naver/callback` |
| Kakao | `https://tripmateapi.digitie.mywire.org/auth/oauth/kakao/callback` |

운영 환경변수:

```dotenv
TRIPMATE_WEB_BASE_URL=https://tripmate.digitie.mywire.org
TRIPMATE_OAUTH_CALLBACK_BASE_URL=https://tripmateapi.digitie.mywire.org
TRIPMATE_CORS_ALLOWED_ORIGINS=["https://tripmate.digitie.mywire.org"]
NEXT_PUBLIC_TRIPMATE_API_URL=https://tripmateapi.digitie.mywire.org
TRIPMATE_ENVIRONMENT=production
```

보안 처리:

- `redirect_uri`는 provider 콘솔에 등록된 callback과 **문자열이 완전히 같아야** 한다.
  경로, scheme, host가 다르면 token exchange가 실패한다.
- OAuth 시작 요청의 `return_to`는 상대 경로 또는 `TRIPMATE_WEB_BASE_URL` 하위 경로만
  허용한다. 외부 URL은 거부해 open redirect를 막는다.
- 운영 cookie는 `Secure`, `HttpOnly`, `SameSite=Lax`로 내려간다.
  `TRIPMATE_ENVIRONMENT=production` 누락 시 `Secure`가 빠질 수 있으므로 운영
  배포에서 필수값으로 둔다.
- CORS origin은 웹 origin인 `https://tripmate.digitie.mywire.org`만 허용한다.
  API origin(`https://tripmateapi.digitie.mywire.org`)이나 wildcard는 허용하지 않는다.
- OAuth code, state, token 응답은 로그에 남기지 않는다. `state`/PKCE verifier는
  hash만 저장하고 TTL 10분 후 만료한다.

## 10. AI agent 구현 체크리스트

- [x] `app.user_oauth_identities` + `app.oauth_login_states` Alembic (Sprint 2)
- [x] `apps/api/app/services/oauth_google.py` httpx 호출 + G-4 매칭 정책
- [x] `apps/api/app/api/v1/oauth.py` Google providers/start/callback/unlink 라우터
- [x] `apps/web/app/(auth)/login/page.tsx` Google 버튼 + provider 목록 fetch
- [ ] Naver/Kakao service + start/callback/link/unlink 라우터
- [ ] Naver/Kakao 로그인 버튼 활성화
- [ ] OAuth Naver 신규 가입 → 자체 verify 메일 트리거
- [ ] 통합 테스트 — VCR.py로 provider 응답 녹화 + 재생
- [ ] state / nonce / PKCE 검증 unit 테스트
- [ ] `account_link_required` 흐름 e2e
- [ ] `users.password_hash NULL` 허용 Alembic
- [ ] `docs/compliance/pipa.md` 위탁자 명시
