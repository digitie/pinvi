# Auth API

## 현재 상태

일반 사용자 인증 API는 Phase 2에서 단계적으로 구현한다. 현재는 가입 요청을 저장하는 `POST /auth/register`와 httpOnly cookie 기반 `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`가 구현되어 있다. 이메일 인증 링크 소비 endpoint는 아직 구현 전이다.
사용자, 이메일 인증, 초대 참여자, 관리자 사용자 관리의 목표 DB 스키마는 `docs/architecture/user-trip-schema.md`를 따른다.

현재 존재하는 테이블:

- `users`
- `sessions`
- `email_verification_tokens`

현재 존재하는 공통 endpoint:

- `GET /health`
- `GET /health/db`

현재 존재하는 일반 사용자 endpoint:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

계획 중인 소셜 로그인 endpoint:

- `GET /auth/oauth/providers`
- `GET /auth/oauth/{provider}/start`
- `GET /auth/oauth/{provider}/callback`
- `POST /auth/oauth/{provider}/link`
- `DELETE /auth/oauth/{provider}`

계획 중인 소셜 로그인 테이블:

- `user_oauth_accounts`
- `oauth_login_states`

현재 존재하는 관리자 인증 endpoint:

- `POST /admin/auth/login`
- `POST /admin/auth/logout`
- `GET /admin/auth/me`

관리자 API 상세는 `docs/api/admin.md`를 따른다. 일반 사용자 로그인 화면은 `/login`이며 관리자 로그인 화면과 분리한다.

## 인증 방식

TripMate는 httpOnly cookie 기반 서버 세션으로 시작한다.

원칙:

- 사용자 로그인 식별자는 이메일이다.
- 이메일은 중복될 수 없다.
- 비밀번호는 평문 저장하지 않고 안전한 password hash만 저장한다.
- 세션 cookie에는 난수 기반 opaque token만 저장한다.
- DB에는 세션 token 원문이 아니라 `session_token_hash`만 저장한다.
- 로그아웃은 서버 세션의 `revoked_at`을 기록하는 방식으로 처리한다.
- 가입 시 이메일 인증을 요구한다.
- 일반 로그인은 현재 `account_status = active`, `is_active = true`인 사용자만 허용한다.
- 초대 참여자는 첫 로그인 때 비밀번호를 설정한다.
- 관리자 비밀번호 초기화는 임시 비밀번호 발급이 아니라 reset link 발송 방식으로 처리한다.
- SMTP/Gmail credential 원문은 DB에 저장하지 않고 secret reference만 저장한다.
- Google/Naver/Kakao 로그인은 provider token을 TripMate 세션으로 쓰지 않는다.
- 소셜 로그인 callback 성공 후에도 기존 `tripmate_session` httpOnly cookie와 `sessions.session_token_hash`를 사용한다.
- provider 고유 식별자는 `user_oauth_accounts(provider, provider_user_id)`에 저장한다.
- 기존 이메일 계정과 provider 계정은 자동 연결하지 않는다.
- provider access token, refresh token, id token 원문은 DB와 로그에 저장하지 않는다.

## 소셜 로그인 계획

상세 설계와 provider별 scope, endpoint, 보안 기준은 `docs/integrations/social-login.md`를 따른다. provider identity 연결 결정은 `docs/decisions/20260508-social-login-provider-identity.md`를 따른다.

지원 대상 provider:

| Provider | TripMate key | 사용자 식별 필드 | 이메일 인증 처리 |
| --- | --- | --- | --- |
| Google | `google` | `sub` | `email_verified = true`일 때 provider 인증을 신뢰 |
| Naver | `naver` | `response.id` | 명시적 verified flag가 없으므로 초기 구현은 TripMate 이메일 인증 요구 |
| Kakao | `kakao` | `id` | `is_email_valid = true` 및 `is_email_verified = true`일 때 provider 인증을 신뢰 |

소셜 로그인 성공 흐름:

