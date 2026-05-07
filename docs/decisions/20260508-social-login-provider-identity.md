# ADR: 소셜 로그인 provider identity 연결 방식

## 상태

Accepted

## 배경

TripMate는 이메일을 로그인 식별자로 쓰고 httpOnly cookie 기반 서버 세션을 사용한다. 로그인 화면에 Google, Naver, Kakao 버튼을 추가하려면 provider가 돌려주는 고유 사용자와 TripMate 사용자 계정을 어떻게 연결할지 결정해야 한다.

provider 이메일만으로 계정을 자동 병합하면 사용자는 편하지만, 이메일 변경, provider별 이메일 검증 수준 차이, 기존 이메일 계정 탈취 위험이 생긴다. 반대로 provider subject를 별도 테이블로 관리하면 구현은 조금 늘지만 각 provider의 고유 식별자를 안전하게 보존할 수 있다.

## 결정

- `users.email`은 계속 TripMate 로그인 식별자다.
- provider 고유 사용자는 `user_oauth_accounts` 테이블에 저장한다.
- `user_oauth_accounts(provider, provider_user_id)`를 provider identity의 단일 진실원으로 둔다.
- Google은 `sub`, Naver는 `response.id`, Kakao는 `id`를 `provider_user_id`로 저장한다.
- provider access token, refresh token, id token 원문은 초기 구현에서 장기 저장하지 않는다.
- 기존 이메일 계정과 provider 계정은 자동 연결하지 않는다.
- 같은 이메일의 사용자가 이미 있으면 기존 TripMate 세션으로 로그인한 뒤 명시적으로 provider를 연결해야 한다.
- 신규 provider-only 사용자를 지원하기 위해 `users.password_hash`는 nullable로 전환한다.
- Naver는 명시적인 email verified boolean을 제공하지 않으므로, 신규 Naver 계정은 별도 TripMate 이메일 인증을 거치는 기본값으로 둔다.

## 대안

- provider 이메일로 자동 병합: UX는 가장 부드럽지만 provider별 이메일 보증 수준 차이를 감추고 계정 탈취 위험을 키운다.
- `users`에 `google_id`, `naver_id`, `kakao_id` 컬럼 추가: 초기에는 단순하지만 provider가 늘 때마다 사용자 테이블과 migration이 커진다.
- provider refresh token 저장: provider API 장기 호출에는 유리하지만 현재 목적은 로그인뿐이므로 secret 저장, 회전, 폐기, 침해 대응 부담이 불필요하다.
- 모든 provider 신규 가입을 즉시 `active`로 생성: 버튼 로그인 UX는 좋지만 이메일 인증 원칙과 provider별 신뢰 차이를 흐린다.

## 결과/영향

- 소셜 로그인 성공 후에도 앱 세션 구조는 기존 `tripmate_session`과 `sessions.session_token_hash`를 그대로 쓴다.
- 사용자 계정과 provider 연결을 분리해 provider 추가/삭제가 쉬워진다.
- 기존 이메일 사용자는 자동 연결이 되지 않아 최초 1회 연결 절차가 필요하다.
- provider-only 사용자는 비밀번호 없이 계정을 가질 수 있으므로 password login 서비스는 `password_hash IS NULL`을 실패 처리해야 한다.
- Naver 신규 사용자는 추가 이메일 인증 단계가 필요할 수 있다.

## 후속 작업

- `docs/integrations/social-login.md` 기준으로 API와 DB를 구현한다.
- `docs/api/auth.md`에 소셜 로그인 endpoint와 오류를 반영한다.
- `docs/architecture/user-trip-schema.md`에 `user_oauth_accounts`, `oauth_login_states` 구현 상태를 반영한다.
- Naver 이메일을 즉시 신뢰하는 제품 결정을 하게 되면 이 ADR 또는 새 ADR로 변경 사유를 남긴다.
