# Google/Naver/Kakao 소셜 로그인 실행 계획

## 상태

Planned. 이 문서는 구현 전 기술 계획과 TODO 목록이다. 현재 코드에는 소셜 로그인 endpoint, DB 테이블, `/login` 화면 버튼이 없다.

## 목표

일반 사용자 로그인 화면(`/login`)에 Google, Naver, Kakao 로그인 버튼을 추가하고, provider 인증 성공 후 기존 `tripmate_access`, `tripmate_refresh` httpOnly cookie JWT 세션으로 TripMate에 로그인시킨다.

## 반드시 지킬 조건

- 사용자 로그인 식별자는 계속 이메일이다.
- 인증 완료 후 앱 세션은 기존 JWT cookie와 `sessions.session_token_hash` 기반 refresh token hash를 사용한다.
- provider access token, refresh token, id token 원문은 일반 DB와 로그에 저장하지 않는다.
- 기존 이메일 계정과 provider 계정은 자동 연결하지 않는다.
- provider 고유 식별자는 이메일이 아니라 provider subject id를 사용한다.
- 관리자 로그인 화면에는 소셜 로그인 버튼을 넣지 않는다.
- Naver 신규 가입을 즉시 `active`로 만들지 않는다. Naver 이메일 신뢰 정책을 바꾸려면 별도 제품 결정/ADR이 필요하다.
- MCP 관련 설계, 구현, 스캐폴딩은 하지 않는다.

## 관련 문서

- 공통 규칙: `AGENTS.md`, `docs/runbooks/agent-working-rules.md`
- 인증 API: `docs/api/auth.md`
- 소셜 로그인 상세: `docs/integrations/social-login.md`
- 사용자 스키마: `docs/architecture/user-trip-schema.md`
- 로그인 화면 디자인: `docs/architecture/map-marker-design.md`
- 로컬 개발: `docs/runbooks/local-dev.md`
- DB skill: `skills/database-architect.ko.md`
- 문서 skill: `skills/documentation-and-adrs.ko.md`

## 범위

### 포함

- `/login` 화면에 Google, Naver, Kakao 버튼 추가.
- provider 활성 상태 조회 API.
- OAuth start/callback endpoint.
- provider profile 정규화 서비스.
- `user_oauth_accounts`, `oauth_login_states` DB 모델과 migration.
- 기존 세션 발급 로직 재사용.
- 신규 provider-only 사용자 생성 정책.
- 기존 사용자 provider 연결/해제 정책.
- 테스트와 수동 검증 runbook.

### 제외

- provider access token 장기 저장.
- provider API를 이용한 캘린더/드라이브/친구/메시지 권한 요청.
- provider 쪽 전역 로그아웃.
- 관리자 계정 소셜 로그인.
- 네이티브 앱 OAuth flow.
- 자동 계정 병합.

## 권장 구현 순서

### Phase 0. 착수 전 확인

TODO:

- `git status --short`로 작업 트리를 확인한다.
- `apps/web/app/login/page.tsx`, `apps/web/app/login/api.ts`, `apps/web/app/shared/api-base.ts`를 읽는다.
- `apps/api/app/api/routes/auth.py`, `apps/api/app/services/admin_auth.py`, `apps/api/app/models/user.py`, `apps/api/app/models/session.py`를 읽는다.
- 최신 provider 공식 문서에서 redirect URI, scope, token endpoint, userinfo response를 다시 확인한다.
- provider별 test app을 만들 수 있는 계정과 callback URI를 확보한다.

완료 조건:

- 실제 구현 파일 경계와 provider console 접근 가능 여부가 정리됐다.

### Phase A. 설정과 의존성

TODO:

- `apps/api/app/core/config.py`에 소셜 로그인 설정을 추가한다.
  - `web_base_url`
  - `oauth_callback_base_url`
  - `google_oauth_client_id`
  - `google_oauth_client_secret`
  - `naver_oauth_client_id`
  - `naver_oauth_client_secret`
  - `kakao_oauth_rest_api_key`
  - `kakao_oauth_client_secret`
  - `oauth_state_ttl_seconds`
  - `oauth_http_timeout_seconds`
- provider가 켜졌는지 판정하는 helper를 만든다.
- OAuth/OIDC 검증용 라이브러리를 결정한다.
  - 권장: `authlib`를 추가해 OIDC/JWK/id token 검증을 직접 구현하지 않는다.
  - 최소 구현: `httpx` + 검증 helper를 직접 작성하되, Google/Kakao id token 검증 테스트를 반드시 둔다.
- `.env.example`이 있으면 이름만 추가하고 secret 값은 넣지 않는다.
- `docs/runbooks/local-dev.md`의 환경변수와 실제 설정명이 일치하는지 확인한다.

완료 조건:

- 설정 누락 provider를 안전하게 disabled 처리할 수 있다.
- secret이 브라우저 bundle에 들어가지 않는다.

### Phase B. DB migration과 모델

TODO:

- `users.password_hash` nullable 전환 migration을 추가한다.
  - 기존 password 로그인 사용자는 기존 hash를 유지한다.
  - `authenticate_user`는 `password_hash is None`이면 password login을 실패 처리한다.
