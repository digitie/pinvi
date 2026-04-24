# Auth API

## 현재 상태

인증 API는 Phase 2에서 구현한다. Phase 1에서는 인증을 위한 DB 기반만 추가되어 있다.

현재 존재하는 테이블:

- `users`
- `sessions`

현재 존재하는 endpoint:

- `GET /health`
- `GET /health/db`

## 인증 방식

TripMate는 httpOnly cookie 기반 서버 세션으로 시작한다.

원칙:

- 사용자 로그인 식별자는 이메일이다.
- 이메일은 중복될 수 없다.
- 비밀번호는 평문 저장하지 않고 안전한 password hash만 저장한다.
- 세션 cookie에는 난수 기반 opaque token만 저장한다.
- DB에는 세션 token 원문이 아니라 `session_token_hash`만 저장한다.
- 로그아웃은 서버 세션의 `revoked_at`을 기록하는 방식으로 처리한다.

## 계획 중인 endpoint

```text
POST /auth/register
POST /auth/login
POST /auth/logout
GET /users/me
PATCH /users/me
```

## 공통 오류 방향

구체 schema는 Phase 2 구현 시 확정한다.

- 중복 이메일: `409 Conflict`
- 잘못된 로그인 정보: `401 Unauthorized`
- 인증 필요: `401 Unauthorized`
- 권한 없음: `403 Forbidden`
- validation 실패: `422 Unprocessable Entity`

## 테스트 기준

Phase 2 구현 시 최소 테스트:

- 회원가입 정상 경로
- 중복 이메일 실패
- 로그인 정상 경로
- 잘못된 비밀번호 실패
- 로그아웃 후 세션 무효화
- 사용자 정보 수정 인가 검사
- 세션 token 원문이 DB와 로그에 남지 않는지 확인