1. `/login`의 provider 버튼이 `GET /auth/oauth/{provider}/start?return_to=/trips`로 top-level navigation한다.
2. API는 난수 `state`를 만들고 hash만 `oauth_login_states`에 저장한다.
3. 사용자는 provider 인증/동의 화면을 거쳐 `GET /auth/oauth/{provider}/callback`으로 돌아온다.
4. API는 `state`, 만료, provider 일치를 검증하고 authorization code를 token으로 교환한다.
5. API는 provider profile을 조회하고 `provider_user_id`를 기준으로 `user_oauth_accounts`를 찾는다.
6. 이미 연결된 계정이면 기존 사용자로 `tripmate_session`을 발급한다.
7. 연결된 계정이 없고 현재 TripMate 세션이 있으면 명시적 연결 흐름으로 처리한다.
8. 연결된 계정이 없고 같은 이메일 사용자가 없으면 provider 이메일 신뢰 정책에 따라 신규 사용자를 만들 수 있다.
9. 같은 이메일 사용자가 이미 있으면 자동 연결하지 않고 `/login?oauth_error=account_link_required&provider=...`로 돌려보낸다.

소셜 로그인 오류 redirect:

```text
/login?oauth_error=provider_disabled&provider=google
/login?oauth_error=provider_denied&provider=naver
/login?oauth_error=state_expired&provider=kakao
/login?oauth_error=email_required&provider=kakao
/login?oauth_error=email_unverified&provider=naver
/login?oauth_error=account_link_required&provider=google
/login?oauth_error=oauth_temporary_failure&provider=kakao
```

사용자 UI는 위 내부 코드를 조치 가능한 한국어 메시지로 변환한다. provider 원문 오류, token, profile raw payload는 화면과 로그에 그대로 노출하지 않는다.

### `GET /auth/oauth/providers`

로그인 화면에서 사용 가능한 provider 목록을 조회한다.

응답:

```json
{
  "providers": [
    {
      "provider": "google",
      "display_name": "Google",
      "enabled": true
    },
    {
      "provider": "naver",
      "display_name": "Naver",
      "enabled": true
    },
    {
      "provider": "kakao",
      "display_name": "Kakao",
      "enabled": true
    }
  ]
}
```

### `GET /auth/oauth/{provider}/start`

provider authorization URL로 redirect한다.

요청 query:

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `return_to` | N | 성공 후 이동할 TripMate 상대 경로. 기본 `/trips` |
| `mode` | N | `login` 또는 `link`. 기본 `login` |

오류:

- `404 Not Found`: 지원하지 않는 provider
- `503 Service Unavailable`: provider 설정 누락
- `422 Unprocessable Entity`: 외부 URL 등 허용되지 않는 `return_to`

### `GET /auth/oauth/{provider}/callback`

provider callback이다. 성공하면 `tripmate_session` cookie를 설정하고 `return_to`로 redirect한다. 실패하면 `/login?oauth_error=...&provider=...`로 redirect한다.

이 endpoint는 일반 JSON API라기보다 브라우저 redirect endpoint다.

### `POST /auth/oauth/{provider}/link`

로그인된 사용자가 provider 계정을 명시적으로 연결할 때 사용한다. 구현은 `start?mode=link`와 callback에서 처리해도 되지만, API 계약상 현재 사용자 세션이 필요한 연결 기능으로 둔다.

### `DELETE /auth/oauth/{provider}`

로그인된 사용자가 provider 연결을 해제한다.

해제 제한:

- 비밀번호가 없고 연결된 provider가 하나뿐이면 해제할 수 없다.
- 다른 사용자에게 연결된 provider 계정은 해제할 수 없다.

## Endpoint

### `POST /auth/register`

일반 사용자 가입 요청을 생성한다. 현재 단계에서는 이메일 발송 provider가 연결되어 있지 않으므로, 사용자는 `pending_email_verification` 상태로 저장되고 `email_verification_tokens.token_hash`만 DB에 남긴다. 원문 token은 DB에 저장하지 않는다.

요청:

```json
{
  "email": "planner@example.com",
  "password": "strong-password-1",
  "nickname": "여행자",
  "name": "홍길동",
  "birth_year_month": "199001",
  "gender": "no_answer",
  "residence_sigungu_code": "1111000000"
}
```

필수:

- `email`
- `password`
- `nickname`
- `name`

선택:

- `birth_year_month`: `YYYYMM`
- `gender`: `female`, `male`, `non_binary`, `no_answer`
- `residence_sigungu_code`: `address_code_standard.legal_dong_code`에 존재하는 활성 시군구 코드

