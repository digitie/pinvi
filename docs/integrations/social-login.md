# 소셜 로그인 통합 설계

## 목적

TripMate 일반 사용자 로그인 화면(`/login`)에 Google, Naver, Kakao 간편 로그인 버튼을 추가하고, 각 provider의 OAuth/OIDC 결과를 기존 httpOnly cookie 기반 TripMate JWT 세션으로 연결한다.

이 문서는 구현 전 기준이다. 현재 저장소에는 이메일/비밀번호 기반 `POST /auth/login`, `tripmate_access`/`tripmate_refresh` cookie, refresh token hash를 보관하는 `sessions` 테이블이 있으며, 소셜 로그인 endpoint, DB 테이블, 화면 버튼은 아직 구현되지 않았다.

## 핵심 결정

- TripMate 로그인 식별자의 기준은 계속 `users.email`이다.
- provider 고유 사용자는 `users`에 직접 섞지 않고 `user_oauth_accounts`에서 연결한다.
- provider access token과 refresh token은 초기 구현에서 장기 저장하지 않는다.
- OAuth callback에서 provider token은 프로필 조회에만 사용하고 즉시 폐기한다.
- 로그인 완료 후에는 기존과 동일한 `tripmate_access`, `tripmate_refresh` httpOnly cookie를 발급한다.
- 기존 이메일 계정과 provider 계정은 자동 병합하지 않는다. 같은 이메일이 이미 있으면 기존 세션으로 로그인한 뒤 명시적으로 연결하게 한다.
- 신규 provider-only 사용자를 지원하려면 `users.password_hash`를 nullable로 전환하는 migration이 필요하다.
- 관리자 로그인(`/admin/login`)에는 Google/Naver/Kakao 버튼을 추가하지 않는다.

## 공식 문서 기준

구현 착수 직전에 아래 공식 문서를 다시 확인한다. provider console의 UI와 redirect URI 정책은 바뀔 수 있다.