- `user_oauth_accounts` 테이블을 추가한다.
  - `id UUID PK`
  - `user_id UUID FK users.id ON DELETE CASCADE`
  - `provider varchar(32)`
  - `provider_user_id varchar(255)`
  - `provider_email varchar(320) nullable`
  - `provider_email_verified boolean`
  - `display_name_snapshot varchar(120) nullable`
  - `linked_at timestamptz`
  - `last_login_at timestamptz nullable`
  - `created_at`, `updated_at`
  - unique `(provider, provider_user_id)`
  - unique `(user_id, provider)`
  - index `user_id`, `provider_email`
- `oauth_login_states` 테이블을 추가한다.
  - `id UUID PK`
  - `provider varchar(32)`
  - `mode varchar(16)` with `login`, `link`
  - `state_hash varchar(128) unique`
  - `nonce_hash varchar(128) nullable`
  - `pkce_code_verifier_hash varchar(128) nullable`
  - `return_to_path varchar(255)`
  - `expires_at timestamptz`
  - `consumed_at timestamptz nullable`
  - `created_at`, `updated_at`
  - index `expires_at`, `(provider, consumed_at)`
- SQLAlchemy 2 `Mapped[]` 모델을 추가한다.
- `User.oauth_accounts` relationship을 추가한다.
- migration contract test를 갱신한다.
- model metadata test를 갱신한다.

완료 조건:

- WSL2 Docker Postgres에서 `alembic upgrade head`가 통과한다.
- unique/FK/check/index 이름이 PostgreSQL 63바이트 제한 안에 있다.

### Phase C. Backend OAuth service

TODO:

- `apps/api/app/api/routes/auth.py` 또는 별도 `oauth.py` route에 endpoint를 추가한다.
  - `GET /auth/oauth/providers`
  - `GET /auth/oauth/{provider}/start`
  - `GET /auth/oauth/{provider}/callback`
  - `POST /auth/oauth/{provider}/link`
  - `DELETE /auth/oauth/{provider}`
- route는 얇게 두고 provider별 로직은 service로 분리한다.
- `OAuthProvider` enum 후보를 `google`, `naver`, `kakao`로 제한한다.
- provider 설정 객체를 만든다.
- `state`, `nonce`, `code_verifier` 생성과 hash helper를 만든다.
- start endpoint에서 `return_to` 상대 경로 검증을 구현한다.
- callback endpoint에서 state 재사용, 만료, provider mismatch를 거부한다.
- provider token 요청은 timeout을 갖는 HTTP client를 사용한다.
- provider profile parser는 `unknown`/dict 경계에서 Pydantic model로 좁힌다.
- provider profile을 공통 `OAuthProfile`로 정규화한다.
  - `provider`
  - `provider_user_id`
  - `email`
  - `email_verified`
  - `display_name`
- provider token/profile 원문은 로그에 남기지 않는다.

완료 조건:

- mock provider 응답으로 callback 성공/실패를 테스트할 수 있다.
- provider 오류가 사용자용 오류 코드로 분류된다.

### Phase D. 계정 연결과 세션 발급

TODO:

- `resolve_oauth_user` service를 만든다.
- 이미 연결된 provider 계정이면 해당 사용자 `last_login_at`, `user_oauth_accounts.last_login_at`을 갱신한다.
- 현재 TripMate 세션이 있고 mode가 `link`이면 현재 사용자에게 provider를 연결한다.
- 기존 이메일 사용자와 신규 provider subject가 충돌하면 자동 연결하지 않는다.
- provider 이메일이 없으면 신규 계정을 만들지 않는다.
- Google은 `email_verified = true`일 때만 provider 이메일을 TripMate 인증 이메일로 취급한다.
- Kakao는 `is_email_valid = true`와 `is_email_verified = true`일 때만 provider 이메일을 TripMate 인증 이메일로 취급한다.
- Naver는 초기 구현에서 별도 TripMate 이메일 인증이 필요하다.
- 신규 provider-only 사용자는 `system_role = planner`, `account_status`는 provider 이메일 신뢰 정책에 따라 `active` 또는 `pending_email_verification`으로 만든다.
- provider-only 사용자의 `password_hash`는 `NULL`로 둔다.
- 기존 JWT 발급 함수를 재사용해 `tripmate_access`, `tripmate_refresh` cookie를 발급한다.

완료 조건:

- password 계정, provider-only 계정, 기존 이메일 충돌 계정의 동작이 각각 테스트된다.

### Phase E. 로그인 화면 UI

TODO:

- `/login` 화면에서 provider 목록을 조회한다.
- 이메일/password 로그인 버튼 아래에 소셜 로그인 버튼 그룹을 추가한다.
- Google, Naver, Kakao 버튼을 full-width 48px 이상으로 만든다.
- 각 버튼에 provider icon 또는 wordmark 영역을 둔다.
- 클릭 시 `GET /auth/oauth/{provider}/start?return_to=/trips`로 top-level navigation한다.
- provider 목록 로딩 중에는 기존 이메일 로그인 form이 계속 동작해야 한다.
- disabled provider는 local/dev에서 비활성 표시, production에서 숨김 중 하나로 구현하고 테스트에 반영한다.
- `/login?oauth_error=...&provider=...`를 사용자용 메시지로 표시한다.
- 모바일에서 form, 버튼, 비밀번호 찾기, 회원가입 링크가 겹치지 않도록 확인한다.