응답:

```json
{
  "user": {
    "id": "00000000-0000-4000-8000-000000000001",
    "email": "planner@example.com",
    "nickname": "여행자",
    "name": "홍길동",
    "account_status": "pending_email_verification",
    "system_role": "planner",
    "email_verification_required": true,
    "verification_email_dispatched": false
  }
}
```

오류:

- `409 Conflict`: 이미 가입된 이메일
- `422 Unprocessable Entity`: 입력값 형식 오류 또는 존재하지 않는 거주지 시군구 코드

### `POST /auth/login`

일반 사용자 로그인이다. 관리자 로그인과 같은 `sessions` 테이블, 같은 `tripmate_session` httpOnly cookie 구조를 사용한다. 차이는 `/auth/login`은 일반 사용자용이고, `/admin/auth/login`은 관리자 권한을 추가로 요구한다는 점이다.

요청:

```json
{
  "email": "planner@example.com",
  "password": "strong-password-1"
}
```

응답:

```json
{
  "user": {
    "id": "00000000-0000-4000-8000-000000000001",
    "email": "planner@example.com",
    "display_name": "여행자",
    "nickname": "여행자",
    "name": "홍길동",
    "account_status": "active",
    "system_role": "planner",
    "email_verified_at": "2026-04-28T09:00:00+09:00",
    "is_admin": false,
    "is_privileged": false
  }
}
```

동작:

- 이메일은 소문자로 정규화해 조회한다.
- 비밀번호 hash 검증에 실패하면 `401 Unauthorized`를 반환한다.
- 이메일 인증 전 계정(`pending_email_verification`), 초대 수락 전 계정(`invited`), 비활성/삭제 계정은 로그인할 수 없다.
- cookie에는 원문 session token을 담고 DB에는 `session_token_hash`만 저장한다.
- 사용자 세션 기본 만료는 `TRIPMATE_USER_SESSION_HOURS` 설정을 따른다. 현재 기본값은 14일이다.

### `GET /auth/me`

현재 일반 사용자 세션을 확인한다. 유효한 `tripmate_session` cookie가 없으면 `401 Unauthorized`를 반환한다.

### `POST /auth/logout`

현재 cookie의 session token hash를 찾아 `sessions.revoked_at`을 기록하고 cookie를 삭제한다.

## 계획 중인 endpoint

```text
POST /auth/verify-email
POST /auth/password-reset/request
POST /auth/password-reset/confirm
PATCH /users/me
GET /users/me/private-profile
PATCH /users/me/private-profile
GET /auth/oauth/providers
GET /auth/oauth/{provider}/start
GET /auth/oauth/{provider}/callback
POST /auth/oauth/{provider}/link
DELETE /auth/oauth/{provider}
```

관리자용 사용자 관리 endpoint 초안:

```text
GET /admin/users
POST /admin/users
PATCH /admin/users/{user_id}
DELETE /admin/users/{user_id}
POST /admin/users/{user_id}/password-reset
```

## 공통 오류 방향

구체 schema는 Phase 2 구현 시 확정한다.

- 중복 이메일: `409 Conflict`
- 잘못된 로그인 정보: `401 Unauthorized`
- 인증 필요: `401 Unauthorized`
- 권한 없음: `403 Forbidden`
- validation 실패: `422 Unprocessable Entity`

## 테스트 기준

최소 테스트:

- 회원가입 정상 경로
- 중복 이메일 실패
- 로그인 정상 경로
- 잘못된 비밀번호 실패
- 로그아웃 후 세션 무효화
- 이메일 인증 전 로그인/접근 제한
- 초대 참여자의 첫 비밀번호 설정
- 관리자 비밀번호 초기화 token 발급
- 사용자 정보 수정 인가 검사
- 세션 token 원문이 DB와 로그에 남지 않는지 확인
- 이메일 인증/reset token 원문이 DB와 로그에 남지 않는지 확인
- 소셜 로그인 state mismatch/만료/재사용 실패
- Google/Naver/Kakao provider profile 정규화
- 기존 이메일 계정과 provider 계정 자동 연결 방지
- provider-only 사용자의 password login 실패
- provider token 원문이 DB와 로그에 남지 않는지 확인
