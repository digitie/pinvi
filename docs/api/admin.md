# 관리자 API

관리자 API는 일반 사용자 로그인과 분리된 내부 운영용 API이다. 현재 구현 범위는 관리자 전용 로그인, ETL/공공데이터 테이블 조회용 데이터 브라우저, 가입 사용자 관리이다.

## 인증

관리자 로그인도 TripMate 기본 인증 원칙과 같이 httpOnly cookie 기반 서버 세션을 사용한다.

- 로그인 endpoint: `POST /admin/auth/login`
- 세션 cookie 이름: `tripmate_session`
- cookie 값: 난수 기반 opaque token
- DB 저장값: `sessions.session_token_hash`
- 기본 관리자 seed: Alembic `20260427_0013_seed_default_admin.py`
- 기본 개발 계정: `admin@ad.min`
- 기본 개발 비밀번호: `admin`

운영 환경에서는 기본 비밀번호를 그대로 쓰지 않는다. 현재 seed migration은 기본 관리자 계정이 없거나 비활성화되어 있어도 관리자 플래그를 활성화한다. 비밀번호 해시는 PBKDF2-SHA256 형식이며 원문 비밀번호는 DB에 저장하지 않는다.

## 타입 안정성 기준

관리자 데이터 브라우저는 동적 테이블을 조회하므로 타입이 쉽게 흐려질 수 있다. 그래서 다음 기준을 둔다.

- 백엔드 service의 public return shape는 `TypedDict`로 고정한다.
- API schema의 row 값은 `JsonValue`로 제한한다. Pydantic schema에서 쓰는 재귀 JSON 타입은 Python 3.12의 `type JsonValue = ...` 문법을 사용한다.
- DB에서 읽은 datetime/date/UUID/Decimal/bytes 값은 응답 직렬화 단계에서 문자열로 변환한다.
- 알 수 없는 객체는 그대로 반환하지 않고 문자열로 변환해 JSON 응답 경계를 닫는다.
- 프론트엔드는 API 응답을 `unknown`으로 받은 뒤 endpoint별 parser로 검증하고 React state에 넣는다.
- 응답 shape가 맞지 않으면 `AdminResponseShapeError`를 발생시켜 조용히 잘못된 테이블을 그리지 않는다.

## Endpoint

### `POST /admin/auth/login`

관리자 전용 로그인이다. 일반 사용자 로그인은 별도 `/auth/*` 흐름으로 구현할 예정이다.

요청:

```json
{
  "email": "admin@ad.min",
  "password": "admin"
}
```

응답:

```json
{
  "user": {
    "id": "00000000-0000-4000-8000-000000000001",
    "email": "admin@ad.min",
    "display_name": "TripMate 관리자",
    "is_admin": true,
    "is_privileged": true
  }
}
```

성공 시 `tripmate_session` httpOnly cookie를 설정한다.

오류:

- `401 Unauthorized`: 계정이 없거나, 비밀번호가 틀리거나, 관리자 권한이 아니다.

### `POST /admin/auth/logout`

현재 cookie의 세션을 revoke 처리하고 cookie를 제거한다.

응답:

```json
{
  "status": "ok"
}
```

### `GET /admin/auth/me`

현재 관리자 세션의 사용자 정보를 반환한다.

오류:

- `401 Unauthorized`: 관리자 세션이 없거나 만료/폐기되었다.

### `GET /admin/users`

가입 사용자 목록을 조회한다. 관리자 사용자 화면(`/admin/users`)에서 사용한다.

Query parameter:

- `page`: 1부터 시작한다.
- `limit`: 1~200. 관리자 화면 기본값은 50이다.
- `search`: 이메일, 닉네임, 이름, 표시명 부분 일치 검색.
- `account_status`: `pending_email_verification`, `invited`, `active`, `disabled`, `deleted`.
- `system_role`: `admin`, `planner`, `participant`.

응답:

```json
{
  "users": [
    {
      "id": "00000000-0000-4000-8000-000000000001",
      "email": "planner@example.com",
      "display_name": "여행자",
      "nickname": "여행자",
      "name": "홍길동",
      "account_status": "pending_email_verification",
      "system_role": "planner",
      "birth_year_month": "199001",
      "gender": "no_answer",
      "residence_sigungu_code": "1111000000",
      "email_verified_at": null,
      "is_active": true,
      "is_admin": false,
      "is_privileged": false,
      "created_at": "2026-04-27T10:00:00+09:00",
      "updated_at": "2026-04-27T10:00:00+09:00"
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 1
}
```

