# 사용자 / 프로필 API (`/users/*`)

내 정보 / 동의 / avatar / OAuth 연결 / 탈퇴. 가입/로그인은 [`auth.md`](./auth.md).

## 1. `GET /users/me`

[`auth.md`](./auth.md) §3.4 `GET /auth/me`와 동일. (alias로 둘 다 지원)

## 2. `PATCH /users/me`

```http
PATCH /users/me
Content-Type: application/json
Cookie: pinvi_access=...

{
  "nickname": "...",
  "avatar_attachment_id": "uuid",   // null이면 default avatar
  "avatar_kind": "default" | "upload",
  "gender": "...",
  "birth_year_month": "199003",
  "residence_sigungu_code": "11680"
}
```

- 선택 정보는 `demographic_use` 동의 있을 때만 저장
- 응답 200: 갱신된 user

## 3. 동의 관리

### 3.1 `GET /users/me/consents`

```jsonc
{
  "data": {
    "consents": [
      { "consent_type": "tos", "version": "v1.0", "agreed_at": "...", "withdrawn_at": null },
      {
        "consent_type": "location_collection",
        "version": "v1.0",
        "agreed_at": "...",
        "withdrawn_at": null,
      },
    ],
  },
}
```

### 3.2 `POST /users/me/consents`

신규 동의 추가 (예: 약관 개정 시 재동의).

```http
POST /users/me/consents
Content-Type: application/json

{ "consent_type": "marketing", "version": "v1.0" }
```

### 3.3 `POST /users/me/consents/withdraw`

```http
POST /users/me/consents/withdraw
Content-Type: application/json

{ "consent_type": "location_collection" }
```

- `app.user_consents.withdrawn_at = now()`
- 부작용:
  - `location_collection` 철회 → 위치 기록 즉시 삭제(`app.location_access_log`는
    법정 6개월 보존이지만 위치 기능 비활성. 사용자 좌표 응답 차단)
  - `demographic_use` 철회 → `users.gender`, `birth_year_month`,
    `residence_sigungu_code` NULL로
  - `marketing` 철회 → Resend 발송 차단 (`email_queue.template != 'marketing'`만)

## 4. Avatar

아바타는 RustFS presigned PUT 2-phase 흐름만 사용한다. multipart 업로드는 제공하지 않는다.
일반 `/storage/upload-urls`에도 `purpose="avatar"`가 남아 있지만, 화면과 클라이언트는
아바타 전역 크기 제한과 image MIME 제한을 적용하는 전용 endpoint를 사용한다.

### 4.1 `POST /users/me/avatar/upload-url`

```http
POST /users/me/avatar/upload-url
Content-Type: application/json
Cookie: pinvi_access=...

{
  "filename": "avatar.jpg",
  "content_type": "image/jpeg",
  "content_length": 524288
}
```

- 허용 MIME: `image/jpeg`, `image/png`, `image/webp`, `image/gif`
- 크기 제한: Admin 전역 설정 `storage_settings.avatar_max_upload_bytes`(기본 2MiB)
- 응답: `UploadUrlResponse` (`bucket`, `storage_key`, `upload_url`, `headers`, `max_upload_bytes`)

### 4.2 `PUT /users/me/avatar`

브라우저가 RustFS `upload_url`로 PUT을 완료한 뒤 메타데이터를 등록한다.

```http
PUT /users/me/avatar
Content-Type: application/json

{
  "bucket": "pinvi-media",
  "storage_key": "user-uploads/avatar/<user_id>/2026/06/<uuid>.jpg",
  "content_type": "image/jpeg",
  "byte_size": 524288,
  "public_url": null
}
```

- `bucket`은 `PINVI_RUSTFS_BUCKET`과 같아야 한다.
- `storage_key`는 `user-uploads/avatar/{current_user_id}/` prefix만 허용한다.
- 응답 200: `AvatarInfo` (`avatar_kind`, `avatar_content_type`, `avatar_byte_size`,
  `avatar_updated_at`, `has_avatar`)

### 4.3 `GET /users/me/avatar/download-url`

현재 사용자의 아바타가 있으면 private object 접근용 presigned GET URL을 반환한다.

### 4.4 `DELETE /users/me/avatar`

현재 아바타 RustFS object 삭제를 시도한 뒤 `avatar_kind = "default"`로 되돌리고 아바타 메타를
비운다. 응답 200: `AvatarInfo`.

## 5. OAuth 연결 관리

[`auth.md`](./auth.md) §6.4 / §6.5와 동일. alias:

- `POST /users/me/oauth/{provider}/link`
- `DELETE /users/me/oauth/{provider}`

## 6. MCP 토큰 (ADR-019, Sprint 6)

외부 AI agent가 Pinvi MCP 서버를 read-only로 호출할 때 쓰는 전용 토큰이다.
일반 `pinvi_access` / `pinvi_refresh` cookie와 분리한다.

### 6.1 `GET /users/me/mcp-tokens`

내 MCP 토큰 목록. 토큰 원문은 반환하지 않고 마스킹 값과 metadata만 반환한다.

```jsonc
{
  "data": [
    {
      "token_id": "uuid",
      "name": "Claude Desktop @ macbook",
      "scopes": ["mcp:read"],
      "masked_token": "mcp_abcd...wxyz",
      "expires_at": "2026-07-07T00:00:00Z",
      "last_used_at": null,
      "revoked_at": null,
      "created_at": "2026-06-07T00:00:00Z",
    },
  ],
}
```

### 6.2 `POST /users/me/mcp-tokens`

```http
POST /users/me/mcp-tokens
Content-Type: application/json

{ "name": "Claude Desktop @ macbook", "expires_at": "2026-07-07T00:00:00Z" }
```

- `scopes`는 1차 구현에서 `["mcp:read"]`만 허용한다.
- 응답은 발급 직후 1회만 `token` 원문을 포함한다.

### 6.3 `DELETE /users/me/mcp-tokens/{token_id}`

내 토큰 회수. `revoked_at = now()` 설정 후 다음 MCP 호출부터 401.

## 7. 탈퇴

[`auth.md`](./auth.md) §7과 동일. alias:

- `DELETE /users/me`

## 8. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/user.py` Pydantic + `packages/schemas/src/user.ts` Zod
- [ ] `apps/api/app/services/user.py` (프로필 갱신 + 동의 부작용 트리거)
- [ ] `apps/api/app/api/v1/users.py` (또는 `auth.py`에 합치기)
- [ ] avatar 처리 (presigned vs multipart 결정 ADR — Sprint 1)
- [ ] 동의 철회 시 부작용 트랜잭션 검증 (location_collection / demographic_use)
- [ ] 통합 테스트 `apps/api/tests/integration/test_user_consents.py`
- [ ] MCP 토큰 발급/회수 API + 원문 1회 노출 테스트
