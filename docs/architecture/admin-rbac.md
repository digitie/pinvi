# Admin RBAC

Admin RBAC의 정본은 `app.users.roles` 배열이다. access token의 role claim은 과거 세션 표시나
클라이언트 힌트로만 취급하고, Admin API는 요청마다 DB의 `users` row를 읽어 권한을 판정한다.

## 역할

| Role       | 용도                                  |
| ---------- | ------------------------------------- |
| `user`     | 모든 계정의 기본 role                 |
| `admin`    | 전체 운영 mutation과 위험 action      |
| `operator` | 운영 조회와 데이터 운영 일부 mutation |
| `cpo`      | 개인정보/위치 감사/침해사고/DSR 처리  |

`user`는 기본 role이므로 Admin UI/API에서 회수하지 않는다. 운영자가 부여/회수할 수 있는 role은
`admin`, `operator`, `cpo`다.

## 권한 판정

- FastAPI route는 `require_role("admin", ...)` dependency로 권한을 선언한다.
- `require_role`은 cookie session의 subject로 DB 사용자 row를 조회하고, `roles` 배열과 허용 role의
  교집합을 검사한다.
- 권한이 없으면 Admin endpoint 존재를 숨기기 위해 `404 RESOURCE_NOT_FOUND`를 반환한다.
- 사용자가 삭제됐거나 비활성 row인 경우도 Admin endpoint에서는 동일하게 404로 처리한다.

## Permission Matrix

`GET /admin/rbac/permission-matrix`는 Admin 콘솔과 운영 점검을 위한 읽기 전용 matrix다.

- 권한: `admin` / `operator` / `cpo`
- 응답: role 설명 map, resource/action/route, 허용 role, `access_reason_required`,
  `audit_required`, notes
- matrix는 UI와 문서화를 돕는 운영 표면이다. 최종 권한 정본은 각 route의 `require_role(...)`와
  service guard다.

## Role Mutation

사용자 role 변경은 `/admin/users/{user_id}/roles/grant`와
`/admin/users/{user_id}/roles/revoke`에서 처리한다.

요구사항:

- 권한: `admin`
- body: `role` (`admin` / `operator` / `cpo`), `access_reason`
- audit: `user.role_grant` / `user.role_revoke`
- audit state: `before_state.roles`, `after_state.roles`
- role 정규화 순서: `user`, `admin`, `operator`, `cpo`

Guard:

- 중복 부여는 `409 INVALID_STATE`
- 미보유 role 회수는 `409 INVALID_STATE`
- 자기 자신의 `admin` role 회수는 `403 PERMISSION_DENIED`
- 마지막 `admin` role 회수는 `403 PERMISSION_DENIED`

마지막 admin 보호 로직은 DB dialect에 의존하지 않는다. 후보 사용자의 role 배열을 조회한 뒤
애플리케이션의 role 정규화 함수로 admin 보유 여부를 계산한다.

## UI

- `/admin/rbac`: role 설명과 permission matrix를 표시한다.
- `/admin/users/{user_id}`: 사용자 상세의 "역할 관리" 섹션에서 role 부여/회수를 수행한다.
- role mutation은 반드시 사유를 입력해야 하며, 성공 후 사용자 상세과 최근 audit을 다시 가져온다.

## 검증

- API integration: matrix 조회, operator의 role mutation 404, grant/revoke 성공, 중복/미보유 guard,
  자기 admin 회수 guard, 마지막 admin 회수 guard, audit action 기록
- Web Playwright: 사용자 상세 role 부여/회수 mock flow, `/admin/rbac` matrix 표시
- 정적 검증: API ruff/mypy, shared schema/API client/web typecheck, Web lint

## 관련 문서

- [`docs/api/admin.md`](../api/admin.md)
- [`docs/runbooks/admin.md`](../runbooks/admin.md)
- ADR-033 (`docs/decisions.md`)