### `PATCH /admin/users/{user_id}`

가입 사용자의 상태, 역할, 이름, 이메일 인증 상태를 조정한다. 현재 가입 테스트 단계에서는 인증 메일 발송이 아직 연결되지 않았으므로 관리자가 이메일 인증 완료와 활성화를 수동 처리할 수 있다.

요청:

```json
{
  "account_status": "active",
  "system_role": "planner",
  "nickname": "새 여행자",
  "name": "홍길동",
  "email_verified": true
}
```

동작 기준:

- `account_status`가 `disabled` 또는 `deleted`면 `is_active = false`로 동기화한다.
- `system_role = admin`이면 기존 호환 필드 `is_admin`, `is_privileged`도 `true`로 동기화한다.
- 관리자는 자기 자신의 관리자 권한을 제거하거나 자기 계정을 비활성화할 수 없다.

오류:

- `400 Bad Request`: 자기 자신의 관리자 권한 제거 또는 비활성화 시도.
- `401 Unauthorized`: 관리자 세션 없음.
- `404 Not Found`: 대상 사용자 없음.

### `GET /admin/datasets`

관리자 데이터 브라우저에서 조회할 수 있는 테이블 목록을 반환한다.

현재 정책:

- `users`, `sessions`, `trips`, `trip_days`는 제외한다.
- ETL로 적재한 주소, 경계, 유가, 휴게소, 날씨, 관광코스, 실행 로그 계열 테이블을 조회 대상으로 둔다.
- 테이블별 row count와 컬럼 메타데이터를 함께 반환한다.
- 기본 페이지 크기는 `100`이다.
- 허용 페이지 크기는 `50`, `100`, `200`, `500`이다.

응답 예:

```json
{
  "datasets": [
    {
      "table_name": "etl_run_logs",
      "row_count": 12,
      "columns": [
        {
          "name": "dataset_key",
          "type": "VARCHAR(120)",
          "nullable": false,
          "searchable": true,
          "filterable": true,
          "sortable": true
        }
      ]
    }
  ],
  "page_size_options": [50, 100, 200, 500],
  "default_page_size": 100
}
```

### `GET /admin/datasets/{table_name}/rows`

선택한 테이블의 행을 조회한다.

Query parameter:

- `page`: 1부터 시작한다.
- `limit`: `50`, `100`, `200`, `500` 중 하나이다. 허용되지 않은 값은 `100`으로 보정한다.
- `search`: 문자열 컬럼 전체 부분 일치 검색.
- `sort_by`: 정렬 컬럼명.
- `sort_dir`: `asc` 또는 `desc`.
- `filter.<column>`: 특정 컬럼 부분 일치 필터. 예: `filter.status=success`

동작 기준:

- geometry 컬럼은 `ST_AsText` 결과로 반환한다.
- JSONB 컬럼은 필터 대상에서 제외한다.
- geometry 컬럼은 검색/필터/정렬 대상에서 제외한다.
- 기본 정렬 후보는 `created_at`, `collected_at`, `updated_at`, `id` 순서이다.
- 반환값은 datetime/date/UUID/Decimal을 JSON 표시 가능한 문자열로 직렬화한다.

오류:

- `401 Unauthorized`: 관리자 세션 없음.
- `404 Not Found`: 조회 대상이 아니거나 존재하지 않는 테이블.

## 테스트 기준

관리자 API 변경 시 최소한 다음을 확인한다.

- 기본 관리자 계정으로 로그인, `me`, 로그아웃 흐름.
- 비관리자 계정 로그인 차단.
- 잘못된 비밀번호 차단.
- 데이터셋 목록에서 사용자/세션/여행 테이블 제외.
- 검색, 필터, 정렬, 페이지 크기 보정.
- 알 수 없는 테이블 조회 차단.
- 가입 사용자 목록 검색과 상태 변경.
- 관리자가 자기 자신의 관리자 권한을 제거하지 못하는지 확인.

현재 관련 테스트:

- `apps/api/tests/test_admin_api.py`
- `apps/api/tests/test_migration_contract.py`
