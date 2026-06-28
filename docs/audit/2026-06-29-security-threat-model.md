# 2026-06-29 보안 threat model / penetration 1차 점검

## 범위

T-283은 Sprint 6 출시 전 보안 경계 1차 점검이다. 대상은 Web/API/Admin 운영 출시 경계 중
다음 surface로 한정한다.

| 영역 | 주요 자산 | 신뢰 경계 |
|------|-----------|-----------|
| Auth / session | access JWT, refresh session, `access_token_version` | Web cookie / mobile Bearer → FastAPI dependency |
| MCP | `mcp_*` Bearer token, `mcp:read` scope, token hash | 외부 AI client → `/mcp/*` |
| Share token | 여행 공유 raw token, token hash | 비로그인 공유 URL → `/trips/{id}/shared/{token}` |
| Rate limit / abuse | bucket hash, override, fail-closed 정책 | public/auth/storage/share 요청 → middleware |
| Storage | presigned PUT URL, storage key, quota | user/admin → `/storage/upload-urls` |
| Admin RBAC / incidents | admin/operator/cpo role, audit log, PIPA incident | authenticated user → `/admin/*` |

최근 2일 PR review 확인:

- `gh pr list --state all --search "updated:>=2026-06-27"`로 최근 PR #278~#307을 확인했다.
- `gh api /repos/digitie/pinvi/pulls/comments --paginate` 기준 2026-06-27 이후 inline review comment는
  없었다.

## Threat Model

| 위협 | 기대 방어 | 확인 증거 |
|------|-----------|-----------|
| MCP 토큰을 일반 API access token으로 재사용 | `get_current_user_id`는 Pinvi access JWT만 수락하고 MCP prefix/JWT는 `TOKEN_INVALID` | `test_mcp_token_and_web_access_token_are_not_interchangeable` |
| Web access JWT를 MCP Bearer로 재사용 | MCP dependency는 `mcp_` prefix, MCP JWT secret, DB token hash, `mcp:read` scope를 검증 | `test_mcp_token_and_web_access_token_are_not_interchangeable`, 기존 `test_mcp_tokens_api.py` |
| 공유 raw token이 owner detail/Admin list에 노출 | 생성 응답 이후 조회 응답은 `share_id`, `visibility`, 상태만 반환하고 raw token은 숨김 | `test_share_token_is_route_scoped_hidden_and_revocable`, 기존 `test_share_link_uses_web_base_url` |
| 공유 token을 다른 trip id에 replay | token hash와 `trip_id`를 함께 검증하고 실패 시 404 | `test_share_token_is_route_scoped_hidden_and_revocable` |
| revoke된 공유 link 재사용 | `revoked_at`이 있는 share token은 shared endpoint에서 404 | `test_share_token_is_route_scoped_hidden_and_revocable` |
| 일반 사용자 또는 MCP token이 curated/admin storage presign 발급 | `curated_*` purpose는 admin role만 허용하고 권한 없음은 404로 숨김. MCP Bearer는 web access token이 아니므로 401 | `test_admin_only_storage_upload_purpose_rejects_user_and_mcp_credentials` |
| Storage path traversal / 임의 object key 주입 | upload URL은 서버가 key를 생성하고 attachment schema는 절대경로/역슬래시/`..`를 거부 | 기존 `test_trips_api.py`, `test_admin_curated_attachments_api.py` |
| Admin incident workflow를 operator가 조회/전이 | incident list/create는 admin/cpo, 상태 전이는 cpo only, 권한 없음은 404 | `test_security_incident_console_hides_from_operator_role`, 기존 `test_admin_incidents_api.py` |
| Rate-limit 우회 또는 abuse override 오용 | policy별 identity dimension, Postgres bucket, fail-closed, TTL block/allow override, 감사 로그 | 기존 `test_rate_limit_middleware.py`, `test_admin_abuse_api.py` |
| disabled/pending_delete/deleted 사용자 token 재사용 | auth dependency, refresh session, MCP token 검증에서 사용자 상태와 token version을 확인 | 기존 `test_admin_users_api.py`, `test_mcp_tokens_api.py` |

## 1차 점검 결과

- Critical / High: 신규 발견 없음.
- Medium: 신규 발견 없음.
- Low / 잔여 리스크:
  - 본 점검은 integration-level boundary regression과 코드 리뷰다. 외부 DAST, 실제 WAF/nginx geo 우회,
    운영 secret rotation drill은 T-270 / v1.0 live gate에서 별도 수행한다.
  - MCP rate limit은 process-local memory다. 단일 API process 기준 1차 방어이며, multi-process 운영 전에는
    shared store 전환 여부를 재검토한다.
  - Share token은 32-byte opaque random token의 SHA-256 hash 저장 방식이다. 현재 brute-force 실익은 낮지만,
    token entropy 변경 시 HMAC 저장으로 올리는 결정을 별도 ADR/Task로 재검토한다.

## 추가된 회귀 테스트

신규 파일: `apps/api/tests/integration/test_security_boundaries_api.py`

- MCP token과 Web access token 상호 재사용 차단.
- Share token raw 값 비노출, trip id scope, revoke 후 접근 차단.
- Admin-only storage presigned URL purpose의 user/MCP credential 차단과 admin 허용.
- Security incident console의 operator 접근 은닉.

실행:

```bash
cd apps/api
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/integration/test_security_boundaries_api.py -q --capture=no
```

결과: 4 passed.

## 결론

T-283 기준 출시 차단 보안 결함은 발견하지 못했다. 신규 테스트는 credential context 분리, 공유 token
수명주기, storage/admin RBAC 경계를 CI에서 회귀 방어한다. 남은 동적/운영 보안 검증은 T-270 성능 /
부하 / 보안 점검과 v1.0 live gate에서 수행한다.