완료 조건:

- 사용자가 이메일 로그인과 소셜 로그인 중 하나를 명확히 선택할 수 있다.
- 관리자 로그인 화면은 변경되지 않는다.

### Phase F. Provider console 설정

TODO:

- Google Cloud Console에서 OAuth Web client를 만든다.
- Google redirect URI를 등록한다.
- Naver Developers에서 애플리케이션을 만들고 Login API 권한과 Callback URL을 등록한다.
- Kakao Developers에서 REST API key, Kakao Login 활성화, Redirect URI, 동의 항목을 설정한다.
- Kakao email과 profile nickname 동의 항목을 확인한다.
- Kakao client secret 기능 사용 여부를 결정하고 환경변수와 일치시킨다.
- local, Docker smoke, 배포 URI를 분리해 문서화한다.

완료 조건:

- 각 provider test app에서 local callback까지 실제 왕복이 가능하다.

### Phase G. 테스트

백엔드 필수 테스트:

- provider 목록 설정 판정.
- start endpoint redirect URL 구성.
- state row 생성과 hash 저장.
- `return_to=https://evil.example` 거부.
- callback state mismatch/expired/reused 실패.
- provider token timeout 실패.
- Google profile 정규화.
- Naver profile 정규화.
- Kakao profile 정규화.
- 기존 provider link 로그인 성공.
- 신규 provider-only 사용자 생성.
- 기존 이메일 충돌 시 `account_link_required`.
- provider token 원문 DB/로그 미노출.
- password_hash `NULL` 사용자는 password login 실패.
- provider 연결 해제 보호 규칙.

프론트엔드 필수 테스트:

- `/login`에 소셜 버튼 표시.
- disabled provider 처리.
- 버튼 클릭 start URL 이동.
- `oauth_error` 메시지 표시.
- 모바일 viewport overflow 없음.

수동 검증:

- Google 실제 계정으로 local 로그인.
- Naver 실제 계정으로 local 로그인.
- Kakao 실제 계정으로 local 로그인.
- 같은 이메일 기존 계정 충돌 처리.
- 로그아웃 후 provider login 재시도.

권장 명령:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run lint"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run typecheck"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run pytest"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run alembic upgrade head"
```

### Phase H. 문서와 운영

TODO:

- `docs/api/auth.md`를 실제 endpoint와 오류 코드에 맞춰 갱신한다.
- `docs/integrations/social-login.md`에 구현된 provider별 scope와 제한을 반영한다.
- `docs/runbooks/local-dev.md`에 provider console 스크린 경로와 redirect URI 등록 값을 추가한다.
- 배포 도메인이 정해지면 provider console redirect URI와 ODROID runbook을 갱신한다.
- 비밀값 주입 방식이 `.env`에서 secret store로 바뀌면 이 문서와 runbook을 함께 갱신한다.

완료 조건:

- 구현, 테스트, 문서, 환경변수, 운영 영향이 같은 계약을 말한다.

## 오류 코드 초안

| 내부 코드 | 사용자 메시지 방향 | 원인 |
| --- | --- | --- |
| `provider_disabled` | 간편 로그인이 아직 설정되지 않았다 | client id/secret 누락 |
| `provider_denied` | 사용자가 provider 인증을 취소했다 | OAuth `error` callback |
| `state_invalid` | 로그인 요청이 만료됐다. 다시 시도해야 한다 | state 없음/불일치 |
| `state_expired` | 로그인 요청 시간이 지났다 | state 만료 |
| `provider_profile_failed` | provider 사용자 정보를 확인하지 못했다 | userinfo 실패 |
| `email_required` | 이메일 제공 동의가 필요하다 | provider email 누락 |
| `email_unverified` | 이메일 인증이 필요하다 | provider email 미검증 |
| `account_link_required` | 이미 가입된 이메일이다. 기존 계정으로 로그인한 뒤 연결해야 한다 | 기존 email 충돌 |
| `oauth_temporary_failure` | 일시적인 인증 오류다 | provider timeout/5xx |

## 완료 정의

- `/login`에 Google/Naver/Kakao 로그인 버튼이 있다.
- provider별 start/callback이 동작한다.
- 성공 시 기존 `tripmate_access`, `tripmate_refresh` cookie가 발급된다.
- `user_oauth_accounts`에 provider subject가 저장된다.
- provider token 원문은 DB와 로그에 저장되지 않는다.
- 기존 이메일 계정은 자동 연결되지 않는다.
- provider-only 계정의 password login은 실패한다.
- 관련 backend/frontend 테스트와 migration 검증이 통과한다.
- provider console 설정과 로컬/배포 redirect URI가 문서화되어 있다.