| Provider | 공식 문서 | 인증 endpoint | token endpoint | 사용자 정보 |
| --- | --- | --- | --- | --- |
| Google | [OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server), [OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) | `https://accounts.google.com/o/oauth2/v2/auth` | `https://oauth2.googleapis.com/token` | `https://openidconnect.googleapis.com/v1/userinfo` 또는 `id_token` |
| Naver | [네이버 로그인 API 명세](https://developers.naver.com/docs/login/api/api.md), [회원 프로필 조회 API](https://developers.naver.com/docs/login/profile/profile.md) | `https://nid.naver.com/oauth2.0/authorize` | `https://nid.naver.com/oauth2.0/token` | `https://openapi.naver.com/v1/nid/me` |
| Kakao | [Kakao Login REST API](https://developers.kakao.com/docs/latest/en/kakaologin/rest-api) | `https://kauth.kakao.com/oauth/authorize` | `https://kauth.kakao.com/oauth/token` | `https://kapi.kakao.com/v2/user/me` |

## Provider별 프로필 매핑

### Google

요청 scope:

```text
openid email profile
```

식별 기준:

- `provider = google`
- `provider_user_id = sub`
- `provider_email = email`
- `provider_email_verified = email_verified`
- `display_name_snapshot = name`

검증:

- `id_token`을 사용하면 `iss`, `aud`, `exp`, `nonce`를 검증한다.
- Google 문서는 사용자를 식별할 때 `email`이 아니라 `sub`를 사용하라고 안내한다. TripMate도 연결 테이블의 unique key에는 `sub`를 사용한다.
- `email_verified = true`일 때만 TripMate 이메일 인증을 provider 인증으로 대체할 수 있다.

### Naver

요청 scope:

- 네이버 로그인은 문서상 `scope`를 별도로 전송할 필요가 없다. 필요한 프로필 항목은 Naver Developers 앱의 API 권한 관리에서 설정한다.

식별 기준:

- `provider = naver`
- `provider_user_id = response.id`
- `provider_email = response.email`
- `display_name_snapshot = response.nickname` 또는 `response.name`

검증:

- `state`는 필수다.
- Naver 프로필 응답은 애플리케이션당 unique한 `response.id`를 제공한다.
- Naver 프로필 문서는 `email`을 제공하지만 별도 `email_verified` boolean을 제공하지 않는다. 초기 구현에서는 Naver 신규 가입을 바로 `active`로 만들지 않고 TripMate 이메일 인증을 요구하는 쪽을 기본값으로 둔다. Naver 이메일을 신뢰해 즉시 활성화하려면 별도 ADR로 제품 결정을 남긴다.

### Kakao

요청 scope:

```text
account_email profile_nickname
```

Kakao 앱에서 OpenID Connect를 켠 경우:

```text
openid account_email profile_nickname
```

식별 기준:

- `provider = kakao`
- `provider_user_id = id`를 문자열로 저장
- `provider_email = kakao_account.email`
- `provider_email_verified = kakao_account.is_email_valid && kakao_account.is_email_verified`
- `display_name_snapshot = kakao_account.profile.nickname`

검증:

- Kakao REST API key와 redirect URI를 앱 관리 페이지에 등록해야 한다.
- Kakao client secret 기능이 켜져 있으면 token 요청에 `client_secret`을 포함한다.
- OIDC를 켠 경우 `nonce`를 검증한다.
- 이메일 동의가 필요하거나 이메일이 유효하지 않으면 신규 계정을 만들지 않고 `/login`으로 돌려보내 조치 가능한 오류를 보여준다.

## API 계약

### `GET /auth/oauth/providers`

로그인 화면이 활성화된 provider 목록을 조회한다.

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

동작:

- provider별 client id와 secret이 모두 설정된 경우에만 `enabled = true`다.
- production에서는 `enabled = false`인 provider 버튼을 숨긴다.
- local/dev에서는 disabled 상태를 표시해 설정 누락을 쉽게 확인할 수 있다.

### `GET /auth/oauth/{provider}/start`

provider 인증 화면으로 리다이렉트한다.

Query:

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `return_to` | N | 로그인 성공 후 이동할 상대 경로. 기본값 `/trips` |
| `mode` | N | `login` 또는 `link`. 기본값 `login` |

동작:

1. `provider`가 `google`, `naver`, `kakao` 중 하나인지 확인한다.
2. `return_to`는 `/`로 시작하는 같은 서비스 내부 경로만 허용한다.
3. 난수 `state`를 만들고 DB에는 `state_hash`만 저장한다.
4. OIDC provider에는 난수 `nonce`를 만들고 DB에는 `nonce_hash`만 저장한다.
5. PKCE를 쓰는 provider에는 `code_verifier`를 만들고 hash만 DB에 저장한다. 원문 `code_verifier`는 짧은 만료의 httpOnly cookie에 둔다.
6. provider authorization URL로 `302` redirect한다.

오류:

- 미지원 provider: `404 Not Found`
- provider 설정 누락: `503 Service Unavailable`
- 잘못된 `return_to`: `422 Unprocessable Entity`

### `GET /auth/oauth/{provider}/callback`

provider가 authorization code 또는 오류를 돌려주는 callback이다.

Query:

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `code` | 성공 시 Y | authorization code |
| `state` | Y | CSRF 방지 state |
| `error` | 실패 시 Y | provider 오류 코드 |
| `error_description` | N | provider 오류 설명 |

성공 동작:

1. `state` hash를 조회하고 provider, 만료, 미사용 상태를 확인한다.
2. provider token endpoint에 authorization code를 교환한다.
3. Google/Kakao OIDC 사용 시 `id_token`을 검증한다.
4. provider userinfo endpoint 또는 검증된 `id_token`에서 provider profile을 정규화한다.
5. `user_oauth_accounts(provider, provider_user_id)`가 있으면 해당 사용자로 세션을 발급한다.
6. 연결 row가 없고 현재 TripMate 세션이 있으면 현재 사용자에 provider를 연결한다.
7. 연결 row가 없고 같은 이메일의 `users`가 없으며 provider 이메일 신뢰 조건을 만족하면 신규 사용자를 만든 뒤 연결한다.
8. 같은 이메일의 `users`가 이미 있으면 자동 연결하지 않고 `account_link_required`로 `/login`에 돌려보낸다.
9. `tripmate_access`, `tripmate_refresh` cookie를 발급하고 `return_to`로 redirect한다.

실패 redirect:

```text
/login?oauth_error=account_link_required&provider=google
/login?oauth_error=email_required&provider=kakao
/login?oauth_error=provider_denied&provider=naver
/login?oauth_error=temporary_failure&provider=kakao
```

callback은 JSON 응답보다 redirect를 기본으로 한다. 사용자는 provider 화면에서 브라우저 이동으로 돌아오기 때문이다.

### `POST /auth/oauth/{provider}/link`

로그인된 사용자가 provider 계정을 명시적으로 연결할 때 사용한다. 실제 구현은 `start?mode=link`와 callback에서 처리해도 된다. API 문서상으로는 명시적 기능으로 남긴다.

원칙:

- 현재 `tripmate_access`가 필요하다.
- 이미 다른 사용자에게 연결된 provider 계정은 연결할 수 없다.
- 한 사용자에게 같은 provider는 하나만 연결한다.

### `DELETE /auth/oauth/{provider}`

로그인된 사용자가 provider 연결을 해제한다.

원칙:

- 현재 `tripmate_access`가 필요하다.
- 비밀번호가 없고 연결된 provider가 하나뿐인 사용자는 해제할 수 없다. 먼저 비밀번호 설정 또는 다른 provider 연결이 필요하다.
- provider access token을 저장하지 않는 초기 구현에서는 provider 측 연결 해제 API까지 호출하지 않는다. 사용자가 provider 콘솔에서 앱 연결을 해제할 수 있음을 안내한다.

## DB 모델

상세 스키마는 `docs/architecture/user-trip-schema.md`를 따른다.

필수 추가 테이블:

- `user_oauth_accounts`
- `oauth_login_states`

핵심 제약:

- `user_oauth_accounts(provider, provider_user_id)` unique.
- `user_oauth_accounts(user_id, provider)` unique.
- `oauth_login_states.state_hash` unique.
- state row는 10분 이하로 만료하고 callback 성공/실패 모두에서 소비 처리한다.

`provider_user_id`는 Google `sub`, Naver `response.id`, Kakao `id`처럼 provider가 보장하는 고유 식별자만 저장한다. provider 이메일은 사용자 표시와 충돌 감지용 snapshot이며 unique key로 쓰지 않는다.

## 환경변수

API 서버 `apps/api/.env` 또는 배포 secret에 둔다. `TRIPMATE_` prefix는 `Settings` 기준이다.

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `TRIPMATE_WEB_BASE_URL` | Y | callback 완료 후 redirect할 웹앱 base URL. local 기본 `http://localhost:3001` |
| `TRIPMATE_OAUTH_CALLBACK_BASE_URL` | Y | provider console에 등록할 API callback base URL. local 기본 `http://localhost:8001` |
| `TRIPMATE_GOOGLE_OAUTH_CLIENT_ID` | provider 사용 시 Y | Google OAuth client id |
| `TRIPMATE_GOOGLE_OAUTH_CLIENT_SECRET` | provider 사용 시 Y | Google OAuth client secret |
| `TRIPMATE_NAVER_OAUTH_CLIENT_ID` | provider 사용 시 Y | Naver client id |
| `TRIPMATE_NAVER_OAUTH_CLIENT_SECRET` | provider 사용 시 Y | Naver client secret |
| `TRIPMATE_KAKAO_OAUTH_REST_API_KEY` | provider 사용 시 Y | Kakao REST API key |
| `TRIPMATE_KAKAO_OAUTH_CLIENT_SECRET` | Kakao 설정에 따라 Y | Kakao client secret 기능이 켜져 있으면 필수 |
| `TRIPMATE_OAUTH_STATE_TTL_SECONDS` | N | 기본 600초 |
| `TRIPMATE_OAUTH_HTTP_TIMEOUT_SECONDS` | N | provider token/profile 요청 timeout. 기본 5초 |

프론트엔드는 provider client secret을 알 필요가 없다. 로그인 버튼은 API의 `GET /auth/oauth/{provider}/start`로 이동만 시킨다.

## Redirect URI

로컬 개발 기본값:

```text
http://localhost:8001/auth/oauth/google/callback
http://localhost:8001/auth/oauth/naver/callback
http://localhost:8001/auth/oauth/kakao/callback
```

앱 Docker smoke 기준:

```text
http://127.0.0.1:18082/auth/oauth/google/callback
http://127.0.0.1:18082/auth/oauth/naver/callback
http://127.0.0.1:18082/auth/oauth/kakao/callback
```

배포 URI는 ODROID/reverse proxy 기준 도메인이 결정된 뒤 갱신한다. provider console에는 정확히 같은 scheme, host, path를 등록해야 한다.

## 보안 기준

- `state`는 모든 provider에서 필수다.
- `state`, `nonce`, `code_verifier` 원문은 로그와 DB에 저장하지 않는다.
- provider token response, access token, refresh token, id token 원문은 로그와 테스트 fixture에 남기지 않는다.
- callback의 `return_to`는 상대 경로 allowlist만 허용한다. 외부 URL redirect는 금지한다.
- provider profile parser는 `unknown` 경계에서 Pydantic model 또는 TypedDict로 좁힌다.
- provider HTTP timeout과 오류 분류를 구현한다.
- OAuth 실패 메시지는 사용자에게 조치 가능한 한국어 메시지로 변환한다. provider 원문 오류를 그대로 노출하지 않는다.
- 기존 이메일 계정에 provider를 자동 연결하지 않는다.
- `user_oauth_accounts`는 사용자 소유 인증 수단이므로 삭제/연결 변경은 현재 사용자 세션 인가를 요구한다.

## 로그인 화면 버튼 기준

상세 시각 기준은 `docs/architecture/map-marker-design.md`의 로그인 화면 기준을 따른다.

버튼 동작:

- 버튼은 `button`이 아니라 링크 또는 `window.location.assign`으로 `GET /auth/oauth/{provider}/start?return_to=/trips`에 이동한다.
- `credentials: include` fetch로 OAuth를 시작하지 않는다. provider 인증은 브라우저 top-level navigation으로 진행한다.
- provider별 버튼은 disabled/loading 상태를 가진다.
- callback 실패 후 `/login?oauth_error=...`가 들어오면 로그인 form 위 또는 버튼 영역 아래에 오류 상태를 보여준다.

권장 순서:

1. Google
2. Naver
3. Kakao

프로덕트에서 한국 사용자 우선 정렬을 원하면 Naver, Kakao, Google 순서로 바꿀 수 있지만, 문서와 테스트를 함께 갱신한다.

## 테스트 기준

백엔드:

- provider 목록에서 설정 누락 provider가 disabled로 내려오는지 확인.
- `start`가 state row를 만들고 provider URL로 redirect하는지 확인.
- `return_to` 외부 URL을 거부하는지 확인.
- callback state mismatch, 만료, 재사용을 거부하는지 확인.
- provider token/profile HTTP 오류를 분류하는지 확인.
- Google `sub`, Kakao `id`, Naver `response.id`가 provider unique key로 저장되는지 확인.
- 기존 이메일 사용자가 있으면 자동 연결하지 않는지 확인.
- 신규 provider-only 사용자 생성 시 `password_hash` 없이 password login이 불가능한지 확인.
- access/refresh cookie에는 JWT를 담고 DB에는 refresh token hash만 저장되는지 확인.
- provider token 원문이 DB와 로그에 남지 않는지 확인.

프론트엔드:

- `/login`에 Google/Naver/Kakao 버튼이 표시되는지 확인.
- disabled provider는 production UI에서 숨기거나 dev에서 비활성 상태로 보이는지 확인.
- 버튼 클릭 시 올바른 start URL로 이동하는지 확인.
- `oauth_error` query가 사용자용 오류 메시지로 렌더링되는지 확인.
- 모바일 폭에서 이메일/password form, 소셜 버튼, 비밀번호 찾기/회원가입 링크가 겹치지 않는지 확인.

E2E:

- provider 실제 계정 E2E는 secret과 외부 동의 화면 의존성이 커서 기본 CI에는 넣지 않는다.
- CI에서는 provider HTTP를 mock하는 callback 테스트와 로그인 화면 navigation 테스트를 우선한다.
- 수동 검증 runbook은 provider별 test app과 redirect URI를 사용해 별도로 기록한다.

## 구현 후 문서 갱신

구현이 들어가면 아래 문서를 함께 갱신한다.

- `docs/api/auth.md`: endpoint, 응답, 오류 코드.
- `docs/architecture/user-trip-schema.md`: migration 반영 상태.
- `docs/runbooks/local-dev.md`: 실제 환경변수와 provider console 설정 절차.
- `docs/architecture/map-marker-design.md`: 최종 버튼 UI.
- `docs/decisions/`: 이메일 자동 연결, Naver 이메일 신뢰 정책이 바뀌면 ADR 추가 또는 갱신.
